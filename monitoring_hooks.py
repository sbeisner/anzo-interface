"""
Monitoring Hooks for Altair Graph Studio (Anzo) Artifacts

This module provides convenient monitoring functions for tracking the status
and health of various Anzo artifacts including:
- Graphmarts (with layers and steps)
- AZG (AnzoGraph) connections
- ES (Entity Storage) and DU (Data Units) via graphmart status

These hooks can be used in monitoring scripts, health checks, CI/CD pipelines,
and automated alerting systems.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException

logger = logging.getLogger(__name__)


class ArtifactStatus(Enum):
    """Status enumeration for monitored artifacts."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class GraphmartStatusReport:
    """Detailed status report for a graphmart."""
    uri: str
    title: str
    status: str
    is_complete: bool
    is_online: bool
    failed_layers: int
    dirty_layers: int
    overall_status: ArtifactStatus
    timestamp: datetime
    error_message: Optional[str] = None


@dataclass
class LayerStatusReport:
    """Status report for a graphmart layer."""
    uri: str
    title: str
    enabled: bool
    has_error: bool
    error_message: Optional[str] = None


def check_graphmart_status(
    api: GraphmartManagerApi,
    graphmart_uri: str,
    include_layers: bool = False
) -> GraphmartStatusReport:
    """
    Check the status of a graphmart and return a detailed report.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to check.
        include_layers: If True, log detailed layer status (default: False).

    Returns:
        GraphmartStatusReport with current status information.

    Example:
        >>> api = GraphmartManagerApi(server='anzo.example.com', username='admin', password='pass')
        >>> report = check_graphmart_status(api, 'http://example.org/graphmart/production')
        >>> print(f"Status: {report.overall_status.value}")
    """
    try:
        title = api.get_title(graphmart_uri=graphmart_uri)
        status = api.status(graphmart_uri=graphmart_uri)
        status_details = api.status_details(graphmart_uri=graphmart_uri)

        is_complete = status_details.get("isComplete", False)
        is_online = "Online" in status
        failed_layers = status_details.get("failedLayers", 0)
        dirty_layers = status_details.get("dirtyLayers", 0)

        # Determine overall status
        if not is_online:
            overall_status = ArtifactStatus.OFFLINE
            error_message = f"Graphmart is {status}"
        elif failed_layers > 0:
            overall_status = ArtifactStatus.FAILED
            error_message = f"{failed_layers} layer(s) failed"
        elif dirty_layers > 0:
            overall_status = ArtifactStatus.DEGRADED
            error_message = f"{dirty_layers} layer(s) are dirty"
        elif is_online and is_complete:
            overall_status = ArtifactStatus.HEALTHY
            error_message = None
        else:
            overall_status = ArtifactStatus.DEGRADED
            error_message = "Processing in progress"

        # Log layer details if requested
        if include_layers and "childLayer" in status_details:
            for layer in status_details["childLayer"]:
                if layer.get("enabled"):
                    layer_status = "✓" if not layer.get("error") else "✗"
                    logger.info(f"  {layer_status} Layer: {layer.get('title', 'Unknown')}")

        return GraphmartStatusReport(
            uri=graphmart_uri,
            title=title,
            status=status,
            is_complete=is_complete,
            is_online=is_online,
            failed_layers=failed_layers,
            dirty_layers=dirty_layers,
            overall_status=overall_status,
            timestamp=datetime.now(),
            error_message=error_message
        )

    except Exception as e:
        logger.error(f"Failed to check graphmart status: {e}")
        return GraphmartStatusReport(
            uri=graphmart_uri,
            title="Unknown",
            status="Unknown",
            is_complete=False,
            is_online=False,
            failed_layers=0,
            dirty_layers=0,
            overall_status=ArtifactStatus.UNKNOWN,
            timestamp=datetime.now(),
            error_message=str(e)
        )


def check_graphmart_health(
    api: GraphmartManagerApi,
    graphmart_uri: str
) -> dict:
    """
    Perform a comprehensive health check on a graphmart.

    This function performs a deep health check that examines all layers
    and steps, logging detailed error information for any failures.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to check.

    Returns:
        Dictionary with 'failedLayers' and 'dirtyLayers' counts.

    Example:
        >>> health = check_graphmart_health(api, 'http://example.org/graphmart/production')
        >>> if health['failedLayers'] > 0:
        >>>     print(f"Warning: {health['failedLayers']} layers have failed")
    """
    try:
        return api.health_check(graphmart_uri=graphmart_uri)
    except Exception as e:
        logger.error(f"Health check failed for {graphmart_uri}: {e}")
        return {'failedLayers': -1, 'dirtyLayers': -1}


