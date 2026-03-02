# pyanzo_interface

Python interface for Altair Graph Studio (Anzo) - programmatically manage graphmarts, layers, and steps without requiring the AGS UI.

## 🚀 Quick Navigation

| I want to... | Go to... |
|--------------|----------|
| **Get started quickly** | [GETTING_STARTED.md](GETTING_STARTED.md) ⭐ |
| **Run monitoring examples** | [examples/](examples/) → [monitor_all.py](examples/monitor_all.py) |
| **Deploy backend service** (for full metrics) | [examples/backend_service/](examples/backend_service/) |
| **Understand file structure** | [FILE_STRUCTURE.md](FILE_STRUCTURE.md) |
| **See API documentation** | Continue reading below |

---

## Overview

This module provides a REST API client for Altair Graph Studio (also known as Anzo) that enables automation of common administrative tasks:

- Restarting AnzoGraph (AZG) Lakehouse
- Refreshing/reloading graphmarts
- Managing layers and steps
- Health monitoring and status checks

Designed for use in Databricks notebooks, CI/CD pipelines, and DevOps workflows.

### Artifacts Managed

- **Graphmarts**: Primary data processing units containing layers and steps that process and transform data
- **AZG (AnzoGraph)**: Lakehouse component that graphmarts connect to for data processing
- **Layers**: Nested processing components within graphmarts that organize related steps
- **Steps**: Individual processing tasks within layers (such as queries, transforms, etc.)
- **ES/DU (Entity Storage/Data Units)**: Internal data model components accessible via graphmart status and layer inspection

## Installation

### Option 1: Using pip with venv (Recommended)

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Option 2: Install as a package

```bash
pip install -e .
```

### Option 3: Databricks

Upload this directory to your Databricks workspace and install dependencies in your notebook:

```python
%pip install requests
```

## Quick Start

```python
from pyanzo_interface import GraphmartManagerApi

# Initialize the API client
api = GraphmartManagerApi(
    server="your-anzo-server.example.com",
    username="sysadmin",
    password="your-password",
    port="8443",        # Default HTTPS port
    https=True,         # Use HTTPS
    verify_ssl=False    # Set to True if using valid SSL certs
)

# Get graphmart status
graphmart_uri = "http://example.org/graphmart/my-graphmart"
status = api.status(graphmart_uri)
print(f"Graphmart status: {status}")

# Refresh a graphmart
api.refresh(graphmart_uri)

# Wait for graphmart to be ready (blocks until online or timeout)
api.block_until_ready(graphmart_uri, timeout=600)
```

## API Reference

### Initialization

```python
GraphmartManagerApi(
    server: str,           # Anzo server hostname or IP
    username: str,         # Authentication username
    password: str,         # Authentication password
    port: str = '8443',    # Server port
    https: bool = True,    # Use HTTPS (True) or HTTP (False)
    verify_ssl: bool = False  # Verify SSL certificates
)
```

### Graphmart Lifecycle Operations

| Method | Description |
|--------|-------------|
| `refresh(graphmart_uri)` | Refresh a graphmart (re-process data without full reload) |
| `reload(graphmart_uri)` | Full reload of a graphmart |
| `activate(graphmart_uri, azg_uri)` | Activate graphmart with a specific AZG server |
| `deactivate(graphmart_uri, timeout=60)` | Deactivate graphmart |

### Status & Monitoring

| Method | Description |
|--------|-------------|
| `status(graphmart_uri)` | Get current status (e.g., "Online", "Offline") |
| `status_details(graphmart_uri)` | Get detailed status including layer info |
| `is_complete(graphmart_uri)` | Check if graphmart processing is complete |
| `health_check(graphmart_uri)` | Perform health check, logs failed/dirty layers |
| `block_until_ready(graphmart_uri, timeout=1000)` | Wait for graphmart to be Online and complete |
| `get_title(graphmart_uri)` | Get the graphmart's display title |

### Layer Management

| Method | Description |
|--------|-------------|
| `graphmart_layers(graphmart_uri)` | Get all layers in a graphmart |
| `create_layer(graphmart_uri, layer_config)` | Create a new layer |
| `move_layer(graphmart_uri, target, position, before)` | Move layer before/after another |
| `enable_layers(graphmart_uri, layer_uris, steps=True)` | Enable layers (optionally with steps) |
| `disable_layers(graphmart_uri, layer_uris, steps=True)` | Disable layers (optionally with steps) |
| `layer_steps(layer_uri)` | Get all steps in a layer |

