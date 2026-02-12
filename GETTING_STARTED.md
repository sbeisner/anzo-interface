# Getting Started with Anzo Monitoring

This guide provides a quick overview of how to use the pyanzo_interface monitoring capabilities.

## 📚 Documentation Overview

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **[GETTING_STARTED.md](GETTING_STARTED.md)** (this file) | Quick start guide | Start here |
| **[README.md](README.md)** | Complete API reference | For detailed API documentation |
| **[INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md)** | What's available via API | Understanding monitoring limitations |
| **[BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md)** | Deploy custom backend service | To access ALL metrics (requires deployment) |

## 🚀 Quick Start

### Step 1: Install

```bash
cd pyanzo_interface
pip install -r requirements.txt
```

### Step 2: Choose Your Monitoring Approach

You have **two options** depending on your deployment capabilities:

---

## Option 1: REST API Monitoring Only (No Backend Required)

**Best for:** Quick setup, no server deployment needed

**What you can monitor:**
- ✅ Graphmart health (Online/Offline, complete status)
- ✅ Layer and step failures (with error details)
- ✅ AnzoGraph connectivity (is graphmart connected?)
- ⚠️ Elasticsearch connectivity (indirect - via layer failures)
- ⚠️ LDAP authentication (indirect - via auth tests)

**What you CANNOT monitor:**
- ❌ JVM memory utilization
- ❌ CPU usage
- ❌ Network bandwidth
- ❌ Disk I/O
- ❌ Direct Elasticsearch cluster health
- ❌ Direct LDAP group validation

### Quick Example:

```python
from pyanzo_interface import (
    GraphmartManagerApi,
    check_graphmart_status,
    check_anzograph_connectivity,
    check_elasticsearch_connectivity,
    check_ldap_authentication,
    ArtifactStatus
)

# Initialize API
api = GraphmartManagerApi(
    server="anzo.example.com",
    username="admin",
    password="password"
)

# Check graphmart health
report = check_graphmart_status(api, "http://example.org/graphmart/production")
print(f"Status: {report.overall_status.value}")
print(f"Failed Layers: {report.failed_layers}")

if report.overall_status == ArtifactStatus.FAILED:
    print(f"Issue: {report.error_message}")

# Check AnzoGraph connectivity
azg = check_anzograph_connectivity(api, "http://example.org/graphmart/production")
print(f"AZG Connected: {azg.is_connected}")

# Check Elasticsearch (indirect via layer failures)
es = check_elasticsearch_connectivity(api, "http://example.org/graphmart/production")
print(f"ES Healthy: {es.is_healthy}")

# Check LDAP (indirect via auth test)
ldap = check_ldap_authentication(
    server="anzo.example.com",
    username="testuser",
    password="testpass"
)
print(f"LDAP Auth: {ldap.is_authenticated} ({ldap.response_time_ms}ms)")
```

### Run Example Scripts:

```bash
# Comprehensive examples
python examples/monitor_all.py

# Simple health check (for cron jobs)
python examples/quick_health_check.py
```

---

## Option 2: Full Monitoring with Backend Service (Recommended)

**Best for:** Complete infrastructure visibility

**Requires:** Ability to deploy a backend service on the Anzo server

**What you can monitor:**
- ✅ **Everything from Option 1** PLUS:
- ✅ JVM memory utilization (heap, GC stats)
- ✅ CPU usage (process-level)
- ✅ Network bandwidth (real-time)
- ✅ Disk I/O (read/write stats)
- ✅ Direct Elasticsearch cluster health
- ✅ Direct LDAP group membership validation
- ✅ AnzoGraph active connections

### Deployment Steps:

**1. Deploy the Backend Service**

Copy the monitoring service to your Anzo server:

```bash
# Copy service files
scp examples/backend_service/anzo_monitoring_service.py anzo-server:/opt/anzo/monitoring/
scp examples/backend_service/requirements.txt anzo-server:/opt/anzo/monitoring/
scp examples/backend_service/anzo-monitoring.service anzo-server:/tmp/

# SSH to server and install
ssh anzo-server

# Install dependencies
cd /opt/anzo/monitoring
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Install systemd service
sudo mv /tmp/anzo-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable anzo-monitoring
sudo systemctl start anzo-monitoring

# Check status
sudo systemctl status anzo-monitoring
```

**2. Use the Backend Client**

```python
from backend_monitoring_client import BackendMonitoringClient

# Connect to your backend service
client = BackendMonitoringClient("http://anzo-server:9090")

# Check if service is available
if not client.health_check():
    print("Backend service not available")
    exit(1)

# Get ALL metrics
jvm = client.get_jvm_metrics()
print(f"JVM Heap: {jvm.heap_utilization_pct}%")

cpu = client.get_cpu_metrics()
print(f"CPU: {cpu.cpu_percent}%")

net = client.get_network_metrics()
print(f"Network RX: {net.bytes_recv / 1024 / 1024:.2f} MB")

es = client.get_elasticsearch_health()
print(f"ES Status: {es.status}, Nodes: {es.number_of_nodes}")

ldap = client.check_ldap_group("jsmith", "anzo-admins")
print(f"LDAP Group Member: {ldap.is_member}")

# Or get everything at once
client.print_summary()
```

**3. Run Backend Examples**

```bash
python examples/backend_monitoring_example.py
```

