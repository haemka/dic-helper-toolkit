import pytest
import responses
import re
#from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.patient import Patient
from dic_helpers.fhir_client import FHIRClient  # Replace 'your_module' with the actual module name


@pytest.fixture
def fhir_client():
    return FHIRClient(base_url="http://example.com/fhir")


@responses.activate
def test_get_resource(fhir_client):
    responses.add(
        responses.GET,
        "http://example.com/fhir/Patient/123",
        json={"resourceType": "Patient", "id": "123", "name": [{"given": ["John"], "family": "Doe"}]},
        status=200
    )

    patient = fhir_client.get_resource("Patient", "123")
    assert isinstance(patient, Patient)
    assert patient.id == "123"
    assert patient.name[0].given[0] == "John"
    assert patient.name[0].family == "Doe"


@responses.activate
def test_create_resource(fhir_client):
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient",
        json={"resourceType": "Patient", "id": "456", "name": [{"given": ["Jane"], "family": "Smith"}]},
        status=201
    )

    new_patient = Patient(name=[{"given": ["Jane"], "family": "Smith"}])
    created_patient = fhir_client.create_resource(new_patient)

    assert isinstance(created_patient, Patient)
    assert created_patient.id == "456"
    assert created_patient.name[0].given[0] == "Jane"
    assert created_patient.name[0].family == "Smith"


@responses.activate
def test_update_resource(fhir_client):
    responses.add(
        responses.PUT,
        "http://example.com/fhir/Patient/789",
        json={"resourceType": "Patient", "id": "789", "name": [{"given": ["Updated"], "family": "Name"}]},
        status=200
    )

    updated_patient = Patient(id="789", name=[{"given": ["Updated"], "family": "Name"}])
    result = fhir_client.update_resource(updated_patient)

    assert isinstance(result, Patient)
    assert result.id == "789"
    assert result.name[0].given[0] == "Updated"
    assert result.name[0].family == "Name"


@responses.activate
def test_delete_resource(fhir_client):
    responses.add(
        responses.DELETE,
        "http://example.com/fhir/Patient/101",
        status=204
    )

    fhir_client.delete_resource("Patient", "101")
    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == "http://example.com/fhir/Patient/101"


@responses.activate
def test_search(fhir_client):
    responses.add(
        responses.GET,
        "http://example.com/fhir/Patient?_count=50",
        json={
            "resourceType": "Bundle",
            "type": "searchset",
            "total": 2,
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "1"}},
                {"resource": {"resourceType": "Patient", "id": "2"}}
            ]
        },
        status=200
    )

    results = list(fhir_client.search("Patient"))
    assert len(results) == 1
    assert isinstance(results[0], Bundle)
    assert results[0].total == 2
    assert len(results[0].entry) == 2


@responses.activate
def test_search_all(fhir_client):
    responses.add(
        responses.GET,
        "http://example.com/fhir/Patient?_count=50",
        json={
            "resourceType": "Bundle",
            "type": "searchset",
            "total": 2,
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "1"}},
                {"resource": {"resourceType": "Patient", "id": "2"}}
            ]
        },
        status=200
    )

    result = fhir_client.search_all("Patient")
    assert isinstance(result, Bundle)
    assert result.total == 2
    assert len(result.entry) == 2


@responses.activate
def test_execute_bundle(fhir_client):
    input_bundle = Bundle(
        type="transaction",
        entry=[{
            "request": {
                "method": "POST",
                "url": "Patient"
            },
            "resource": {
                "resourceType": "Patient",
                "name": [{"given": ["John"], "family": "Doe"}]
            }
        }]
    )

    responses.add(
        responses.POST,
        re.compile(r"http://example\.com/fhir/?$"),
        json={
            "resourceType": "Bundle",
            "type": "transaction-response",
            "entry": [{
                "response": {
                    "status": "201 Created",
                    "location": "Patient/123"
                }
            }]
        },
        status=200
    )

    result = fhir_client.execute_bundle(input_bundle)
    assert isinstance(result, Bundle)
    assert result.type == "transaction-response"
    assert len(result.entry) == 1


@responses.activate
def test_get_capability_statement(fhir_client):
    responses.add(
        responses.GET,
        "http://example.com/fhir/metadata",
        json={
            "resourceType": "CapabilityStatement",
            "status": "active",
            "fhirVersion": "4.0.1",
            "date": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
            "format": ["json", "xml"],
            "kind": "instance"
        },
        status=200
    )

    result = fhir_client.get_capability_statement()
    assert result.get_resource_type() == "CapabilityStatement"
    assert result.status == "active"
    assert result.fhirVersion == "4.0.1"


@responses.activate
def test_execute_operation(fhir_client):
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient/123/$everything",
        json={
            "resourceType": "Parameters",
            "parameter": [{
                "name": "return",
                "resource": {
                    "resourceType": "Bundle",
                    "type": "searchset",
                    "total": 1,
                    "entry": [{
                        "resource": {
                            "resourceType": "Patient",
                            "id": "123"
                        }
                    }]
                }
            }]
        },
        status=200
    )

    result = fhir_client.execute_operation("everything", resource_type="Patient", id="123")
    assert result.get_resource_type() == "Parameters"
    assert len(result.parameter) == 1
    assert result.parameter[0].name == "return"
    assert result.parameter[0].resource.get_resource_type() == "Bundle"

@responses.activate
def test_execute_operation_url_building(fhir_client):
    # Test case 1: Both resource_type and id are provided
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient/123/$everything",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("everything", resource_type="Patient", id="123")
    assert responses.calls[-1].request.url == "http://example.com/fhir/Patient/123/$everything"

    # Test case 2: Only resource_type is provided
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient/$everything",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("everything", resource_type="Patient")
    assert responses.calls[-1].request.url == "http://example.com/fhir/Patient/$everything"

    # Test case 3: Neither resource_type nor id is provided
    responses.add(
        responses.POST,
        "http://example.com/fhir/$everything",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("everything")
    assert responses.calls[-1].request.url == "http://example.com/fhir/$everything"

    # Test case 4: Resource_type is provided, id is None
    responses.add(
        responses.POST,
        "http://example.com/fhir/Observation/$everything",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("everything", resource_type="Observation", id=None)
    assert responses.calls[-1].request.url == "http://example.com/fhir/Observation/$everything"

    # Test case 5: Different operation name
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient/456/$validate",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("validate", resource_type="Patient", id="456")
    assert responses.calls[-1].request.url == "http://example.com/fhir/Patient/456/$validate"

    # Test case 6: With parameters
    responses.add(
        responses.POST,
        "http://example.com/fhir/Patient/$everything",
        json={"resourceType": "Parameters"},
        status=200
    )
    fhir_client.execute_operation("everything", resource_type="Patient", parameters={"start": "2023-01-01"})
    assert responses.calls[-1].request.url == "http://example.com/fhir/Patient/$everything"
    assert responses.calls[-1].request.body == b'{"start": "2023-01-01"}'
