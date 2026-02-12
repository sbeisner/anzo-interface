#!/usr/bin/env python3
"""
Infrastructure Monitoring Example Script

This script demonstrates how to monitor AGS/Anzo infrastructure components
that are available via the REST API:

✓ AVAILABLE via REST API:
  - Elasticsearch connectivity (inferred from layer status)
  - AnzoGraph connectivity (via graphmart activation status)
  - LDAP authentication health (via auth test)

✗ NOT AVAILABLE via REST API (require external tools):
  - AnzoGraph bandwidth/throughput
  - JVM memory utilization (requires JMX)
  - CPU utilization
  - Network bandwidth
  - Disk I/O metrics

See print_external_monitoring_guidance() for details on external monitoring.

Usage:
    python infrastructure_monitor_example.py
"""

import logging
import sys

from graphmart_manager import GraphmartManagerApi
from infrastructure_monitoring import (
    check_anzograph_connectivity,
    check_elasticsearch_connectivity,
    check_ldap_authentication,
    print_external_monitoring_guidance,
    run_infrastructure_health_check,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False

# Graphmarts to monitor
GRAPHMARTS = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
]


# =============================================================================
# EXAMPLE CHECKS
# =============================================================================

def example_1_elasticsearch_check(api: GraphmartManagerApi) -> None:
    """
    Example 1: Check Elasticsearch connectivity (inferred from graphmart status).

    Elasticsearch connectivity is not directly exposed via REST API, but
    ES-related failures appear in graphmart layer/step status.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 1: Elasticsearch Connectivity Check (Indirect)")
    logger.info("=" * 70)

    for graphmart_uri in GRAPHMARTS:
        try:
            title = api.get_title(graphmart_uri=graphmart_uri)
            logger.info(f"\nChecking Elasticsearch for: {title}")

            es_report = check_elasticsearch_connectivity(api, graphmart_uri)

            status_icon = "✓" if es_report.is_healthy else "✗"
            logger.info(
                f"{status_icon} Elasticsearch Health: "
                f"{'Healthy' if es_report.is_healthy else 'Issues Detected'}"
            )

            if es_report.failed_es_layers > 0:
                logger.warning(f"  └─ Failed ES-related layers: {es_report.failed_es_layers}")

            for error in es_report.error_messages:
                logger.error(f"  └─ {error}")

        except Exception as e:
            logger.error(f"Failed to check ES for {graphmart_uri}: {e}")

    logger.info("\nNote: This is an INDIRECT check. ES connectivity is inferred from")
    logger.info("layer/step failures that contain Elasticsearch-related errors.")


def example_2_anzograph_check(api: GraphmartManagerApi) -> None:
    """
    Example 2: Check AnzoGraph (AZG) connectivity.

    This checks whether graphmarts are successfully connected to their
    AnzoGraph lakehouse servers.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 2: AnzoGraph Connectivity Check")
    logger.info("=" * 70)

    for graphmart_uri in GRAPHMARTS:
        try:
            title = api.get_title(graphmart_uri=graphmart_uri)
            logger.info(f"\nChecking AnzoGraph for: {title}")

            azg_report = check_anzograph_connectivity(api, graphmart_uri)

            status_icon = "✓" if azg_report.is_connected else "✗"
            logger.info(
                f"{status_icon} AnzoGraph Connection: "
                f"{'Connected' if azg_report.is_connected else 'Disconnected'}"
            )

            if azg_report.azg_uri:
                logger.info(f"  └─ AZG Server: {azg_report.azg_uri}")

            logger.info(f"  └─ Graphmart Status: {azg_report.graphmart_status}")

            if azg_report.error_message:
                logger.warning(f"  └─ Issue: {azg_report.error_message}")

        except Exception as e:
            logger.error(f"Failed to check AZG for {graphmart_uri}: {e}")


