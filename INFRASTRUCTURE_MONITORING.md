# Infrastructure Monitoring Capabilities

## Overview

This document outlines the infrastructure monitoring capabilities for Altair Graph Studio (AGS/Anzo), detailing what **IS** available through the REST API and what **IS NOT** available (requiring external monitoring tools).

## Requested Monitoring Capabilities

### 1. ✓ Elasticsearch Connectivity - **AVAILABLE** (Indirect)

**Implementation:** `check_elasticsearch_connectivity()`

**How it works:**
- Elasticsearch connectivity is not exposed as a dedicated REST API endpoint
- **However**, Elasticsearch issues manifest as layer/step failures in graphmarts
- Our implementation analyzes the detailed graphmart status to identify ES-related errors
- Searches for keywords: 'elasticsearch', 'elastic', 'es index', 'indexing service', etc.

**Usage:**
```python
from pyanzo_interface import check_elasticsearch_connectivity

es_report = check_elasticsearch_connectivity(api, graphmart_uri)
if not es_report.is_healthy:
    print(f"ES Issues: {es_report.failed_es_layers} failed layers")
    for error in es_report.error_messages:
        print(f"  - {error}")
```

**Limitations:**
- This is an **indirect** check - we infer ES health from layer failures
- Only detects ES issues that cause layer/step failures
- Cannot check ES cluster health directly
- Cannot monitor ES performance metrics

**Recommendation for direct monitoring:**
Use Elasticsearch's native APIs:
```bash
# Direct ES health check (not through AGS)
curl -X GET "http://elasticsearch:9200/_cluster/health"
```

---

### 2. ✓ AnzoGraph Connectivity - **AVAILABLE** (Direct)

**Implementation:** `check_anzograph_connectivity()`

**How it works:**
- Checks graphmart activation status
- Verifies AZG server URI is configured
- Validates graphmart is Online

**Usage:**
```python
from pyanzo_interface import check_anzograph_connectivity

azg_report = check_anzograph_connectivity(api, graphmart_uri)
print(f"Connected: {azg_report.is_connected}")
print(f"AZG Server: {azg_report.azg_uri}")
print(f"Status: {azg_report.graphmart_status}")
```

**What it checks:**
- ✓ Is graphmart connected to an AZG server?
- ✓ What is the AZG server URI?
- ✓ Is the graphmart Online?

**What it CANNOT check:**
- ✗ AnzoGraph query performance
- ✗ AnzoGraph resource utilization
- ✗ AnzoGraph cluster health (if clustered)

---

### 3. ✗ AnzoGraph Bandwidth - **NOT AVAILABLE via REST API**

**Status:** Not exposed through AGS REST API

**Why not available:**
- The AGS REST API is designed for data management operations (graphmarts, layers, steps)
- Infrastructure metrics like bandwidth are not exposed via REST endpoints
- AnzoGraph performance metrics require direct access to AnzoGraph or system-level monitoring

**Recommended alternatives:**

#### Option 1: Network Monitoring Tools
```bash
# Monitor network interface on AnzoGraph host
sudo iftop -i eth0  # View bandwidth usage in real-time
sudo nethogs       # Monitor per-process bandwidth
vnstat             # Track network statistics
```

#### Option 2: Prometheus + Grafana
```yaml
# Use Prometheus node_exporter for network metrics
node_exporter:
  collectors:
    - netdev  # Network device statistics
    - netstat # Network statistics
```

#### Option 3: Cloud Provider Metrics
- **AWS CloudWatch:** Monitor EC2 instance network metrics
- **Azure Monitor:** Track VM network throughput
- **GCP Monitoring:** View network interface metrics

#### Option 4: SNMP Monitoring
Monitor network switch ports where AnzoGraph server is connected:
```bash
# Query switch for interface statistics
snmpwalk -v2c -c public switch-ip ifInOctets
snmpwalk -v2c -c public switch-ip ifOutOctets
```

#### Option 5: Query-Level Performance
Analyze AnzoGraph query logs for slow queries:
```bash
# Enable query logging in AnzoGraph configuration
# Parse logs to track query execution times
grep "Query time:" /var/log/anzograph/query.log | awk '{sum+=$3; count++} END {print sum/count}'
```

---

### 4. ✗ Memory Utilization - **NOT AVAILABLE via REST API**

**Status:** Not exposed through AGS REST API (requires JMX)

