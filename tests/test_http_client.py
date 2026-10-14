import ssl
import pytest
import responses
from unittest.mock import patch, MagicMock
from requests.exceptions import HTTPError
from dic_helpers.http_client import HTTPClient, NoRFC5280HTTPAdapter


@pytest.fixture
def http_client():
    return HTTPClient(base_url="https://api.example.com", username="user", password="pass")


def test_normalize_url():
    assert HTTPClient._normalize_url("https://example.com") == "https://example.com/"
    assert HTTPClient._normalize_url("https://example.com/") == "https://example.com/"


@responses.activate
def test_get_request(http_client):
    responses.add(responses.GET, 'https://api.example.com/test', json={'key': 'value'}, status=200)
    response = http_client.get('/test')
    assert response.status_code == 200
    assert response.json() == {'key': 'value'}


@responses.activate
def test_post_request(http_client):
    responses.add(responses.POST, 'https://api.example.com/test', json={'result': 'success'}, status=201)
    response = http_client.post('/test', json={'data': 'test'})
    assert response.status_code == 201
    assert response.json() == {'result': 'success'}


@responses.activate
def test_put_request(http_client):
    responses.add(responses.PUT, 'https://api.example.com/test', json={'result': 'updated'}, status=200)
    response = http_client.put('/test', json={'data': 'update'})
    assert response.status_code == 200
    assert response.json() == {'result': 'updated'}


@responses.activate
def test_delete_request(http_client):
    responses.add(responses.DELETE, 'https://api.example.com/test', status=204)
    response = http_client.delete('/test')
    assert response.status_code == 204


@responses.activate
def test_patch_request(http_client):
    responses.add(responses.PATCH, 'https://api.example.com/test', json={'result': 'patched'}, status=200)
    response = http_client.patch('/test', json={'data': 'patch'})
    assert response.status_code == 200
    assert response.json() == {'result': 'patched'}


@responses.activate
def test_request_with_params(http_client):
    responses.add(responses.GET, 'https://api.example.com/test?param=value', json={'key': 'value'}, status=200)
    response = http_client.get('/test', params={'param': 'value'})
    assert response.status_code == 200
    assert response.json() == {'key': 'value'}


@responses.activate
def test_request_with_headers(http_client):
    def check_headers(request):
        assert request.headers['Custom-Header'] == 'Test'
        return (200, {}, '{"key": "value"}')

    responses.add_callback(responses.GET, 'https://api.example.com/test', callback=check_headers)
    response = http_client.get('/test', headers={'Custom-Header': 'Test'})
    assert response.status_code == 200
    assert response.json() == {'key': 'value'}


@responses.activate
def test_request_error_handling(http_client):
    responses.add(responses.GET, 'https://api.example.com/error', status=404)
    with pytest.raises(HTTPError):
        http_client.get('/error')


def test_create_session_basic_auth(http_client):
    assert http_client.session.auth is not None
    assert http_client.session.auth.username == 'user'
    assert http_client.session.auth.password == 'pass'


def test_rfc5280_relaxed_by_default():
    client = HTTPClient(base_url="https://api.example.com")
    adapter = client.session.get_adapter("https://api.example.com")
    assert isinstance(adapter, NoRFC5280HTTPAdapter)
    ctx = adapter.poolmanager.connection_pool_kw["ssl_context"]
    assert not ctx.verify_flags & ssl.VERIFY_X509_STRICT
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname


def test_rfc5280_relaxed_through_proxy():
    adapter = HTTPClient(base_url="https://api.example.com").session.get_adapter("https://api.example.com")
    proxy_manager = adapter.proxy_manager_for("http://proxy.example.com:3128")
    assert proxy_manager.connection_pool_kw["ssl_context"] is adapter._ssl_context


def test_rfc5280_strict():
    client = HTTPClient(base_url="https://api.example.com", rfc5280=True)
    assert not isinstance(client.session.get_adapter("https://api.example.com"), NoRFC5280HTTPAdapter)
