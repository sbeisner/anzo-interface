# File Structure Overview

Quick reference for navigating the pyanzo_interface project.

## 📁 Directory Layout

```
pyanzo_interface/
│
├── 📘 Documentation (Start Here!)
│   ├── GETTING_STARTED.md          ⭐ START HERE - Quick start guide
│   ├── README.md                   📖 Complete API documentation
│   ├── INFRASTRUCTURE_MONITORING.md   🔍 What metrics are available
│   ├── BACKEND_SERVICE_GUIDE.md    🛠️  How to deploy backend service
│   └── FILE_STRUCTURE.md           📁 This file
│
├── 🐍 Core Python Modules
│   ├── graphmart_manager.py        # Main AGS REST API client
│   ├── monitoring_hooks.py         # Graphmart monitoring functions
│   ├── infrastructure_monitoring.py # Infrastructure checks (REST API)
│   └── backend_monitoring_client.py # Backend service client (optional)
│
├── 📝 Examples (Ready to Use!)
│   ├── examples/README.md          # Examples documentation
│   ├── examples/monitor_all.py     # Comprehensive monitoring demo
│   ├── examples/quick_health_check.py  # Simple health check for cron
│   │
│   └── examples/backend_service/   # Backend service deployment
│       ├── README.md               # Deployment guide
│       ├── anzo_monitoring_service.py  # Flask service (deploy to server)
│       ├── requirements.txt        # Service dependencies
│       └── anzo-monitoring.service # Systemd service file
│
└── 🔧 Legacy/Reference
    ├── reload_graphmarts_sequential.py  # Sequential graphmart reload
    ├── monitor_artifacts_example.py     # (superseded by examples/monitor_all.py)
    ├── infrastructure_monitor_example.py # (superseded by examples/monitor_all.py)
    └── quick_monitor.py                 # (superseded by examples/quick_health_check.py)
```

## 🗺️ Navigation Guide

### "I want to get started quickly"
→ **[GETTING_STARTED.md](GETTING_STARTED.md)**

### "I want to run monitoring now"
→ **[examples/monitor_all.py](examples/monitor_all.py)**
→ **[examples/quick_health_check.py](examples/quick_health_check.py)**

### "I need complete API documentation"
→ **[README.md](README.md)**

### "What monitoring capabilities are available?"
→ **[INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md)**

### "I need JVM memory, CPU, bandwidth metrics"
→ **[BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md)**
→ **[examples/backend_service/README.md](examples/backend_service/README.md)**

### "How do I deploy the backend service?"
→ **[examples/backend_service/README.md](examples/backend_service/README.md)**

## 📚 Documentation by Topic

### Getting Started
| Document | Purpose |
|----------|---------|
| [GETTING_STARTED.md](GETTING_STARTED.md) | Quick start, decision tree, basic examples |
| [examples/README.md](examples/README.md) | Example scripts documentation |
| [README.md](README.md) | Complete API reference and usage guide |

### Monitoring Capabilities
| Document | Purpose |
|----------|---------|
| [INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md) | Detailed breakdown of what IS and IS NOT available |
| [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md) | Full backend service implementation options |
| [examples/backend_service/README.md](examples/backend_service/README.md) | Backend deployment instructions |

### Implementation Details
| File | Purpose |
|------|---------|
| [graphmart_manager.py](graphmart_manager.py) | Core AGS REST API client class |
| [monitoring_hooks.py](monitoring_hooks.py) | Graphmart monitoring functions |
| [infrastructure_monitoring.py](infrastructure_monitoring.py) | Infrastructure health checks |
| [backend_monitoring_client.py](backend_monitoring_client.py) | Backend service client class |

## 🎯 Quick Reference by Use Case

### Use Case 1: "I just want to monitor my graphmarts"

```
1. Read: GETTING_STARTED.md → "Option 1: REST API Monitoring Only"
2. Edit: examples/monitor_all.py → Update configuration
3. Run: python examples/monitor_all.py
```

### Use Case 2: "I need a simple health check for cron"

```
1. Edit: examples/quick_health_check.py → Update configuration
2. Run: python examples/quick_health_check.py
3. Add to cron: */5 * * * * /path/to/quick_health_check.py
```