### Step Management

| Method | Description |
|--------|-------------|
| `enable_step(step_uri)` | Enable a step |
| `disable_step(step_uri)` | Disable a step |
| `enable_layer_steps(layer_uri, step_uris)` | Enable specific steps in a layer |
| `disable_layer_steps(layer_uri, step_uris)` | Disable specific steps in a layer |
| `get_step_details(step_uri, query)` | Get detailed step information |
| `update_step(step_uri, data)` | Update step configuration |

### In-Flight Query Cancellation

| Method | Description |
|--------|-------------|
| `get_inflight_queries()` | List all currently executing queries (operationId + datasource) |
| `cancel_query(datasource_uri, operation_id)` | Cancel a specific in-flight query |
| `cancel_all_inflight_queries()` | Cancel every currently executing query; returns count cancelled |

> **Requires sysadmin privileges.** `cancel_query` raises `GraphmartManagerApiException` if the
> caller lacks permission or the target query has already finished.

#### How Query Cancellation Works

Cancellation is a two-step process handled transparently by these methods:

1. **Fetch** — `get_inflight_queries()` runs a SPARQL SELECT against the
   `InflightQueries` system graph to retrieve the `operationId` and datasource
   URI of every running query.
2. **Cancel** — `cancel_query()` builds a uniquely-named TriG payload and
   POSTs it to the Anzo `cancelQuery` semantic service endpoint.

#### Examples

```python
from pyanzo_interface import GraphmartManagerApi

api = GraphmartManagerApi(
    server="anzo.example.com",
    username="sysadmin",
    password="password"
)

# --- List in-flight queries ---
queries = api.get_inflight_queries()
for q in queries:
    print(f"operationId={q['operationId']}  datasource={q['datasource']}")

# --- Cancel one specific query ---
api.cancel_query(
    datasource_uri=queries[0]['datasource'],
    operation_id=queries[0]['operationId'],
)

# --- Cancel ALL in-flight queries ---
cancelled = api.cancel_all_inflight_queries()
print(f"Cancelled {cancelled} queries")
```

#### Error Handling

```python
from pyanzo_interface import GraphmartManagerApi, GraphmartManagerApiException
import requests

try:
    api.cancel_query(datasource_uri, operation_id)
except GraphmartManagerApiException as e:
    # Raised for permission denied (403) or query already finished
    print(f"Cancellation failed: {e}")
except requests.exceptions.HTTPError as e:
    # Raised for unexpected HTTP errors from the semantic service
    print(f"HTTP error: {e}")
```

## Monitoring Hooks

The `monitoring_hooks` module provides convenient functions for monitoring artifact status and health. These are useful for:
- Automated health checks
- Dashboard integrations
- CI/CD pipeline validation
- Alerting and notification systems

### Quick Monitoring Example

```python
from pyanzo_interface import GraphmartManagerApi
from pyanzo_interface.monitoring_hooks import check_graphmart_status, ArtifactStatus

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")

# Check status of a graphmart
report = check_graphmart_status(api, "http://example.org/graphmart/production")

print(f"Graphmart: {report.title}")
print(f"Status: {report.overall_status.value}")
print(f"Failed Layers: {report.failed_layers}")

# Take action based on status
if report.overall_status == ArtifactStatus.FAILED:
    # Send alert
    print(f"ALERT: {report.error_message}")
```

### Available Monitoring Functions

| Function | Description |
|----------|-------------|
| `check_graphmart_status(api, uri)` | Get detailed status report for a graphmart |
| `check_graphmart_health(api, uri)` | Perform comprehensive health check with error details |
| `get_layer_status(api, uri)` | Get status of all layers in a graphmart |
| `check_azg_connection(api, uri)` | Check AZG (AnzoGraph) connection status |
| `monitor_graphmarts(api, uris, interval)` | Continuous monitoring with callbacks |
| `wait_for_graphmart_ready(api, uri, timeout)` | Wait for graphmart to become ready (boolean return) |

### Running the Example Script

A comprehensive monitoring example is provided in [monitor_artifacts_example.py](monitor_artifacts_example.py):

```bash
# Configure your environment in the script, then run:
python monitor_artifacts_example.py
```

The example demonstrates:
1. Basic status checks
2. Detailed health checks with layer inspection
3. AZG connection verification
4. Multi-graphmart monitoring summaries
5. Continuous monitoring with alert callbacks
6. Waiting for graphmart readiness

## Infrastructure Monitoring

