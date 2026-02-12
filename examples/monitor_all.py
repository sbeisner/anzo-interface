#!/usr/bin/env python3
"""
Comprehensive Anzo Monitoring Example

This script demonstrates all monitoring capabilities available via the AGS REST API:
1. Graphmart status and health
2. Layer and step inspection
3. AnzoGraph connectivity
4. Elasticsearch connectivity (indirect)
5. LDAP authentication (indirect)
6. Continuous monitoring with alerts

Configure your environment below and run:
    python examples/monitor_all.py
"""

import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graphmart_manager import GraphmartManagerApi
from monitoring_hooks import (
    ArtifactStatus,
    check_graphmart_status,
    get_layer_status,
    monitor_graphmarts,
)
from infrastructure_monitoring import (
    check_anzograph_connectivity,
    check_elasticsearch_connectivity,
    check_ldap_authentication,
    run_infrastructure_health_check,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
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

# =============================================================================
# MONITORING EXAMPLES
# =============================================================================

def example_graphmart_status(api: GraphmartManagerApi) -> bool:
    """Check status of all graphmarts."""
    logger.info("\n" + "=" * 70)
    logger.info("GRAPHMART STATUS CHECK")
    logger.info("=" * 70)

    all_healthy = True
    for gm_uri in GRAPHMARTS:
        report = check_graphmart_status(api, gm_uri, include_layers=True)

        status_icon = {
            ArtifactStatus.HEALTHY: "✓",
            ArtifactStatus.DEGRADED: "⚠",
            ArtifactStatus.FAILED: "✗",
            ArtifactStatus.OFFLINE: "○",
            ArtifactStatus.UNKNOWN: "?"
        }.get(report.overall_status, "?")

        logger.info(
            f"\n{status_icon} {report.title}: {report.overall_status.value} ({report.status})"
        )

        if report.error_message:
            logger.warning(f"  └─ {report.error_message}")

        if report.failed_layers > 0 or report.dirty_layers > 0:
            logger.info(f"  └─ Failed: {report.failed_layers}, Dirty: {report.dirty_layers}")
            all_healthy = False

    return all_healthy


def example_infrastructure_health(api: GraphmartManagerApi) -> bool:
    """Run comprehensive infrastructure health check."""
    logger.info("\n" + "=" * 70)
    logger.info("INFRASTRUCTURE HEALTH CHECK")
    logger.info("=" * 70)

    results = run_infrastructure_health_check(
        api,
        graphmart_uris=GRAPHMARTS,
        check_ldap=True
    )

    # Print summary
    logger.info(f"\n{'✓' if results['overall_healthy'] else '✗'} Overall: {'HEALTHY' if results['overall_healthy'] else 'ISSUES DETECTED'}")

    # Elasticsearch
    es_icon = "✓" if results['elasticsearch_healthy'] else "✗"
    logger.info(f"{es_icon} Elasticsearch: {'Healthy' if results['elasticsearch_healthy'] else 'Issues detected'}")
    for detail in results['elasticsearch_details']:
        if not detail['is_healthy']:
            logger.warning(f"  └─ {detail['graphmart_uri']}: {len(detail['errors'])} error(s)")

    # AnzoGraph
    azg_icon = "✓" if results['anzograph_healthy'] else "✗"
    logger.info(f"{azg_icon} AnzoGraph: {'Connected' if results['anzograph_healthy'] else 'Issues detected'}")
    for detail in results['anzograph_details']:
        if not detail['is_connected']:
            logger.warning(f"  └─ {detail['graphmart_uri']}: {detail['error']}")

    # LDAP
    if results['ldap_details']:
        ldap_icon = "✓" if results['ldap_healthy'] else "✗"
        logger.info(
            f"{ldap_icon} LDAP: {'Authenticated' if results['ldap_healthy'] else 'Failed'} "
            f"({results['ldap_details']['response_time_ms']:.2f}ms)"
        )

    return results['overall_healthy']


def example_detailed_layer_inspection(api: GraphmartManagerApi) -> None:
    """Inspect individual layers for detailed error information."""
    logger.info("\n" + "=" * 70)
    logger.info("DETAILED LAYER INSPECTION")
    logger.info("=" * 70)

    for gm_uri in GRAPHMARTS[:1]:  # Just check first graphmart for demo
        try:
            title = api.get_title(graphmart_uri=gm_uri)
            logger.info(f"\nGraphmart: {title}")

            layers = get_layer_status(api, gm_uri)
            for layer in layers:
                status_icon = "✓" if not layer.has_error else "✗"
                enabled_text = "enabled" if layer.enabled else "disabled"
                logger.info(f"  {status_icon} {layer.title} ({enabled_text})")

                if layer.has_error and layer.error_message:
                    logger.error(f"      Error: {layer.error_message[:100]}...")

        except Exception as e:
            logger.error(f"Failed to inspect layers: {e}")


def run_all_checks(api: GraphmartManagerApi) -> int:
    """Run all monitoring checks and return exit code."""
    logger.info("=" * 70)
    logger.info("ANZO COMPREHENSIVE MONITORING")
    logger.info("=" * 70)

    try:
        # Run all checks
        graphmart_healthy = example_graphmart_status(api)
        infrastructure_healthy = example_infrastructure_health(api)
        example_detailed_layer_inspection(api)

        # Final summary
        logger.info("\n" + "=" * 70)
        logger.info("FINAL SUMMARY")
        logger.info("=" * 70)

        overall_healthy = graphmart_healthy and infrastructure_healthy

        if overall_healthy:
            logger.info("✓ All systems healthy")
            return 0
        else:
            logger.error("✗ One or more systems have issues")
            return 1

    except Exception as e:
        logger.error(f"Monitoring failed: {e}", exc_info=True)
        return 1


def main():
    """Main execution."""
    logger.info("Initializing Anzo Monitoring")

    # Initialize API
    api = GraphmartManagerApi(
        server=SERVER,
        username=USERNAME,
        password=PASSWORD,
        port=PORT,
        https=HTTPS,
        verify_ssl=VERIFY_SSL
    )

    # Run all checks
    exit_code = run_all_checks(api)

    logger.info("\n" + "=" * 70)
    logger.info(f"Monitoring complete - Exit code: {exit_code}")
    logger.info("=" * 70)

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
