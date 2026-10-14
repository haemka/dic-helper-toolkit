import logging
import json
from typing import Dict, Any, Generator, Optional
from urllib.parse import urlparse, parse_qs, urlencode, urljoin
from fhir.resources.R4B import get_fhir_model_class
from fhir.resources.R4B.bundle import Bundle
from dic_helpers.http_client import HTTPClient


logger = logging.getLogger(__name__)


class FHIRClient(HTTPClient):
    """
    A FHIR API client that abstracts an advanced HTTP client.

    This client uses the custom implementation for a HTTP client from the same package (dic-helper-toolkit). It offers
    easy to use function for FHIR requests and uses fhir.resources as object representations of resources.
    """
    def __init__(self, page_size=50, next_param: Optional[str] = None, *args, **kwargs) -> None:
        """Initialize the FHIRClient

        :param page_size: Number of entries to request per search page.
        :param next_param: Query parameter for offset paging, for servers that don't provide standard FHIR paging
            links (e.g. '_offset'). Defaults to None, which uses standard FHIR paging only.
        :param args: Positional arguments to pass to the parent HTTPClient.
        :param kwargs: Keyword arguments to pass to the parent HTTPClient.
        """
        super().__init__(*args, **kwargs)
        self.page_size = page_size
        # An empty string counts as not configured
        self.next_param: Optional[str] = next_param or None

    def _is_standard_paging(self, bundle: Dict[str, Any]) -> bool:
        """Check if the bundle follows standard FHIR paging

        :param bundle: A dictionary representing a FHIR Bundle.
        :type bundle: Dict[str, Any]
        :return: True if the bundle uses standard paging, False otherwise.
        :rtype: bool
        """
        if 'link' in bundle:
            return any(link['relation'] in ['next', 'previous'] for link in bundle['link'])
        return False

    def _get_next_url(self, bundle: Dict[str, Any]) -> Optional[str]:
        """Get the 'next' URL from the bundle

        :param bundle: A dictionary representing a FHIR Bundle.
        :type bundle: Dict[str, Any]
        :return: The next URL from the bundle.
        :rtype: str
        """
        if 'link' in bundle:
            next_link = next((link['url'] for link in bundle['link'] if link['relation'] == 'next'), None)
            return next_link
        return None

    def _construct_next_params(self, original_params: str, offset: int) -> str:
        """Construct the next URL for non-standard paging

        :param original_url: The original URL to use for constructing the next URL.
        :type original_url: str
        :param offset: The offset to use for constructing the next URL.
        :type offset: int
        :return: The next URL.
        :rtype: str
        """
        query_params = original_params
        query_params['_count'] = str(self.page_size)
        query_params[self.next_param] = str(offset)
        return query_params

    @staticmethod
    def _parse_params(params: str) -> Dict[str, Any]:
        return dict(param.split('=', 1) for param in params.split('&'))

    def search(self, resource_type: str, params: Optional[Any] = None) -> Generator[Bundle, None, None]:
        if params is None:
            params = {}
        elif isinstance(params, str):
            params = self._parse_params(params)
        params['_count'] = params.get('_count', self.page_size)

        url = urljoin(self.base_url, resource_type)
        path = resource_type
        logger.debug(f"Search request with path {path} and params {params}")

        previous_entries = None
        received = 0
        while path:
            response = self.get(path, params=params)
            bundle_dict = response.json()
            entries = bundle_dict.get('entry') or []
            # A server ignoring the offset parameter returns the same page again, which would otherwise loop forever
            if entries and entries == previous_entries:
                logger.warning(f"Server returned the same page again for paging parameter '{self.next_param}'. It "
                               f"probably does not support this parameter. Stopping the search.")
                break
            previous_entries = entries
            received += len(entries)
            resource_class = get_fhir_model_class('Bundle')
            bundle = resource_class.model_validate_json(json.dumps(bundle_dict))

            yield bundle

            if self._is_standard_paging(bundle_dict):
                # Standard FHIR paging
                next_url = self._get_next_url(bundle_dict)
                if next_url:
                    parsed_next_url = urlparse(next_url)
                    path = parsed_next_url.path
                    params = parse_qs(parsed_next_url.query)  # Correctly parse query parameters
                else:
                    path = None
            elif self.next_param and len(entries) == self.page_size:
                # Non-standard offset paging, only if configured
                current_offset = int(params.get(self.next_param, 0))
                next_offset = current_offset + self.page_size

                params = self._construct_next_params(params, next_offset)
            else:
                total = bundle_dict.get('total')
                if self.next_param is None and isinstance(total, int) and total > received:
                    logger.warning(f"Search for {resource_type} returned {received} of {total} results without a next "
                                   f"link. The server probably doesn't support standard FHIR paging, configure "
                                   f"next_param to use offset paging.")
                path = None
            if path:
                logger.debug(f"Next URL has path '{path}' and params '{params}'")

    def search_all(self, resource_type: str, params: Optional[Dict[str, Any]] = None) -> Bundle:
        """Perform a FHIR search and return a single Bundle containing all entries.

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param params: Optional parameters to pass to the parent HTTPClient.
        :type params: Dict[str, Any]
        :return: A generator that yields Bundles.
        :rtype: Generator[Bundle, None, None]
        """
        # Initialize an empty Bundle to store all entries
        all_entries_bundle = Bundle(
            type='searchset',
            total=0,
            entry=[]
        )

        # Call the original search function
        for page_bundle in self.search(resource_type, params):
            # Add entries from each page to the all_entries_bundle
            if page_bundle.entry:
                all_entries_bundle.entry.extend(page_bundle.entry)

            # Copy metadata from the last page
            all_entries_bundle.type = page_bundle.type
            all_entries_bundle.total = page_bundle.total

            # Update other relevant fields
            if hasattr(page_bundle, 'meta'):
                all_entries_bundle.meta = page_bundle.meta
            if hasattr(page_bundle, 'link'):
                all_entries_bundle.link = page_bundle.link

        # If total wasn't set in the original bundles, use the length of entries
        if all_entries_bundle.total is None or all_entries_bundle.total == 0:
            all_entries_bundle.total = len(all_entries_bundle.entry)

        return all_entries_bundle

    def get_resource(self, resource_type: str, id: str, **kwargs: Any) -> Any:
        """Retrieve a single resource

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param id: The id of the resource to retrieve.
        :type id: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The resource retrieved.
        :rtype: Any
        """
        response = self.get(f"{resource_type}/{id}", **kwargs)
        resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate_json(json.dumps(resource_dict))

    def post_resource(self, resource: Any, **kwargs: Any) -> Any:
        """Create a new resource

        :param resource: The resource to create.
        :type resource: Any
        :param kwargs: Additional arguments to pass to the request.
        :return: The created resource.
        :rtype: Any
        """
        resource_type = resource.get_resource_type()
        path = None if resource_type == "Bundle" else resource_type
        response = self.post(path=path, json=json.loads(resource.model_dump_json()), **kwargs)
        created_resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate_json(json.dumps(created_resource_dict))

    # Alias for post_resource()
    create_resource = post_resource

    def put_resource(self, resource: Any, **kwargs: Any) -> Any:
        """Update an existing resource

        :param resource: The resource to update.
        :type resource: Any
        :param kwargs: Additional arguments to pass to the request.
        :return: The updated resource.
        :rtype: Any
        """
        resource_type = resource.get_resource_type()
        resource_id = resource.id
        response = self.put(f"{resource_type}/{resource_id}",
                            json=json.loads(resource.model_dump_json()), **kwargs)
        updated_resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate_json(json.dumps(updated_resource_dict))

    # Alias for put_resource()
    update_resource = put_resource

    def delete_resource(self, resource_type: str, id: str, **kwargs: Any) -> None:
        """Delete a resource

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param kwargs: Additional arguments to pass to the request.
        :param id: The id of the resource to delete.
        :type id: str
        """
        self.delete(f"{resource_type}/{id}", **kwargs)

    def post_bundle(self, bundle: Bundle, **kwargs: Any) -> Bundle:
        """Execute a transaction or batch Bundle

        :param bundle: The Bundle to execute.
        :type bundle: Bundle
        :param kwargs: Additional arguments to pass to the request.
        :return: The executed Bundle.
        :rtype: Bundle
        """
        response = self.post("", json=json.loads(bundle.model_dump_json()), **kwargs)
        result_bundle_dict = response.json()
        resource_class = get_fhir_model_class('Bundle')
        return resource_class.model_validate_json(json.dumps(result_bundle_dict))

    # Alias for post_bundle()
    execute_bundle = post_bundle

    def get_capability_statement(self) -> Any:
        """Retrieve the server's capability statement

        :return: The server's capability statement.
        :rtype: Any
        """
        response = self.get("metadata")
        capability_statement_dict = response.json()
        resource_class = get_fhir_model_class('CapabilityStatement')
        return resource_class.model_validate_json(json.dumps(capability_statement_dict))

    def execute_operation(self, operation_name: str, resource_type: Optional[str] = None,
                          id: Optional[str] = None, parameters: Optional[Dict[str, Any]] = None) -> Any:
        """Execute a FHIR operation

        :param operation_name: The operation to execute.
        :type operation_name: str
        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param id: The id of the resource to execute.
        :type id: str
        :param parameters: Optional parameters to pass to the parent HTTPClient.
        :type parameters: Dict[str, Any]
        :return: The executed operation.
        :rtype: Any
        """
        path = f"${operation_name}"
        if resource_type and id:
            path = f"{resource_type}/{id}/" + path
        elif resource_type:
            path = f"{resource_type}/" + path

        response = self.post(path, json=parameters)
        result_dict = response.json()
        resource_class = get_fhir_model_class('Parameters')
        return resource_class.model_validate_json(json.dumps(result_dict))