---

## 📁 File Organization

```
pyanzo_interface/
├── README.md                              # Complete API documentation
├── GETTING_STARTED.md                     # This file - start here!
├── INFRASTRUCTURE_MONITORING.md           # Detailed monitoring capabilities
├── BACKEND_SERVICE_GUIDE.md              # How to deploy backend service
│
├── Core API:
│   ├── graphmart_manager.py              # Main AGS REST API client
│   ├── monitoring_hooks.py               # Graphmart monitoring functions
│   ├── infrastructure_monitoring.py      # Infrastructure checks (REST API)
│   └── backend_monitoring_client.py      # Backend service client
│
└── examples/
    ├── monitor_all.py                    # Comprehensive monitoring example
    ├── quick_health_check.py             # Simple health check script
    ├── reload_graphmarts_sequential.py   # Sequential graphmart reload
    │
    └── backend_service/                  # Backend service deployment
        ├── anzo_monitoring_service.py    # Flask service (deploy to server)
        ├── requirements.txt              # Service dependencies
        ├── anzo-monitoring.service       # Systemd service file
        └── README.md                     # Backend deployment guide
```

---

## 🎯 Common Use Cases

### 1. Health Check Script for Cron

```python
#!/usr/bin/env python3
"""Simple health check for cron jobs."""

from pyanzo_interface import GraphmartManagerApi, check_graphmart_status, ArtifactStatus
import sys

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")

graphmarts = [
    "http://example.org/graphmart/gm1",
    "http://example.org/graphmart/gm2"
]

all_healthy = True
for gm_uri in graphmarts:
    report = check_graphmart_status(api, gm_uri)
    if report.overall_status != ArtifactStatus.HEALTHY:
        print(f"UNHEALTHY: {report.title} - {report.error_message}")
        all_healthy = False

sys.exit(0 if all_healthy else 1)
```

### 2. Monitoring Dashboard Integration

```python
"""Send metrics to monitoring dashboard."""

from pyanzo_interface import run_infrastructure_health_check, GraphmartManagerApi

api = GraphmartManagerApi(server="anzo.example.com", username="admin", password="pw")

results = run_infrastructure_health_check(
    api,
    graphmart_uris=["http://example.org/graphmart/gm1"]
)

# Send to your monitoring system
send_to_datadog({
    "graphmart.healthy": 1 if results['overall_healthy'] else 0,
    "elasticsearch.healthy": 1 if results['elasticsearch_healthy'] else 0,
    "anzograph.healthy": 1 if results['anzograph_healthy'] else 0,
    "ldap.healthy": 1 if results['ldap_healthy'] else 0
})
```

### 3. Alert on Failures

```python
"""Monitor continuously and send alerts."""

from pyanzo_interface import monitor_graphmarts, ArtifactStatus

def alert_callback(report):
    if report.overall_status == ArtifactStatus.FAILED:
        send_slack_alert(f"🚨 {report.title} FAILED: {report.error_message}")
    elif report.overall_status == ArtifactStatus.DEGRADED:
        send_slack_warning(f"⚠️ {report.title} degraded: {report.error_message}")

monitor_graphmarts(
    api,
    graphmart_uris=["http://example.org/graphmart/gm1"],
    interval=300,  # Check every 5 minutes
    callback=alert_callback
)
```

---

## 🔧 Configuration

All example scripts use these configuration variables at the top:

```python
# Server connection
SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False

# Graphmarts to monitor
GRAPHMARTS = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
]
```

Update these values for your environment before running.

---

## 🆘 Troubleshooting

### "Connection refused" or timeout errors

- Check that the Anzo server is accessible
- Verify the port (default: 8443 for HTTPS)
- Check firewall rules

### "Unauthorized" or 401 errors

- Verify username and password
- Check that the user has appropriate permissions

### "SSL Certificate verify failed"

- Set `VERIFY_SSL = False` if using self-signed certificates
- Or install proper SSL certificates and set `VERIFY_SSL = True`

### Backend service not available

- Check that the service is running: `sudo systemctl status anzo-monitoring`
- Check logs: `sudo journalctl -u anzo-monitoring -f`
- Verify the port is accessible: `curl http://localhost:9090/health`

---

## 📖 Next Steps

1. **Start with Option 1** - Try REST API monitoring with the example scripts
2. **Review capabilities** - Read [INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md) to understand what's available
3. **Deploy backend service** - If you need full metrics, follow [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md)
4. **Integrate with your tools** - Adapt the examples for your monitoring platform
5. **Review API docs** - See [README.md](README.md) for complete API reference

---

## 💡 Decision Tree

```
Do you need JVM memory, CPU, bandwidth metrics?
│
├─ NO  → Use Option 1 (REST API only)
│        ├─ Install: pip install -r requirements.txt
│        ├─ Run: python examples/monitor_all.py
│        └─ Integrate with your monitoring platform
│
└─ YES → Use Option 2 (Backend Service)
         ├─ Deploy: Follow BACKEND_SERVICE_GUIDE.md
         ├─ Test: python backend_monitoring_client.py
         └─ Integrate: Use BackendMonitoringClient in your scripts
```

---

## 📞 Support

For issues or questions:
- Review documentation in this directory
- Check example scripts in `examples/`
- Contact Altair/Cambridge Semantics support for AGS-specific questions
