#!/usr/bin/env python3
"""
Artifact Monitoring Example Script

This script demonstrates how to use the monitoring_hooks module to monitor
the status and health of Anzo artifacts including:
- Graphmarts (and their layers/steps)
- AZG (AnzoGraph) connections
- ES (Entity Storage) and DU (Data Units) via graphmart components

Usage:
    python monitor_artifacts_example.py

Configuration:
    Update the SERVER, USERNAME, PASSWORD, and GRAPHMARTS_TO_MONITOR
    variables below with your environment details.
"""

import logging
import sys
from dataclasses import dataclass

from graphmart_manager import GraphmartManagerApi
from monitoring_hooks import (
    ArtifactStatus,
    GraphmartStatusReport,
    check_azg_connection,
    check_graphmart_health,
    check_graphmart_status,
    get_layer_status,
    monitor_graphmarts,
    wait_for_graphmart_ready,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Server connection configuration
SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False

# Graphmarts to monitor
GRAPHMARTS_TO_MONITOR = [
    'http://cambridgesemantics.com/graphmart/graphmart1',
    'http://cambridgesemantics.com/graphmart/graphmart2',
    'http://cambridgesemantics.com/graphmart/graphmart3',
]


# =============================================================================
# MONITORING EXAMPLES
# =============================================================================

def example_1_basic_status_check(api: GraphmartManagerApi) -> None:
    """
    Example 1: Perform a basic status check on a single graphmart.

    This demonstrates the simplest monitoring use case - checking if a
    graphmart is healthy.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 1: Basic Status Check")
    logger.info("=" * 70)

    graphmart_uri = GRAPHMARTS_TO_MONITOR[0]

    report = check_graphmart_status(api, graphmart_uri, include_layers=False)

    logger.info(f"Graphmart: {report.title}")
    logger.info(f"Status: {report.status}")
    logger.info(f"Overall Health: {report.overall_status.value}")
    logger.info(f"Is Online: {report.is_online}")
    logger.info(f"Is Complete: {report.is_complete}")
    logger.info(f"Failed Layers: {report.failed_layers}")
    logger.info(f"Dirty Layers: {report.dirty_layers}")

    if report.error_message:
        logger.warning(f"Issue: {report.error_message}")


def example_2_detailed_health_check(api: GraphmartManagerApi) -> None:
    """
    Example 2: Perform a detailed health check that examines layers and steps.

    This provides deep visibility into which specific layers or steps have
    issues, useful for troubleshooting.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 2: Detailed Health Check with Layers")
    logger.info("=" * 70)

    graphmart_uri = GRAPHMARTS_TO_MONITOR[0]

    # Get basic status with layer details
    report = check_graphmart_status(api, graphmart_uri, include_layers=True)

    logger.info(f"\nGraphmart: {report.title}")
    logger.info(f"Overall Status: {report.overall_status.value}")

    # Perform comprehensive health check (logs detailed errors)
    logger.info("\nPerforming detailed health check...")
    health = check_graphmart_health(api, graphmart_uri)

    # Get individual layer status
    logger.info("\nLayer Status Details:")
    layers = get_layer_status(api, graphmart_uri)
    for layer in layers:
        status_icon = "✓" if not layer.has_error else "✗"
        enabled_text = "enabled" if layer.enabled else "disabled"
        logger.info(f"  {status_icon} {layer.title} ({enabled_text})")

        if layer.has_error and layer.error_message:
            logger.error(f"      Error: {layer.error_message}")


def example_3_azg_connection_check(api: GraphmartManagerApi) -> None:
    """
    Example 3: Check AZG (AnzoGraph) connection status.

    This verifies that graphmarts are properly connected to their
    AZG lakehouse servers.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 3: AZG Connection Status")
    logger.info("=" * 70)

    for graphmart_uri in GRAPHMARTS_TO_MONITOR:
        try:
            title = api.get_title(graphmart_uri=graphmart_uri)
            azg_status = check_azg_connection(api, graphmart_uri)

            connection_icon = "✓" if azg_status['connected'] else "✗"
            logger.info(f"\n{connection_icon} Graphmart: {title}")
            logger.info(f"  Connected: {azg_status['connected']}")
            logger.info(f"  Status: {azg_status['status']}")

            if azg_status.get('azg_uri'):
                logger.info(f"  AZG Server: {azg_status['azg_uri']}")

        except Exception as e:
            logger.error(f"Failed to check AZG connection for {graphmart_uri}: {e}")


def example_4_multiple_graphmart_monitoring(api: GraphmartManagerApi) -> None:
    """
    Example 4: Monitor multiple graphmarts and generate a summary report.

    This is useful for dashboards or periodic health checks across
    an entire environment.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 4: Multiple Graphmart Status Summary")
    logger.info("=" * 70)

    summary = {
        'healthy': 0,
        'degraded': 0,
        'failed': 0,
        'offline': 0,
        'unknown': 0
    }

    for graphmart_uri in GRAPHMARTS_TO_MONITOR:
        report = check_graphmart_status(api, graphmart_uri)

        # Update summary counts
        if report.overall_status == ArtifactStatus.HEALTHY:
            summary['healthy'] += 1
        elif report.overall_status == ArtifactStatus.DEGRADED:
            summary['degraded'] += 1
        elif report.overall_status == ArtifactStatus.FAILED:
            summary['failed'] += 1
        elif report.overall_status == ArtifactStatus.OFFLINE:
            summary['offline'] += 1
        else:
            summary['unknown'] += 1

        # Log individual status
        status_icon = {
            ArtifactStatus.HEALTHY: "✓",
            ArtifactStatus.DEGRADED: "⚠",
            ArtifactStatus.FAILED: "✗",
            ArtifactStatus.OFFLINE: "○",
            ArtifactStatus.UNKNOWN: "?"
        }.get(report.overall_status, "?")

        logger.info(
            f"{status_icon} {report.title}: {report.overall_status.value} - {report.status}"
        )

        if report.error_message:
            logger.info(f"    Issue: {report.error_message}")

    # Print summary
    logger.info("\n--- Summary ---")
    logger.info(f"Total Graphmarts: {len(GRAPHMARTS_TO_MONITOR)}")
    logger.info(f"Healthy: {summary['healthy']}")
    logger.info(f"Degraded: {summary['degraded']}")
    logger.info(f"Failed: {summary['failed']}")
    logger.info(f"Offline: {summary['offline']}")
    logger.info(f"Unknown: {summary['unknown']}")


def example_5_continuous_monitoring_with_callback(api: GraphmartManagerApi) -> None:
    """
    Example 5: Continuous monitoring with custom callback for alerting.

    This demonstrates how to set up ongoing monitoring that can trigger
    alerts or actions based on status changes.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 5: Continuous Monitoring with Alerts")
    logger.info("=" * 70)
    logger.info("Monitoring for 5 minutes (press Ctrl+C to stop earlier)...")
    logger.info("=" * 70)

    # Define a callback function for custom actions
    def alert_callback(report: GraphmartStatusReport) -> None:
        """
        Custom callback function that gets called for each status check.

        In a production environment, this could:
        - Send emails or Slack notifications
        - Write to a monitoring database
        - Trigger automated remediation
        - Update a dashboard
        """
        if report.overall_status == ArtifactStatus.FAILED:
            logger.error(
                f"🚨 ALERT: Graphmart {report.title} has FAILED! "
                f"Reason: {report.error_message}"
            )
            # In production, you would send an alert here:
            # send_email_alert(report)
            # post_to_slack(report)

        elif report.overall_status == ArtifactStatus.DEGRADED:
            logger.warning(
                f"⚠️  WARNING: Graphmart {report.title} is DEGRADED. "
                f"Reason: {report.error_message}"
            )

        elif report.overall_status == ArtifactStatus.OFFLINE:
            logger.error(
                f"📴 ALERT: Graphmart {report.title} is OFFLINE! "
                f"Status: {report.status}"
            )

    # Start continuous monitoring
    # This will run until the duration expires or user presses Ctrl+C
    monitor_graphmarts(
        api=api,
        graphmart_uris=GRAPHMARTS_TO_MONITOR,
        interval=30,  # Check every 30 seconds
        duration=300,  # Run for 5 minutes (300 seconds)
        callback=alert_callback
    )


def example_6_wait_for_ready(api: GraphmartManagerApi) -> None:
    """
    Example 6: Wait for a graphmart to become ready after reload.

    This is useful in automated workflows where you need to wait for
    a graphmart to finish processing before proceeding.
    """
    logger.info("\n" + "=" * 70)
    logger.info("EXAMPLE 6: Wait for Graphmart Ready")
    logger.info("=" * 70)

    graphmart_uri = GRAPHMARTS_TO_MONITOR[0]
    title = api.get_title(graphmart_uri=graphmart_uri)

    logger.info(f"Checking if {title} is ready...")

    # Check if graphmart is ready (non-blocking check)
    report = check_graphmart_status(api, graphmart_uri)

    if report.overall_status == ArtifactStatus.HEALTHY:
        logger.info(f"✓ Graphmart {title} is already ready")
    else:
        logger.info(f"⏳ Graphmart {title} is not ready yet: {report.status}")
        logger.info("Waiting for graphmart to become ready (timeout: 600s)...")

        # Wait for up to 10 minutes
        if wait_for_graphmart_ready(api, graphmart_uri, timeout=600):
            logger.info(f"✓ Graphmart {title} is now ready!")
        else:
            logger.error(f"✗ Graphmart {title} did not become ready within timeout")


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function - runs all monitoring examples."""

    logger.info("Initializing Graphmart Manager API")
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
        example_1_basic_status_check(api)
        example_2_detailed_health_check(api)
        example_3_azg_connection_check(api)
        example_4_multiple_graphmart_monitoring(api)
        example_6_wait_for_ready(api)

        # Example 5 is commented out by default as it runs continuously
        # Uncomment the line below to enable continuous monitoring
        # example_5_continuous_monitoring_with_callback(api)

        logger.info("\n" + "=" * 70)
        logger.info("All monitoring examples completed successfully!")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Monitoring failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
