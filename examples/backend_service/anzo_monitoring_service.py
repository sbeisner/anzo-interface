#!/usr/bin/env python3
"""
Anzo Backend Monitoring Sidecar Service

Exposes infrastructure metrics not available via the AGS REST API:
- JVM heap and GC statistics (via jstat)
- CPU and process-level metrics (via psutil or /proc fallback)
- Network interface statistics (via psutil)
- Disk I/O statistics (via psutil)
- Direct Elasticsearch cluster health
- AnzoGraph active connections (via psutil)
- LDAP group membership validation (optional, requires python-ldap)

Run with:
    python anzo_monitoring_service.py

Or as a systemd service — see anzo-monitoring.service in this directory.

Configuration via environment variables:
    ES_HOST           Elasticsearch host:port (default: localhost:9200)
    AZG_PORT          AnzoGraph port (default: 5600)
    LDAP_SERVER       LDAP server URI (default: ldap://localhost:389)
    LDAP_BASE_DN      LDAP base DN (default: dc=example,dc=com)
    API_KEY           If set, all requests must include X-API-Key header
    ANZO_PROCESS_NAME Substring matched against cmdline args to find the Anzo
                      JVM process (default: anzo.jar; use AnzoLauncher for
                      install4j deployments)
    JSTAT_PATH        Full path to jstat binary when not on PATH (default: jstat)
    JSTAT_SUDO        Set to 'true' to prefix jstat with 'sudo -n', enabling
                      GC stats when running as a non-root user with a narrow
                      sudoers entry (see below)

Running without root
--------------------
The Anzo JVM process is typically owned by root on install4j deployments.
CPU and memory metrics fall back to reading /proc/{pid}/stat and
/proc/{pid}/status, which are world-readable.

JVM GC statistics (jstat) require ptrace-attach privileges. To enable
these without running the full service as root, add a narrow sudoers rule:

    # /etc/sudoers.d/anzo-monitor
    Cmnd_Alias ANZO_JSTAT = /opt/i4j_jres/1.8.472/bin/jstat -gc *
    monitoring_user ALL=(root) NOPASSWD: ANZO_JSTAT

Then set JSTAT_SUDO=true when starting the service.
"""

import os
import subprocess
import time
from datetime import datetime
from functools import wraps

import psutil
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

ES_HOST = os.getenv('ES_HOST', 'localhost:9200')
AZG_PORT = int(os.getenv('AZG_PORT', '5600'))
LDAP_SERVER = os.getenv('LDAP_SERVER', 'ldap://localhost:389')
LDAP_BASE_DN = os.getenv('LDAP_BASE_DN', 'dc=example,dc=com')
API_KEY = os.getenv('API_KEY')

# ANZO_PROCESS_NAME: substring matched against each cmdline argument of running processes.
# Default 'anzo.jar' works for standard installs; set to 'AnzoLauncher' for install4j deployments.
ANZO_PROCESS_NAME = os.getenv('ANZO_PROCESS_NAME', 'anzo.jar')

# JSTAT_PATH: full path to jstat binary. Only needed when jstat is not on PATH
# (e.g. install4j bundles its own JRE at /opt/i4j_jres/<version>/bin/jstat).
JSTAT_PATH = os.getenv('JSTAT_PATH', 'jstat')

# JSTAT_SUDO: prefix jstat with 'sudo -n' so a non-root service user can attach
# to a root-owned JVM. Requires a narrow sudoers rule — see module docstring.
JSTAT_SUDO = os.getenv('JSTAT_SUDO', '').lower() in ('true', '1', 'yes')


# ---------------------------------------------------------------------------
# Optional API key authentication
# ---------------------------------------------------------------------------

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_KEY and request.headers.get('X-API-Key') != API_KEY:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_anzo_pid():
    """Return the PID of the running Anzo JVM, or None."""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if any(ANZO_PROCESS_NAME in (arg or '') for arg in (proc.info['cmdline'] or [])):
                return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def _proc_memory_mb(pid):
    """Read resident memory from /proc/{pid}/status (world-readable, no root needed)."""
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1]) / 1024  # KB -> MB
    except OSError:
        pass
    return None


def _proc_cpu_percent(pid, interval=1.0):
    """
    Compute CPU % for pid from /proc/{pid}/stat (world-readable, no root needed).
    Takes two samples separated by interval seconds.
    """
    def _read_stat(pid):
        try:
            with open(f'/proc/{pid}/stat') as f:
                fields = f.read().split()
            utime = int(fields[13])
            stime = int(fields[14])
            with open('/proc/uptime') as f:
                uptime = float(f.read().split()[0])
            return utime + stime, uptime
        except OSError:
            return None, None

    t1, up1 = _read_stat(pid)
    if t1 is None:
        return None
    time.sleep(interval)
    t2, up2 = _read_stat(pid)
    if t2 is None:
        return None

    clk_tck = os.sysconf('SC_CLK_TCK')
    elapsed = (up2 - up1) * clk_tck
    if elapsed <= 0:
        return 0.0
    return round((t2 - t1) / elapsed * 100, 2)


