# pyanzo_interface

Python interface for Altair Graph Studio (AGS/Anzo) — programmatically manage graphmarts, layers, steps, and monitor infrastructure without the AGS UI.

Designed for use in Databricks notebooks, CI/CD pipelines, and DevOps automation.

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [API Reference — GraphmartManagerApi](#api-reference--graphmartmanagerapi)
- [Monitoring Hooks](#monitoring-hooks)
- [Infrastructure Monitoring](#infrastructure-monitoring)
- [Log-Based Monitoring](#log-based-monitoring)
- [AnzoGraph Direct Monitoring](#anzograph-direct-monitoring)
- [Elasticsearch Direct Monitoring](#elasticsearch-direct-monitoring)
- [Backend Sidecar Service](#backend-sidecar-service)
- [Common Use Cases](#common-use-cases)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)

---

## Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Databricks:**
```python
%pip install requests
```

**Optional — remote log access via SSH:**
```bash
pip install paramiko
```

---

## Quick Start

```python
from graphmart_manager import GraphmartManagerApi

api = GraphmartManagerApi(
    server="your-anzo-server.example.com",
    username="sysadmin",
    password="your-password",
    port="443",
    https=True,
    verify_ssl=False
)

status = api.status("http://example.org/graphmart/production")
print(f"Status: {status}")

api.refresh("http://example.org/graphmart/production")
api.block_until_ready("http://example.org/graphmart/production", timeout=600)
```

---

## API Reference — GraphmartManagerApi

### Initialization

```python
GraphmartManagerApi(
    server: str,              # Anzo server hostname or IP
    username: str,
    password: str,
    port: str = '8443',       # Use '443' for standard HTTPS deployments
    https: bool = True,
    verify_ssl: bool = False, # Set True if using valid certificates
    api_version: str = '',    # Leave empty for Anzo 5.4.2+ (including 5.4.15+)
                              # Set 'v1' only for Anzo 5.4.1
)
```

### Graphmart Lifecycle

| Method | Description |
|--------|-------------|
| `refresh(graphmart_uri)` | Refresh a graphmart (re-process without full reload) |
| `reload(graphmart_uri)` | Full reload of a graphmart |
| `reload_and_wait(graphmart_uri, timeout)` | Full reload, blocks until Online |
| `activate(graphmart_uri, azg_uri)` | Activate graphmart against a specific AZG server |
| `deactivate(graphmart_uri, timeout=60)` | Deactivate graphmart |

### Status & Health

| Method | Description |
|--------|-------------|
| `status(graphmart_uri)` | Current status string (e.g. `"Online"`) |
| `status_details(graphmart_uri)` | Full JSON status including layer info |
| `is_complete(graphmart_uri)` | Whether graphmart processing is complete |
| `health_check(graphmart_uri)` | Logs failed/dirty layers; returns counts |
| `block_until_ready(graphmart_uri, timeout=1000)` | Blocks until Online and complete |
| `get_title(graphmart_uri)` | Human-readable graphmart title |

### Layer Management

| Method | Description |
|--------|-------------|
| `graphmart_layers(graphmart_uri)` | List all layers |
| `create_layer(graphmart_uri, layer_config)` | Create a new layer |
| `create_layer_step(layer_uri, step_config)` | Create a QueryStep in a layer |
| `move_layer(graphmart_uri, target, position, before)` | Reorder layers |
| `enable_layers(graphmart_uri, layer_uris=None, steps=True)` | Enable layers (pass `None` for all) |
| `disable_layers(graphmart_uri, layer_uris=None, steps=True)` | Disable layers |
| `layer_steps(layer_uri)` | List all steps in a layer |

### Step Management

| Method | Description |
|--------|-------------|
| `enable_step(step_uri)` | Enable a step |
| `disable_step(step_uri)` | Disable a step |
| `enable_layer_steps(layer_uri, step_uris=None)` | Enable steps in a layer |
| `disable_layer_steps(layer_uri, step_uris=None)` | Disable steps in a layer |
| `get_step_details(step_uri, query)` | Get expanded step details |
| `update_step(step_uri, data)` | Update step configuration |

### In-Flight Query Management

> Requires Anzo **5.4.15 or later** and sysadmin privileges.

| Method | Description |
|--------|-------------|
| `get_inflight_queries()` | List all running queries (`operationId` + `datasource`) |
| `cancel_query(datasource_uri, operation_id)` | Cancel a specific query |
| `cancel_all_inflight_queries()` | Cancel all running queries; returns count cancelled |

```python
queries = api.get_inflight_queries()
for q in queries:
    print(f"operationId={q['operationId']}  datasource={q['datasource']}")

# Cancel one
api.cancel_query(queries[0]['datasource'], queries[0]['operationId'])

# Cancel all
cancelled = api.cancel_all_inflight_queries()
print(f"Cancelled {cancelled} queries")
```

### AnzoGraph Cluster Restart

```python
api.restart_anzograph(
    azg_uri="http://anzograph-host/datasource/AnzoGraph",
    graphmart_uris=[
        "http://cambridgesemantics.com/graphmart/gm1",
        "http://cambridgesemantics.com/graphmart/gm2",
    ],
    deactivate_timeout=120,
    ready_timeout=1800,
)
```

This deactivates all supplied graphmarts, sends a `GqeReloadRequest` to restart AnzoGraph, then reactivates and waits for each graphmart to come back online.

---

## Monitoring Hooks

`monitoring_hooks.py` provides graphmart-level monitoring functions suitable for dashboards, CI/CD validation, and alerting.

```python
from monitoring_hooks import check_graphmart_status, ArtifactStatus, monitor_graphmarts

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")

report = check_graphmart_status(api, "http://example.org/graphmart/production")
print(f"Status: {report.overall_status.value}")
print(f"Failed layers: {report.failed_layers}")

if report.overall_status == ArtifactStatus.FAILED:
    print(f"Error: {report.error_message}")
```

| Function | Description |
|----------|-------------|
| `check_graphmart_status(api, uri)` | Detailed status report |
| `check_graphmart_health(api, uri)` | Health check with layer error details |
| `get_layer_status(api, uri)` | Status of all layers in a graphmart |
| `check_azg_connection(api, uri)` | AZG connectivity status |
| `monitor_graphmarts(api, uris, interval, callback)` | Continuous monitoring with callbacks |
| `wait_for_graphmart_ready(api, uri, timeout)` | Returns bool when ready |

**Continuous monitoring with alerting:**
```python
def on_status(report):
    if report.overall_status == ArtifactStatus.FAILED:
        send_slack_alert(f"{report.title} FAILED: {report.error_message}")

monitor_graphmarts(api, ["http://example.org/graphmart/gm1"], interval=300, callback=on_status)
```

---

## Infrastructure Monitoring

`infrastructure_monitoring.py` checks infrastructure health using the AGS REST API.

### Elasticsearch Connectivity

Indirect — inferred from layer/step failures that mention Elasticsearch:

```python
from infrastructure_monitoring import check_elasticsearch_connectivity

report = check_elasticsearch_connectivity(api, graphmart_uri)
if not report.is_healthy:
    print(f"{report.failed_es_layers} ES-related layer failures")
    for err in report.error_messages:
        print(f"  {err}")
```

### AnzoGraph Connectivity

```python
from infrastructure_monitoring import check_anzograph_connectivity

report = check_anzograph_connectivity(api, graphmart_uri)
print(f"Connected: {report.is_connected}  AZG: {report.azg_uri}")
```

### LDAP Authentication Check

One-shot test — authenticates against the API and measures response time:

```python
from infrastructure_monitoring import check_ldap_authentication

report = check_ldap_authentication(
    server="anzo.example.com",
    username="testuser",
    password="testpass"
)
print(f"Authenticated: {report.is_authenticated} ({report.response_time_ms:.0f}ms)")
```

### LDAP Periodic Revalidation

Runs repeated authentication checks at a fixed interval over a time window. Useful for detecting transient LDAP connectivity issues:

```python
from infrastructure_monitoring import monitor_ldap_authentication

def on_failure(report):
    send_alert(f"LDAP auth failed at {report.timestamp}: {report.error_message}")

result = monitor_ldap_authentication(
    server="anzo.example.com",
    username="sysadmin",
    password="secret",
    window_seconds=3600,    # Monitor for 1 hour
    interval_seconds=60,    # Check every minute
    on_failure=on_failure,  # Optional: called immediately on each failure
)

print(f"Passed {result.checks_passed}/{result.checks_performed} checks")
print(f"Avg response: {result.avg_response_time_ms:.0f}ms")
if result.checks_failed > 0:
    print(f"Failures at: {result.failure_timestamps}")
```

### Comprehensive Infrastructure Check

```python
from infrastructure_monitoring import run_infrastructure_health_check

results = run_infrastructure_health_check(
    api,
    graphmart_uris=["http://example.org/graphmart/gm1"],
    check_ldap=True
)

print(f"Overall: {results['overall_healthy']}")
print(f"Elasticsearch: {results['elasticsearch_healthy']}")
print(f"AnzoGraph: {results['anzograph_healthy']}")
print(f"LDAP: {results['ldap_healthy']}")
```

---

## Log-Based Monitoring

`log_monitoring.py` scans Anzo server log files for LDAP exceptions and AnzoGraph user activity. Supports reading logs locally or remotely over SSH (`pip install paramiko`).

Default log path: `/opt/Anzo/Server/logs/AnzoServer.log` (Anzo 5.4+)

### LDAP Exception Detection

Scans logs for Java LDAP stack traces (`javax.naming.*Exception`, `com.unboundid.ldap`), bind failures, and generic LDAP error strings within a time window:

```python
from log_monitoring import scan_ldap_exceptions

# Local logs
report = scan_ldap_exceptions(window_minutes=60)
print(f"LDAP exceptions in last hour: {report.exception_count}")
for exc in report.exceptions:
    print(f"  [{exc['timestamp']}] {exc['message']}")
```

**Remote logs via SSH:**
```python
report = scan_ldap_exceptions(
    window_minutes=60,
    ssh_host="192.168.5.96",
    ssh_user="foundry",
    ssh_key_path="~/.ssh/devops_id_rsa",
)
```

**Custom log paths or additional patterns:**
```python
import re
report = scan_ldap_exceptions(
    window_minutes=30,
    log_paths=["/opt/Anzo/Server/logs/AnzoServer.log"],
    extra_patterns=[re.compile(r"my-custom-ldap-error", re.IGNORECASE)],
)
```

### AnzoGraph User Activity Monitoring

Counts unique users who submitted queries to AnzoGraph within a time window by parsing log lines for username patterns:

```python
from log_monitoring import scan_anzograph_user_activity

report = scan_anzograph_user_activity(window_minutes=120)
print(f"Unique users in last 2 hours: {report.unique_user_count}")
print(f"Total query log lines: {report.query_count}")
for user in sorted(report.users):
    print(f"  {user}")
```

**Remote:**
```python
report = scan_anzograph_user_activity(
    window_minutes=60,
    ssh_host="192.168.5.96",
    ssh_user="foundry",
    ssh_key_path="~/.ssh/devops_id_rsa",
)
```

> **Note:** Username extraction depends on your Anzo log format. If `unique_user_count` is 0 but you expect activity, supply `extra_user_patterns` with compiled regex patterns that match your log format (each must have one capture group for the username).

---

## AnzoGraph Direct Monitoring

`anzograph_monitoring.py` talks directly to AnzoGraph's SPARQL endpoint (back-end port 7070, no authentication required) to validate reachability and measure performance independently of Anzo.

```python
from anzograph_monitoring import (
    check_anzograph_liveness,
    measure_anzograph_latency,
    measure_anzograph_throughput,
)

liveness = check_anzograph_liveness("azg-host.example.com")
print(f"Alive: {liveness.is_alive}  ({liveness.response_time_ms:.1f}ms)")

latency = measure_anzograph_latency("azg-host.example.com", num_probes=10)
print(f"Median: {latency.median_ms:.1f}ms  stdev: {latency.stdev_ms:.1f}ms")

throughput = measure_anzograph_throughput("azg-host.example.com", row_limit=10_000)
print(f"Throughput: {throughput.rows_per_second:,.0f} rows/sec")
```

Run the example: `python examples/check_anzograph.py`

---

## Elasticsearch Direct Monitoring

`elasticsearch_monitoring.py` validates ES connectivity by calling the Elasticsearch HTTP API directly — no Anzo involved:

```python
from elasticsearch_monitoring import validate_elasticsearch_connectivity

report = validate_elasticsearch_connectivity(
    host="es-host.example.com",
    port=9200,
    index_filter="anzo",
)

print(f"Reachable: {report.is_reachable}")
print(f"Cluster: {report.cluster_health.cluster_name} — {report.cluster_health.status}")
print(f"Unassigned shards: {report.cluster_health.unassigned_shards}")

for node in report.nodes.nodes:
    print(f"  {node.node_name}: heap {node.heap_used_pct:.1f}%  OS mem {node.os_used_pct:.1f}%")

for idx in report.indices:
    print(f"  {'✓' if idx.is_queryable else '✗'} {idx.index}: {idx.health}  {idx.doc_count:,} docs")
```

Run the example: `python examples/check_elasticsearch.py`

---

## Backend Sidecar Service

Some metrics are not available via the AGS REST API and require a small sidecar service deployed on the Anzo server. `backend_monitoring_client.py` is the Python client for this service.

### What the sidecar unlocks

| Metric | Without sidecar | With sidecar |
|--------|----------------|--------------|
| Network bandwidth (AZG↔Anzo) | See `anzograph_monitoring.py` (SPARQL timing) | Full interface stats via `psutil` |
| JVM heap / GC stats | Not available | Direct via `jstat` |
| CPU utilization | Not available | Process-level via `psutil` |
| Disk I/O | Not available | Via `psutil` |
| Elasticsearch direct health | Via `elasticsearch_monitoring.py` | Redundant (use `elasticsearch_monitoring.py` directly) |
| LDAP group membership | Auth-test only | Direct LDAP query |
| AnzoGraph active connections | Not available | `netstat`/`psutil` |

### Using the client

```python
from backend_monitoring_client import BackendMonitoringClient

client = BackendMonitoringClient("http://anzo-server:9090")

if not client.health_check():
    raise RuntimeError("Backend service not reachable")

jvm = client.get_jvm_metrics()
print(f"Heap: {jvm.heap_utilization_pct:.1f}%  Full GCs: {jvm.full_gc_count}")

net = client.get_network_metrics()
print(f"RX: {net.bytes_recv / 1024 / 1024:.1f} MB  TX: {net.bytes_sent / 1024 / 1024:.1f} MB")

ldap = client.check_ldap_group("jsmith", "anzo-admins")
print(f"Is member: {ldap.is_member}  All groups: {ldap.all_groups}")

client.print_summary()  # Human-readable summary of all metrics
```

### Deploying the sidecar

The sidecar is a Python Flask service in `examples/backend_service/`:

```bash
# Copy to server
scp examples/backend_service/anzo_monitoring_service.py anzo-server:/opt/anzo/monitoring/
scp examples/backend_service/requirements.txt anzo-server:/opt/anzo/monitoring/

ssh anzo-server
cd /opt/anzo/monitoring
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Install as a systemd service
sudo cp examples/backend_service/anzo-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now anzo-monitoring
sudo systemctl status anzo-monitoring
```

The service listens on `localhost:9090` by default. Secure it with an API key if exposing beyond localhost — pass `api_key` to `BackendMonitoringClient` and set the `API_KEY` environment variable on the service.

---

## Common Use Cases

### Restart AnzoGraph and bring graphmarts back online

```python
api.restart_anzograph(
    azg_uri="http://example.org/azg/lakehouse",
    graphmart_uris=["http://example.org/graphmart/prod"],
)
```

### Scheduled graphmart refresh (Databricks)

```python
server = dbutils.secrets.get(scope="anzo", key="server")
username = dbutils.secrets.get(scope="anzo", key="username")
password = dbutils.secrets.get(scope="anzo", key="password")

api = GraphmartManagerApi(server=server, username=username, password=password)
api.refresh("http://example.org/graphmart/daily-refresh")
api.block_until_ready("http://example.org/graphmart/daily-refresh", timeout=3600)

health = api.health_check("http://example.org/graphmart/daily-refresh")
if health['failedLayers'] > 0:
    raise Exception(f"Refresh completed with {health['failedLayers']} failed layers")
```

### Health check script for cron

```python
#!/usr/bin/env python3
import sys
from graphmart_manager import GraphmartManagerApi
from monitoring_hooks import check_graphmart_status, ArtifactStatus

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")
graphmarts = ["http://example.org/graphmart/gm1", "http://example.org/graphmart/gm2"]

all_healthy = True
for uri in graphmarts:
    report = check_graphmart_status(api, uri)
    if report.overall_status != ArtifactStatus.HEALTHY:
        print(f"UNHEALTHY: {report.title} — {report.error_message}")
        all_healthy = False

sys.exit(0 if all_healthy else 1)
```

### Enable/disable specific layers

```python
layers = api.graphmart_layers(graphmart_uri)
layer_uris = [l['uri'] for l in layers if 'optional' in l['title'].lower()]

api.disable_layers(graphmart_uri, layer_uris, steps=True)
# ... do something ...
api.enable_layers(graphmart_uri, layer_uris, steps=True)
```

---

## Error Handling

```python
from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException
import requests

try:
    api.block_until_ready(graphmart_uri, timeout=300)
except GraphmartManagerApiException as e:
    # Timeout, failed layers, dirty layers, or permission denied
    print(f"Graphmart error: {e}")
except requests.exceptions.HTTPError as e:
    # 401, 404, 500, etc.
    print(f"HTTP error: {e}")
except requests.exceptions.ConnectionError as e:
    print(f"Connection error: {e}")
```

**SSL warnings** — suppress when using self-signed certs:
```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

---

## Troubleshooting

**Connection refused / timeout**
- Confirm the server is reachable and port is correct (default `8443`; use `443` for standard HTTPS deployments)
- Check firewall rules on the server

**401 Unauthorized**
- Verify username and password
- Confirm the user account is not locked in LDAP

**SSL Certificate verify failed**
- Set `verify_ssl=False` for self-signed certs, or install valid certs and set `verify_ssl=True`

**`get_inflight_queries` returns HTTP 400**
- This requires Anzo 5.4.15+. Earlier versions do not support the `/sparql/lds/` endpoint for system tables.

**Log monitoring returns 0 results**
- Confirm log file paths with `ls /opt/Anzo/Server/logs/`
- Check `window_minutes` is large enough to cover the time range you expect
- For SSH access, verify the key path and that the remote user can read the log files
- If usernames aren't extracted, your log format may differ — use `extra_user_patterns`

**Backend sidecar not responding**
- `sudo systemctl status anzo-monitoring`
- `sudo journalctl -u anzo-monitoring -f`
- `curl http://localhost:9090/health`

---

## Module Reference

| Module | Purpose |
|--------|---------|
| `graphmart_manager.py` | Core AGS REST API client (`GraphmartManagerApi`) |
| `monitoring_hooks.py` | Graphmart-level monitoring and continuous polling |
| `infrastructure_monitoring.py` | LDAP auth, ES/AZG connectivity via REST API |
| `log_monitoring.py` | LDAP exception detection and user activity from logs |
| `anzograph_monitoring.py` | Direct SPARQL-based AZG liveness, latency, throughput |
| `elasticsearch_monitoring.py` | Direct ES HTTP API health and index checks |
| `backend_monitoring_client.py` | Client for optional backend sidecar service |

## Requirements

- Python 3.10+
- `requests >= 2.28.0`
- `paramiko` (optional, for remote log access via SSH)
