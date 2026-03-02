#!/usr/bin/env python3
"""
Elasticsearch Connectivity Validation Script

Validates Elasticsearch cluster health, per-node memory utilization, and
index queryability by talking directly to the Elasticsearch HTTP API.

Unlike the indirect check in infrastructure_monitoring.py — which infers ES
health from Anzo graphmart layer failures — this script talks directly to ES
and returns precise diagnostic information.

Checks performed
----------------
  1. Cluster health  (GET /_cluster/health)
     Status (green/yellow/red), node counts, shard status.

  2. Per-node memory  (GET /_nodes/stats/jvm,os)
     JVM heap used/max, OS memory used/total — per node in the cluster.

  3. Index validation  (GET /_cat/indices + GET /<index>/_count)
     Health, status, document count, and whether each index accepts queries.

Usage:
    python examples/check_elasticsearch.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from elasticsearch_monitoring import validate_elasticsearch_connectivity

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION — update for your environment
# =============================================================================

ES_HOST = 'your-elasticsearch-host.example.com'
ES_PORT = 9200
ES_USE_HTTPS = False
ES_USERNAME = None   # Set to a string if your cluster requires authentication
ES_PASSWORD = None   # Set to a string if your cluster requires authentication
ES_VERIFY_SSL = False
ES_TIMEOUT = 15

# Optional: restrict index validation to indices matching this substring.
# Set to None to validate all indices.
INDEX_FILTER = 'anzo'


def main() -> int:
    logger.info("=" * 70)
    logger.info("ELASTICSEARCH CONNECTIVITY VALIDATION")
    logger.info(f"Target: {ES_HOST}:{ES_PORT}")
    logger.info("=" * 70)

    report = validate_elasticsearch_connectivity(
        host=ES_HOST,
        port=ES_PORT,
        index_filter=INDEX_FILTER,
        use_https=ES_USE_HTTPS,
        username=ES_USERNAME,
        password=ES_PASSWORD,
        timeout=ES_TIMEOUT,
        verify_ssl=ES_VERIFY_SSL,
    )

    if not report.is_reachable:
        logger.error(f"✗  Cannot reach Elasticsearch: {report.error_message}")
        return 1

    # ------------------------------------------------------------------
    # 1. Cluster health
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("── CLUSTER HEALTH ──────────────────────────────────────────────")
    h = report.cluster_health
    status_icon = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(h.status, "?")
    logger.info(f"   {status_icon}  Cluster '{h.cluster_name}': {h.status.upper()}")
    logger.info(f"      Nodes (total / data)  : {h.number_of_nodes} / {h.number_of_data_nodes}")
    logger.info(f"      Active shards         : {h.active_shards} ({h.active_primary_shards} primary)")
    logger.info(f"      Relocating shards     : {h.relocating_shards}")
    logger.info(f"      Initializing shards   : {h.initializing_shards}")
    logger.info(f"      Unassigned shards     : {h.unassigned_shards}")
    logger.info(f"      Response time         : {h.response_time_ms:.1f}ms")

    if h.unassigned_shards > 0:
        logger.warning(
            f"   ⚠  {h.unassigned_shards} unassigned shards — "
            f"data may be partially unavailable."
        )

    # ------------------------------------------------------------------
    # 2. Per-node memory
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("── PER-NODE MEMORY ─────────────────────────────────────────────")
    if report.nodes and report.nodes.nodes:
        logger.info(
            f"   {'Node':<30} {'Heap used':>12}  {'Heap %':>8}  "
            f"{'OS Mem used':>14}  {'OS Mem %':>9}"
        )
        logger.info("   " + "-" * 80)
        for node in report.nodes.nodes:
            heap_warn = " ⚠" if node.heap_used_pct > 85 else ""
            logger.info(
                f"   {node.node_name:<30} "
                f"{node.heap_used_mb:>8.0f} MB  "
                f"{node.heap_used_pct:>7.1f}%{heap_warn}  "
                f"{node.os_used_mb:>10.0f} MB  "
                f"{node.os_used_pct:>8.1f}%"
            )
        logger.info("   " + "-" * 80)
        logger.info(
            f"   {'TOTAL':<30} "
            f"{report.nodes.total_heap_used_mb:>8.0f} MB  "
            f"{report.nodes.avg_heap_used_pct:>7.1f}%  "
            f"{'(avg)':<14}  {'':>9}"
        )

        if report.nodes.max_heap_used_pct > 85:
            logger.warning(
                f"   ⚠  One or more nodes have heap usage > 85% "
                f"(max: {report.nodes.max_heap_used_pct:.1f}%)."
            )
    else:
        logger.warning("   No node memory data available.")

    # ------------------------------------------------------------------
    # 3. Index validation
    # ------------------------------------------------------------------
    logger.info("")
    filter_note = f"(filter: '{INDEX_FILTER}')" if INDEX_FILTER else "(all indices)"
    logger.info(f"── INDEX VALIDATION {filter_note} ──────────────────────────────")

    if report.indices:
        for idx in report.indices:
            status_icon = {"green": "✓", "yellow": "⚠", "red": "✗"}.get(idx.health, "?")
            queryable_str = f"{idx.query_time_ms:.0f}ms" if idx.query_time_ms else "ERROR"
            logger.info(
                f"   {status_icon}  {idx.index:<40} "
                f"{idx.health:<8}  "
                f"{idx.doc_count:>10,} docs  "
                f"query: {queryable_str}"
            )
            if not idx.is_queryable:
                logger.warning(f"      → {idx.error_message}")
    else:
        logger.info(
            f"   No indices found{' matching filter' if INDEX_FILTER else ''}."
        )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    if report.overall_healthy:
        logger.info(f"✓  Elasticsearch at {ES_HOST}:{ES_PORT} is healthy.")
    else:
        logger.error(f"✗  Elasticsearch at {ES_HOST}:{ES_PORT} has issues — see above.")
    logger.info("=" * 70)

    return 0 if report.overall_healthy else 1


if __name__ == '__main__':
    sys.exit(main())