def _proc_num_threads(pid):
    """Read thread count from /proc/{pid}/status (world-readable)."""
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('Threads:'):
                    return int(line.split()[1])
    except OSError:
        pass
    return None


def _proc_num_fds(pid):
    """Count open file descriptors from /proc/{pid}/fd (may require same UID or root)."""
    try:
        return len(os.listdir(f'/proc/{pid}/fd'))
    except PermissionError:
        return None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


@app.route('/metrics/jvm')
@require_api_key
def get_jvm_metrics():
    """
    JVM heap and GC statistics via jstat.

    Requires ptrace-attach to the Anzo JVM process. When running as a
    non-root user, set JSTAT_SUDO=true and add a narrow sudoers rule:
        Cmnd_Alias ANZO_JSTAT = /path/to/jstat -gc *
        your_user ALL=(root) NOPASSWD: ANZO_JSTAT
    """
    pid = _get_anzo_pid()
    if pid is None:
        return jsonify({'error': 'Anzo process not found'}), 404

    cmd = (['sudo', '-n'] if JSTAT_SUDO else []) + [JSTAT_PATH, '-gc', str(pid)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            hint = ('Set JSTAT_SUDO=true and add a sudoers rule — see service docstring.'
                    if 'permission' in result.stderr.lower() or 'attach' in result.stderr.lower()
                    else '')
            return jsonify({'error': 'jstat failed', 'stderr': result.stderr.strip(),
                            'hint': hint}), 500

        headers = result.stdout.strip().split('\n')[0].split()
        values = result.stdout.strip().split('\n')[1].split()
        stats = dict(zip(headers, values))

        s0c, s1c = float(stats.get('S0C', 0)), float(stats.get('S1C', 0))
        ec, oc = float(stats.get('EC', 0)), float(stats.get('OC', 0))
        s0u, s1u = float(stats.get('S0U', 0)), float(stats.get('S1U', 0))
        eu, ou = float(stats.get('EU', 0)), float(stats.get('OU', 0))
        mc, mu = float(stats.get('MC', 0)), float(stats.get('MU', 0))

        heap_capacity = s0c + s1c + ec + oc
        heap_used = s0u + s1u + eu + ou

        return jsonify({
            'heap_capacity_kb': heap_capacity,
            'heap_used_kb': heap_used,
            'heap_utilization_pct': round(heap_used / heap_capacity * 100, 2) if heap_capacity else 0,
            'metaspace_capacity_kb': mc,
            'metaspace_used_kb': mu,
            'young_gc_count': int(float(stats.get('YGC', 0))),
            'young_gc_time': float(stats.get('YGCT', 0)),
            'full_gc_count': int(float(stats.get('FGC', 0))),
            'full_gc_time': float(stats.get('FGCT', 0)),
            'timestamp': datetime.now().isoformat(),
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'jstat timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/cpu')
@require_api_key
def get_cpu_metrics():
    """
    CPU and process-level memory for the Anzo JVM process.

    Falls back to reading /proc/{pid}/stat and /proc/{pid}/status when
    psutil raises AccessDenied (e.g. cross-UID process access). These
    /proc files are world-readable and do not require root.
    """
    pid = _get_anzo_pid()
    if pid is None:
        return jsonify({'error': 'Anzo process not found'}), 404

    try:
        proc = psutil.Process(pid)
        cpu_pct = proc.cpu_percent(interval=1.0)
        memory_mb = round(proc.memory_info().rss / 1024 / 1024, 2)
        num_threads = proc.num_threads()
        num_fds = proc.num_fds() if hasattr(proc, 'num_fds') else None
        source = 'psutil'
    except psutil.AccessDenied:
        # Fall back to /proc — world-readable, no root required
        cpu_pct = _proc_cpu_percent(pid)
        memory_mb = _proc_memory_mb(pid)
        num_threads = _proc_num_threads(pid)
        num_fds = _proc_num_fds(pid)
        source = '/proc'
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'cpu_percent': cpu_pct,
        'memory_mb': memory_mb,
        'num_threads': num_threads,
        'num_fds': num_fds,
        'source': source,
        'timestamp': datetime.now().isoformat(),
    })


