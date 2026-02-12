# Backend Service Implementation Guide

## Overview

If you can deploy a backend service (bash script, Express/Flask server, etc.) on the Anzo server or in the same environment, you can implement **ALL** the missing monitoring capabilities that aren't exposed via the AGS REST API.

This guide shows how to build a custom monitoring service to expose infrastructure metrics.

---

## What Becomes Possible with Backend Access

| Metric | Current Status | With Backend Service | Difficulty |
|--------|---------------|---------------------|------------|
| **AnzoGraph Bandwidth** | ❌ Not available | ✅ Full monitoring | Easy |
| **JVM Memory** | ❌ Requires JMX | ✅ Direct JMX access | Easy |
| **CPU Utilization** | ❌ Not available | ✅ OS-level monitoring | Easy |
| **Elasticsearch Health** | ⚠️ Indirect only | ✅ Direct cluster health | Easy |
| **LDAP Group Validation** | ⚠️ Auth test only | ✅ Direct LDAP queries | Easy |
| **Query Performance** | ❌ Not available | ✅ Log parsing & analysis | Medium |
| **Disk I/O** | ❌ Not available | ✅ OS-level monitoring | Easy |
| **Active Connections** | ❌ Not available | ✅ netstat monitoring | Easy |

---

## Option 1: Bash Script + HTTP Server (Simplest)

### Simple Bash Monitoring Script

Create a bash script that exposes metrics via a simple HTTP server:

```bash
#!/bin/bash
# monitoring_service.sh

PORT=9090

# Function to get JVM memory usage
get_jvm_memory() {
    ANZO_PID=$(pgrep -f "anzo.jar")
    if [ -n "$ANZO_PID" ]; then
        jstat -gc $ANZO_PID | tail -1 | awk '{
            used = ($3 + $4 + $6 + $8)
            capacity = ($1 + $2 + $5 + $7)
            printf "{\"heap_used_kb\": %.0f, \"heap_capacity_kb\": %.0f, \"heap_utilization_pct\": %.2f}",
                   used, capacity, (used/capacity)*100
        }'
    else
        echo '{"error": "Anzo process not found"}'
    fi
}

# Function to get CPU usage
get_cpu_usage() {
    ANZO_PID=$(pgrep -f "anzo.jar")
    if [ -n "$ANZO_PID" ]; then
        ps -p $ANZO_PID -o %cpu,rss | tail -1 | awk '{
            printf "{\"cpu_percent\": %.2f, \"memory_mb\": %.2f}", $1, $2/1024
        }'
    else
        echo '{"error": "Anzo process not found"}'
    fi
}

# Function to get network bandwidth
get_network_bandwidth() {
    # Get network stats for eth0 (adjust interface name as needed)
    cat /proc/net/dev | grep eth0 | awk '{
        printf "{\"rx_bytes\": %s, \"tx_bytes\": %s}", $2, $10
    }'
}

# Function to get Elasticsearch health
get_elasticsearch_health() {
    ES_HOST="${ES_HOST:-localhost:9200}"
    curl -s "http://$ES_HOST/_cluster/health" 2>/dev/null || echo '{"error": "ES not reachable"}'
}

# Function to check AnzoGraph connections
get_anzograph_connections() {
    AZG_PORT="${AZG_PORT:-5600}"
    CONNECTIONS=$(netstat -an | grep ":$AZG_PORT" | grep ESTABLISHED | wc -l)
    echo "{\"active_connections\": $CONNECTIONS}"
}

# Simple HTTP server using netcat
handle_request() {
    local endpoint=$1

    case "$endpoint" in
        "/metrics/jvm")
            get_jvm_memory
            ;;
        "/metrics/cpu")
            get_cpu_usage
            ;;
        "/metrics/network")
            get_network_bandwidth
            ;;
        "/metrics/elasticsearch")
            get_elasticsearch_health
            ;;
        "/metrics/anzograph")
            get_anzograph_connections
            ;;
        "/metrics/all")
            echo "{"
            echo "  \"jvm\": $(get_jvm_memory),"
            echo "  \"cpu\": $(get_cpu_usage),"
            echo "  \"network\": $(get_network_bandwidth),"
            echo "  \"elasticsearch\": $(get_elasticsearch_health),"
            echo "  \"anzograph\": $(get_anzograph_connections)"
            echo "}"
            ;;
        *)
            echo '{"error": "Unknown endpoint"}'
            ;;
    esac
}

# Start HTTP server
echo "Starting monitoring service on port $PORT"
while true; do
    echo "Waiting for connection..."
    RESPONSE=$(echo "GET /metrics/all" | nc -l -p $PORT -q 1 | grep "^GET" | awk '{print $2}')

    OUTPUT=$(handle_request "$RESPONSE")

    echo -ne "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n$OUTPUT" | nc -l -p $PORT -q 1
done
```