def example_3_ldap_check() -> None:
    """
    Example 3: Check LDAP authentication health.

    This tests LDAP connectivity by attempting authentication and measuring
    response time. There is no dedicated LDAP status endpoint, so this
    serves as a proxy health check.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 3: LDAP Authentication Health Check (Indirect)")
    logger.info("=" * 70)

    logger.info("\nTesting LDAP authentication...")

    ldap_report = check_ldap_authentication(
        server=SERVER,
        username=USERNAME,
        password=PASSWORD,
        port=PORT,
        https=HTTPS,
        verify_ssl=VERIFY_SSL
    )

    status_icon = "✓" if ldap_report.is_authenticated else "✗"
    logger.info(
        f"{status_icon} LDAP Authentication: "
        f"{'Success' if ldap_report.is_authenticated else 'Failed'}"
    )
    logger.info(f"  └─ Response Time: {ldap_report.response_time_ms:.2f}ms")

    if ldap_report.error_message:
        logger.error(f"  └─ Error: {ldap_report.error_message}")

    logger.info("\nNote: This is an INDIRECT check. LDAP health is tested by")
    logger.info("attempting authentication and measuring response time.")


def example_4_comprehensive_check(api: GraphmartManagerApi) -> None:
    """
    Example 4: Run a comprehensive infrastructure health check.

    This runs all available infrastructure checks and provides a summary
    report suitable for monitoring dashboards or alerting systems.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 4: Comprehensive Infrastructure Health Check")
    logger.info("=" * 70)

    logger.info("\nRunning comprehensive health check...")
    logger.info("This may take a moment...\n")

    results = run_infrastructure_health_check(
        api=api,
        graphmart_uris=GRAPHMARTS,
        check_ldap=True
    )

    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("INFRASTRUCTURE HEALTH SUMMARY")
    logger.info("=" * 70)

    # Overall status
    overall_icon = "✓" if results['overall_healthy'] else "✗"
    logger.info(
        f"\n{overall_icon} Overall Status: "
        f"{'HEALTHY' if results['overall_healthy'] else 'ISSUES DETECTED'}"
    )

    # Elasticsearch summary
    es_icon = "✓" if results['elasticsearch_healthy'] else "✗"
    logger.info(f"\n{es_icon} Elasticsearch: {'Healthy' if results['elasticsearch_healthy'] else 'Issues'}")
    for detail in results['elasticsearch_details']:
        if not detail['is_healthy']:
            logger.warning(
                f"  └─ {detail['graphmart_uri']}: "
                f"{detail['failed_layers']} failed layer(s)"
            )

    # AnzoGraph summary
    azg_icon = "✓" if results['anzograph_healthy'] else "✗"
    logger.info(f"\n{azg_icon} AnzoGraph: {'Connected' if results['anzograph_healthy'] else 'Issues'}")
    for detail in results['anzograph_details']:
        if not detail['is_connected']:
            logger.warning(f"  └─ {detail['graphmart_uri']}: {detail['error']}")

    # LDAP summary
    if results['ldap_details']:
        ldap_icon = "✓" if results['ldap_healthy'] else "✗"
        ldap_status = 'Authenticated' if results['ldap_healthy'] else 'Failed'
        logger.info(
            f"\n{ldap_icon} LDAP Authentication: {ldap_status} "
            f"({results['ldap_details']['response_time_ms']:.2f}ms)"
        )
        if not results['ldap_healthy']:
            logger.error(f"  └─ {results['ldap_details']['error']}")

    logger.info("\n" + "=" * 70)

    # Exit with appropriate code
    if results['overall_healthy']:
        logger.info("✓ All infrastructure components are healthy")
        return True
    else:
        logger.error("✗ One or more infrastructure components have issues")
        return False


def example_5_monitoring_guidance() -> None:
    """
    Example 5: Display guidance for metrics not available via REST API.

    Many infrastructure metrics (bandwidth, memory, CPU) are not exposed
    via the AGS REST API and require external monitoring tools.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 5: External Monitoring Guidance")
    logger.info("=" * 70)

    print_external_monitoring_guidance()


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function - runs all infrastructure monitoring examples."""

    logger.info("=" * 70)
    logger.info("AGS/ANZO INFRASTRUCTURE MONITORING EXAMPLES")
    logger.info("=" * 70)

    # Initialize API
    logger.info("\nInitializing Graphmart Manager API...")
    api = GraphmartManagerApi(
        server=SERVER,
        username=USERNAME,
        password=PASSWORD,
        port=PORT,
        https=HTTPS,
        verify_ssl=VERIFY_SSL
    )

    try:
        # Run all examples
        example_1_elasticsearch_check(api)
        example_2_anzograph_check(api)
        example_3_ldap_check()

        # Comprehensive check returns boolean for health status
        all_healthy = example_4_comprehensive_check(api)

        # Show guidance for external monitoring
        example_5_monitoring_guidance()

        logger.info("\n" + "=" * 70)
        logger.info("All infrastructure monitoring examples completed!")
        logger.info("=" * 70)

        # Exit with appropriate code based on health check
        sys.exit(0 if all_healthy else 1)

    except Exception as e:
        logger.error(f"Infrastructure monitoring failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