def get_layer_status(
    api: GraphmartManagerApi,
    graphmart_uri: str
) -> list[LayerStatusReport]:
    """
    Get status information for all layers in a graphmart.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart.

    Returns:
        List of LayerStatusReport objects for each layer.

    Example:
        >>> layers = get_layer_status(api, 'http://example.org/graphmart/production')
        >>> for layer in layers:
        >>>     print(f"{layer.title}: {'Enabled' if layer.enabled else 'Disabled'}")
    """
    try:
        status_details = api.status_details(graphmart_uri=graphmart_uri)
        layer_reports = []

        for layer in status_details.get("childLayer", []):
            error = layer.get("error")
            layer_reports.append(LayerStatusReport(
                uri=layer.get("uri", ""),
                title=layer.get("title", "Unknown"),
                enabled=layer.get("enabled", False),
                has_error=error is not None,
                error_message=error[:200] if error else None  # Truncate long errors
            ))

        return layer_reports

    except Exception as e:
        logger.error(f"Failed to get layer status: {e}")
        return []


def monitor_graphmarts(
    api: GraphmartManagerApi,
    graphmart_uris: list[str],
    interval: int = 60,
    duration: Optional[int] = None,
    callback: Optional[Callable[[GraphmartStatusReport], None]] = None
) -> None:
    """
    Continuously monitor multiple graphmarts at a specified interval.

    This function runs in a loop, checking the status of all specified
    graphmarts and optionally calling a callback function with each report.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uris: List of graphmart URIs to monitor.
        interval: Time in seconds between checks (default: 60).
        duration: Total monitoring duration in seconds, or None for infinite (default: None).
        callback: Optional function to call with each status report.

    Example:
        >>> def alert_on_failure(report: GraphmartStatusReport):
        >>>     if report.overall_status == ArtifactStatus.FAILED:
        >>>         send_alert(f"Graphmart {report.title} has failed!")
        >>>
        >>> monitor_graphmarts(
        >>>     api,
        >>>     ['http://example.org/graphmart/gm1', 'http://example.org/graphmart/gm2'],
        >>>     interval=300,  # Check every 5 minutes
        >>>     callback=alert_on_failure
        >>> )
    """
    start_time = time.time()
    iteration = 0

    try:
        while True:
            iteration += 1
            logger.info(f"=== Monitoring Check #{iteration} ===")

            for graphmart_uri in graphmart_uris:
                report = check_graphmart_status(api, graphmart_uri)

                # Log status
                status_icon = {
                    ArtifactStatus.HEALTHY: "✓",
                    ArtifactStatus.DEGRADED: "⚠",
                    ArtifactStatus.FAILED: "✗",
                    ArtifactStatus.OFFLINE: "○",
                    ArtifactStatus.UNKNOWN: "?"
                }.get(report.overall_status, "?")

                logger.info(
                    f"{status_icon} {report.title}: {report.overall_status.value} "
                    f"({report.status})"
                )

                if report.error_message:
                    logger.info(f"  └─ {report.error_message}")

                # Call callback if provided
                if callback:
                    try:
                        callback(report)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")

            # Check if duration limit reached
            if duration and (time.time() - start_time) >= duration:
                logger.info(f"Monitoring duration of {duration}s reached. Stopping.")
                break

            logger.info(f"Next check in {interval} seconds...")
            time.sleep(interval)

    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")


def check_azg_connection(
    api: GraphmartManagerApi,
    graphmart_uri: str
) -> dict:
    """
    Check the AZG (AnzoGraph) connection status for a graphmart.

    This function examines the graphmart's status details to determine
    if it is properly connected to an AZG lakehouse server.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to check.

    Returns:
        Dictionary with connection information:
        - 'connected': bool indicating if connected to AZG
        - 'azg_uri': URI of the connected AZG server (if available)
        - 'status': Current graphmart status

    Example:
        >>> azg_status = check_azg_connection(api, 'http://example.org/graphmart/production')
        >>> if azg_status['connected']:
        >>>     print(f"Connected to AZG: {azg_status['azg_uri']}")
    """
    try:
        status = api.status(graphmart_uri=graphmart_uri)
        status_details = api.status_details(graphmart_uri=graphmart_uri)

        # Check if graphmart is active (connected to AZG)
        # An active graphmart typically has "Online" status
        is_connected = "Online" in status

        return {
            'connected': is_connected,
            'azg_uri': status_details.get('staticAzgServer'),
            'status': status
        }

    except Exception as e:
        logger.error(f"Failed to check AZG connection: {e}")
        return {
            'connected': False,
            'azg_uri': None,
            'status': 'Unknown',
            'error': str(e)
        }


def wait_for_graphmart_ready(
    api: GraphmartManagerApi,
    graphmart_uri: str,
    timeout: int = 1000,
    check_interval: int = 5
) -> bool:
    """
    Wait for a graphmart to become ready (Online and complete).

    This is a simplified wrapper around block_until_ready that returns
    a boolean instead of raising exceptions.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to wait for.
        timeout: Maximum seconds to wait (default: 1000).
        check_interval: Seconds between status checks (default: 5).

    Returns:
        True if graphmart became ready, False if timeout or error.

    Example:
        >>> if wait_for_graphmart_ready(api, graphmart_uri, timeout=600):
        >>>     print("Graphmart is ready!")
        >>> else:
        >>>     print("Graphmart failed to become ready")
    """
    try:
        api.block_until_ready(graphmart_uri=graphmart_uri, timeout=timeout)
        return True
    except GraphmartManagerApiException as e:
        logger.error(f"Graphmart did not become ready: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error waiting for graphmart: {e}")
        return False