### AnzoGraph Connectivity & Performance

`anzograph_monitoring.py` talks directly to AnzoGraph's SPARQL endpoints to
validate reachability and measure query performance.

**Available via AnzoGraph SPARQL endpoints ✓**

| Function | Endpoint used | Description |
|----------|--------------|-------------|
| `check_anzograph_liveness(host, port)` | `GET /sparql` (back-end port 7070) | Is AnzoGraph accepting queries? |
| `measure_anzograph_latency(host, port, num_probes)` | `GET /sparql` (back-end port 7070) | Round-trip query latency (min/median/max/stdev) across N probes |
| `measure_anzograph_throughput(host, port, row_limit)` | `GET /sparql` (back-end port 7070) | Rows/second for a bounded result-set query |

> **Back-end port 7070 requires no authentication** and bypasses Anzo's
> gateway, giving a clean measurement of the Anzo→AZG network path.

```python
from anzograph_monitoring import (
    check_anzograph_liveness,
    measure_anzograph_latency,
    measure_anzograph_throughput,
)

liveness = check_anzograph_liveness("azg-host.example.com")
print(f"Alive: {liveness.is_alive}  ({liveness.response_time_ms:.1f}ms)")

latency = measure_anzograph_latency("azg-host.example.com", num_probes=10)
print(f"Median latency: {latency.median_ms:.1f}ms  stdev: {latency.stdev_ms:.1f}ms")

throughput = measure_anzograph_throughput("azg-host.example.com", row_limit=10_000)
print(f"Throughput: {throughput.rows_per_second:,.0f} rows/sec")
```

**NOT available without a backend sidecar per AZG node ✗**

| Metric | Why | Alternative |
|--------|-----|-------------|
| **Per-node / per-worker memory** | AZG management uses gRPC (port 5600), not REST. No public endpoint exists. | Deploy `psutil` sidecar on each node — see [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md) |
| **True intra-cluster interconnect bandwidth** | The Admin Console has a network benchmark but it is UI-only with no API equivalent. | OS-level tools (`iftop`, Prometheus `node_exporter`) on each AZG node |

Run the example: `python examples/check_anzograph.py`

---

### Elasticsearch Direct Validation

`elasticsearch_monitoring.py` validates ES connectivity by calling the
Elasticsearch HTTP API directly — no Anzo involved.

**Available via Elasticsearch REST API ✓**

| Function | ES endpoint | Description |
|----------|------------|-------------|
| `check_cluster_health(host, port)` | `GET /_cluster/health` | Status (green/yellow/red), node counts, shard distribution |
| `check_node_memory(host, port)` | `GET /_nodes/stats/jvm,os` | Per-node JVM heap and OS memory for every node in the cluster |
| `check_indices(host, port, index_filter)` | `GET /_cat/indices` + `GET /<index>/_count` | Index health, document counts, and query validation |
| `validate_elasticsearch_connectivity(...)` | All of the above | Single call that runs all checks and returns a composite report |

```python
from elasticsearch_monitoring import validate_elasticsearch_connectivity

report = validate_elasticsearch_connectivity(
    host="es-host.example.com",
    port=9200,
    index_filter="anzo",    # only validate indices matching this substring
)

print(f"Reachable: {report.is_reachable}")
print(f"Cluster: {report.cluster_health.cluster_name} — {report.cluster_health.status}")
print(f"Unassigned shards: {report.cluster_health.unassigned_shards}")

for node in report.nodes.nodes:
    print(f"  {node.node_name}: heap {node.heap_used_pct:.1f}%  "
          f"OS mem {node.os_used_pct:.1f}%")

for idx in report.indices:
    ok = "✓" if idx.is_queryable else "✗"
    print(f"  {ok} {idx.index}: {idx.health}  {idx.doc_count:,} docs")

print(f"Overall healthy: {report.overall_healthy}")
```

Run the example: `python examples/check_elasticsearch.py`

---

### What IS Available via REST API ✓

| Component | Availability | Method |
|-----------|-------------|---------|
| **Elasticsearch Connectivity** | ✓ Indirect (via Anzo) | Layer/step failures in graphmart status |
| **Elasticsearch Connectivity** | ✓ **Direct** | `elasticsearch_monitoring.validate_elasticsearch_connectivity()` |
| **AnzoGraph Liveness** | ✓ Direct | `anzograph_monitoring.check_anzograph_liveness()` via SPARQL port |
| **AnzoGraph Latency** | ✓ Direct | `anzograph_monitoring.measure_anzograph_latency()` via SPARQL port |
| **AnzoGraph via graphmart** | ✓ Direct | `infrastructure_monitoring.check_anzograph_connectivity()` |
| **LDAP Authentication** | ✓ Indirect | `infrastructure_monitoring.check_ldap_authentication()` |
| **Graphmart Health** | ✓ Direct | `monitoring_hooks.check_graphmart_status()` |

