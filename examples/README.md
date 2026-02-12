# Examples Directory

This directory contains ready-to-use examples for monitoring Anzo infrastructure.

## 📁 Directory Structure

```
examples/
├── README.md                           # This file
├── monitor_all.py                      # Comprehensive monitoring example
├── quick_health_check.py               # Simple health check for cron/CI
│
└── backend_service/                    # Backend service for full metrics
    ├── README.md                       # Deployment instructions
    ├── anzo_monitoring_service.py      # Flask service (deploy to server)
    ├── requirements.txt                # Service dependencies
    └── anzo-monitoring.service         # Systemd service file
```

## 🚀 Quick Start

### 1. Configure Your Environment

Edit the configuration section at the top of each script:

```python
SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'

GRAPHMARTS = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
]
```

### 2. Run Examples

```bash
# Comprehensive monitoring (all checks)
python examples/monitor_all.py

# Quick health check (for cron/CI)
python examples/quick_health_check.py
```

## 📖 Example Scripts

### [monitor_all.py](monitor_all.py) - Comprehensive Monitoring

**Purpose:** Demonstrates all available monitoring capabilities

**What it checks:**
- Graphmart status and health
- Layer and step failures
- AnzoGraph connectivity
- Elasticsearch connectivity (indirect)
- LDAP authentication (indirect)

**When to use:**
- Manual monitoring and troubleshooting
- Understanding what monitoring is available
- Integrating with monitoring dashboards

**Exit codes:**
- `0` - All systems healthy
- `1` - One or more issues detected

**Example output:**
```
======================================================================
GRAPHMART STATUS CHECK
======================================================================

✓ Production Graphmart: healthy (Online)
⚠ Analytics Graphmart: degraded (Online)
  └─ 2 layer(s) are dirty

======================================================================
INFRASTRUCTURE HEALTH CHECK
======================================================================

✓ Overall: HEALTHY
✓ Elasticsearch: Healthy
✓ AnzoGraph: Connected
✓ LDAP: Authenticated (45.23ms)
```

---

### [quick_health_check.py](quick_health_check.py) - Simple Health Check

**Purpose:** Lightweight health check for automated monitoring

**What it checks:**
- Basic graphmart status
- AnzoGraph connectivity

**When to use:**
- Cron jobs
- CI/CD pipelines
- Automated alerting
- Health check endpoints

**Exit codes:**
- `0` - All healthy
- `1` - Issues detected

**Cron example:**
```bash
# Check every 5 minutes
*/5 * * * * /path/to/venv/bin/python /path/to/examples/quick_health_check.py || echo "Anzo unhealthy" | mail -s "Alert" admin@example.com
```

**Example output (success):**
```
✓ All systems healthy
```

**Example output (failure):**
```
ERROR: ✗ Production Graphmart: failed - 3 layer(s) failed
ERROR: ✗ Analytics Graphmart: AnzoGraph not connected - Graphmart is Offline
✗ Health check failed - see errors above
```

---

## 🔧 Backend Service (Optional)

For **full infrastructure metrics** (JVM memory, CPU, bandwidth, etc.), deploy the backend service.

See [backend_service/README.md](backend_service/README.md) for deployment instructions.

**Quick deploy:**
```bash
cd examples/backend_service
./deploy.sh anzo-server
```

Once deployed, use the backend client:
```python
from backend_monitoring_client import BackendMonitoringClient

client = BackendMonitoringClient("http://anzo-server:9090")
client.print_summary()
```

---

## 🎯 Common Integration Patterns

### Cron Job Health Check

```bash
#!/bin/bash
# /etc/cron.d/anzo-health-check
*/5 * * * * anzo-user /opt/anzo/venv/bin/python /opt/anzo/examples/quick_health_check.py || /usr/local/bin/send-alert.sh
```

### Monitoring Dashboard (Datadog Example)

```python
from datadog import statsd
from pyanzo_interface import run_infrastructure_health_check

results = run_infrastructure_health_check(api, graphmart_uris=GRAPHMARTS)

statsd.gauge('anzo.graphmarts.healthy', 1 if results['overall_healthy'] else 0)
statsd.gauge('anzo.elasticsearch.healthy', 1 if results['elasticsearch_healthy'] else 0)
statsd.gauge('anzo.anzograph.healthy', 1 if results['anzograph_healthy'] else 0)
```

### Slack Alerts

```python
import requests
from monitoring_hooks import monitor_graphmarts, ArtifactStatus

def alert_callback(report):
    if report.overall_status == ArtifactStatus.FAILED:
        requests.post(SLACK_WEBHOOK_URL, json={
            'text': f'🚨 Anzo Alert: {report.title} FAILED\n{report.error_message}'
        })

monitor_graphmarts(api, GRAPHMARTS, interval=300, callback=alert_callback)
```

### Prometheus Exporter

```python
from prometheus_client import start_http_server, Gauge
from pyanzo_interface import check_graphmart_status, ArtifactStatus

# Create metrics
graphmart_healthy = Gauge('anzo_graphmart_healthy', 'Graphmart health status', ['graphmart'])
failed_layers = Gauge('anzo_failed_layers', 'Number of failed layers', ['graphmart'])

# Update metrics
def update_metrics():
    for gm_uri in GRAPHMARTS:
        report = check_graphmart_status(api, gm_uri)
        graphmart_healthy.labels(graphmart=report.title).set(
            1 if report.overall_status == ArtifactStatus.HEALTHY else 0
        )
        failed_layers.labels(graphmart=report.title).set(report.failed_layers)

# Start server
start_http_server(8000)
while True:
    update_metrics()
    time.sleep(60)
```

---

## 📚 Additional Resources

- [GETTING_STARTED.md](../GETTING_STARTED.md) - Quick start guide
- [README.md](../README.md) - Complete API documentation
- [INFRASTRUCTURE_MONITORING.md](../INFRASTRUCTURE_MONITORING.md) - Available metrics
- [BACKEND_SERVICE_GUIDE.md](../BACKEND_SERVICE_GUIDE.md) - Full monitoring setup

---

## 💡 Tips

1. **Start simple** - Use `quick_health_check.py` first
2. **Test configuration** - Verify credentials and graphmart URIs before deploying
3. **Monitor logs** - Use logging to understand what's being checked
4. **Exit codes** - All scripts return 0 for success, 1 for failure
5. **Deploy backend** - If you need full metrics, deploy the backend service

---

## 🆘 Troubleshooting

**"Connection refused"**
- Check SERVER and PORT configuration
- Verify firewall rules
- Ensure Anzo server is accessible

**"Unauthorized"**
- Verify USERNAME and PASSWORD
- Check user permissions in Anzo

**"Graphmart URI not found"**
- Verify GRAPHMARTS URIs are correct
- Check that graphmarts exist in your Anzo instance

**"SSL errors"**
- Set `VERIFY_SSL = False` for self-signed certificates
- Or install proper SSL certificates

For more help, see [GETTING_STARTED.md](../GETTING_STARTED.md#-troubleshooting)
