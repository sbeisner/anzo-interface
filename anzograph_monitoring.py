"""
AnzoGraph Monitoring

Provides liveness checks, query latency measurement, and approximate
Anzo→AnzoGraph throughput estimation using the AnzoGraph SPARQL endpoints.

WHAT IS AVAILABLE without a backend service
--------------------------------------------
AnzoGraph exposes two SPARQL HTTP endpoints that can be queried remotely:

  • Back-end port (default 7070 / HTTPS 8256) — no authentication required.
    Ideal for monitoring because it bypasses Anzo's gateway and hits the
    database engine directly, giving a true end-to-end latency measurement.

  • Front-end port (default 443 / 80) — HTTP Basic Auth required.
    Queries routed through Anzo's frontend proxy layer.

Using these endpoints we can measure:
  ✓  SPARQL endpoint liveness (is AnzoGraph accepting queries?)
  ✓  Query round-trip latency (Anzo → AnzoGraph path)
  ✓  Approximate query throughput (rows/second for a known query)
  ✓  AZG connection status via graphmart activation (see graphmart_manager.py)

WHAT IS NOT AVAILABLE via any REST or SPARQL API
-------------------------------------------------
AnzoGraph's internal cluster management uses gRPC (port 5600), not REST.
There is no publicly documented REST or SPARQL endpoint for:

  ✓  Per-node memory utilization — via ``get_anzograph_memory()``.
      → Requires the backend sidecar running on the AZG node (reads /proc,
        no root needed).  See README for sidecar setup.

  ✗  True intra-cluster interconnect bandwidth
      → The Admin Console has a network benchmark (UI only, not API-accessible).
        Programmatic measurement requires OS-level tools (iftop, /proc/net/dev,
        Prometheus node_exporter) on each cluster node.

  ✗  Per-slice CPU / thread counts
      → Same limitation as memory — requires OS access or commercial APM.

See BACKEND_SERVICE_GUIDE.md for deploying a sidecar on each AZG node.
"""

import logging
import statistics
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

# Simple SPARQL query used for latency probes — returns a single row fast.
_PING_QUERY = "SELECT (1 AS ?ping) WHERE {}"

# Throughput probe: pull a bounded result set to measure rows/second.
# Callers can substitute their own query for a domain-relevant measurement.
_THROUGHPUT_QUERY = "SELECT ?s ?p ?o WHERE {{ ?s ?p ?o }} LIMIT {limit}"


@dataclass
class AnzoGraphLivenessReport:
    """Result of a single SPARQL endpoint liveness check."""
    host: str
    port: int
    is_alive: bool
    response_time_ms: float
    http_status: Optional[int]
    error_message: Optional[str]
    timestamp: datetime


@dataclass
class AnzoGraphLatencyReport:
    """Query round-trip latency statistics across multiple probes."""
    host: str
    port: int
    num_probes: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    stdev_ms: float
    failed_probes: int
    timestamp: datetime


@dataclass
class AnzoGraphThroughputReport:
    """Approximate query throughput measured by timing a bounded SELECT."""
    host: str
    port: int
    rows_fetched: int
    elapsed_ms: float
    rows_per_second: float
    # NOTE: This measures result-set delivery speed from AZG to the
    # calling host (Anzo or this script). It is NOT equivalent to
    # intra-cluster interconnect bandwidth.
    timestamp: datetime


