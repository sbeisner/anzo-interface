"""
pyanzo_interface - Python interface for Altair Graph Studio (Anzo).

This package provides a programmatic interface for managing Anzo graphmarts,
layers, and steps without requiring the AGS UI. Designed for use in automation
pipelines, Databricks notebooks, and DevOps workflows.
"""

from .graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException
from .monitoring_hooks import (
    ArtifactStatus,
    GraphmartStatusReport,
    LayerStatusReport,
    check_azg_connection,
    check_graphmart_health,
    check_graphmart_status,
    get_layer_status,
    monitor_graphmarts,
    wait_for_graphmart_ready,
)
from .infrastructure_monitoring import (
    AnzoGraphConnectionReport,
    ElasticsearchHealthReport,
    LDAPHealthReport,
    check_anzograph_connectivity,
    check_elasticsearch_connectivity,
    check_ldap_authentication,
    print_external_monitoring_guidance,
    run_infrastructure_health_check,
)

__version__ = "1.0.0"
__all__ = [
    "GraphmartManagerApi",
    "GraphmartManagerApiException",
    # Monitoring hooks
    "ArtifactStatus",
    "GraphmartStatusReport",
    "LayerStatusReport",
    "check_azg_connection",
    "check_graphmart_health",
    "check_graphmart_status",
    "get_layer_status",
    "monitor_graphmarts",
    "wait_for_graphmart_ready",
    # Infrastructure monitoring
    "AnzoGraphConnectionReport",
    "ElasticsearchHealthReport",
    "LDAPHealthReport",
    "check_anzograph_connectivity",
    "check_elasticsearch_connectivity",
    "check_ldap_authentication",
    "print_external_monitoring_guidance",
    "run_infrastructure_health_check",
]