### What is NOT Available via REST API ✗

The following metrics require external monitoring tools (JMX, OS tools, APM):

| Metric | Recommended Approach |
|--------|---------------------|
| **AZG per-node memory** | Backend sidecar with `psutil` on each AZG node (see [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md)) |
| **AZG intra-cluster bandwidth** | OS-level: `iftop`, Prometheus `node_exporter` on each AZG node |
| **AnzoGraph Bandwidth** | Network monitoring tools (Prometheus node_exporter, Datadog) |
| **JVM Memory Utilization** | JMX monitoring (JConsole, VisualVM, Prometheus JMX Exporter) |
| **CPU Utilization** | OS-level monitoring (top, htop) or APM tools |
| **Query Performance** | AnzoGraph query logs, SPARQL endpoint timing |
| **Network Bandwidth** | Network monitoring (iftop, SNMP, cloud provider metrics) |
| **Disk I/O** | OS tools (iostat, iotop) or Prometheus node_exporter |

### Custom Backend Service Solution ⭐

**If you can deploy a backend service** on the Anzo server or in the same environment, you can access **ALL** the missing metrics! See [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md) for:

- ✅ **Full implementation** - Python Flask service that exposes all infrastructure metrics
- ✅ **Direct JVM metrics** - Heap usage, GC stats via local JMX access
- ✅ **Network bandwidth** - Real-time interface statistics
- ✅ **Direct ES health** - Cluster status, shard counts, node stats
- ✅ **LDAP group validation** - Direct LDAP queries for group membership
- ✅ **CPU, Disk, Connections** - Full OS-level metrics

**Quick Example:**
```python
from backend_monitoring_client import BackendMonitoringClient

# Connect to your deployed backend service
client = BackendMonitoringClient("http://anzo-server:9090")

# Get JVM metrics (direct access)
jvm = client.get_jvm_metrics()
print(f"Heap: {jvm.heap_utilization_pct}%")

# Get direct Elasticsearch health
es = client.get_elasticsearch_health()
print(f"ES Status: {es.status}, Nodes: {es.number_of_nodes}")

# Check LDAP group membership
ldap = client.check_ldap_group("jsmith", "anzo-admins")
print(f"Is member: {ldap.is_member}")

# Print full summary
client.print_summary()
```

See [backend_monitoring_client.py](backend_monitoring_client.py) for the Python client integration.

### Infrastructure Monitoring Example

```python
from pyanzo_interface import GraphmartManagerApi
from pyanzo_interface.infrastructure_monitoring import (
    check_elasticsearch_connectivity,
    check_anzograph_connectivity,
    check_ldap_authentication,
    run_infrastructure_health_check
)

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")

# Check Elasticsearch (indirect - via layer status)
es_report = check_elasticsearch_connectivity(api, "http://example.org/graphmart/prod")
if not es_report.is_healthy:
    print(f"ES Issues: {es_report.error_messages}")

# Check AnzoGraph connectivity
azg_report = check_anzograph_connectivity(api, "http://example.org/graphmart/prod")
print(f"AZG Connected: {azg_report.is_connected}")

# Check LDAP authentication
ldap_report = check_ldap_authentication(
    server="anzo.example.com",
    username="testuser",
    password="testpass"
)
print(f"LDAP Auth: {ldap_report.is_authenticated} ({ldap_report.response_time_ms}ms)")

# Comprehensive check
results = run_infrastructure_health_check(
    api,
    graphmart_uris=["http://example.org/graphmart/gm1", "http://example.org/graphmart/gm2"]
)
print(f"Overall Healthy: {results['overall_healthy']}")
```

### Running Infrastructure Monitoring Examples

```bash
# Comprehensive infrastructure monitoring examples
python infrastructure_monitor_example.py
```

### External Monitoring Setup Recommendations

For metrics not available via REST API, integrate AGS with:

1. **JMX Monitoring** (Memory, GC, Threads)
   - Enable JMX on Anzo server (port 1099)
   - Use Prometheus JMX Exporter, JConsole, or VisualVM
   - Monitor MBeans: `java.lang:type=Memory`, `java.lang:type=GarbageCollector`