@dataclass
class AnzoGraphMemoryReport:
    """Memory consumption of the AnzoGraph process, read via the backend sidecar.

    Obtained by calling GET /metrics/cpu on the monitoring sidecar deployed on
    the AnzoGraph node.  The sidecar reads /proc/{pid}/status (world-readable)
    so it works without root access.
    """
    host: str
    sidecar_port: int
    memory_mb: Optional[float]
    cpu_percent: Optional[float]
    num_threads: Optional[int]
    source: str            # e.g. "psutil" or "/proc"
    error_message: Optional[str]
    timestamp: datetime


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _sparql_get(
    host: str,
    port: int,
    query: str,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 30,
    verify_ssl: bool = False,
) -> tuple[requests.Response, float]:
    """Issue a SPARQL GET and return (response, elapsed_ms)."""
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{host}:{port}/sparql"
    auth = HTTPBasicAuth(username, password) if username else None

    start = time.perf_counter()
    response = requests.get(
        url,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        auth=auth,
        timeout=timeout,
        verify=verify_ssl,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000
    return response, elapsed_ms


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_anzograph_liveness(
    host: str,
    port: int = 7070,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 10,
    verify_ssl: bool = False,
) -> AnzoGraphLivenessReport:
    """Check whether the AnzoGraph SPARQL endpoint is accepting queries.

    Uses the back-end port (7070, no auth) by default for a direct liveness
    check that bypasses Anzo's gateway.  Pass the front-end port (443/80)
    with credentials to probe through the gateway layer instead.

    Args:
        host:        AnzoGraph hostname or IP.
        port:        SPARQL port.  Default 7070 (back-end, no auth).
                     Use 8256 for back-end HTTPS.  Use 443/80 for front-end.
        use_https:   Use HTTPS scheme.
        username:    Required only for front-end port.
        password:    Required only for front-end port.
        timeout:     Request timeout in seconds.
        verify_ssl:  Verify SSL certificate.

    Returns:
        AnzoGraphLivenessReport

    Example::

        report = check_anzograph_liveness("azg-host.example.com")
        if report.is_alive:
            print(f"AZG responding in {report.response_time_ms:.1f}ms")
    """
    try:
        response, elapsed_ms = _sparql_get(
            host=host, port=port, query=_PING_QUERY,
            use_https=use_https, username=username, password=password,
            timeout=timeout, verify_ssl=verify_ssl,
        )
        return AnzoGraphLivenessReport(
            host=host,
            port=port,
            is_alive=response.ok,
            response_time_ms=elapsed_ms,
            http_status=response.status_code,
            error_message=None if response.ok else response.text[:200],
            timestamp=datetime.now(),
        )
    except requests.exceptions.ConnectionError as e:
        return AnzoGraphLivenessReport(
            host=host, port=port, is_alive=False,
            response_time_ms=0.0, http_status=None,
            error_message=f"Connection refused: {e}",
            timestamp=datetime.now(),
        )
    except requests.exceptions.Timeout:
        return AnzoGraphLivenessReport(
            host=host, port=port, is_alive=False,
            response_time_ms=float(timeout * 1000), http_status=None,
            error_message=f"Timed out after {timeout}s",
            timestamp=datetime.now(),
        )
    except Exception as e:
        return AnzoGraphLivenessReport(
            host=host, port=port, is_alive=False,
            response_time_ms=0.0, http_status=None,
            error_message=str(e),
            timestamp=datetime.now(),
        )


def measure_anzograph_latency(
    host: str,
    port: int = 7070,
    num_probes: int = 5,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 15,
    verify_ssl: bool = False,
) -> AnzoGraphLatencyReport:
    """Measure Anzo→AnzoGraph query round-trip latency over multiple probes.

    Sends ``num_probes`` lightweight SPARQL queries (``SELECT (1 AS ?ping)
    WHERE {}``) and computes min/max/mean/median/stdev statistics.

    This is the best available proxy for *interconnect speed* between Anzo
    and AnzoGraph without OS-level access to the network interfaces.

    Note:
        For true intra-cluster interconnect bandwidth, OS-level monitoring
        on each AZG node is required (see BACKEND_SERVICE_GUIDE.md).

    Args:
        host:       AnzoGraph hostname or IP.
        port:       SPARQL port (default 7070, back-end, no auth).
        num_probes: Number of query round-trips to measure.
        use_https:  Use HTTPS scheme.
        username:   Required only for front-end port.
        password:   Required only for front-end port.
        timeout:    Per-probe timeout in seconds.
        verify_ssl: Verify SSL certificate.

    Returns:
        AnzoGraphLatencyReport with latency statistics.

    Example::

        report = measure_anzograph_latency("azg-host.example.com", num_probes=10)
        print(f"Median latency: {report.median_ms:.1f}ms")
        print(f"p99 proxy (max): {report.max_ms:.1f}ms")
    """
    samples: list[float] = []
    failed = 0

    for i in range(num_probes):
        try:
            response, elapsed_ms = _sparql_get(
                host=host, port=port, query=_PING_QUERY,
                use_https=use_https, username=username, password=password,
                timeout=timeout, verify_ssl=verify_ssl,
            )
            if response.ok:
                samples.append(elapsed_ms)
                logger.debug(f"Probe {i + 1}/{num_probes}: {elapsed_ms:.1f}ms")
            else:
                logger.warning(f"Probe {i + 1} returned HTTP {response.status_code}")
                failed += 1
        except Exception as e:
            logger.warning(f"Probe {i + 1} failed: {e}")
            failed += 1

    if not samples:
        # All probes failed — return zeroed report
        return AnzoGraphLatencyReport(
            host=host, port=port, num_probes=num_probes,
            min_ms=0, max_ms=0, mean_ms=0, median_ms=0, stdev_ms=0,
            failed_probes=failed, timestamp=datetime.now(),
        )

    return AnzoGraphLatencyReport(
        host=host,
        port=port,
        num_probes=num_probes,
        min_ms=min(samples),
        max_ms=max(samples),
        mean_ms=statistics.mean(samples),
        median_ms=statistics.median(samples),
        stdev_ms=statistics.stdev(samples) if len(samples) > 1 else 0.0,
        failed_probes=failed,
        timestamp=datetime.now(),
    )


def measure_anzograph_throughput(
    host: str,
    port: int = 7070,
    row_limit: int = 10_000,
    custom_query: Optional[str] = None,
    use_https: bool = False,
    username: Optional[str] = None,
    password: Optional[str] = None,
    timeout: int = 60,
    verify_ssl: bool = False,
) -> AnzoGraphThroughputReport:
    """Estimate result-set delivery throughput from AnzoGraph.

    Times how long AnzoGraph takes to execute a bounded triple-pattern query
    and deliver its result set, then reports rows/second.

    This measures the **result delivery path** (AZG engine → HTTP → caller),
    which is a useful proxy for Anzo→AZG communication performance. It is
    NOT equivalent to intra-cluster network bandwidth.

    Args:
        host:         AnzoGraph hostname or IP.
        port:         SPARQL port (default 7070, back-end, no auth).
        row_limit:    Maximum rows to fetch (default 10 000).
        custom_query: Override the default SPO query with a domain-specific
                      one.  Include a ``LIMIT`` clause to bound the result.
        use_https:    Use HTTPS scheme.
        username:     Required only for front-end port.
        password:     Required only for front-end port.
        timeout:      Request timeout in seconds.
        verify_ssl:   Verify SSL certificate.

    Returns:
        AnzoGraphThroughputReport

    Example::

        report = measure_anzograph_throughput("azg-host.example.com", row_limit=50_000)
        print(f"Throughput: {report.rows_per_second:.0f} rows/sec")
    """
    query = custom_query or _THROUGHPUT_QUERY.format(limit=row_limit)

    try:
        response, elapsed_ms = _sparql_get(
            host=host, port=port, query=query,
            use_https=use_https, username=username, password=password,
            timeout=timeout, verify_ssl=verify_ssl,
        )
        response.raise_for_status()

        bindings = response.json().get("results", {}).get("bindings", [])
        rows_fetched = len(bindings)
        elapsed_sec = elapsed_ms / 1000
        rows_per_second = rows_fetched / elapsed_sec if elapsed_sec > 0 else 0.0

        return AnzoGraphThroughputReport(
            host=host, port=port,
            rows_fetched=rows_fetched,
            elapsed_ms=elapsed_ms,
            rows_per_second=rows_per_second,
            timestamp=datetime.now(),
        )
    except Exception as e:
        logger.error(f"Throughput measurement failed: {e}")
        return AnzoGraphThroughputReport(
            host=host, port=port,
            rows_fetched=0, elapsed_ms=0.0, rows_per_second=0.0,
            timestamp=datetime.now(),
        )


def get_anzograph_memory(
    host: str,
    sidecar_port: int = 5000,
    use_https: bool = False,
    timeout: int = 10,
    verify_ssl: bool = False,
) -> AnzoGraphMemoryReport:
    """Return current memory consumption of the AnzoGraph process.

    Calls ``GET /metrics/cpu`` on the monitoring sidecar deployed on the
    AnzoGraph node.  The sidecar reads ``/proc/{pid}/status`` (world-readable),
    so it works without root access on the AZG host.

    Prerequisites:
        The backend monitoring sidecar (``anzo_monitoring_service.py``) must be
        running on the AnzoGraph node and reachable from the caller.  The
        sidecar automatically discovers the AnzoGraph process by the name
        configured in its ``ANZO_PROCESS_NAME`` environment variable.

    Args:
        host:         Hostname or IP of the AnzoGraph node.
        sidecar_port: Port the monitoring sidecar listens on (default 5000).
        use_https:    Use HTTPS to reach the sidecar.
        timeout:      Request timeout in seconds.
        verify_ssl:   Verify SSL certificate when ``use_https=True``.

    Returns:
        AnzoGraphMemoryReport

    Example::

        report = get_anzograph_memory("azg-host.example.com")
        if report.error_message:
            print(f"Could not fetch memory: {report.error_message}")
        else:
            print(f"AnzoGraph memory: {report.memory_mb:.0f} MB ({report.source})")
    """
    scheme = "https" if use_https else "http"
    url = f"{scheme}://{host}:{sidecar_port}/metrics/cpu"

    try:
        response = requests.get(url, timeout=timeout, verify=verify_ssl)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            return AnzoGraphMemoryReport(
                host=host, sidecar_port=sidecar_port,
                memory_mb=None, cpu_percent=None, num_threads=None,
                source="sidecar",
                error_message=data["error"],
                timestamp=datetime.now(),
            )

        return AnzoGraphMemoryReport(
            host=host,
            sidecar_port=sidecar_port,
            memory_mb=data.get("memory_mb"),
            cpu_percent=data.get("cpu_percent"),
            num_threads=data.get("num_threads"),
            source=data.get("source", "sidecar"),
            error_message=None,
            timestamp=datetime.now(),
        )

    except requests.exceptions.ConnectionError:
        return AnzoGraphMemoryReport(
            host=host, sidecar_port=sidecar_port,
            memory_mb=None, cpu_percent=None, num_threads=None,
            source="sidecar",
            error_message=f"Connection refused — is the sidecar running on {host}:{sidecar_port}?",
            timestamp=datetime.now(),
        )
    except Exception as e:
        return AnzoGraphMemoryReport(
            host=host, sidecar_port=sidecar_port,
            memory_mb=None, cpu_percent=None, num_threads=None,
            source="sidecar",
            error_message=str(e),
            timestamp=datetime.now(),
        )
