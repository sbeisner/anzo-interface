#!/usr/bin/env python3
"""
Sequential Graphmart Reload Script

Reloads multiple graphmarts in sequence, ensuring each one completes
before the next one starts. This is useful when graphmarts have dependencies
on each other (e.g., graphmart 2 uses data from graphmart 1).

Usage:
    python reload_graphmarts_sequential.py

Configuration:
    Update the GRAPHMARTS list and server connection details below.
"""

import logging
import sys
from dataclasses import dataclass

from graphmart_manager import GraphmartManagerApi, GraphmartManagerApiException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Server connection configuration
SERVER = 'your-anzo-server.example.com'
PORT = '8443'
USERNAME = 'your-username'
PASSWORD = 'your-password'
HTTPS = True
VERIFY_SSL = False


@dataclass
class GraphmartConfig:
    """Configuration for a graphmart reload."""
    uri: str
    timeout: int  # Timeout in seconds


# Graphmarts to reload in order (each waits for the previous to complete)
# Replace these with your actual graphmart URIs and appropriate timeouts
GRAPHMARTS = [
    GraphmartConfig(
        uri='http://cambridgesemantics.com/graphmart/graphmart1',
        timeout=7200,  # 2 hours
    ),
    GraphmartConfig(
        uri='http://cambridgesemantics.com/graphmart/graphmart2',
        timeout=10800,  # 3 hours
    ),
    GraphmartConfig(
        uri='http://cambridgesemantics.com/graphmart/graphmart3',
        timeout=3600,  # 1 hour
    ),
]


def reload_graphmarts_sequential(
    api: GraphmartManagerApi,
    graphmarts: list[GraphmartConfig],
) -> None:
    """
    Reload graphmarts sequentially, waiting for each to complete before starting the next.

    Args:
        api: GraphmartManagerApi instance.
        graphmarts: List of GraphmartConfig objects specifying URI and timeout for each.

    Raises:
        GraphmartManagerApiException: If any graphmart fails to reload properly.
    """
    total = len(graphmarts)
    for i, config in enumerate(graphmarts, start=1):
        title = api.get_title(graphmart_uri=config.uri)
        timeout_hours = config.timeout / 3600
        logger.info(
            f'[{i}/{total}] Starting reload of graphmart: {title} '
            f'(timeout: {timeout_hours:.1f} hours)'
        )

        api.reload_and_wait(graphmart_uri=config.uri, timeout=config.timeout)

        logger.info(f'[{i}/{total}] Successfully completed reload of graphmart: {title}')

    logger.info(f'All {total} graphmarts reloaded successfully')


def main():
    logger.info('Initializing Graphmart Manager API')
    api = GraphmartManagerApi(
        server=SERVER,
        username=USERNAME,
        password=PASSWORD,
        port=PORT,
        https=HTTPS,
        verify_ssl=VERIFY_SSL
    )

    try:
        reload_graphmarts_sequential(api=api, graphmarts=GRAPHMARTS)
    except GraphmartManagerApiException as e:
        logger.error(f'Graphmart reload failed: {e}')
        sys.exit(1)
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
