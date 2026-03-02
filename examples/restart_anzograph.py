#!/usr/bin/env python3
"""
AnzoGraph Cluster Restart

Safely restarts a specific AnzoGraph cluster via the AGS semantic service,
with optional graphmart deactivation before the restart and automatic
reactivation afterward.

Restart sequence
----------------
  1. Deactivate all graphmarts connected to the AZG cluster so in-flight
     queries can drain and no new queries are routed during restart.

  2. POST a GqeReloadRequest TriG payload to the semantic-services endpoint.
     This triggers AnzoGraph to perform a full cluster reload.

  3. Reactivate each graphmart and block until it is fully Online.

IMPORTANT — When to use this script
-------------------------------------
  • AZG cluster is unresponsive or stuck.
  • You need to apply AZG configuration changes that require a restart.
  • After a failed graphmart activation that left AZG in a bad state.

  Do NOT restart AZG during active production load without first confirming
  all in-flight queries have completed or been cancelled.  See:
    examples/cancel_inflight_queries.py   (cancel running queries first)
    examples/check_anzograph.py           (verify AZG is alive first)

Usage:
    python examples/restart_anzograph.py
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION — update for your environment
# =============================================================================

# Anzo server connection
ANZO_HOST     = 'your-anzo-host.example.com'
ANZO_PORT     = 8443
ANZO_USERNAME = 'admin'
ANZO_PASSWORD = 'Passw0rd1'

# URI of the AnzoGraph datasource to restart.
# Find this in the AGS UI under Administration → Datasources,
# or from the graphmart detail page in the AZG connection section.
AZG_URI = 'http://cambridgesemantics.com/anzograph/AnzoGraph'

# Graphmarts that are currently connected to this AZG cluster.
# They will be deactivated before the restart and reactivated afterward.
# Leave this list empty only if you want to restart AZG without touching
# graphmarts (advanced use — queries may fail during the restart window).
GRAPHMART_URIS = [
    # 'http://cambridgesemantics.com/graphmart/MyGraphmart1',
    # 'http://cambridgesemantics.com/graphmart/MyGraphmart2',
]

# Timeout (seconds) for each graphmart deactivation call
DEACTIVATE_TIMEOUT = 120

# Timeout (seconds) per graphmart when waiting for it to come back online.
# AnzoGraph restarts typically take 2–10 minutes; the default 30 minutes
# (1800s) is intentionally generous for large clusters.
READY_TIMEOUT = 1800


def main() -> int:
    api = GraphmartManagerApi(
        server=ANZO_HOST,
        port=ANZO_PORT,
        username=ANZO_USERNAME,
        password=ANZO_PASSWORD,
    )

    # ------------------------------------------------------------------
    # Optional pre-flight: confirm AZG is currently reachable before
    # attempting a restart.  Remove this block if AZG is already down.
    # ------------------------------------------------------------------
    logger.info('=' * 70)
    logger.info('ANZOGRAPH CLUSTER RESTART')
    logger.info('=' * 70)
    logger.info(f'  AZG datasource : {AZG_URI}')
    logger.info(f'  Graphmarts     : {len(GRAPHMART_URIS)} configured')
    if GRAPHMART_URIS:
        for uri in GRAPHMART_URIS:
            logger.info(f'    • {uri}')
    logger.info('')

    # ------------------------------------------------------------------
    # Execute the restart
    # ------------------------------------------------------------------
    try:
        api.restart_anzograph(
            azg_uri=AZG_URI,
            graphmart_uris=GRAPHMART_URIS,
            deactivate_timeout=DEACTIVATE_TIMEOUT,
            ready_timeout=READY_TIMEOUT,
        )
    except GraphmartManagerApiException as e:
        logger.error(f'Restart failed: {e}')
        return 1

    logger.info('')
    logger.info('=' * 70)
    logger.info('✓  AnzoGraph restart complete — all graphmarts are online.')
    logger.info('=' * 70)
    return 0


if __name__ == '__main__':
    sys.exit(main())
