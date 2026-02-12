# Backend Monitoring Service Deployment

This directory contains everything needed to deploy a custom backend monitoring service on your Anzo server to access ALL infrastructure metrics.

## 📦 What's Included

| File | Purpose |
|------|---------|
| `anzo_monitoring_service.py` | Flask service that exposes infrastructure metrics |
| `requirements.txt` | Python dependencies for the service |
| `anzo-monitoring.service` | Systemd service file for automatic startup |
| `deploy.sh` | Automated deployment script |

## 🎯 What You Get

Once deployed, you'll have access to metrics NOT available via AGS REST API:

| Metric | Endpoint | Description |
|--------|----------|-------------|
| **JVM Memory** | `/metrics/jvm` | Heap usage, GC stats, metaspace |
| **CPU Usage** | `/metrics/cpu` | Process CPU%, memory, threads |
| **Network Bandwidth** | `/metrics/network` | Bytes sent/received, errors, drops |
| **Disk I/O** | `/metrics/disk` | Read/write bytes, operations, timing |
| **Elasticsearch Health** | `/metrics/elasticsearch` | Direct cluster status, shard counts |
| **AnzoGraph Connections** | `/metrics/anzograph` | Active connections by state |
| **LDAP Groups** | `/metrics/ldap` (POST) | Direct group membership validation |
| **All Metrics** | `/metrics/all` | Everything in one call |

## 🚀 Quick Deployment

### Option 1: Automated Deployment (Recommended)

```bash
# Make deploy script executable
chmod +x deploy.sh

# Deploy to your Anzo server
./deploy.sh your-anzo-server.example.com

# The script will:
# 1. Copy files to the server
# 2. Create virtual environment
# 3. Install dependencies
# 4. Install systemd service
# 5. Start the service
```

### Option 2: Manual Deployment

**1. Copy files to server:**
```bash
# Create directory on server
ssh anzo-server
sudo mkdir -p /opt/anzo/monitoring
sudo chown $(whoami):$(whoami) /opt/anzo/monitoring

# Copy files from your local machine
scp anzo_monitoring_service.py anzo-server:/opt/anzo/monitoring/
scp requirements.txt anzo-server:/opt/anzo/monitoring/
scp anzo-monitoring.service anzo-server:/tmp/
```

**2. Install dependencies:**
```bash
ssh anzo-server

cd /opt/anzo/monitoring

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**3. Configure environment:**
```bash
# Edit environment variables in the service file if needed
sudo vi /tmp/anzo-monitoring.service

# Update these if your setup differs:
# Environment="ES_HOST=localhost:9200"
# Environment="AZG_PORT=5600"
# Environment="LDAP_SERVER=ldap://localhost:389"
```

**4. Install and start service:**
```bash
# Install systemd service
sudo mv /tmp/anzo-monitoring.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable anzo-monitoring
sudo systemctl start anzo-monitoring

# Check status
sudo systemctl status anzo-monitoring
```

**5. Verify it's working:**
```bash
# Test health endpoint
curl http://localhost:9090/health

# Should return: {"status": "healthy", "timestamp": "..."}

# Test JVM metrics
curl http://localhost:9090/metrics/jvm
```

## 🔧 Configuration

### Service Configuration

Edit `/etc/systemd/system/anzo-monitoring.service`:

```ini
[Service]
# Change user if needed
User=anzo

# Update environment variables
Environment="ES_HOST=your-elasticsearch:9200"
Environment="AZG_PORT=5600"
Environment="LDAP_SERVER=ldap://your-ldap-server:389"
Environment="LDAP_BASE_DN=dc=your-domain,dc=com"
Environment="API_KEY=your-secret-key"  # Optional: for authentication
```

After changes:
```bash
sudo systemctl daemon-reload
sudo systemctl restart anzo-monitoring
```

### Security (Recommended)

Add API key authentication by setting the `API_KEY` environment variable:

```bash
# Generate a random API key
API_KEY=$(openssl rand -base64 32)

# Add to service file
sudo systemctl edit anzo-monitoring

# Add:
[Service]
Environment="API_KEY=your-generated-key"

# Restart
sudo systemctl restart anzo-monitoring
```

Then use it from your client:
```python
from backend_monitoring_client import BackendMonitoringClient

client = BackendMonitoringClient(
    "http://anzo-server:9090",
    api_key="your-generated-key"
)
```

## 📊 Using the Service

### From Python (Recommended)

```python
# Add parent directory to path
import sys
sys.path.insert(0, '/path/to/pyanzo_interface')

from backend_monitoring_client import BackendMonitoringClient

# Connect to service
client = BackendMonitoringClient("http://anzo-server:9090")

# Check if available
if not client.health_check():
    print("Service not available")
    exit(1)

