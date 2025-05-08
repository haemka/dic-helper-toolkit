# Python DIC Helper Toolkit

This Toolkit contains helper libraries for the data integration centers daily tasks.

## Installation

Follow the instructions for installation of your desired version in the
[packages section](https://git.smith.care/diz-jena/py-dic-helper-toolkit/-/packages/).

## Contents

### HTTP client

A wrapper around the `requests` library which allows to create an object for an endpoint holding all needed
configuration including authentication and certificate verification. It supports Basic Auth and OAuth 2.0.

#### Usage:

```python
from dic_helpers.http_client import HTTPClient

## No authentication or CA certificate at all
client = HTTPClient("https://example.com")

## Basic Auth with CA certificate
#client = HTTPClient("https://example.com", username="user", password="P4SSW0RD", ca_file="MyCA.crt")

## OAuth 2.0 with username and password
#client = HTTPClient("https://example.com", username="user", password="P4SSW0RD",
#                    auth_url="https://keycloak.example.com", realm="MyRealm", client_id="MyClient",
#                    client_secret="00000000-00000000-00000000-00000000", ca_file="MyCA.crt")

with client.get("index.html") as result:
    print(result)
```


### FHIR client

A simple FHIR client library which uses the HTTP client from above and handles resources directly as `fhir.resources`
(https://github.com/nazrulworld/fhir.resources) object.

#### Usage:

```python
from dic_helpers.fhir_client import FHIRClient
from fhir.resources.R4B.address import Address

client = FHIRClient("https://example.com", username="user", password="P4SSW0RD",
                    auth_url="https://keycloak.example.com", realm="MyRealm", client_id="MyClient",
                    client_secret="00000000-00000000-00000000-00000000", ca_file="MyCA.crt")

# Fetch a patient 
with client.search("Patient", "identifier=0123456789&_lastUpdated=ge2025-01-01") as patient:
    print(patient)
```
*Keep in mind, that this returns an object.* 

### Directory reader

A simple helper class for recursive directory reading.

