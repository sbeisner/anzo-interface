"""
Elasticsearch Connectivity Monitoring

Direct validation of an Elasticsearch cluster's health, node memory, and
index accessibility — no backend sidecar required.

Unlike the indirect check in infrastructure_monitoring.py (which infers ES
health from Anzo graphmart layer failures), this module talks directly to the
Elasticsearch HTTP API and reports detailed diagnostic information.

Elasticsearch API endpoints used
---------------------------------
  GET /_cluster/health          — Overall cluster status and shard counts.
  GET /_nodes/stats/jvm,os      — Per-node JVM heap and OS memory stats.
  GET /_cat/indices             — Per-index health and document counts.
  GET /<index>/_count           — Validate that a specific index is queryable.

All calls use the standard ES REST API; no Elasticsearch plugins or agents
are required.  Supports both authenticated and unauthenticated clusters.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ESClusterHealthReport:
    """Overall cluster health from GET /_cluster/health."""
    cluster_name: str
    status: str                  # "green", "yellow", or "red"
    is_healthy: bool             # True only for green
    number_of_nodes: int
    number_of_data_nodes: int
    active_primary_shards: int
    active_shards: int
    relocating_shards: int
    initializing_shards: int
    unassigned_shards: int
    response_time_ms: float
    timestamp: datetime


@dataclass
class ESNodeMemoryReport:
    """JVM heap and OS memory for a single Elasticsearch node."""
    node_id: str
    node_name: str
    heap_used_mb: float
    heap_max_mb: float
    heap_used_pct: float
    os_used_mb: float
    os_total_mb: float
    os_used_pct: float


@dataclass
class ESNodesReport:
    """Aggregated per-node memory report from GET /_nodes/stats/jvm,os."""
    nodes: List[ESNodeMemoryReport]
    # Convenience aggregates across all nodes
    total_heap_used_mb: float
    total_heap_max_mb: float
    avg_heap_used_pct: float
    max_heap_used_pct: float
    timestamp: datetime


@dataclass
class ESIndexReport:
    """Health and document count for a single index."""
    index: str
    health: str       # "green", "yellow", "red"
    status: str       # "open", "close"
    doc_count: int
    is_queryable: bool
    query_time_ms: Optional[float] = None
    error_message: Optional[str] = None


@dataclass
class ESConnectivityReport:
    """Top-level result of a full Elasticsearch connectivity validation."""
    host: str
    port: int
    is_reachable: bool
    cluster_health: Optional[ESClusterHealthReport]
    nodes: Optional[ESNodesReport]
    indices: List[ESIndexReport] = field(default_factory=list)
    overall_healthy: bool = False
    error_message: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _ESClient:
    """Thin wrapper around the Elasticsearch HTTP API."""

    def __init__(
        self,
        host: str,
        port: int = 9200,
        use_https: bool = False,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 15,
        verify_ssl: bool = False,
    ):
        self.base_url = f"{'https' if use_https else 'http'}://{host}:{port}"
        self.auth = HTTPBasicAuth(username, password) if username else None
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    def get(self, path: str, **params) -> Tuple[requests.Response, float]:
        start = time.perf_counter()
        response = requests.get(
            f"{self.base_url}{path}",
            params=params or None,
            auth=self.auth,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response, elapsed_ms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_cluster_health(
    host: str,
    port: int = 9200,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> ESClusterHealthReport:
    """Check Elasticsearch cluster health via GET /_cluster/health.

    Args:
        host:       Elasticsearch hostname or IP.
        port:       HTTP port (default 9200).
        use_https:  Use HTTPS.
        username:   Username for authenticated clusters.
        password:   Password for authenticated clusters.
        timeout:    Request timeout in seconds.
        verify_ssl: Verify SSL certificate.

    Returns:
        ESClusterHealthReport.

    Raises:
        requests.exceptions.RequestException: On network or HTTP errors.

    Example::

        report = check_cluster_health("es-host.example.com")
        print(f"Cluster '{report.cluster_name}': {report.status}")
        if report.unassigned_shards:
            print(f"  WARNING: {report.unassigned_shards} unassigned shards")
    """
    client = _ESClient(host, port, use_https, username, password, timeout, verify_ssl)
    response, elapsed_ms = client.get("/_cluster/health")
    data = response.json()

    status = data.get("status", "red")
    return ESClusterHealthReport(
        cluster_name=data.get("cluster_name", "unknown"),
        status=status,
        is_healthy=status == "green",
        number_of_nodes=data.get("number_of_nodes", 0),
        number_of_data_nodes=data.get("number_of_data_nodes", 0),
        active_primary_shards=data.get("active_primary_shards", 0),
        active_shards=data.get("active_shards", 0),
        relocating_shards=data.get("relocating_shards", 0),
        initializing_shards=data.get("initializing_shards", 0),
        unassigned_shards=data.get("unassigned_shards", 0),
        response_time_ms=elapsed_ms,
        timestamp=datetime.now(),
    )


def check_node_memory(
    host: str,
    port: int = 9200,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> ESNodesReport:
    """Return per-node JVM heap and OS memory usage.

    Calls GET /_nodes/stats/jvm,os and parses memory figures for every node
    in the cluster, enabling per-node comparison.

    Args:
        host:       Elasticsearch hostname or IP.
        port:       HTTP port (default 9200).
        use_https:  Use HTTPS.
        username:   Username for authenticated clusters.
        password:   Password for authenticated clusters.
        timeout:    Request timeout in seconds.
        verify_ssl: Verify SSL certificate.

    Returns:
        ESNodesReport with a list of ESNodeMemoryReport (one per node).

    Example::

        report = check_node_memory("es-host.example.com")
        for node in report.nodes:
            print(f"  {node.node_name}: heap {node.heap_used_pct:.1f}%  "
                  f"OS mem {node.os_used_pct:.1f}%")
    """
    client = _ESClient(host, port, use_https, username, password, timeout, verify_ssl)
    response, _ = client.get("/_nodes/stats/jvm,os")
    data = response.json()

    node_reports: List[ESNodeMemoryReport] = []
    for node_id, node in data.get("nodes", {}).items():
        jvm = node.get("jvm", {}).get("mem", {})
        os_mem = node.get("os", {}).get("mem", {})

        heap_used_mb = jvm.get("heap_used_in_bytes", 0) / 1024 / 1024
        heap_max_mb = jvm.get("heap_max_in_bytes", 1) / 1024 / 1024
        heap_pct = jvm.get("heap_used_percent", 0)

        os_used_bytes = os_mem.get("used_in_bytes", 0)
        os_total_bytes = os_mem.get("total_in_bytes", 1)
        os_used_pct = (os_used_bytes / os_total_bytes * 100) if os_total_bytes else 0

        node_reports.append(ESNodeMemoryReport(
            node_id=node_id,
            node_name=node.get("name", node_id),
            heap_used_mb=heap_used_mb,
            heap_max_mb=heap_max_mb,
            heap_used_pct=heap_pct,
            os_used_mb=os_used_bytes / 1024 / 1024,
            os_total_mb=os_total_bytes / 1024 / 1024,
            os_used_pct=os_used_pct,
        ))

    heap_pcts = [n.heap_used_pct for n in node_reports]
    return ESNodesReport(
        nodes=node_reports,
        total_heap_used_mb=sum(n.heap_used_mb for n in node_reports),
        total_heap_max_mb=sum(n.heap_max_mb for n in node_reports),
        avg_heap_used_pct=sum(heap_pcts) / len(heap_pcts) if heap_pcts else 0,
        max_heap_used_pct=max(heap_pcts) if heap_pcts else 0,
        timestamp=datetime.now(),
    )


def check_indices(
    host: str,
    port: int = 9200,
    index_filter: Optional[str] = None,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> List[ESIndexReport]:
    """List indices and validate each is queryable.

    Calls GET /_cat/indices (JSON format) and then issues a lightweight
    GET /<index>/_count to confirm each index actually accepts queries.

    Args:
        host:          Elasticsearch hostname or IP.
        port:          HTTP port (default 9200).
        index_filter:  Only check indices whose name contains this string.
                       Pass None to check all indices.
        use_https:     Use HTTPS.
        username:      Username for authenticated clusters.
        password:      Password for authenticated clusters.
        timeout:       Request timeout in seconds.
        verify_ssl:    Verify SSL certificate.

    Returns:
        List of ESIndexReport, one per matching index.

    Example::

        indices = check_indices("es-host.example.com", index_filter="anzo")
        for idx in indices:
            status_icon = "✓" if idx.is_queryable else "✗"
            print(f"  {status_icon} {idx.index}: {idx.health}  {idx.doc_count:,} docs")
    """
    client = _ESClient(host, port, use_https, username, password, timeout, verify_ssl)
    response, _ = client.get("/_cat/indices", h="health,status,index,docs.count", format="json")
    raw_indices = response.json()

    if index_filter:
        raw_indices = [i for i in raw_indices if index_filter in i.get("index", "")]

    results: List[ESIndexReport] = []
    for idx in raw_indices:
        index_name = idx.get("index", "")
        doc_count = int(idx.get("docs.count") or 0)

        # Confirm the index is actually queryable
        try:
            count_response, query_ms = client.get(f"/{index_name}/_count")
            is_queryable = count_response.ok
            error_msg = None
        except requests.exceptions.RequestException as e:
            is_queryable = False
            query_ms = None
            error_msg = str(e)

        results.append(ESIndexReport(
            index=index_name,
            health=idx.get("health", "unknown"),
            status=idx.get("status", "unknown"),
            doc_count=doc_count,
            is_queryable=is_queryable,
            query_time_ms=query_ms if is_queryable else None,
            error_message=error_msg,
        ))

    return results


def validate_elasticsearch_connectivity(
    host: str,
    port: int = 9200,
    index_filter: Optional[str] = None,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> ESConnectivityReport:
    """Run a full Elasticsearch connectivity and health validation.

    Combines cluster health, per-node memory, and index queryability into a
    single top-level report.  Safe to call from monitoring scripts or CI/CD
    pipelines; individual failures are captured rather than raised.

    Args:
        host:          Elasticsearch hostname or IP.
        port:          HTTP port (default 9200).
        index_filter:  Only validate indices whose name contains this string.
        use_https:     Use HTTPS.
        username:      Username for authenticated clusters.
        password:      Password for authenticated clusters.
        timeout:       Request timeout in seconds.
        verify_ssl:    Verify SSL certificate.

    Returns:
        ESConnectivityReport with all sub-reports populated.

    Example::

        report = validate_elasticsearch_connectivity(
            "es-host.example.com",
            index_filter="anzo",
        )
        print(f"Reachable: {report.is_reachable}")
        print(f"Cluster: {report.cluster_health.status}")
        print(f"Overall healthy: {report.overall_healthy}")
        for node in report.nodes.nodes:
            print(f"  {node.node_name}: {node.heap_used_pct:.1f}% heap")
        for idx in report.indices:
            print(f"  {idx.index}: {'OK' if idx.is_queryable else 'ERROR'}")
    """
    report = ESConnectivityReport(host=host, port=port, is_reachable=False,
                                  cluster_health=None, nodes=None)
    try:
        # 1. Cluster health
        report.cluster_health = check_cluster_health(
            host, port, use_https, username, password, timeout, verify_ssl
        )
        report.is_reachable = True
        logger.info(
            f"ES cluster '{report.cluster_health.cluster_name}': "
            f"{report.cluster_health.status}  "
            f"({report.cluster_health.number_of_nodes} nodes, "
            f"{report.cluster_health.unassigned_shards} unassigned shards)"
        )

        # 2. Per-node memory
        report.nodes = check_node_memory(
            host, port, use_https, username, password, timeout, verify_ssl
        )
        for node in report.nodes.nodes:
            logger.info(
                f"  Node '{node.node_name}': "
                f"heap {node.heap_used_mb:.0f}/{node.heap_max_mb:.0f}MB "
                f"({node.heap_used_pct:.1f}%)  "
                f"OS mem {node.os_used_pct:.1f}%"
            )

        # 3. Index validation
        report.indices = check_indices(
            host, port, index_filter, use_https, username, password, timeout, verify_ssl
        )
        for idx in report.indices:
            if idx.is_queryable:
                logger.info(f"  Index '{idx.index}': {idx.health}  {idx.doc_count:,} docs")
            else:
                logger.warning(f"  Index '{idx.index}': NOT queryable — {idx.error_message}")

        # Overall health: cluster green + no unqueryable indices
        unqueryable = [i for i in report.indices if not i.is_queryable]
        report.overall_healthy = (
            report.cluster_health.status in ("green", "yellow")
            and not unqueryable
        )

    except requests.exceptions.ConnectionError as e:
        report.error_message = f"Cannot reach Elasticsearch at {host}:{port} — {e}"
        logger.error(report.error_message)
    except requests.exceptions.Timeout:
        report.error_message = f"Timed out connecting to Elasticsearch at {host}:{port}"
        logger.error(report.error_message)
    except requests.exceptions.RequestException as e:
        report.error_message = str(e)
        logger.error(f"Elasticsearch validation failed: {e}")

    return report
