#!/usr/bin/env python3
"""
Quick Health Check Script

Simple script for cron jobs or CI/CD pipelines that checks basic
health of Anzo graphmarts and exits with appropriate code.

Exit codes:
    0 - All healthy
    1 - One or more issues detected

Usage:
    python examples/quick_health_check.py

    # In cron:
    */5 * * * * /path/to/venv/bin/python /path/to/examples/quick_health_check.py || echo "Anzo health check failed" | mail -s "Alert" admin@example.com
"""

import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphmart_manager import GraphmartManagerApi
from monitoring_hooks import check_graphmart_status, ArtifactStatus
from infrastructure_monitoring import check_anzograph_connectivity

# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - Update these for your environment
# =============================================================================

SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False

GRAPHMARTS = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
]


def main():
    """Quick health check."""
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
    for gm_uri in GRAPHMARTS:
        try:
            # Check graphmart status
            report = check_graphmart_status(api, gm_uri)

            if report.overall_status != ArtifactStatus.HEALTHY:
                logger.error(f"✗ {report.title}: {report.overall_status.value} - {report.error_message}")
                all_healthy = False

            # Check AnzoGraph connection
            azg = check_anzograph_connectivity(api, gm_uri)
            if not azg.is_connected:
                logger.error(f"✗ {report.title}: AnzoGraph not connected - {azg.error_message}")
                all_healthy = False

        except Exception as e:
            logger.error(f"✗ Failed to check {gm_uri}: {e}")
            all_healthy = False

    if all_healthy:
        print("✓ All systems healthy")
        sys.exit(0)
    else:
        print("✗ Health check failed - see errors above")
        sys.exit(1)


if __name__ == '__main__':
    main()