### Use Case 3: "I need full infrastructure metrics"

```
1. Read: BACKEND_SERVICE_GUIDE.md → Understand options
2. Deploy: Follow examples/backend_service/README.md
3. Use: backend_monitoring_client.py in your scripts
```

### Use Case 4: "I'm building a monitoring dashboard"

```
1. For REST API metrics: Use monitoring_hooks.py + infrastructure_monitoring.py
2. For full metrics: Deploy backend service + use backend_monitoring_client.py
3. Reference: examples/README.md → "Common Integration Patterns"
```

### Use Case 5: "I need to reload graphmarts sequentially"

```
1. Reference: reload_graphmarts_sequential.py
2. Or use: graphmart_manager.py → reload_and_wait() method
3. Documentation: README.md → "API Reference"
```

## 🔄 Migration from Old Examples

If you were using the old example scripts, here's the mapping:

| Old File | New File | Notes |
|----------|----------|-------|
| `monitor_artifacts_example.py` | `examples/monitor_all.py` | Cleaner, better organized |
| `infrastructure_monitor_example.py` | `examples/monitor_all.py` | Consolidated into one |
| `quick_monitor.py` | `examples/quick_health_check.py` | Simplified, cron-friendly |

The old files still work but the new ones are recommended for new deployments.

## 📦 Python Module Organization

```python
# Core API
from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException

# Graphmart monitoring
from monitoring_hooks import (
    check_graphmart_status,
    check_graphmart_health,
    get_layer_status,
    monitor_graphmarts,
    ArtifactStatus
)

# Infrastructure monitoring (REST API)
from infrastructure_monitoring import (
    check_elasticsearch_connectivity,
    check_anzograph_connectivity,
    check_ldap_authentication,
    run_infrastructure_health_check
)

# Backend service client (optional - requires backend deployment)
from backend_monitoring_client import BackendMonitoringClient
```

## 🎓 Learning Path

### Beginner Path
1. **[GETTING_STARTED.md](GETTING_STARTED.md)** - Understand basics
2. **[examples/quick_health_check.py](examples/quick_health_check.py)** - Run simple check
3. **[examples/monitor_all.py](examples/monitor_all.py)** - See all capabilities
4. **[README.md](README.md)** - Learn complete API

### Advanced Path
1. **[INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md)** - Understand limitations
2. **[BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md)** - Review backend options
3. **[examples/backend_service/README.md](examples/backend_service/README.md)** - Deploy backend
4. **[backend_monitoring_client.py](backend_monitoring_client.py)** - Use full metrics

## 🔍 Finding Specific Information

| Looking for... | Check... |
|----------------|----------|
| How to check graphmart status | [README.md](README.md) → "Status & Monitoring" |
| How to reload graphmarts | [README.md](README.md) → "Graphmart Lifecycle Operations" |
| Available monitoring functions | [monitoring_hooks.py](monitoring_hooks.py) → docstrings |
| Infrastructure capabilities | [INFRASTRUCTURE_MONITORING.md](INFRASTRUCTURE_MONITORING.md) → Summary Table |
| Backend service endpoints | [BACKEND_SERVICE_GUIDE.md](BACKEND_SERVICE_GUIDE.md) → "What You Get" |
| Deployment instructions | [examples/backend_service/README.md](examples/backend_service/README.md) |
| Example integrations | [examples/README.md](examples/README.md) → "Common Integration Patterns" |
| Troubleshooting | Each README has a "Troubleshooting" section |

## 💡 Pro Tips

1. **Always start with [GETTING_STARTED.md](GETTING_STARTED.md)** - It has a decision tree
2. **Example scripts are production-ready** - Just update configuration
3. **Backend service is optional** - Only deploy if you need full metrics
4. **Old examples still work** - But new ones are cleaner
5. **All scripts have configuration at top** - Easy to customize

## 📞 Need Help?

1. Check [GETTING_STARTED.md](GETTING_STARTED.md) → Troubleshooting section
2. Check relevant README → Troubleshooting section
3. Review example scripts for patterns
4. Contact Altair/Cambridge Semantics support for AGS-specific questions
