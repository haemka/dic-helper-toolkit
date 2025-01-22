import logging
import json
from typing import Dict, Any, Generator, Optional
from urllib.parse import urlparse, parse_qs, urlencode
from fhir.resources.R4B import get_fhir_model_class
from fhir.resources.R4B.bundle import Bundle
from dic_helpers.http_client import HTTPClient


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class FHIRClient(HTTPClient):
    """
    A FHIR API client that abstracts an advanced HTTP client.

    This client uses the custom implementation for a HTTP client from the same package (dic-helper-toolkit). It offers
    easy to use function for FHIR requests and uses fhir.resources as object representations of resources.
    """
    def __init__(self, *args, **kwargs) -> None:
        """Initialize the FHIRClient

        :param args: Positional arguments to pass to the parent HTTPClient.
        :param kwargs: Keyword arguments to pass to the parent HTTPClient.
        """
        super().__init__(*args, **kwargs)
        self.page_size = kwargs.get('page_size', 50)

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

    def _construct_next_url(self, original_url: str, offset: int) -> str:
        """Construct the next URL for non-standard paging

        :param original_url: The original URL to use for constructing the next URL.
        :type original_url: str
        :param offset: The offset to use for constructing the next URL.
        :type offset: int
        :return: The next URL.
        :rtype: str
        """
        parsed_url = urlparse(original_url)
        query_params = parse_qs(parsed_url.query)
        query_params['_count'] = [str(self.page_size)]
        query_params['_getpagesoffset'] = [str(offset)]
        new_query = urlencode(query_params, doseq=True)
        return parsed_url._replace(query=new_query).geturl()

    def search(self, resource_type: str, params: Optional[Dict[str, Any]] = None) -> Generator[Bundle, None, None]:
        """Perform a FHIR search and yield each page of results as a Bundle.

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param params: Optional parameters to pass to the parent HTTPClient.
        :type params: Dict[str, Any]
        :return: A generator that yields Bundles.
        :rtype: Generator[Bundle, None, None]
        """
        if params is None:
            params = {}

        # Ensure _count parameter is set
        params['_count'] = self.page_size

        # Construct initial URL
        path = f"{resource_type}?{urlencode(params, doseq=True)}"
        url = self.base_url + path

        while url:
            response = self.get(url)
            bundle_dict = response.json()
            resource_class = get_fhir_model_class('Bundle')
            bundle = resource_class.model_validate_json(json.dumps(bundle_dict))

            yield bundle

            if self._is_standard_paging(bundle_dict):
                # Standard FHIR paging
                url = self._get_next_url(bundle_dict)
            else:
                # Non-standard paging
                if 'entry' in bundle_dict and len(bundle_dict['entry']) == self.page_size:
                    current_offset = int(parse_qs(urlparse(url).query).get('_getpagesoffset', ['0'])[0])
                    next_offset = current_offset + self.page_size
                    url = self._construct_next_url(url, next_offset)
                else:
                    url = None

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

    def get_resource(self, resource_type: str, id: str) -> Any:
        """Retrieve a single resource

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param id: The id of the resource to retrieve.
        :type id: str
        :return: The resource retrieved.
        :rtype: Any
        """
        response = self.get(f"{resource_type}/{id}")
        resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate(resource_dict)

    def create_resource(self, resource: Any) -> Any:
        """Create a new resource

        :param resource: The resource to create.
        :type resource: Any
        :return: The created resource.
        :rtype: Any
        """
        resource_type = resource.get_resource_type()
        response = self.post(f"{resource_type}", json=resource.dict())
        created_resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate(created_resource_dict)

    def update_resource(self, resource: Any) -> Any:
        """Update an existing resource

        :param resource: The resource to update.
        :type resource: Any
        :return: The updated resource.
        :rtype: Any
        """
        resource_type = resource.get_resource_type()
        resource_id = resource.id
        response = self.put(f"{resource_type}/{resource_id}", json=resource.dict())
        updated_resource_dict = response.json()
        resource_class = get_fhir_model_class(resource_type)
        return resource_class.model_validate(updated_resource_dict)

    def delete_resource(self, resource_type: str, id: str) -> None:
        """Delete a resource

        :param resource_type: The resource type to search for.
        :type resource_type: str
        :param id: The id of the resource to delete.
        :type id: str
        """
        self.delete(f"{resource_type}/{id}")

    def execute_bundle(self, bundle: Bundle) -> Bundle:
        """Execute a transaction or batch Bundle

        :param bundle: The Bundle to execute.
        :type bundle: Bundle
        :return: The executed Bundle.
        :rtype: Bundle
        """
        response = self.post("", json=bundle.model_dump_json())
        result_bundle_dict = response.json()
        resource_class = get_fhir_model_class('Bundle')
        return resource_class.model_validate(result_bundle_dict)

    def get_capability_statement(self) -> Any:
        """Retrieve the server's capability statement

        :return: The server's capability statement.
        :rtype: Any
        """
        response = self.get("metadata")
        capability_statement_dict = response.json()
        resource_class = get_fhir_model_class('CapabilityStatement')
        return resource_class.model_validate(capability_statement_dict)

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
        return resource_class.model_validate(result_dict)
