"""
Infrastructure Monitoring for Altair Graph Studio (Anzo)

This module provides infrastructure-level monitoring for AGS/Anzo environments,
implementing capabilities that are available through the AGS REST API and
providing guidance for capabilities that require external monitoring tools.

IMPORTANT: The AGS REST API is primarily focused on data management operations
rather than infrastructure monitoring. System-level metrics (CPU, memory, bandwidth)
are not exposed via REST API and require alternative monitoring approaches.

Available via REST API:
- Elasticsearch connectivity (inferred from layer/step status)
- AnzoGraph connectivity (via graphmart activation status)
- LDAP authentication health (via authentication test calls)
- Graphmart health and availability

NOT Available via REST API (require external monitoring):
- AnzoGraph bandwidth/throughput metrics
- JVM memory utilization (requires JMX)
- CPU utilization
- Disk I/O metrics
- Network bandwidth
- Query performance metrics
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException

logger = logging.getLogger(__name__)


@dataclass
class ElasticsearchHealthReport:
    """Health report for Elasticsearch connectivity inferred from graphmart status."""
    is_healthy: bool
    failed_es_layers: int
    error_messages: list[str]
    timestamp: datetime


@dataclass
class LDAPHealthReport:
    """Health report for LDAP authentication."""
    is_authenticated: bool
    response_time_ms: float
    error_message: Optional[str]
    timestamp: datetime


@dataclass
class AnzoGraphConnectionReport:
    """Health report for AnzoGraph (AZG) connectivity."""
    is_connected: bool
    azg_uri: Optional[str]
    graphmart_status: str
    error_message: Optional[str]
    timestamp: datetime


# =============================================================================
# ELASTICSEARCH CONNECTIVITY MONITORING
# =============================================================================

def check_elasticsearch_connectivity(
    api: GraphmartManagerApi,
    graphmart_uri: str
) -> ElasticsearchHealthReport:
    """
    Check Elasticsearch connectivity by examining graphmart layer/step status.

    Elasticsearch connectivity issues manifest as layer or step failures in
    graphmarts that use Elasticsearch for indexing. This function analyzes
    the detailed status to identify ES-related failures.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to check.

    Returns:
        ElasticsearchHealthReport with connectivity status.

    Example:
        >>> api = GraphmartManagerApi(server='anzo.example.com', username='admin', password='pw')
        >>> es_report = check_elasticsearch_connectivity(api, 'http://example.org/graphmart/prod')
        >>> if not es_report.is_healthy:
        >>>     print(f"Elasticsearch issues detected: {es_report.error_messages}")

    Note:
        This is an INDIRECT check. Elasticsearch connectivity is not exposed
        as a dedicated endpoint. This function infers ES health from layer
        failures that mention Elasticsearch-related errors.
    """
    try:
        status_details = api.status_details(graphmart_uri=graphmart_uri)

        es_related_errors = []
        failed_es_layers = 0

        # Keywords that indicate Elasticsearch-related issues
        es_keywords = [
            'elasticsearch',
            'elastic',
            'es index',
            'es indexing',
            'indexing service',
            'search index'
        ]

        # Check each layer for ES-related errors
        for layer in status_details.get('childLayer', []):
            if layer.get('enabled'):
                error = layer.get('error', '').lower()

                # Check if error mentions Elasticsearch
                if error and any(keyword in error for keyword in es_keywords):
                    failed_es_layers += 1
                    # Truncate long error messages
                    error_summary = layer.get('error', '')[:200]
                    es_related_errors.append(
                        f"Layer '{layer.get('title', 'Unknown')}': {error_summary}"
                    )

                # Also check steps within the layer
                for step in layer.get('child', []):
                    if step.get('enabled'):
                        step_error = step.get('error', '').lower()
                        if step_error and any(keyword in step_error for keyword in es_keywords):
                            error_summary = step.get('error', '')[:200]
                            es_related_errors.append(
                                f"Step '{step.get('title', 'Unknown')}': {error_summary}"
                            )

        is_healthy = failed_es_layers == 0 and len(es_related_errors) == 0

        return ElasticsearchHealthReport(
            is_healthy=is_healthy,
            failed_es_layers=failed_es_layers,
            error_messages=es_related_errors,
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"Failed to check Elasticsearch connectivity: {e}")
        return ElasticsearchHealthReport(
            is_healthy=False,
            failed_es_layers=-1,
            error_messages=[str(e)],
            timestamp=datetime.now()
        )


# =============================================================================
# LDAP AUTHENTICATION MONITORING
# =============================================================================

def check_ldap_authentication(
    server: str,
    username: str,
    password: str,
    port: str = '8443',
    https: bool = True,
    verify_ssl: bool = False
) -> LDAPHealthReport:
    """
    Check LDAP authentication health by attempting authentication.

    This function tests LDAP connectivity by making an authenticated API
    call and measuring response time. This serves as a proxy for LDAP
    health since there's no dedicated LDAP status endpoint.

    Args:
        server: Anzo server hostname or IP address.
        username: Username for LDAP authentication.
        password: Password for LDAP authentication.
        port: Server port (default: '8443').
        https: Use HTTPS if True (default: True).
        verify_ssl: Verify SSL certificates (default: False).

    Returns:
        LDAPHealthReport with authentication status and response time.

    Example:
        >>> report = check_ldap_authentication(
        >>>     server='anzo.example.com',
        >>>     username='testuser',
        >>>     password='testpass'
        >>> )
        >>> if report.is_authenticated:
        >>>     print(f"LDAP auth successful in {report.response_time_ms}ms")
        >>> else:
        >>>     print(f"LDAP auth failed: {report.error_message}")

    Note:
        This is an INDIRECT check. There is no dedicated LDAP status endpoint.
        This function tests authentication by making a simple API call and
        measuring whether authentication succeeds and how long it takes.
    """
    prefix = 'https' if https else 'http'
    # Use a lightweight endpoint for auth testing
    url = f'{prefix}://{server}:{port}/api/graphmarts'

    start_time = time.time()

    try:
        response = requests.get(
            url,
            headers={'accept': 'application/json'},
            auth=HTTPBasicAuth(username, password),
            timeout=30,
            verify=verify_ssl
        )

        response_time_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            return LDAPHealthReport(
                is_authenticated=True,
                response_time_ms=response_time_ms,
                error_message=None,
                timestamp=datetime.now()
            )
        else:
            return LDAPHealthReport(
                is_authenticated=False,
                response_time_ms=response_time_ms,
                error_message=f"HTTP {response.status_code}: {response.reason}",
                timestamp=datetime.now()
            )

    except requests.exceptions.Timeout:
        response_time_ms = (time.time() - start_time) * 1000
        return LDAPHealthReport(
            is_authenticated=False,
            response_time_ms=response_time_ms,
            error_message="Authentication request timed out",
            timestamp=datetime.now()
        )

    except requests.exceptions.ConnectionError as e:
        response_time_ms = (time.time() - start_time) * 1000
        return LDAPHealthReport(
            is_authenticated=False,
            response_time_ms=response_time_ms,
            error_message=f"Connection error: {str(e)}",
            timestamp=datetime.now()
        )

    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return LDAPHealthReport(
            is_authenticated=False,
            response_time_ms=response_time_ms,
            error_message=str(e),
            timestamp=datetime.now()
        )


# =============================================================================
# ANZOGRAPH CONNECTIVITY MONITORING
# =============================================================================

def check_anzograph_connectivity(
    api: GraphmartManagerApi,
    graphmart_uri: str
) -> AnzoGraphConnectionReport:
    """
    Check AnzoGraph (AZG) connectivity for a graphmart.

    This function examines whether a graphmart is successfully connected
    to its AnzoGraph lakehouse server.

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uri: URI of the graphmart to check.

    Returns:
        AnzoGraphConnectionReport with AZG connectivity status.

    Example:
        >>> api = GraphmartManagerApi(server='anzo.example.com', username='admin', password='pw')
        >>> azg_report = check_anzograph_connectivity(api, 'http://example.org/graphmart/prod')
        >>> if azg_report.is_connected:
        >>>     print(f"Connected to AZG: {azg_report.azg_uri}")
        >>> else:
        >>>     print(f"AZG connection issue: {azg_report.error_message}")
    """
    try:
        status = api.status(graphmart_uri=graphmart_uri)
        status_details = api.status_details(graphmart_uri=graphmart_uri)

        azg_uri = status_details.get('staticAzgServer')
        is_online = 'Online' in status

        # Consider connected if online and has AZG URI
        is_connected = is_online and azg_uri is not None

        error_message = None
        if not is_connected:
            if not azg_uri:
                error_message = "No AZG server configured"
            elif not is_online:
                error_message = f"Graphmart is {status}"

        return AnzoGraphConnectionReport(
            is_connected=is_connected,
            azg_uri=azg_uri,
            graphmart_status=status,
            error_message=error_message,
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"Failed to check AnzoGraph connectivity: {e}")
        return AnzoGraphConnectionReport(
            is_connected=False,
            azg_uri=None,
            graphmart_status="Unknown",
            error_message=str(e),
            timestamp=datetime.now()
        )


# =============================================================================
# COMPREHENSIVE INFRASTRUCTURE CHECK
# =============================================================================

def run_infrastructure_health_check(
    api: GraphmartManagerApi,
    graphmart_uris: list[str],
    check_ldap: bool = True
) -> dict:
    """
    Run a comprehensive infrastructure health check.

    This function checks all available infrastructure components:
    - Elasticsearch connectivity (inferred from graphmart status)
    - AnzoGraph connectivity
    - LDAP authentication (if enabled)

    Args:
        api: GraphmartManagerApi instance.
        graphmart_uris: List of graphmart URIs to check.
        check_ldap: Whether to test LDAP authentication (default: True).

    Returns:
        Dictionary with health check results for all components.

    Example:
        >>> api = GraphmartManagerApi(server='anzo.example.com', username='admin', password='pw')
        >>> results = run_infrastructure_health_check(
        >>>     api,
        >>>     ['http://example.org/graphmart/gm1', 'http://example.org/graphmart/gm2']
        >>> )
        >>> print(f"Elasticsearch: {'✓' if results['elasticsearch_healthy'] else '✗'}")
        >>> print(f"AnzoGraph: {'✓' if results['anzograph_healthy'] else '✗'}")
        >>> print(f"LDAP: {'✓' if results['ldap_healthy'] else '✗'}")
    """
    results = {
        'timestamp': datetime.now(),
        'elasticsearch_healthy': True,
        'anzograph_healthy': True,
        'ldap_healthy': True,
        'elasticsearch_details': [],
        'anzograph_details': [],
        'ldap_details': None,
        'overall_healthy': True
    }

    # Check Elasticsearch connectivity for each graphmart
    logger.info("Checking Elasticsearch connectivity...")
    for graphmart_uri in graphmart_uris:
        es_report = check_elasticsearch_connectivity(api, graphmart_uri)
        results['elasticsearch_details'].append({
            'graphmart_uri': graphmart_uri,
            'is_healthy': es_report.is_healthy,
            'failed_layers': es_report.failed_es_layers,
            'errors': es_report.error_messages
        })

        if not es_report.is_healthy:
            results['elasticsearch_healthy'] = False
            results['overall_healthy'] = False
            logger.warning(
                f"Elasticsearch issues detected in {graphmart_uri}: "
                f"{len(es_report.error_messages)} error(s)"
            )

    # Check AnzoGraph connectivity for each graphmart
    logger.info("Checking AnzoGraph connectivity...")
    for graphmart_uri in graphmart_uris:
        azg_report = check_anzograph_connectivity(api, graphmart_uri)
        results['anzograph_details'].append({
            'graphmart_uri': graphmart_uri,
            'is_connected': azg_report.is_connected,
            'azg_uri': azg_report.azg_uri,
            'status': azg_report.graphmart_status,
            'error': azg_report.error_message
        })

        if not azg_report.is_connected:
            results['anzograph_healthy'] = False
            results['overall_healthy'] = False
            logger.warning(
                f"AnzoGraph connection issue for {graphmart_uri}: "
                f"{azg_report.error_message}"
            )

    # Check LDAP authentication
    if check_ldap:
        logger.info("Checking LDAP authentication...")
        ldap_report = check_ldap_authentication(
            server=api.server,
            username=api.username,
            password=api.password,
            port=api.port,
            https=(api.prefix == 'https'),
            verify_ssl=api.verify_ssl
        )

        results['ldap_details'] = {
            'is_authenticated': ldap_report.is_authenticated,
            'response_time_ms': ldap_report.response_time_ms,
            'error': ldap_report.error_message
        }

        if not ldap_report.is_authenticated:
            results['ldap_healthy'] = False
            results['overall_healthy'] = False
            logger.warning(f"LDAP authentication failed: {ldap_report.error_message}")

    return results


# =============================================================================
# MONITORING GUIDANCE FOR NON-API METRICS
# =============================================================================

def print_external_monitoring_guidance() -> None:
    """
    Print guidance for monitoring capabilities not available via REST API.

    This function provides recommendations for monitoring infrastructure
    metrics that cannot be obtained through the AGS REST API.
    """
    guidance = """
