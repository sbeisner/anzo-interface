#!/usr/bin/env python3
"""
Quick Artifact Monitor - Simple health check script

This is a minimal monitoring script that checks the health of:
- Graphmarts (including their layers and steps - which represent ES/DU components)
- AZG (AnzoGraph) connections

Perfect for:
- Cron jobs
- CI/CD health checks
- Quick manual status checks
- Integration with external monitoring systems

Usage:
    python quick_monitor.py

Exit codes:
    0 - All artifacts healthy
    1 - One or more artifacts unhealthy
"""

import logging
import sys

from graphmart_manager import GraphmartManagerApi
from monitoring_hooks import (
    ArtifactStatus,
    check_azg_connection,
    check_graphmart_status,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - Update these values for your environment
# =============================================================================

SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False

# List all graphmarts you want to monitor
GRAPHMARTS = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
]


def main():
    """Run health checks and report status."""

    # Initialize API
    api = GraphmartManagerApi(
        server=SERVER,
        username=USERNAME,
        password=PASSWORD,
        port=PORT,
        https=HTTPS,
        verify_ssl=VERIFY_SSL
    )

    all_healthy = True

    # Check each graphmart
    for graphmart_uri in GRAPHMARTS:
        try:
            # Get graphmart status (includes ES/DU via layers/steps)
            report = check_graphmart_status(api, graphmart_uri)

            # Check AZG connection
            azg_status = check_azg_connection(api, graphmart_uri)

            # Log status
            status_symbol = "✓" if report.overall_status == ArtifactStatus.HEALTHY else "✗"
            logger.info(f"{status_symbol} {report.title}: {report.overall_status.value}")

            if report.error_message:
                logger.warning(f"  └─ Issue: {report.error_message}")
                all_healthy = False

            # Check AZG connection
            azg_symbol = "✓" if azg_status['connected'] else "✗"
            logger.info(f"  {azg_symbol} AZG Connection: {'Connected' if azg_status['connected'] else 'Disconnected'}")

            if not azg_status['connected']:
                all_healthy = False

            # Report on layers (ES/DU components)
            if report.failed_layers > 0:
                logger.error(f"  └─ {report.failed_layers} layer(s) failed")
                all_healthy = False

            if report.dirty_layers > 0:
                logger.warning(f"  └─ {report.dirty_layers} layer(s) dirty")

        except Exception as e:
            logger.error(f"✗ Failed to check {graphmart_uri}: {e}")
            all_healthy = False

    # Exit with appropriate code
    if all_healthy:
        logger.info("\n✓ All artifacts are healthy")
        sys.exit(0)
    else:
        logger.error("\n✗ One or more artifacts are unhealthy")
        sys.exit(1)


if __name__ == '__main__':
    main()
