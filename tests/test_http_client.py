import pytest
import responses
from unittest.mock import patch, MagicMock
from oauthlib.oauth2 import TokenExpiredError
from dic_helpers.http_client import HTTPClient


@pytest.fixture
def http_client():
    return HTTPClient(base_url="https://api.example.com", username="user", password="pass")


@pytest.fixture
def oauth_client():
    return HTTPClient(
        base_url="https://api.example.com",
        auth_url="https://auth.example.com",
        realm="myrealm",
        client_id="client_id",
        client_secret="client_secret"
    )


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

def test_normalize_url():
    assert HTTPClient._normalize_url("https://example.com") == "https://example.com/"
    assert HTTPClient._normalize_url("https://example.com/") == "https://example.com/"