2. **OS-Level Monitoring** (CPU, Disk, Network)
   - Prometheus node_exporter
   - Datadog agent
   - New Relic infrastructure agent

3. **Network Monitoring** (Bandwidth, Throughput)
   - SNMP monitoring for network switches
   - Cloud provider network metrics (AWS CloudWatch, Azure Monitor)
   - NetFlow/sFlow for traffic analysis

4. **Query Performance**
   - Enable AnzoGraph query logging
   - Parse logs for slow queries
   - Monitor SPARQL endpoint response times

See `infrastructure_monitoring.print_external_monitoring_guidance()` for detailed recommendations.

## Common Use Cases

### Restart AnzoGraph Lakehouse and Reload Graphmart

```python
from pyanzo_interface import GraphmartManagerApi, GraphmartManagerApiException

api = GraphmartManagerApi(
    server="anzo.example.com",
    username="admin",
    password="password"
)

graphmart_uri = "http://example.org/graphmart/production"
azg_uri = "http://example.org/azg/lakehouse"

try:
    # Deactivate the graphmart
    print("Deactivating graphmart...")
    api.deactivate(graphmart_uri, timeout=120)

    # Reactivate with AZG server
    print("Activating graphmart...")
    api.activate(graphmart_uri, azg_uri)

    # Wait for it to come online
    print("Waiting for graphmart to be ready...")
    api.block_until_ready(graphmart_uri, timeout=1800)

    print("Graphmart is online and ready!")

except GraphmartManagerApiException as e:
    print(f"Error: {e}")
```

### Scheduled Graphmart Refresh (Databricks)

```python
# Databricks notebook cell
from pyanzo_interface import GraphmartManagerApi

# Use Databricks secrets for credentials
server = dbutils.secrets.get(scope="anzo", key="server")
username = dbutils.secrets.get(scope="anzo", key="username")
password = dbutils.secrets.get(scope="anzo", key="password")

api = GraphmartManagerApi(server=server, username=username, password=password)

graphmart_uri = "http://example.org/graphmart/daily-refresh"

# Refresh and wait
api.refresh(graphmart_uri)
api.block_until_ready(graphmart_uri, timeout=3600)

# Perform health check
health = api.health_check(graphmart_uri)
if health['failedLayers'] > 0:
    raise Exception(f"Refresh completed with {health['failedLayers']} failed layers")
```

### Enable/Disable Specific Layers

```python
api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")
graphmart_uri = "http://example.org/graphmart/test"

# Get all layers
layers = api.graphmart_layers(graphmart_uri)
for layer in layers:
    print(f"Layer: {layer['title']} - {layer['uri']}")

# Disable specific layers (without their steps)
layer_uris = [
    "http://example.org/layer/optional-1",
    "http://example.org/layer/optional-2"
]
api.disable_layers(graphmart_uri, layer_uris, steps=False)

# Re-enable them
api.enable_layers(graphmart_uri, layer_uris, steps=True)
```

## Logging

The module uses Python's standard logging. Configure it in your application:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Or for specific module logging
logger = logging.getLogger('pyanzo_interface.graphmart_manager')
logger.setLevel(logging.INFO)
```

## SSL Configuration

By default, SSL verification is disabled (`verify_ssl=False`) to support self-signed certificates common in enterprise deployments. For production environments with valid certificates:

```python
api = GraphmartManagerApi(
    server="anzo.example.com",
    username="admin",
    password="password",
    verify_ssl=True  # Enable SSL verification
)
```

To suppress SSL warnings when using `verify_ssl=False`:

```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
```

## Error Handling

The module raises `GraphmartManagerApiException` for API-level errors and `requests.exceptions.HTTPError` for HTTP errors:

```python
from pyanzo_interface import GraphmartManagerApi, GraphmartManagerApiException
import requests

try:
    api.block_until_ready(graphmart_uri, timeout=300)
except GraphmartManagerApiException as e:
    # Timeout, failed layers, or dirty layers
    print(f"Graphmart error: {e}")
except requests.exceptions.HTTPError as e:
    # HTTP errors (401, 404, 500, etc.)
    print(f"HTTP error: {e}")
except requests.exceptions.ConnectionError as e:
    # Network connectivity issues
    print(f"Connection error: {e}")
```

## Requirements

- Python 3.9+
- requests >= 2.28.0

## License

Internal use only.