**Why not available:**
- JVM memory metrics are available via JMX (Java Management Extensions)
- REST API does not expose JVM statistics
- Memory monitoring requires JMX connection or external APM tools

**Recommended alternatives:**

#### Option 1: JMX Monitoring
Enable JMX on Anzo server and use monitoring tools:

```bash
# Start Anzo with JMX enabled
JAVA_OPTS="-Dcom.sun.management.jmxremote \
           -Dcom.sun.management.jmxremote.port=1099 \
           -Dcom.sun.management.jmxremote.ssl=false \
           -Dcom.sun.management.jmxremote.authenticate=false"
```

**Tools:**
- **JConsole:** `jconsole <hostname>:1099`
- **VisualVM:** Connect to JMX port for heap analysis
- **Java Mission Control:** Advanced profiling and monitoring

#### Option 2: Prometheus JMX Exporter
```yaml
# jmx_exporter_config.yaml
rules:
  - pattern: "java.lang<type=Memory><HeapMemoryUsage>(.*):(.*)"
    name: jvm_memory_heap_$1
    value: $2
  - pattern: "java.lang<type=Memory><NonHeapMemoryUsage>(.*):(.*)"
    name: jvm_memory_nonheap_$1
    value: $2
```

Start JMX exporter as Java agent:
```bash
java -javaagent:jmx_prometheus_javaagent.jar=8080:config.yaml -jar anzo.jar
```

#### Option 3: APM Tools
- **Datadog:** Install agent on Anzo server
- **New Relic:** Java APM agent
- **AppDynamics:** Java agent for JVM monitoring

#### Option 4: Manual JMX Query
```python
# Using jmxquery library (not part of REST API)
from jmxquery import JMXConnection, JMXQuery

jmx = JMXConnection("service:jmx:rmi:///jndi/rmi://anzo-host:1099/jmxrmi")
heap_query = JMXQuery("java.lang:type=Memory/HeapMemoryUsage")
result = jmx.query([heap_query])
print(f"Heap used: {result[0].value['used']} bytes")
```

**Key MBeans to monitor:**
- `java.lang:type=Memory` - Heap and non-heap memory usage
- `java.lang:type=GarbageCollector,name=*` - GC statistics
- `java.lang:type=Threading` - Thread counts
- `java.lang:type=OperatingSystem` - System CPU load

---

### 5. ✓ LDAP Group Revalidation - **AVAILABLE** (Indirect)

**Implementation:** `check_ldap_authentication()`

**How it works:**
- No dedicated LDAP status endpoint exists
- Tests LDAP by attempting authentication via the API
- Measures authentication response time as a health indicator
- Authentication failures indicate LDAP issues

**Usage:**
```python
from pyanzo_interface import check_ldap_authentication

ldap_report = check_ldap_authentication(
    server="anzo.example.com",
    username="testuser",
    password="testpass"
)

print(f"Authenticated: {ldap_report.is_authenticated}")
print(f"Response Time: {ldap_report.response_time_ms}ms")

if not ldap_report.is_authenticated:
    print(f"Error: {ldap_report.error_message}")
```

**What it checks:**
- ✓ Can user authenticate successfully?
- ✓ Authentication response time (latency)
- ✓ Connection to LDAP server (indirect)

**What it CANNOT check:**
- ✗ LDAP server health directly
- ✗ Group membership changes
- ✗ LDAP replication status
- ✗ Specific group validation without actual group operations

**Recommendation for direct LDAP monitoring:**
```python
# Use python-ldap library for direct LDAP queries (not through AGS)
import ldap

conn = ldap.initialize('ldap://ldap-server:389')
conn.simple_bind_s('cn=admin,dc=example,dc=com', 'password')

# Check user's group memberships
result = conn.search_s(
    'ou=users,dc=example,dc=com',
    ldap.SCOPE_SUBTREE,
    '(uid=testuser)',
    ['memberOf']
)
print(f"User groups: {result[0][1]['memberOf']}")
```

**LDAP monitoring best practices:**
1. Monitor LDAP server directly (not through AGS)
2. Use LDAP monitoring tools: Nagios, Zabbix, Datadog LDAP checks
3. Monitor LDAP query response times
4. Set up alerts for LDAP server downtime
5. Track failed authentication attempts in LDAP logs

---

## Summary Table