Run as a systemd service:

```ini
# /etc/systemd/system/anzo-monitoring.service
[Unit]
Description=Anzo Infrastructure Monitoring Service
After=network.target

[Service]
Type=simple
User=anzo
WorkingDirectory=/opt/anzo/monitoring
ExecStart=/opt/anzo/monitoring/monitoring_service.sh
Restart=always
Environment="ES_HOST=localhost:9200"
Environment="AZG_PORT=5600"

[Install]
WantedBy=multi-user.target
```

---

## Option 2: Python Flask/FastAPI Service (Recommended)

### Full-Featured Python Monitoring Service

```python
#!/usr/bin/env python3
"""
anzo_monitoring_service.py

Custom backend monitoring service for Anzo infrastructure.
Exposes metrics not available via AGS REST API.

Run with: python anzo_monitoring_service.py
"""

from flask import Flask, jsonify
import psutil
import subprocess
import json
import re
import requests
from datetime import datetime
import os

app = Flask(__name__)

# Configuration
ANZO_PROCESS_NAME = "anzo.jar"
ELASTICSEARCH_HOST = os.getenv("ES_HOST", "localhost:9200")
ANZOGRAPH_PORT = int(os.getenv("AZG_PORT", "5600"))
LDAP_SERVER = os.getenv("LDAP_SERVER", "ldap://localhost:389")
LDAP_BASE_DN = os.getenv("LDAP_BASE_DN", "dc=example,dc=com")


def get_anzo_process():
    """Find the Anzo Java process."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if any(ANZO_PROCESS_NAME in arg for arg in proc.info['cmdline']):
                return psutil.Process(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/metrics/jvm', methods=['GET'])
def get_jvm_metrics():
    """
    Get JVM memory metrics via JMX.

    Returns heap usage, non-heap usage, GC stats.
    """
    proc = get_anzo_process()
    if not proc:
        return jsonify({'error': 'Anzo process not found'}), 404

    try:
        # Use jstat to get JVM metrics
        result = subprocess.run(
            ['jstat', '-gc', str(proc.pid)],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            headers = lines[0].split()
            values = lines[1].split()

            stats = dict(zip(headers, values))

            # Calculate heap usage
            s0c = float(stats.get('S0C', 0))
            s1c = float(stats.get('S1C', 0))
            ec = float(stats.get('EC', 0))
            oc = float(stats.get('OC', 0))
            mc = float(stats.get('MC', 0))

            s0u = float(stats.get('S0U', 0))
            s1u = float(stats.get('S1U', 0))
            eu = float(stats.get('EU', 0))
            ou = float(stats.get('OU', 0))
            mu = float(stats.get('MU', 0))

            heap_capacity = s0c + s1c + ec + oc
            heap_used = s0u + s1u + eu + ou

            return jsonify({
                'heap_capacity_kb': heap_capacity,
                'heap_used_kb': heap_used,
                'heap_utilization_pct': (heap_used / heap_capacity * 100) if heap_capacity > 0 else 0,
                'metaspace_capacity_kb': mc,
                'metaspace_used_kb': mu,
                'young_gc_count': int(stats.get('YGC', 0)),
                'young_gc_time': float(stats.get('YGCT', 0)),
                'full_gc_count': int(stats.get('FGC', 0)),
                'full_gc_time': float(stats.get('FGCT', 0)),
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Failed to get JVM stats'}), 500

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'jstat command timed out'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/cpu', methods=['GET'])
def get_cpu_metrics():
    """Get CPU and memory usage for Anzo process."""
    proc = get_anzo_process()
    if not proc:
        return jsonify({'error': 'Anzo process not found'}), 404

    try:
        return jsonify({
            'cpu_percent': proc.cpu_percent(interval=1.0),
            'memory_mb': proc.memory_info().rss / 1024 / 1024,
            'num_threads': proc.num_threads(),
            'num_fds': proc.num_fds() if hasattr(proc, 'num_fds') else None,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/network', methods=['GET'])
def get_network_metrics():
    """Get network bandwidth metrics."""
    try:
        net_io = psutil.net_io_counters()

        return jsonify({
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'errin': net_io.errin,
            'errout': net_io.errout,
            'dropin': net_io.dropin,
            'dropout': net_io.dropout,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/disk', methods=['GET'])
def get_disk_metrics():
    """Get disk I/O metrics."""
    try:
        disk_io = psutil.disk_io_counters()

        return jsonify({
            'read_bytes': disk_io.read_bytes,
            'write_bytes': disk_io.write_bytes,
            'read_count': disk_io.read_count,
            'write_count': disk_io.write_count,
            'read_time_ms': disk_io.read_time,
            'write_time_ms': disk_io.write_time,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/elasticsearch', methods=['GET'])
def get_elasticsearch_health():
    """Get direct Elasticsearch cluster health."""
    try:
        response = requests.get(
            f'http://{ELASTICSEARCH_HOST}/_cluster/health',
            timeout=5
        )

        if response.status_code == 200:
            health = response.json()

            # Get additional node stats
            nodes_response = requests.get(
                f'http://{ELASTICSEARCH_HOST}/_nodes/stats',
                timeout=5
            )

            node_stats = {}
            if nodes_response.status_code == 200:
                nodes_data = nodes_response.json()
                for node_id, node in nodes_data.get('nodes', {}).items():
                    node_stats[node_id] = {
                        'heap_used_pct': node.get('jvm', {}).get('mem', {}).get('heap_used_percent'),
                        'cpu_percent': node.get('os', {}).get('cpu', {}).get('percent')
                    }

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
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': f'ES returned {response.status_code}'}), 500

    except requests.RequestException as e:
        return jsonify({'error': f'Cannot connect to Elasticsearch: {str(e)}'}), 500


@app.route('/metrics/anzograph', methods=['GET'])
def get_anzograph_metrics():
    """Get AnzoGraph connection metrics."""
    try:
        connections = psutil.net_connections()

        # Count connections to AnzoGraph port
        anzograph_connections = [
            conn for conn in connections
            if conn.laddr.port == ANZOGRAPH_PORT or conn.raddr.port == ANZOGRAPH_PORT
        ]

        established = len([c for c in anzograph_connections if c.status == 'ESTABLISHED'])
        time_wait = len([c for c in anzograph_connections if c.status == 'TIME_WAIT'])

        return jsonify({
            'port': ANZOGRAPH_PORT,
            'total_connections': len(anzograph_connections),
            'established_connections': established,
            'time_wait_connections': time_wait,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/ldap', methods=['POST'])
def check_ldap_group():
    """
    Check LDAP group membership.

    POST body: {"username": "user", "group": "groupname"}
    """
    try:
        import ldap
        from flask import request

        data = request.get_json()
        username = data.get('username')
        group = data.get('group')

        if not username or not group:
            return jsonify({'error': 'username and group required'}), 400

        # Connect to LDAP
        conn = ldap.initialize(LDAP_SERVER)
        conn.simple_bind_s()  # Anonymous bind, or use credentials

        # Search for user
        user_filter = f'(uid={username})'
        user_results = conn.search_s(
            LDAP_BASE_DN,
            ldap.SCOPE_SUBTREE,
            user_filter,
            ['memberOf']
        )

        if not user_results:
            return jsonify({'error': 'User not found'}), 404

        # Check group membership
        member_of = user_results[0][1].get('memberOf', [])
        member_of_str = [m.decode('utf-8') for m in member_of]

        is_member = any(f'cn={group},' in m for m in member_of_str)

        return jsonify({
            'username': username,
            'group': group,
            'is_member': is_member,
            'all_groups': member_of_str,
            'timestamp': datetime.now().isoformat()
        })

    except ImportError:
        return jsonify({'error': 'python-ldap not installed'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics/all', methods=['GET'])
def get_all_metrics():
    """Get all metrics in one call."""
    metrics = {}

    # Get each metric, capturing errors
    endpoints = [
        ('jvm', get_jvm_metrics),
        ('cpu', get_cpu_metrics),
        ('network', get_network_metrics),
        ('disk', get_disk_metrics),
        ('elasticsearch', get_elasticsearch_health),
        ('anzograph', get_anzograph_metrics)
    ]

    for name, func in endpoints:
        try:
            response = func()
            if response[1] if isinstance(response, tuple) else 200 == 200:
                metrics[name] = response[0].get_json() if isinstance(response, tuple) else response.get_json()
            else:
                metrics[name] = {'error': 'Failed to retrieve'}
        except Exception as e:
            metrics[name] = {'error': str(e)}

    return jsonify(metrics)


if __name__ == '__main__':
    # Run on localhost only for security
    app.run(host='127.0.0.1', port=9090, debug=False)
```