@app.route('/metrics/network')
@require_api_key
def get_network_metrics():
    """Host-level network interface counters (cumulative since boot)."""
    try:
        net = psutil.net_io_counters()
        return jsonify({
            'bytes_sent': net.bytes_sent,
            'bytes_recv': net.bytes_recv,
            'packets_sent': net.packets_sent,
            'packets_recv': net.packets_recv,
            'errin': net.errin,
            'errout': net.errout,
            'dropin': net.dropin,
            'dropout': net.dropout,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/disk')
@require_api_key
def get_disk_metrics():
    """Host-level disk I/O counters (cumulative since boot)."""
    try:
        disk = psutil.disk_io_counters()
        return jsonify({
            'read_bytes': disk.read_bytes,
            'write_bytes': disk.write_bytes,
            'read_count': disk.read_count,
            'write_count': disk.write_count,
            'read_time_ms': disk.read_time,
            'write_time_ms': disk.write_time,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/elasticsearch')
@require_api_key
def get_elasticsearch_health():
    """Direct Elasticsearch cluster health."""
    try:
        resp = requests.get(f'http://{ES_HOST}/_cluster/health', timeout=5)
        resp.raise_for_status()
        health = resp.json()

        node_stats = {}
        try:
            nodes_resp = requests.get(f'http://{ES_HOST}/_nodes/stats', timeout=5)
            if nodes_resp.status_code == 200:
                for node_id, node in nodes_resp.json().get('nodes', {}).items():
                    node_stats[node_id] = {
                        'heap_used_pct': node.get('jvm', {}).get('mem', {}).get('heap_used_percent'),
                        'cpu_percent': node.get('os', {}).get('cpu', {}).get('percent'),
                    }
        except Exception:
            pass

        return jsonify({
            'cluster_name': health.get('cluster_name'),
            'status': health.get('status'),
            'number_of_nodes': health.get('number_of_nodes'),
            'number_of_data_nodes': health.get('number_of_data_nodes'),
            'active_primary_shards': health.get('active_primary_shards'),
            'active_shards': health.get('active_shards'),
            'relocating_shards': health.get('relocating_shards'),
            'initializing_shards': health.get('initializing_shards'),
            'unassigned_shards': health.get('unassigned_shards'),
            'node_stats': node_stats,
            'timestamp': datetime.now().isoformat(),
        })
    except requests.RequestException as e:
        return jsonify({'error': f'Cannot connect to Elasticsearch: {e}'}), 500


@app.route('/metrics/anzograph')
@require_api_key
def get_anzograph_metrics():
    """AnzoGraph active connection counts by TCP state."""
    try:
        conns = psutil.net_connections()
        azg = [c for c in conns if c.laddr.port == AZG_PORT or (c.raddr and c.raddr.port == AZG_PORT)]
        return jsonify({
            'port': AZG_PORT,
            'total_connections': len(azg),
            'established_connections': sum(1 for c in azg if c.status == 'ESTABLISHED'),
            'time_wait_connections': sum(1 for c in azg if c.status == 'TIME_WAIT'),
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/ldap', methods=['POST'])
@require_api_key
def check_ldap_group():
    """
    Check LDAP group membership.

    POST body: {"username": "jsmith", "group": "anzo-admins"}
    Requires python-ldap: pip install python-ldap
    """
    try:
        import ldap as ldap_lib
    except ImportError:
        return jsonify({'error': 'python-ldap not installed — pip install python-ldap'}), 501

    data = request.get_json() or {}
    username = data.get('username')
    group = data.get('group')
    if not username or not group:
        return jsonify({'error': 'username and group are required'}), 400

    try:
        conn = ldap_lib.initialize(LDAP_SERVER)
        conn.simple_bind_s()
        results = conn.search_s(
            LDAP_BASE_DN, ldap_lib.SCOPE_SUBTREE, f'(uid={username})', ['memberOf']
        )
        if not results:
            return jsonify({'error': f'User {username} not found'}), 404

        member_of = [m.decode('utf-8') for m in results[0][1].get('memberOf', [])]
        is_member = any(f'cn={group},' in m for m in member_of)

        return jsonify({
            'username': username,
            'group': group,
            'is_member': is_member,
            'all_groups': member_of,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/all')
@require_api_key
def get_all_metrics():
    """All metrics in one call."""
    result = {}
    for name, fn in [
        ('jvm', get_jvm_metrics),
        ('cpu', get_cpu_metrics),
        ('network', get_network_metrics),
        ('disk', get_disk_metrics),
        ('elasticsearch', get_elasticsearch_health),
        ('anzograph', get_anzograph_metrics),
    ]:  # type: ignore[assignment]
        try:
            resp = fn()
            result[name] = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
        except Exception as e:
            result[name] = {'error': str(e)}
    return jsonify(result)


if __name__ == '__main__':
    port = int(os.environ.get('SERVICE_PORT', 9090))
    # Bind to 0.0.0.0 so the service is reachable from outside the container
    # in Docker/Kubernetes deployments. For host-only deployments you can
    # restrict this to 127.0.0.1 via the BIND_HOST environment variable.
    bind_host = os.environ.get('BIND_HOST', '0.0.0.0')
    app.run(host=bind_host, port=port, debug=False)