| Requested Feature | Available? | Method | Notes |
|-------------------|-----------|--------|-------|
| **Elasticsearch Connectivity** | ✓ Indirect | `check_elasticsearch_connectivity()` | Inferred from layer failures |
| **AnzoGraph Bandwidth** | ✗ No | External tools required | Use network monitoring, SNMP, or logs |
| **Memory Utilization** | ✗ No | JMX required | Use JMX monitoring tools |
| **AnzoGraph Connectivity** | ✓ Direct | `check_anzograph_connectivity()` | Via graphmart activation status |
| **LDAP Authentication** | ✓ Indirect | `check_ldap_authentication()` | Via auth test calls |

## Comprehensive Health Check

For a complete infrastructure health check using available capabilities:

```python
from pyanzo_interface import run_infrastructure_health_check, GraphmartManagerApi

api = GraphmartManagerApi(
    server="anzo.example.com",
    username="admin",
    password="password"
)

results = run_infrastructure_health_check(
    api,
    graphmart_uris=[
        "http://example.org/graphmart/gm1",
        "http://example.org/graphmart/gm2"
    ],
    check_ldap=True
)

print(f"Overall Healthy: {results['overall_healthy']}")
print(f"Elasticsearch: {results['elasticsearch_healthy']}")
print(f"AnzoGraph: {results['anzograph_healthy']}")
print(f"LDAP: {results['ldap_healthy']}")

# Access detailed results
for es_detail in results['elasticsearch_details']:
    if not es_detail['is_healthy']:
        print(f"ES issue in {es_detail['graphmart_uri']}")

for azg_detail in results['anzograph_details']:
    if not azg_detail['is_connected']:
        print(f"AZG issue: {azg_detail['error']}")
```

## Recommended Monitoring Stack

For complete infrastructure monitoring of AGS/Anzo:

### What to Monitor via AGS REST API ✓
1. **Graphmart health** - Use `monitoring_hooks.py`
2. **Layer/Step status** - Use `check_graphmart_health()`
3. **ES connectivity** - Use `check_elasticsearch_connectivity()` (indirect)
4. **AZG connectivity** - Use `check_anzograph_connectivity()`
5. **LDAP auth** - Use `check_ldap_authentication()` (indirect)

### What to Monitor Externally ✗
1. **JVM Memory** → JMX + Prometheus JMX Exporter
2. **CPU/Disk/Network** → Prometheus node_exporter
3. **AnzoGraph Performance** → Query logs + SPARQL timing
4. **Bandwidth** → Network monitoring (iftop, SNMP)
5. **Elasticsearch Health** → Direct ES monitoring
6. **LDAP Health** → Direct LDAP monitoring

### Recommended Architecture
```
┌─────────────────────────────────────────────────────────┐
│                    Grafana Dashboard                      │
└─────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Prometheus  │  │     ELK      │  │   Datadog    │
└──────────────┘  └──────────────┘  └──────────────┘
        │                  │                  │
   ┌────┴────┬────────────┴─────────┬────────┴────┐
   ▼         ▼         ▼            ▼             ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────────────┐ ┌──────┐
│ JMX  │ │ Node │ │ AGS  │ │ Elasticsearch│ │ LDAP │
│Export│ │Export│ │ API  │ │    Direct    │ │Direct│
└──────┘ └──────┘ └──────┘ └──────────────┘ └──────┘
   │         │         │            │             │
   └─────────┴─────────┴────────────┴─────────────┘
                       │
              ┌────────┴────────┐
              │  Anzo/AGS Stack │
              └─────────────────┘
```

## Example Scripts

1. **[infrastructure_monitor_example.py](infrastructure_monitor_example.py)** - Demonstrates all available capabilities
2. **[quick_monitor.py](quick_monitor.py)** - Simple health check script for cron/CI
3. **[monitor_artifacts_example.py](monitor_artifacts_example.py)** - Graphmart-focused monitoring

## Getting Help

For infrastructure metrics not available via REST API, contact:
- **Altair/Cambridge Semantics Support** - Request documentation for:
  - JMX monitoring setup
  - AnzoGraph performance metrics
  - System-level monitoring best practices
  - Integration with enterprise monitoring tools

## References

- [AGS REST API Documentation](https://docs.cambridgesemantics.com/anzo/v2025.0/userdoc/api.htm)
- [Prometheus JMX Exporter](https://github.com/prometheus/jmx_exporter)
- [Grafana Dashboard Examples](https://grafana.com/grafana/dashboards/)