### Requirements for Python Service

```txt
# requirements.txt
flask==3.0.0
psutil==5.9.6
requests==2.31.0
python-ldap==3.4.4  # Optional, for LDAP features
```

### Systemd Service

```ini
# /etc/systemd/system/anzo-monitoring.service
[Unit]
Description=Anzo Custom Monitoring Service
After=network.target

[Service]
Type=simple
User=anzo
WorkingDirectory=/opt/anzo/monitoring
ExecStart=/opt/anzo/monitoring/venv/bin/python /opt/anzo/monitoring/anzo_monitoring_service.py
Restart=always
Environment="ES_HOST=localhost:9200"
Environment="AZG_PORT=5600"
Environment="LDAP_SERVER=ldap://localhost:389"
Environment="LDAP_BASE_DN=dc=example,dc=com"

[Install]
WantedBy=multi-user.target
```

---

## Option 3: Node.js Express Service

```javascript
// anzo-monitoring-service.js
const express = require('express');
const { exec } = require('child_process');
const axios = require('axios');
const app = express();

const PORT = 9090;
const ES_HOST = process.env.ES_HOST || 'localhost:9200';
const AZG_PORT = process.env.AZG_PORT || '5600';

// JVM Metrics via jstat
app.get('/metrics/jvm', (req, res) => {
    exec("ps aux | grep anzo.jar | grep -v grep | awk '{print $2}'", (err, pid) => {
        if (err || !pid.trim()) {
            return res.status(404).json({ error: 'Anzo process not found' });
        }

        exec(`jstat -gc ${pid.trim()}`, (err, stdout) => {
            if (err) {
                return res.status(500).json({ error: err.message });
            }

            const lines = stdout.trim().split('\n');
            const headers = lines[0].split(/\s+/);
            const values = lines[1].split(/\s+/);

            const stats = {};
            headers.forEach((header, i) => {
                stats[header] = parseFloat(values[i]) || 0;
            });

            const heapCapacity = stats.S0C + stats.S1C + stats.EC + stats.OC;
            const heapUsed = stats.S0U + stats.S1U + stats.EU + stats.OU;

            res.json({
                heap_capacity_kb: heapCapacity,
                heap_used_kb: heapUsed,
                heap_utilization_pct: (heapUsed / heapCapacity * 100).toFixed(2),
                young_gc_count: parseInt(stats.YGC),
                full_gc_count: parseInt(stats.FGC),
                timestamp: new Date().toISOString()
            });
        });
    });
});

// Elasticsearch Health
app.get('/metrics/elasticsearch', async (req, res) => {
    try {
        const response = await axios.get(`http://${ES_HOST}/_cluster/health`);
        res.json({
            ...response.data,
            timestamp: new Date().toISOString()
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// Network Metrics
app.get('/metrics/network', (req, res) => {
    exec('cat /proc/net/dev | grep eth0', (err, stdout) => {
        if (err) {
            return res.status(500).json({ error: err.message });
        }

        const parts = stdout.trim().split(/\s+/);
        res.json({
            rx_bytes: parseInt(parts[1]),
            tx_bytes: parseInt(parts[9]),
            timestamp: new Date().toISOString()
        });
    });
});

// Health check
app.get('/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`Anzo monitoring service running on port ${PORT}`);
});
```

---

## Integration with pyanzo_interface

Once your backend service is deployed, integrate it with the Python interface:

```python
# backend_monitoring_client.py

import requests
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class BackendMetrics:
    """Metrics from custom backend service."""
    jvm_heap_used_kb: float
    jvm_heap_capacity_kb: float
    jvm_heap_utilization_pct: float
    cpu_percent: float
    memory_mb: float
    network_rx_bytes: int
    network_tx_bytes: int
    es_cluster_status: str
    anzograph_connections: int
    timestamp: datetime


class BackendMonitoringClient:
    """Client for custom backend monitoring service."""

    def __init__(self, backend_url: str = "http://localhost:9090"):
        self.backend_url = backend_url.rstrip('/')

    def get_jvm_metrics(self) -> dict:
        """Get JVM memory metrics."""
        response = requests.get(f'{self.backend_url}/metrics/jvm', timeout=5)
        response.raise_for_status()
        return response.json()

    def get_cpu_metrics(self) -> dict:
        """Get CPU metrics."""
        response = requests.get(f'{self.backend_url}/metrics/cpu', timeout=5)
        response.raise_for_status()
        return response.json()

    def get_network_metrics(self) -> dict:
        """Get network metrics."""
        response = requests.get(f'{self.backend_url}/metrics/network', timeout=5)
        response.raise_for_status()
        return response.json()

    def get_elasticsearch_health(self) -> dict:
        """Get Elasticsearch cluster health."""
        response = requests.get(f'{self.backend_url}/metrics/elasticsearch', timeout=5)
        response.raise_for_status()
        return response.json()

    def get_anzograph_metrics(self) -> dict:
        """Get AnzoGraph connection metrics."""
        response = requests.get(f'{self.backend_url}/metrics/anzograph', timeout=5)
        response.raise_for_status()
        return response.json()

    def check_ldap_group(self, username: str, group: str) -> dict:
        """Check LDAP group membership."""
        response = requests.post(
            f'{self.backend_url}/metrics/ldap',
            json={'username': username, 'group': group},
            timeout=5
        )
        response.raise_for_status()
        return response.json()

    def get_all_metrics(self) -> BackendMetrics:
        """Get all metrics in one call."""
        response = requests.get(f'{self.backend_url}/metrics/all', timeout=10)
        response.raise_for_status()
        data = response.json()

        return BackendMetrics(
            jvm_heap_used_kb=data['jvm']['heap_used_kb'],
            jvm_heap_capacity_kb=data['jvm']['heap_capacity_kb'],
            jvm_heap_utilization_pct=data['jvm']['heap_utilization_pct'],
            cpu_percent=data['cpu']['cpu_percent'],
            memory_mb=data['cpu']['memory_mb'],
            network_rx_bytes=data['network']['bytes_recv'],
            network_tx_bytes=data['network']['bytes_sent'],
            es_cluster_status=data['elasticsearch']['status'],
            anzograph_connections=data['anzograph']['established_connections'],
            timestamp=datetime.now()
        )


# Usage example
if __name__ == '__main__':
    client = BackendMonitoringClient("http://localhost:9090")

    # Get all metrics
    metrics = client.get_all_metrics()
    print(f"JVM Heap: {metrics.jvm_heap_utilization_pct}%")
    print(f"CPU: {metrics.cpu_percent}%")
    print(f"ES Status: {metrics.es_cluster_status}")
    print(f"AZG Connections: {metrics.anzograph_connections}")
```

---

## Deployment Recommendations

### 1. Security Considerations

```python
# Add authentication to your backend service
from functools import wraps
from flask import request, jsonify

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key != os.getenv('API_KEY'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/metrics/all', methods=['GET'])
@require_api_key
def get_all_metrics():
    # ... implementation
```

### 2. Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    procps \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY anzo_monitoring_service.py .

ENV FLASK_APP=anzo_monitoring_service.py
EXPOSE 9090

CMD ["python", "anzo_monitoring_service.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  anzo-monitoring:
    build: .
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - /proc:/host/proc:ro
    environment:
      - ES_HOST=elasticsearch:9200
      - AZG_PORT=5600
    network_mode: host  # Required for process monitoring
```

### 3. Kubernetes Deployment

```yaml
# kubernetes-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: anzo-monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: anzo-monitoring
  template:
    metadata:
      labels:
        app: anzo-monitoring
    spec:
      hostNetwork: true  # Required for process monitoring
      containers:
      - name: monitoring
        image: anzo-monitoring:latest
        ports:
        - containerPort: 9090
        env:
        - name: ES_HOST
          value: "elasticsearch:9200"
        - name: AZG_PORT
          value: "5600"
        volumeMounts:
        - name: proc
          mountPath: /host/proc
          readOnly: true
      volumes:
      - name: proc
        hostPath:
          path: /proc
---
apiVersion: v1
kind: Service
metadata:
  name: anzo-monitoring
spec:
  selector:
    app: anzo-monitoring
  ports:
  - port: 9090
    targetPort: 9090
  type: ClusterIP
```

---

## Summary

With a custom backend service deployed on the Anzo server:

| Feature | Without Backend | With Backend |
|---------|----------------|--------------|
| **Bandwidth Monitoring** | ❌ | ✅ Full network stats |
| **Memory Utilization** | ❌ | ✅ JVM heap details |
| **CPU Usage** | ❌ | ✅ Process-level CPU |
| **ES Direct Health** | ⚠️ Indirect | ✅ Direct cluster health |
| **LDAP Group Check** | ⚠️ Auth only | ✅ Group membership validation |
| **Query Performance** | ❌ | ✅ Log parsing available |
| **Disk I/O** | ❌ | ✅ Full disk metrics |
| **Active Connections** | ❌ | ✅ Port monitoring |

**Recommendation:** Deploy the **Python Flask service** (Option 2) - it's the most feature-complete and maintainable solution.
