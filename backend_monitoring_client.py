"""
Backend Monitoring Client

This module provides a client for a custom backend monitoring service
that exposes infrastructure metrics not available via the AGS REST API.

If you deploy the backend monitoring service (see BACKEND_SERVICE_GUIDE.md),
this client allows you to access:
- JVM memory utilization (direct JMX access)
- CPU usage (process-level)
- Network bandwidth (interface statistics)
- Direct Elasticsearch cluster health
- AnzoGraph connection metrics
- LDAP group membership validation
- Disk I/O statistics

Usage:
    from backend_monitoring_client import BackendMonitoringClient

    client = BackendMonitoringClient("http://localhost:9090")
    metrics = client.get_all_metrics()
    print(f"JVM Heap: {metrics.jvm_heap_utilization_pct}%")
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class JVMMetrics:
    """JVM memory and garbage collection metrics."""
    heap_used_kb: float
    heap_capacity_kb: float
    heap_utilization_pct: float
    metaspace_used_kb: float
    metaspace_capacity_kb: float
    young_gc_count: int
    young_gc_time: float
    full_gc_count: int
    full_gc_time: float
    timestamp: datetime


@dataclass
class CPUMetrics:
    """CPU and process-level metrics."""
    cpu_percent: float
    memory_mb: float
    num_threads: int
    num_fds: Optional[int]
    timestamp: datetime


@dataclass
class NetworkMetrics:
    """Network interface statistics."""
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int
    timestamp: datetime


@dataclass
class DiskMetrics:
    """Disk I/O statistics."""
    read_bytes: int
    write_bytes: int
    read_count: int
    write_count: int
    read_time_ms: int
    write_time_ms: int
    timestamp: datetime


@dataclass
class ElasticsearchMetrics:
    """Direct Elasticsearch cluster health metrics."""
    cluster_name: str
    status: str  # green, yellow, red
    number_of_nodes: int
    number_of_data_nodes: int
    active_primary_shards: int
    active_shards: int
    relocating_shards: int
    initializing_shards: int
    unassigned_shards: int
    node_stats: dict
    timestamp: datetime


@dataclass
class AnzoGraphMetrics:
    """AnzoGraph connection metrics."""
    port: int
    total_connections: int
    established_connections: int
    time_wait_connections: int
    timestamp: datetime


@dataclass
class LDAPGroupCheck:
    """LDAP group membership validation result."""
    username: str
    group: str
    is_member: bool
    all_groups: list[str]
    timestamp: datetime


class BackendMonitoringClient:
    """
    Client for custom backend monitoring service.

    This client connects to a backend service deployed on the Anzo server
    that exposes infrastructure metrics not available via AGS REST API.

    Args:
        backend_url: Base URL of the backend monitoring service (e.g., http://localhost:9090)
        api_key: Optional API key for authentication
        timeout: Request timeout in seconds (default: 5)

    Example:
        >>> client = BackendMonitoringClient("http://anzo-server:9090")
        >>> jvm = client.get_jvm_metrics()
        >>> print(f"Heap usage: {jvm.heap_utilization_pct}%")
    """

    def __init__(
        self,
        backend_url: str = "http://localhost:9090",
        api_key: Optional[str] = None,
        timeout: int = 5
    ):
        self.backend_url = backend_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({'X-API-Key': api_key})

    def _get(self, endpoint: str) -> dict:
        """Make GET request to backend service."""
        try:
            response = self.session.get(
                f'{self.backend_url}{endpoint}',
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Backend request failed: {e}")
            raise

    def _post(self, endpoint: str, data: dict) -> dict:
        """Make POST request to backend service."""
        try:
            response = self.session.post(
                f'{self.backend_url}{endpoint}',
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Backend request failed: {e}")
            raise

    def health_check(self) -> bool:
        """
        Check if backend monitoring service is available.

        Returns:
            True if service is healthy, False otherwise.

        Example:
            >>> if client.health_check():
            >>>     print("Backend service is available")
        """
        try:
            data = self._get('/health')
            return data.get('status') == 'healthy'
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_jvm_metrics(self) -> JVMMetrics:
        """
        Get JVM memory and garbage collection metrics.

        Returns:
            JVMMetrics with heap usage, GC statistics, etc.

        Example:
            >>> jvm = client.get_jvm_metrics()
            >>> print(f"Heap: {jvm.heap_used_kb} / {jvm.heap_capacity_kb} KB")
            >>> print(f"Utilization: {jvm.heap_utilization_pct}%")
            >>> print(f"Full GCs: {jvm.full_gc_count} ({jvm.full_gc_time}s)")
        """
        data = self._get('/metrics/jvm')
        return JVMMetrics(
            heap_used_kb=data['heap_used_kb'],
            heap_capacity_kb=data['heap_capacity_kb'],
            heap_utilization_pct=data['heap_utilization_pct'],
            metaspace_used_kb=data.get('metaspace_used_kb', 0),
            metaspace_capacity_kb=data.get('metaspace_capacity_kb', 0),
            young_gc_count=data.get('young_gc_count', 0),
            young_gc_time=data.get('young_gc_time', 0),
            full_gc_count=data.get('full_gc_count', 0),
            full_gc_time=data.get('full_gc_time', 0),
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_cpu_metrics(self) -> CPUMetrics:
        """
        Get CPU and process-level metrics.

        Returns:
            CPUMetrics with CPU usage, memory, threads, file descriptors.

        Example:
            >>> cpu = client.get_cpu_metrics()
            >>> print(f"CPU: {cpu.cpu_percent}%")
            >>> print(f"Memory: {cpu.memory_mb} MB")
            >>> print(f"Threads: {cpu.num_threads}")
        """
        data = self._get('/metrics/cpu')
        return CPUMetrics(
            cpu_percent=data['cpu_percent'],
            memory_mb=data['memory_mb'],
            num_threads=data['num_threads'],
            num_fds=data.get('num_fds'),
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_network_metrics(self) -> NetworkMetrics:
        """
        Get network interface statistics.

        Returns:
            NetworkMetrics with bytes/packets sent/received, errors, drops.

        Example:
            >>> net = client.get_network_metrics()
            >>> print(f"RX: {net.bytes_recv / 1024 / 1024} MB")
            >>> print(f"TX: {net.bytes_sent / 1024 / 1024} MB")
            >>> print(f"Errors: {net.errin + net.errout}")
        """
        data = self._get('/metrics/network')
        return NetworkMetrics(
            bytes_sent=data['bytes_sent'],
            bytes_recv=data['bytes_recv'],
            packets_sent=data['packets_sent'],
            packets_recv=data['packets_recv'],
            errin=data['errin'],
            errout=data['errout'],
            dropin=data['dropin'],
            dropout=data['dropout'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_disk_metrics(self) -> DiskMetrics:
        """
        Get disk I/O statistics.

        Returns:
            DiskMetrics with read/write bytes, counts, and times.

        Example:
            >>> disk = client.get_disk_metrics()
            >>> print(f"Read: {disk.read_bytes / 1024 / 1024} MB")
            >>> print(f"Write: {disk.write_bytes / 1024 / 1024} MB")
            >>> print(f"Read ops: {disk.read_count}")
        """
        data = self._get('/metrics/disk')
        return DiskMetrics(
            read_bytes=data['read_bytes'],
            write_bytes=data['write_bytes'],
            read_count=data['read_count'],
            write_count=data['write_count'],
            read_time_ms=data['read_time_ms'],
            write_time_ms=data['write_time_ms'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_elasticsearch_health(self) -> ElasticsearchMetrics:
        """
        Get direct Elasticsearch cluster health.

        This provides direct ES cluster health without needing to infer
        from graphmart layer failures.

        Returns:
            ElasticsearchMetrics with cluster status, shard counts, etc.

        Example:
            >>> es = client.get_elasticsearch_health()
            >>> print(f"Cluster: {es.cluster_name}")
            >>> print(f"Status: {es.status}")
            >>> print(f"Nodes: {es.number_of_nodes}")
            >>> print(f"Unassigned shards: {es.unassigned_shards}")
        """
        data = self._get('/metrics/elasticsearch')
        return ElasticsearchMetrics(
            cluster_name=data['cluster_name'],
            status=data['status'],
            number_of_nodes=data['number_of_nodes'],
            number_of_data_nodes=data['number_of_data_nodes'],
            active_primary_shards=data['active_primary_shards'],
            active_shards=data['active_shards'],
            relocating_shards=data['relocating_shards'],
            initializing_shards=data['initializing_shards'],
            unassigned_shards=data['unassigned_shards'],
            node_stats=data.get('node_stats', {}),
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_anzograph_metrics(self) -> AnzoGraphMetrics:
        """
        Get AnzoGraph connection metrics.

        Returns:
            AnzoGraphMetrics with connection counts by state.

        Example:
            >>> azg = client.get_anzograph_metrics()
            >>> print(f"Active connections: {azg.established_connections}")
            >>> print(f"Total connections: {azg.total_connections}")
        """
        data = self._get('/metrics/anzograph')
        return AnzoGraphMetrics(
            port=data['port'],
            total_connections=data['total_connections'],
            established_connections=data['established_connections'],
            time_wait_connections=data['time_wait_connections'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def check_ldap_group(self, username: str, group: str) -> LDAPGroupCheck:
        """
        Check if a user is a member of an LDAP group.

        This performs direct LDAP queries to validate group membership,
        unlike the indirect auth test in infrastructure_monitoring.py.

        Args:
            username: Username to check
            group: Group name to check membership in

        Returns:
            LDAPGroupCheck with membership status and all user groups.

        Example:
            >>> result = client.check_ldap_group("jsmith", "anzo-admins")
            >>> if result.is_member:
            >>>     print(f"{result.username} is in {result.group}")
            >>> print(f"All groups: {result.all_groups}")
        """
        data = self._post('/metrics/ldap', {'username': username, 'group': group})
        return LDAPGroupCheck(
            username=data['username'],
            group=data['group'],
            is_member=data['is_member'],
            all_groups=data['all_groups'],
            timestamp=datetime.fromisoformat(data['timestamp'])
        )

    def get_all_metrics(self) -> dict:
        """
        Get all metrics in a single call.

        This is more efficient than calling each metric endpoint individually.

        Returns:
            Dictionary with all metrics organized by category.

        Example:
            >>> all_metrics = client.get_all_metrics()
            >>> print(f"JVM Heap: {all_metrics['jvm']['heap_utilization_pct']}%")
            >>> print(f"CPU: {all_metrics['cpu']['cpu_percent']}%")
            >>> print(f"ES Status: {all_metrics['elasticsearch']['status']}")
        """
        return self._get('/metrics/all')

    def print_summary(self) -> None:
        """
        Print a human-readable summary of all metrics.

        Example:
            >>> client.print_summary()
            === Infrastructure Metrics Summary ===
            JVM Heap: 2048.0 / 4096.0 KB (50.0%)
            CPU: 45.2%
            ...
        """
        try:
            print("\n" + "=" * 70)
            print("INFRASTRUCTURE METRICS SUMMARY")
            print("=" * 70)

            # JVM
            jvm = self.get_jvm_metrics()
            print(f"\n📊 JVM Memory:")
            print(f"  Heap: {jvm.heap_used_kb:.0f} / {jvm.heap_capacity_kb:.0f} KB ({jvm.heap_utilization_pct:.1f}%)")
            print(f"  Metaspace: {jvm.metaspace_used_kb:.0f} / {jvm.metaspace_capacity_kb:.0f} KB")
            print(f"  Young GC: {jvm.young_gc_count} ({jvm.young_gc_time:.2f}s)")
            print(f"  Full GC: {jvm.full_gc_count} ({jvm.full_gc_time:.2f}s)")

            # CPU
            cpu = self.get_cpu_metrics()
            print(f"\n💻 CPU & Process:")
            print(f"  CPU: {cpu.cpu_percent:.1f}%")
            print(f"  Memory: {cpu.memory_mb:.1f} MB")
            print(f"  Threads: {cpu.num_threads}")

            # Network
            net = self.get_network_metrics()
            print(f"\n🌐 Network:")
            print(f"  RX: {net.bytes_recv / 1024 / 1024:.2f} MB")
            print(f"  TX: {net.bytes_sent / 1024 / 1024:.2f} MB")
            print(f"  Errors: {net.errin + net.errout}")

            # Disk
            disk = self.get_disk_metrics()
            print(f"\n💾 Disk I/O:")
            print(f"  Read: {disk.read_bytes / 1024 / 1024:.2f} MB ({disk.read_count} ops)")
            print(f"  Write: {disk.write_bytes / 1024 / 1024:.2f} MB ({disk.write_count} ops)")

            # Elasticsearch
            es = self.get_elasticsearch_health()
            status_icon = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(es.status, "?")
            print(f"\n🔍 Elasticsearch:")
            print(f"  Status: {status_icon} {es.status}")
            print(f"  Cluster: {es.cluster_name}")
            print(f"  Nodes: {es.number_of_nodes}")
            print(f"  Unassigned shards: {es.unassigned_shards}")

            # AnzoGraph
            azg = self.get_anzograph_metrics()
            print(f"\n📈 AnzoGraph (port {azg.port}):")
            print(f"  Established connections: {azg.established_connections}")
            print(f"  Total connections: {azg.total_connections}")

            print("\n" + "=" * 70 + "\n")

        except Exception as e:
            print(f"Error getting metrics: {e}")


# Example usage
if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    # Initialize client
    backend_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9090"
    client = BackendMonitoringClient(backend_url)

    # Check if service is available
    if not client.health_check():
        print("❌ Backend monitoring service is not available")
        print(f"   Make sure it's running at {backend_url}")
        print("   See BACKEND_SERVICE_GUIDE.md for deployment instructions")
        sys.exit(1)

    print(f"✓ Connected to backend monitoring service at {backend_url}")

    # Print summary
    client.print_summary()