# Get metrics
jvm = client.get_jvm_metrics()
print(f"Heap: {jvm.heap_utilization_pct}%")

cpu = client.get_cpu_metrics()
print(f"CPU: {cpu.cpu_percent}%")

es = client.get_elasticsearch_health()
print(f"ES: {es.status}")

# Or get everything at once
client.print_summary()
```

### From Command Line (curl)

```bash
# Health check
curl http://anzo-server:9090/health

# JVM metrics
curl http://anzo-server:9090/metrics/jvm

# All metrics
curl http://anzo-server:9090/metrics/all | jq .

# LDAP group check (POST)
curl -X POST http://anzo-server:9090/metrics/ldap \
  -H "Content-Type: application/json" \
  -d '{"username": "jsmith", "group": "anzo-admins"}'
```

## 🐳 Docker Deployment (Alternative)

If you prefer Docker:

```bash
# Build image
docker build -t anzo-monitoring:latest .

# Run container
docker run -d \
  --name anzo-monitoring \
  --network host \
  -e ES_HOST=localhost:9200 \
  -e AZG_PORT=5600 \
  -v /proc:/host/proc:ro \
  anzo-monitoring:latest

# Check logs
docker logs anzo-monitoring
```

## 🔍 Monitoring the Service

### Check Status
```bash
# Service status
sudo systemctl status anzo-monitoring

# View logs
sudo journalctl -u anzo-monitoring -f

# Check if listening
sudo netstat -tlnp | grep 9090
```

### Health Check Endpoint
```bash
# Should return {"status": "healthy"}
curl http://localhost:9090/health

# If not responding, check logs:
sudo journalctl -u anzo-monitoring -n 50
```

## 🆘 Troubleshooting

### Service won't start

```bash
# Check logs
sudo journalctl -u anzo-monitoring -n 50

# Common issues:
# 1. Port already in use
sudo netstat -tlnp | grep 9090

# 2. Python not found
which python3

# 3. Permissions
ls -la /opt/anzo/monitoring/

# 4. Dependencies missing
/opt/anzo/monitoring/venv/bin/pip list
```

### "Anzo process not found"

The service looks for a process with "anzo.jar" in the command line:
```bash
# Check if Anzo is running
ps aux | grep anzo.jar

# If running but not detected, update ANZO_PROCESS_NAME in the service code
```

### Cannot connect to Elasticsearch

```bash
# Check ES is accessible from Anzo server
curl http://localhost:9200/_cluster/health

# Update ES_HOST if needed
sudo systemctl edit anzo-monitoring
```

### Metrics return errors

```bash
# Enable debug logging
sudo systemctl edit anzo-monitoring

# Add:
[Service]
Environment="FLASK_DEBUG=1"

# Restart and check logs
sudo systemctl restart anzo-monitoring
sudo journalctl -u anzo-monitoring -f
```

## 🔒 Security Best Practices

1. **Run on localhost only** - Service listens on 127.0.0.1 by default
2. **Add API key** - Set API_KEY environment variable
3. **Use firewall** - Block port 9090 from external access
4. **Regular updates** - Keep dependencies updated
5. **Monitor logs** - Watch for unauthorized access attempts

```bash
# Firewall example (iptables)
sudo iptables -A INPUT -p tcp --dport 9090 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 9090 -j DROP
```

## 📝 Customization

### Add Custom Metrics

Edit `anzo_monitoring_service.py` and add new endpoints:

```python
@app.route('/metrics/custom', methods=['GET'])
def get_custom_metrics():
    """Your custom metric."""
    # Your implementation
    return jsonify({
        'custom_metric': value,
        'timestamp': datetime.now().isoformat()
    })
```

### Change Port

Edit service file:
```bash
sudo systemctl edit anzo-monitoring

# Add:
[Service]
Environment="PORT=8080"
```

## 📚 Additional Resources

- Parent directory: [BACKEND_SERVICE_GUIDE.md](../../BACKEND_SERVICE_GUIDE.md) - Detailed implementation guide
- [GETTING_STARTED.md](../../GETTING_STARTED.md) - Quick start
- [backend_monitoring_client.py](../../backend_monitoring_client.py) - Python client

## ✅ Deployment Checklist

- [ ] Files copied to server (`/opt/anzo/monitoring/`)
- [ ] Virtual environment created
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Environment variables configured
- [ ] Systemd service installed
- [ ] Service started (`systemctl start anzo-monitoring`)
- [ ] Health check passes (`curl http://localhost:9090/health`)
- [ ] Metrics accessible (`curl http://localhost:9090/metrics/all`)
- [ ] Client can connect (test with `backend_monitoring_client.py`)
- [ ] Firewall configured (if needed)
- [ ] Monitoring/alerting set up
