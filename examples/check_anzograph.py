#!/usr/bin/env python3
"""
AnzoGraph Connectivity & Performance Check

Validates the Anzo→AnzoGraph communication path by:
  1. Checking that the AZG SPARQL endpoint is alive.
  2. Measuring query round-trip latency across multiple probes.
  3. Estimating result-set delivery throughput.

WHY the back-end port (7070) is preferred for monitoring
---------------------------------------------------------
AnzoGraph exposes two HTTP SPARQL interfaces:

  • Back-end  (port 7070 / HTTPS 8256) — no authentication required.
    Bypasses Anzo's gateway so latency measured here reflects the network
    path between your monitoring host and the AZG engine directly.

  • Front-end (port 443 / 80) — HTTP Basic Auth required.
    Queries are routed through Anzo's frontend container layer, so latency
    includes Anzo processing overhead in addition to AZG engine time.

IMPORTANT — What this script does NOT measure
----------------------------------------------
  ✗  Per-node / per-worker memory utilization
     AnzoGraph's cluster management uses internal gRPC (port 5600), not REST.
     There is no public REST or SPARQL endpoint for node-level memory stats.
     → Deploy a backend sidecar on each AZG node: see BACKEND_SERVICE_GUIDE.md

  ✗  True intra-cluster interconnect bandwidth
     The Admin Console has a network benchmark but it is UI-only with no API.
     → Use OS-level tools (iftop, /proc/net/dev, Prometheus node_exporter)
       on each AZG cluster node.

Usage:
    python examples/check_anzograph.py
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anzograph_monitoring import (
    check_anzograph_liveness,
    measure_anzograph_latency,
    measure_anzograph_throughput,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION — update for your environment
# =============================================================================

# AnzoGraph hostname or IP
AZG_HOST = 'your-anzograph-host.example.com'

# Back-end port (no auth, bypasses Anzo gateway) — preferred for monitoring
AZG_BACKEND_PORT = 7070

# Front-end port (Basic Auth, routed through Anzo's proxy layer)
# AZG_FRONTEND_PORT = 443
# AZG_USERNAME = 'admin'
# AZG_PASSWORD = 'Passw0rd1'

# Number of latency probe round-trips
LATENCY_PROBES = 10

# Rows to fetch for throughput measurement (larger = more representative)
THROUGHPUT_ROW_LIMIT = 10_000


def main() -> int:
    all_ok = True

    # ------------------------------------------------------------------
    # 1. Liveness check
    # ------------------------------------------------------------------
    logger.info("=" * 70)
    logger.info("1. ANZOGRAPH SPARQL ENDPOINT LIVENESS")
    logger.info("=" * 70)

    liveness = check_anzograph_liveness(host=AZG_HOST, port=AZG_BACKEND_PORT)

    if liveness.is_alive:
        logger.info(
            f"✓  AnzoGraph is alive at {AZG_HOST}:{AZG_BACKEND_PORT}  "
            f"({liveness.response_time_ms:.1f}ms)"
        )
    else:
        logger.error(
            f"✗  AnzoGraph is NOT reachable at {AZG_HOST}:{AZG_BACKEND_PORT}  "
            f"— {liveness.error_message}"
        )
        logger.error("Cannot proceed without a live endpoint.")
        return 1

    # ------------------------------------------------------------------
    # 2. Latency measurement  (proxy for Anzo→AZG interconnect speed)
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("2. QUERY ROUND-TRIP LATENCY  (Anzo → AnzoGraph path)")
    logger.info("=" * 70)
    logger.info(
        f"   Sending {LATENCY_PROBES} lightweight SPARQL probes …"
    )

    latency = measure_anzograph_latency(
        host=AZG_HOST,
        port=AZG_BACKEND_PORT,
        num_probes=LATENCY_PROBES,
    )

    successful = LATENCY_PROBES - latency.failed_probes
    logger.info(f"   Probes completed: {successful}/{LATENCY_PROBES}")
    logger.info(f"   Min    : {latency.min_ms:.2f} ms")
    logger.info(f"   Median : {latency.median_ms:.2f} ms")
    logger.info(f"   Mean   : {latency.mean_ms:.2f} ms")
    logger.info(f"   Max    : {latency.max_ms:.2f} ms")
    logger.info(f"   StdDev : {latency.stdev_ms:.2f} ms")

    if latency.failed_probes > 0:
        logger.warning(f"   ⚠  {latency.failed_probes} probe(s) failed")
        all_ok = False

    # Flag high latency as a warning
    if latency.median_ms > 500:
        logger.warning(
            f"   ⚠  Median latency {latency.median_ms:.0f}ms is high — "
            f"check network path between Anzo and AnzoGraph."
        )
        all_ok = False
    else:
        logger.info("   ✓  Latency is within acceptable range.")

    logger.info("")
    logger.info("   NOTE: For true interconnect bandwidth between AZG cluster nodes,")
    logger.info("   deploy a backend sidecar per node (BACKEND_SERVICE_GUIDE.md).")

    # ------------------------------------------------------------------
    # 3. Result-set delivery throughput
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("3. RESULT-SET DELIVERY THROUGHPUT")
    logger.info("=" * 70)
    logger.info(f"   Fetching up to {THROUGHPUT_ROW_LIMIT:,} triples …")

    throughput = measure_anzograph_throughput(
        host=AZG_HOST,
        port=AZG_BACKEND_PORT,
        row_limit=THROUGHPUT_ROW_LIMIT,
    )

    if throughput.rows_fetched > 0:
        logger.info(f"   Rows fetched  : {throughput.rows_fetched:,}")
        logger.info(f"   Elapsed       : {throughput.elapsed_ms:.0f} ms")
        logger.info(f"   Throughput    : {throughput.rows_per_second:,.0f} rows/sec")
    else:
        logger.warning("   ⚠  No rows returned — database may be empty or query failed.")

    logger.info("")
    logger.info("   NOTE: This measures result delivery to the calling host,")
    logger.info("   not intra-cluster interconnect bandwidth.")

    # ------------------------------------------------------------------
    # 4. Per-node memory — unavailable summary
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("4. PER-NODE CLUSTER MEMORY — NOT AVAILABLE via REST API")
    logger.info("=" * 70)
    logger.info(
        "   AnzoGraph cluster management uses gRPC (port 5600), not REST.\n"
        "   There is no public endpoint for per-node or per-worker memory.\n"
        "\n"
        "   Options:\n"
        "   • Deploy a psutil-based sidecar on each AZG node\n"
        "     → See BACKEND_SERVICE_GUIDE.md\n"
        "   • Use Prometheus node_exporter on each AZG node\n"
        "   • Use a commercial APM agent (Datadog, New Relic, Dynatrace)"
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    if all_ok:
        logger.info("✓  AnzoGraph connectivity checks passed.")
    else:
        logger.error("✗  One or more checks failed — review output above.")
    logger.info("=" * 70)

    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
