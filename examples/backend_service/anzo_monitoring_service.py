#!/usr/bin/env python3
"""
Anzo Backend Monitoring Sidecar Service

Exposes infrastructure metrics not available via the AGS REST API:
- JVM heap and GC statistics (via jstat)
- CPU and process-level metrics (via psutil)
- Network interface statistics (via psutil)
- Disk I/O statistics (via psutil)
- Direct Elasticsearch cluster health
- AnzoGraph active connections (via psutil)
- LDAP group membership validation (optional, requires python-ldap)

Run with:
    python anzo_monitoring_service.py

Or as a systemd service — see anzo-monitoring.service in this directory.

Configuration via environment variables:
    ES_HOST      Elasticsearch host:port (default: localhost:9200)
    AZG_PORT     AnzoGraph port (default: 5600)
    LDAP_SERVER  LDAP server URI (default: ldap://localhost:389)
    LDAP_BASE_DN LDAP base DN (default: dc=example,dc=com)
    API_KEY      If set, all requests must include X-API-Key header
"""

import os
import subprocess
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

ANZO_PROCESS_NAME = 'anzo.jar'


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

def _get_anzo_process():
    """Return the psutil.Process for the running Anzo JVM, or None."""
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if any(ANZO_PROCESS_NAME in (arg or '') for arg in proc.info['cmdline']):
                return psutil.Process(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
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
    """JVM heap and GC statistics via jstat."""
    proc = _get_anzo_process()
    if not proc:
        return jsonify({'error': 'Anzo process not found'}), 404

    try:
        result = subprocess.run(
            ['jstat', '-gc', str(proc.pid)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return jsonify({'error': 'jstat failed', 'stderr': result.stderr}), 500

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
    """CPU and process-level memory for the Anzo JVM process."""
    proc = _get_anzo_process()
    if not proc:
        return jsonify({'error': 'Anzo process not found'}), 404

    try:
        return jsonify({
            'cpu_percent': proc.cpu_percent(interval=1.0),
            'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 2),
            'num_threads': proc.num_threads(),
            'num_fds': proc.num_fds() if hasattr(proc, 'num_fds') else None,
            'timestamp': datetime.now().isoformat(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
    ]:
        try:
            resp = fn()
            result[name] = resp.get_json() if hasattr(resp, 'get_json') else resp[0].get_json()
        except Exception as e:
            result[name] = {'error': str(e)}
    return jsonify(result)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=9090, debug=False)