================================================================================
EXTERNAL MONITORING GUIDANCE
================================================================================

The following infrastructure metrics are NOT available via the AGS REST API
and require external monitoring tools or JMX access:

1. ANZOGRAPH BANDWIDTH & THROUGHPUT
   - Not exposed via REST API
   - Recommendations:
     * Use network monitoring tools (Prometheus node_exporter, Datadog, etc.)
     * Monitor network interface metrics on AnzoGraph host
     * Use SPARQL query performance logs for query-level metrics
     * Contact Altair support for AnzoGraph-specific monitoring solutions

2. MEMORY UTILIZATION (JVM)
   - Not exposed via REST API (requires JMX)
   - Recommendations:
     * Enable JMX on Anzo server (typically port 1099)
     * Use JMX monitoring tools: JConsole, VisualVM, Prometheus JMX Exporter
     * Monitor these MBeans:
       - java.lang:type=Memory (heap/non-heap usage)
       - java.lang:type=GarbageCollector
       - java.lang:type=Threading
     * Example Prometheus JMX Exporter config available

3. CPU UTILIZATION
   - Not exposed via REST API
   - Recommendations:
     * Use OS-level monitoring: top, htop, sar
     * Use APM tools: Datadog, New Relic, AppDynamics
     * Use Prometheus node_exporter for metrics collection

4. QUERY PERFORMANCE METRICS
   - Not exposed via REST API
   - Recommendations:
     * Enable query logging in AnzoGraph
     * Parse query logs for performance analysis
     * Use SPARQL endpoint response times as proxy metrics
     * Contact Altair for query performance monitoring tools

5. NETWORK BANDWIDTH
   - Not exposed via REST API
   - Recommendations:
     * Use network monitoring: iftop, nethogs, vnstat
     * Use SNMP monitoring for network switches
     * Use cloud provider network metrics (AWS CloudWatch, etc.)

6. DISK I/O METRICS
   - Not exposed via REST API
   - Recommendations:
     * Use OS tools: iostat, iotop
     * Monitor disk space used by graphmart data directories
     * Use Prometheus node_exporter disk metrics

WHAT IS AVAILABLE VIA REST API:
- Graphmart health status (Online/Offline)
- Layer and step failures (indicates ES/processing issues)
- AnzoGraph connectivity (via graphmart activation status)
- LDAP authentication (via auth test calls)

For comprehensive infrastructure monitoring, integrate AGS with:
- Prometheus + Grafana
- Datadog
- New Relic
- Elastic Stack (ELK)
- Your organization's existing monitoring platform

================================================================================
"""
    print(guidance)
