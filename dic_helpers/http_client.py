import requests
import logging
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import LegacyApplicationClient, BackendApplicationClient, TokenExpiredError
from urllib.parse import urljoin


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class HTTPClient:
    def __init__(self, base_url, username=None, password=None, auth_url=None,
                 realm=None, client_id=None, client_secret=None, ca_file=None):
        self.base_url = self._normalize_url(base_url)
        self.username = username
        self.password = password
        self.auth_url = self._normalize_url(auth_url)
        self.realm = realm
        self.client_id = client_id
        self.client_secret = client_secret
        self.ca_file = ca_file
        self.session = None
        self.token = None
        self.token_url = None
        self._create_session()

    @staticmethod
    def _normalize_url(url):
        if url.endswith('/'):
            return url
        else:
            return f"{url}/"

    def _get_openid_configuration(self):
        config_url = urljoin(urljoin(self.auth_url, f"realms/{self.realm}/"),
                             ".well-known/openid-configuration")
        response = requests.get(config_url, verify=self.ca_file)
        response.raise_for_status()
        return response.json()

    def _fetch_token(self):
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

    def _create_session(self):
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
                extra = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                }
                client = BackendApplicationClient(client_id=self.client_id)
                self.session = OAuth2Session(client=client,
                                             auto_refresh_url=config.get('token_endpoint', self.token_url),
                                             auto_refresh_kwargs=extra,
                                             token_updater=self._token_updater)

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

    def _token_updater(self, token):
        logger.debug(f"Token updater called with token {token}")
        self.token = token

    def _make_request(self, method, path, **kwargs):
        url = urljoin(self.base_url, path.lstrip('/'))
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

    def get(self, path, **kwargs):
        return self._make_request('GET', urljoin(self.base_url, path), **kwargs)

    def post(self, path, **kwargs):
        return self._make_request('POST', urljoin(self.base_url, path), **kwargs)

    def put(self, path, **kwargs):
        return self._make_request('PUT', urljoin(self.base_url, path), **kwargs)

    def delete(self, path, **kwargs):
        return self._make_request('DELETE', urljoin(self.base_url, path), **kwargs)

    def patch(self, path, **kwargs):
        return self._make_request('PATCH', urljoin(self.base_url, path), **kwargs)

    def request(self, method, path, **kwargs):
        if method == 'GET':
            self.get(path, **kwargs)
        elif method == 'POST':
            self.post(path, **kwargs)
        elif method == 'PUT':
            self.put(path, **kwargs)
        elif method == 'DELETE':
            self.delete(path, **kwargs)
        elif method == 'PATCH':
            self.patch(path, **kwargs)
