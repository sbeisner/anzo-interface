"""
Graphmart Manager API - Python interface for Altair Graph Studio (Anzo).

This module provides a programmatic interface to manage graphmarts, layers,
and steps in Altair Graph Studio without requiring the AGS UI.
"""

import json
import logging
import os
import time
import urllib.parse
import uuid
from datetime import timedelta
from typing import Optional, Union

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class GraphmartManagerApiException(Exception):
    """Exception raised for Graphmart Manager API errors."""

    def __init__(self, message: str = "Graphmart Manager API Exception"):
        super().__init__(message)


class GraphmartManagerApi:
    """
    API client for managing Altair Graph Studio (Anzo) graphmarts.

    Provides methods for:
    - Graphmart lifecycle management (activate, deactivate, refresh, reload)
    - Layer management (create, enable, disable, move)
    - Step management (enable, disable, update)
    - Status monitoring and health checks
    """

    OPERATION_TYPE = ['graphmarts', 'layers', 'steps']
    REQUEST_TIMEOUT = 180
    SLEEP_TIME = 0
    STATUS = 'status'
    ACTIVATE = 'activate'
    DEACTIVATE = 'deactivate'
    REFRESH = 'refresh'
    RELOAD = 'reload'
    LAYERS = 'layers'

    CANCEL_QUERY_SERVICE_URI = 'http://openanzo.org/semanticServices/datasources#cancelQuery'
    INFLIGHT_QUERIES_SPARQL = """
SELECT ?operationId ?datasource
FROM <http://cambridgesemantics.com/datasource/SystemTables/InflightQueries>
WHERE {
    ?query <http://openanzo.org/ontologies/2008/07/System#operationId> ?operationId ;
           <http://openanzo.org/ontologies/2008/07/System#datasource> ?datasource .
}
""".strip()

    CANCEL_PAYLOAD_TEMPLATE = """\
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix dc: <http://purl.org/dc/elements/1.1/> .
@prefix dcterms: <http://purl.org/dc/terms/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix system: <http://openanzo.org/ontologies/2008/07/System#> .
@prefix anzo: <http://openanzo.org/ontologies/2008/07/Anzo#> .
@prefix ld: <http://cambridgesemantics.com/ontologies/2009/05/LinkedData#> .
@prefix graphmart: <http://cambridgesemantics.com/ontologies/Graphmarts#> .

<http://serviceRequest{request_uuid}> {{
    <http://serviceRequest{request_uuid}> a system:DatasourceRequest ;
        system:datasource <{datasource_uri}> ;
        system:operationId "{operation_id}" .
}}"""

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        port: str = '8443',
        https: bool = True,
        verify_ssl: bool = False
    ):
        """
        Initialize the Graphmart Manager API client.

        Args:
            server: Anzo server hostname or IP address.
            username: Username for authentication.
            password: Password for authentication.
            port: Server port (default: '8443').
            https: Use HTTPS if True, HTTP if False (default: True).
            verify_ssl: Verify SSL certificates (default: False for self-signed certs).
        """
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.prefix = 'https' if https else 'http'
        self.verify_ssl = verify_ssl

    def _send_get(
        self,
        op_type: int,
        uri: str,
        endpoint: Optional[str] = None,
        query: Optional[str] = None
    ) -> requests.Response:
        url = f'{self.prefix}://{self.server}:{self.port}/api/{self.OPERATION_TYPE[op_type]}/' \
              f'{urllib.parse.quote_plus(uri)}'
        if endpoint:
            url += f'/{endpoint}'
        if query:
            url += f'?{query}'
        headers = {'accept': 'application/json'}
        response = requests.get(
            url,
            headers=headers,
            auth=HTTPBasicAuth(self.username, self.password),
            timeout=self.REQUEST_TIMEOUT,
            verify=self.verify_ssl
        )
        response.raise_for_status()
        return response

    def _send_post(
        self,
        op_type: int,
        uri: str,
        endpoint: Optional[str] = None,
        query: Optional[str] = None,
        data: Optional[dict] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        url = f'{self.prefix}://{self.server}:{self.port}/api/{self.OPERATION_TYPE[op_type]}/' \
              f'{urllib.parse.quote_plus(uri)}'
        if endpoint:
            url += f'/{endpoint}'
        if query:
            url += f'?{query}'
        headers = {'accept': 'application/json'}
        if data:
            headers['Content-Type'] = 'application/json'
            response = requests.post(
                url,
                headers=headers,
                auth=HTTPBasicAuth(self.username, self.password),
                data=json.dumps(data),
                timeout=timeout or self.REQUEST_TIMEOUT,
                verify=self.verify_ssl
            )
        else:
            response = requests.post(
                url,
                headers=headers,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.REQUEST_TIMEOUT,
                verify=self.verify_ssl
            )
        response.raise_for_status()
        return response

    def _send_patch(
        self,
        op_type: int,
        uri: str,
        endpoint: Optional[str] = None,
        data: Optional[Union[dict, list]] = None
    ) -> requests.Response:
        url = f'{self.prefix}://{self.server}:{self.port}/api/{self.OPERATION_TYPE[op_type]}/' \
              f'{urllib.parse.quote_plus(uri)}'
        if endpoint:
            url += f'/{endpoint}'
        headers = {'accept': 'application/json', 'Content-Type': 'application/json'}
        if data:
            response = requests.patch(
                url,
                headers=headers,
                auth=HTTPBasicAuth(self.username, self.password),
                data=json.dumps(data),
                timeout=self.REQUEST_TIMEOUT,
                verify=self.verify_ssl
            )
        else:
            response = requests.patch(
                url,
                headers=headers,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.REQUEST_TIMEOUT,
                verify=self.verify_ssl
            )
        response.raise_for_status()
        return response

    def refresh(self, graphmart_uri: str) -> None:
        logger.debug(f'Refreshing graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        self._send_post(op_type=0, uri=graphmart_uri, endpoint=self.REFRESH)
        time.sleep(self.SLEEP_TIME)

    def reload(self, graphmart_uri: str) -> None:
        logger.debug(f'Reloading graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        self._send_post(op_type=0, uri=graphmart_uri, endpoint=self.RELOAD)
        time.sleep(self.SLEEP_TIME)

    def reload_and_wait(self, graphmart_uri: str, timeout: int = 1000) -> None:
        """
        Reload a graphmart and block until it is ready.

        This is a convenience method that combines reload() and block_until_ready()
        for use cases where you need to wait for the reload to complete before
        proceeding (e.g., sequential graphmart reloads with dependencies).

        Args:
            graphmart_uri: URI of the graphmart to reload.
            timeout: Maximum seconds to wait for the graphmart to be ready (default: 1000).

        Raises:
            GraphmartManagerApiException: If the graphmart fails to become ready
                within the timeout, or if there are failed/dirty layers.
        """
        title = self.get_title(graphmart_uri=graphmart_uri)
        logger.info(f'Starting reload of graphmart: {title}')
        self.reload(graphmart_uri=graphmart_uri)
        self.block_until_ready(graphmart_uri=graphmart_uri, timeout=timeout)
        logger.info(f'Reload complete for graphmart: {title}')

    def activate(self, graphmart_uri: str, azg_uri: str) -> None:
        logger.debug(f'Activating graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        self._send_post(op_type=0, uri=graphmart_uri, endpoint=self.ACTIVATE, data={"staticAzgServer": azg_uri})
        time.sleep(self.SLEEP_TIME)

    def deactivate(self, graphmart_uri: str, timeout: int = 60) -> None:
        logger.debug(f'Deactivating graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        self._send_post(op_type=0, uri=graphmart_uri, endpoint=self.DEACTIVATE, timeout=timeout)
        time.sleep(self.SLEEP_TIME)

    def is_complete(self, graphmart_uri: str) -> bool:
        status_graph = self.status_details(graphmart_uri=graphmart_uri)
        return status_graph.get("isComplete", False)

    def status(self, graphmart_uri: str) -> str:
        return self._send_get(op_type=0, uri=graphmart_uri, endpoint=self.STATUS).json()['status'].split('#')[1]

    def status_details(self, graphmart_uri: str) -> dict:
        # logger.debug(f'Getting status details of graphmart: {self.get_title(graphmart_uri)}')
        return self._send_get(op_type=0, uri=graphmart_uri, endpoint=self.STATUS, query='detail=true').json()

    def health_check(self, graphmart_uri: str) -> dict:
        logger.debug(f'Performing health check of graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        status_graph = self.status_details(graphmart_uri=graphmart_uri)
        logger.info(f'Found {status_graph["failedLayers"]} failed layers and '
                    f'{status_graph["dirtyLayers"]} dirty layers')
        for layer in status_graph['childLayer']:
            if layer['enabled']:
                if error := layer.get('error'):
                    logger.info(f'Layer [ {layer["title"]} ] failed with error:\n'
                                f'{os.linesep.join(error.split(os.linesep)[:5])}...')
                    for step in layer['child']:
                        if step['enabled']:
                            if error := step.get('error'):
                                logger.info(f'Step [ {layer["title"]} ] failed with error:\n'
                                            f'{os.linesep.join(error.split(os.linesep)[:5])}...')
        return {'failedLayers': status_graph['failedLayers'], 'dirtyLayers': status_graph['dirtyLayers']}

    def get_title(self, graphmart_uri: str) -> str:
        return self._send_get(op_type=0, uri=graphmart_uri).json()['title']

    def block_until_ready(self, graphmart_uri: str, timeout: int = 1000, extra_message: str = '') -> None:
        title = self.get_title(graphmart_uri=graphmart_uri)
        logger.debug(f'Waiting {timeout}s for graphmart {title} to be ready')
        online = False
        complete = False
        log_interval = 300  # 5 minutes in seconds
        start_time = time.time()
        next_log_time = start_time
        while time.time() - start_time < timeout:
            try:
                online = 'Online' in self.status(graphmart_uri=graphmart_uri)
                complete = self.is_complete(graphmart_uri=graphmart_uri)
                if online and complete:
                    break  # Exit loop if online and complete
            except requests.exceptions.HTTPError:
                logger.info("Graphmart is unavailable for a status check, sleeping before retrying")
                time.sleep(30)  # Catch HTTPError and sleep for 30 seconds
            else:
                current_time = time.time()
                if current_time >= next_log_time:
                    logger.info(f"Running status check loop, "
                                f"elapsed time: {str(timedelta(seconds=current_time - start_time)).split('.')[0]}")
                    next_log_time = current_time + log_interval  # Update next log time
                time.sleep(5)  # If no exception occurred, sleep for 5 seconds before retrying
        if not online:  # Graphmart must have timed out
            raise GraphmartManagerApiException(f'{extra_message}\nGraphmart {title} not ready after {timeout} seconds, '
                                               f'final status: {self.status(graphmart_uri=graphmart_uri)}')
        logger.info(f'Graphmart status: {self.status(graphmart_uri=graphmart_uri)}')
        logger.info(f'Graphmart is complete: {complete}')
        logger.info(f"Total wait time: {str(timedelta(seconds=time.time() - start_time)).split('.')[0]}")
        health_check = self.health_check(graphmart_uri=graphmart_uri)
        if health_check['failedLayers'] > 0:
            raise GraphmartManagerApiException(f'Graphmart {title} has {health_check["failedLayers"]} failed layers')
        elif health_check['dirtyLayers'] > 0:
            raise GraphmartManagerApiException(f'Graphmart {title} has {health_check["dirtyLayers"]} dirty layers')
        logger.info(f'Graphmart: {title} is Online')

    def graphmart_layers(self, graphmart_uri: str) -> dict:
        logger.debug(f'Getting layers of graphmart: {self.get_title(graphmart_uri=graphmart_uri)}')
        return self._send_get(op_type=0, uri=graphmart_uri, endpoint=self.LAYERS).json()

    def create_layer(self, graphmart_uri: str, layer_configuration: dict) -> str:
        logger.debug(f'Creating layer on graphmart: {graphmart_uri}')
        return self._send_post(op_type=0, uri=graphmart_uri, endpoint=self.LAYERS,
                               data=layer_configuration).json()['uri']

    def move_layer(self, graphmart_uri: str, target_layer: str, position_layer: str, before: bool) -> None:
        place = 'before' if before else 'after'
        logger.debug(f'Moving layer {target_layer} {place} {position_layer}')
        endpoint = f'{self.LAYERS}/{urllib.parse.quote_plus(target_layer)}/move'
        self._send_post(op_type=0, uri=graphmart_uri, endpoint=endpoint, query=f'{place}={position_layer}')
        time.sleep(self.SLEEP_TIME)

    def enable_layers(self, graphmart_uri: str, layer_uris: list = None, steps: bool = True) -> None:
        logger.debug(f'Enabling layers: {layer_uris or "ALL"} with steps: {steps}')
        endpoint = f'enableLayers?{"includeSteps=true&" if steps else ""}failOnError=true'
        self._send_patch(op_type=0, uri=graphmart_uri, endpoint=endpoint, data=layer_uris)

    def disable_layers(self, graphmart_uri: str, layer_uris: list = None, steps: bool = True) -> None:
        logger.debug(f'Disabling layers: {layer_uris or "ALL"} with steps: {steps}')
        endpoint = f'disableLayers?{"includeSteps=true&" if steps else ""}failOnError=true'
        self._send_patch(op_type=0, uri=graphmart_uri, endpoint=endpoint, data=layer_uris)

    def enable_layer_steps(self, layer_uri: str, step_uris: list = None,
                           include_layer: bool = True, fail_on_error: bool = True) -> None:
        logger.debug(f'Enabling steps: {step_uris or "ALL"} of layer: {layer_uri}')
        endpoint = (f'enableSteps?'
                    f'includeLayer={"true" if include_layer else "false"}&'
                    f'failOnError={"true" if fail_on_error else "false"}')
        self._send_patch(op_type=1, uri=layer_uri, endpoint=endpoint, data=step_uris)

    def disable_layer_steps(self, layer_uri: str, step_uris: list = None,
                            include_layer: bool = True, fail_on_error: bool = True) -> None:
        logger.debug(f'Disabling steps: {step_uris or "ALL"} of layer: {layer_uri}')
        endpoint = (f'disableSteps?'
                    f'includeLayer={"true" if include_layer else "false"}&'
                    f'failOnError={"true" if fail_on_error else "false"}')
        self._send_patch(op_type=1, uri=layer_uri, endpoint=endpoint, data=step_uris)

    def layer_steps(self, layer_uri: str) -> dict:
        logger.debug(f'Getting steps of layer: {layer_uri}')
        return self._send_get(op_type=1, uri=layer_uri, endpoint='steps').json()

    def enable_step(self, step_uri: str) -> None:
        self._enable_step(step_uri=step_uri, step_type=self._get_step_type(step_uri=step_uri))

    def _enable_step(self, step_uri: str, step_type: str) -> None:
        logger.debug(f'Enabling step: {step_uri}')
        self._send_patch(op_type=2, uri=step_uri, data={'type': step_type, 'enabled': True})
        time.sleep(self.SLEEP_TIME)

    def disable_step(self, step_uri: str) -> None:
        self._disable_step(step_uri=step_uri, step_type=self._get_step_type(step_uri=step_uri))

    def _disable_step(self, step_uri: str, step_type: str) -> None:
        logger.debug(f'Disabling step: {step_uri}')
        self._send_patch(op_type=2, uri=step_uri, data={'type': step_type, 'enabled': False})
        time.sleep(self.SLEEP_TIME)

    def _get_step_type(self, step_uri: str) -> str:
        logger.debug(f'Getting step type of step: {step_uri}')
        return self._send_get(op_type=2, uri=step_uri).json()['type']

    def get_step_details(self, step_uri: str, query: str) -> dict:
        logger.debug(f'Getting details of step: {step_uri}')
        return self._send_get(op_type=2, uri=step_uri, query=f'expand={query}').json()

    def update_step(self, step_uri: str, data: dict) -> None:
        logger.debug(f'Updating step: {step_uri}')
        self._send_patch(op_type=2, uri=step_uri, data=data)
        time.sleep(self.SLEEP_TIME)

    # -------------------------------------------------------------------------
    # In-Flight Query Cancellation
    # -------------------------------------------------------------------------

    def _send_sparql(self, query: str) -> dict:
        """Execute a SPARQL SELECT query against the Anzo SPARQL endpoint.

        Args:
            query: SPARQL SELECT query string.

        Returns:
            Parsed SPARQL JSON response dict.

        Raises:
            requests.exceptions.HTTPError: On non-2xx responses.
        """
        url = f'{self.prefix}://{self.server}:{self.port}/sparql'
        response = requests.get(
            url,
            params={'query': query},
            headers={'accept': 'application/sparql-results+json'},
            auth=HTTPBasicAuth(self.username, self.password),
            timeout=self.REQUEST_TIMEOUT,
            verify=self.verify_ssl
        )
        response.raise_for_status()
        return response.json()

    def _build_cancel_payload(self, datasource_uri: str, operation_id: str) -> str:
        """Build the TriG payload required by the cancelQuery semantic service.

        Each payload uses a freshly generated UUID so concurrent cancellation
        requests do not collide in the semantic service queue.

        Args:
            datasource_uri: The datasource URI returned by get_inflight_queries().
            operation_id: The operationId returned by get_inflight_queries().

        Returns:
            TriG-formatted string ready for POST.
        """
        request_uuid = str(uuid.uuid4())
        return self.CANCEL_PAYLOAD_TEMPLATE.format(
            request_uuid=request_uuid,
            datasource_uri=datasource_uri,
            operation_id=operation_id,
        )

    def get_inflight_queries(self) -> list[dict]:
        """Return all currently executing queries from the Anzo system tables.

        Queries the InflightQueries system graph via SPARQL and returns a list
        of dicts, each containing ``operationId`` and ``datasource`` strings
        that can be passed directly to :meth:`cancel_query`.

        Returns:
            List of dicts with keys ``operationId`` and ``datasource``.
            Returns an empty list when no queries are in flight.

        Raises:
            requests.exceptions.HTTPError: On SPARQL endpoint errors.

        Example::

            queries = api.get_inflight_queries()
            for q in queries:
                print(q['operationId'], q['datasource'])
        """
        logger.debug('Fetching in-flight queries from system tables')
        result = self._send_sparql(self.INFLIGHT_QUERIES_SPARQL)
        bindings = result.get('results', {}).get('bindings', [])
        queries = [
            {
                'operationId': b['operationId']['value'],
                'datasource': b['datasource']['value'],
            }
            for b in bindings
        ]
        logger.info(f'Found {len(queries)} in-flight query/queries')
        return queries

    def cancel_query(self, datasource_uri: str, operation_id: str) -> None:
        """Cancel a single in-flight query via the Anzo semantic service.

        Constructs a uniquely-named TriG payload and POSTs it to the
        ``cancelQuery`` semantic service endpoint.  Requires sysadmin
        privileges; raises :class:`GraphmartManagerApiException` if the
        caller lacks permission or the query has already completed.

        Args:
            datasource_uri: Datasource URI of the running query
                (from :meth:`get_inflight_queries`).
            operation_id: Operation ID of the running query
                (from :meth:`get_inflight_queries`).

        Raises:
            GraphmartManagerApiException: If cancellation is rejected
                (e.g. insufficient privileges, query already finished).
            requests.exceptions.HTTPError: On unexpected HTTP errors.

        Example::

            queries = api.get_inflight_queries()
            if queries:
                q = queries[0]
                api.cancel_query(q['datasource'], q['operationId'])
        """
        logger.info(f'Cancelling query operationId={operation_id} on datasource={datasource_uri}')
        payload = self._build_cancel_payload(datasource_uri, operation_id)
        url = f'{self.prefix}://{self.server}:{self.port}/semantic-services'
        try:
            response = requests.post(
                url,
                params={'uri': self.CANCEL_QUERY_SERVICE_URI},
                headers={
                    'Content-Type': 'application/trig',
                    'Accept': 'application/json',
                },
                data=payload.encode('utf-8'),
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.REQUEST_TIMEOUT,
                verify=self.verify_ssl
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else 'unknown'
            if status_code == 403:
                raise GraphmartManagerApiException(
                    f'Permission denied cancelling query {operation_id}: sysadmin privileges required'
                ) from e
            raise GraphmartManagerApiException(
                f'Failed to cancel query {operation_id}: HTTP {status_code}'
            ) from e
        logger.info(f'Successfully cancelled query operationId={operation_id}')

    def cancel_all_inflight_queries(self) -> int:
        """Cancel every currently executing query.

        Convenience wrapper that chains :meth:`get_inflight_queries` and
        :meth:`cancel_query`.  Cancellation errors for individual queries are
        logged but do not abort the remaining cancellations.

        Returns:
            Number of queries successfully cancelled.

        Raises:
            requests.exceptions.HTTPError: If the initial SPARQL fetch fails.

        Example::

            cancelled = api.cancel_all_inflight_queries()
            print(f'Cancelled {cancelled} queries')
        """
        queries = self.get_inflight_queries()
        if not queries:
            logger.info('No in-flight queries to cancel')
            return 0

        cancelled = 0
        for q in queries:
            try:
                self.cancel_query(
                    datasource_uri=q['datasource'],
                    operation_id=q['operationId'],
                )
                cancelled += 1
            except (GraphmartManagerApiException, requests.exceptions.HTTPError) as e:
                logger.error(f'Could not cancel query {q["operationId"]}: {e}')

        logger.info(f'Cancelled {cancelled}/{len(queries)} in-flight queries')
        return cancelled