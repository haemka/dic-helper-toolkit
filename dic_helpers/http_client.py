import requests
import logging
from typing import Optional, Dict, Any
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import LegacyApplicationClient, BackendApplicationClient, TokenExpiredError
from urllib.parse import urljoin


logger = logging.getLogger(__name__)


class HTTPClient:
    """
    A client for making HTTP requests with support for OAuth2 authentication.

    This client can handle basic authentication, OAuth2 Resource Owner Password Credentials flow, and OAuth2 Client
    Credentials flow.
    """
    def __init__(self, base_url: str, username: Optional[str] = None, password: Optional[str] = None,
                 auth_url: Optional[str] = None, realm: Optional[str] = None,
                 client_id: Optional[str] = None, client_secret: Optional[str] = None,
                 ca_file: Optional[str] = None) -> None:
        """Initialize the HTTPClient.

        :param base_url: The base URL for API requests.
        :type base_url: str
        :param username: Username for authentication.
        :type username: str, optional
        :param password: Password for authentication.
        :type password: str, optional
        :param auth_url: URL for OAuth2 authentication.
        :type auth_url: str, optional
        :param realm: Realm for OAuth2 authentication.
        :type realm: str, optional
        :param client_id: Client ID for OAuth2 authentication.
        :type client_id: str, optional
        :param client_secret: Client secret for OAuth2 authentication.
        :type client_secret: str, optional
        :param ca_file: Path to CA certificate file for SSL verification.
        :type ca_file: str, optional
        """
        self.base_url: str = self._normalize_url(base_url)
        self.username: Optional[str] = username
        self.password: Optional[str] = password
        self.auth_url: Optional[str] = self._normalize_url(auth_url) if auth_url else None
        self.realm: Optional[str] = realm
        self.client_id: Optional[str] = client_id
        self.client_secret: Optional[str] = client_secret
        self.ca_file: Optional[str] = ca_file
        self.session: Optional[requests.Session] = None
        self.token: Optional[Dict[str, Any]] = None
        self.token_url: Optional[str] = None
        self._create_session()

    @staticmethod
    def _normalize_url(url: str) -> str:
        """
        Ensure the URL ends with a forward slash.

        :param url: The URL to normalize.
        :type url: str
        :return: The normalized URL.
        :rtype: str
        """
        if url.endswith('/'):
            return url
        else:
            return f"{url}/"

    def _get_openid_configuration(self) -> Dict[str, Any]:
        """
        Retrieve the OpenID configuration from the authentication server.

        :return: The OpenID configuration.
        :rtype: dict
        :raises requests.HTTPError: If the request fails.
        """
        config_url = urljoin(urljoin(self.auth_url, f"realms/{self.realm}/"),
                             ".well-known/openid-configuration")
        response = requests.get(config_url, verify=self.ca_file)
        response.raise_for_status()
        return response.json()

    def _fetch_token(self) -> Dict[str, Any]:
        """
        Fetch an OAuth2 token from the authentication server.

        :return: The OAuth2 token.
        :rtype: dict
        :raises oauthlib.oauth2.OAuth2Error: If token fetching fails.
        """
        if self.username and self.password:
            # Resource Owner Password Credentials flow
            return self.session.fetch_token(
                token_url=self.token_url,
                username=self.username,
                password=self.password,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
        else:
            # Client Credentials flow
            # TODO: untested, needs to be tested, after KeyCloak update
            return self.session.fetch_token(
                token_url=self.token_url,
                client_id=self.client_id,
                client_secret=self.client_secret
            )

    def _create_session(self) -> None:
        """
        Create and configure the HTTP session based on the authentication method.
        """
        if self.auth_url and self.realm and self.client_id and self.client_secret:
            # OAuth2 flow
            config = self._get_openid_configuration()
            self.token_url = config['token_endpoint']

            if self.username and self.password:
                # Resource Owner Password Credentials flow
                client = LegacyApplicationClient(client_id=self.client_id)
                self.session = OAuth2Session(client=client)
            else:
                # Client Credentials flow
                client = BackendApplicationClient(client_id=self.client_id)
                self.session = OAuth2Session(client=client)

            if self.ca_file:
                self.session.verify = self.ca_file

            # Fetch initial token
            token = self._fetch_token()
            self.token = token
        else:
            self.session = requests.Session()
            if self.username and self.password:
                # Basic authentication
                self.session.auth = HTTPBasicAuth(self.username, self.password)
            if self.ca_file:
                self.session.verify = self.ca_file

    def _token_updater(self, token: Dict[str, Any]) -> None:
        """
        Update the stored token when it's refreshed.

        :param token: The new token.
        :type token: dict
        """
        logger.debug(f"Token updater called with token {token}")
        self.token = token

    def _make_request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """
        Make an HTTP request, handling token expiration if necessary.

        :param method: The HTTP method (GET, POST, etc.).
        :type method: str
        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        :raises requests.HTTPError: If the request fails.
        """
        url = urljoin(self.base_url, path)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except TokenExpiredError:
            logger.debug(f"Token expired for {url}, Re-fetching...")
            self.token = self._fetch_token()
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a GET request.

        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        """
        return self._make_request('GET', path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a POST request.

        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        """
        return self._make_request('POST', path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a PUT request.

        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        """
        return self._make_request('PUT', path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a DELETE request.

        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        """
        return self._make_request('DELETE', path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a PATCH request.

        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        """
        return self._make_request('PATCH', path, **kwargs)

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        """
        Send a custom HTTP request.

        This method allows sending any HTTP request method and is used internally
        by other convenience methods like get(), post(), etc.

        :param method: The HTTP method (GET, POST, PUT, DELETE, etc.).
        :type method: str
        :param path: The path to request.
        :type path: str
        :param kwargs: Additional arguments to pass to the request.
        :return: The HTTP response.
        :rtype: requests.Response
        :raises requests.HTTPError: If the request fails.
        """
        return self._make_request(method, path, **kwargs)
