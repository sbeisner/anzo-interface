# pyanzo_interface

Python interface for Altair Graph Studio (Anzo) - programmatically manage graphmarts, layers, and steps without requiring the AGS UI.

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
