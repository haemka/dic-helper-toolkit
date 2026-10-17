import gzip
import json
import sys

import pytest

from dic_helpers.fhir_file_reader import FHIRFileError, FHIRFileItem, FHIRFileReader

# These tests write small FHIR files to tmp_path and check what FHIRFileReader reads from them
# (README "FHIR file reader").

PATIENT = '{"resourceType": "Patient", "id": "p1"}'
PATIENT_XML = '<Patient xmlns="http://hl7.org/fhir"><id value="p1"/></Patient>'


def read(*paths, **options):
    """Type and id of every resource read, with the file name and line it was read from."""
    return [(item.path.name, item.line, item.resource.get_resource_type(), item.resource.id)
            for item in FHIRFileReader(paths, **options).resources()]


# A .json file with a single resource; the result carries the path, and None as line
def test_json_resource(tmp_path):
    (tmp_path / "patient.json").write_text(PATIENT)

    items = list(FHIRFileReader(tmp_path / "patient.json").resources())

    assert len(items) == 1
    assert isinstance(items[0], FHIRFileItem)
    assert items[0].path == tmp_path / "patient.json"
    assert items[0].line is None
    assert items[0].resource.get_resource_type() == "Patient"
    assert items[0].resource.id == "p1"


# The files are read in the given order
def test_files_in_the_given_order(tmp_path):
    (tmp_path / "a.json").write_text('{"resourceType": "Patient", "id": "a"}')
    (tmp_path / "b.json").write_text('{"resourceType": "Patient", "id": "b"}')

    assert read(tmp_path / "b.json", tmp_path / "a.json") == [
        ("b.json", None, "Patient", "b"),
        ("a.json", None, "Patient", "a"),
    ]


# A Bundle gives the resources of its entries, in order; entries without a resource are left out
def test_bundle_is_unpacked(tmp_path):
    (tmp_path / "bundle.json").write_text(json.dumps({
        "resourceType": "Bundle", "type": "transaction-response",
        "entry": [
            {"resource": {"resourceType": "Patient", "id": "p1"}, "response": {"status": "201"}},
            {"response": {"status": "200"}},
            {"resource": {"resourceType": "Observation", "id": "o1", "status": "final", "code": {"text": "Hb"}},
             "response": {"status": "201"}},
        ],
    }))

    assert read(tmp_path / "bundle.json") == [
        ("bundle.json", None, "Patient", "p1"),
        ("bundle.json", None, "Observation", "o1"),
    ]


# With unpack_bundles False, the Bundle itself is returned
def test_bundle_is_kept(tmp_path):
    (tmp_path / "bundle.json").write_text(json.dumps({
        "resourceType": "Bundle", "id": "b1", "type": "collection",
        "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}],
    }))

    assert read(tmp_path / "bundle.json", unpack_bundles=False) == [("bundle.json", None, "Bundle", "b1")]


# Only the outermost Bundle is unpacked, a Bundle inside it is returned as it is
def test_only_the_outermost_bundle_is_unpacked(tmp_path):
    (tmp_path / "bundle.json").write_text(json.dumps({
        "resourceType": "Bundle", "type": "collection",
        "entry": [{"resource": {"resourceType": "Bundle", "id": "inner", "type": "collection",
                                "entry": [{"resource": {"resourceType": "Patient", "id": "p1"}}]}}],
    }))

    assert read(tmp_path / "bundle.json") == [("bundle.json", None, "Bundle", "inner")]


# .ndjson: a resource per line, with its line number; empty lines are skipped
def test_ndjson(tmp_path):
    (tmp_path / "Patient.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        '\n'
        '{"resourceType": "Patient", "id": "p2"}\n')

    assert read(tmp_path / "Patient.ndjson") == [
        ("Patient.ndjson", 1, "Patient", "p1"),
        ("Patient.ndjson", 3, "Patient", "p2"),
    ]


# A Bundle on an NDJSON line is unpacked too; its resources have the line of the Bundle
def test_bundle_in_ndjson(tmp_path):
    (tmp_path / "bundles.ndjson").write_text(
        PATIENT + "\n"
        + json.dumps({"resourceType": "Bundle", "type": "collection",
                      "entry": [{"resource": {"resourceType": "Patient", "id": "p2"}}]}) + "\n")

    assert read(tmp_path / "bundles.ndjson") == [
        ("bundles.ndjson", 1, "Patient", "p1"),
        ("bundles.ndjson", 2, "Patient", "p2"),
    ]


# .xml: a resource in FHIR XML, the resource type comes from the root element
def test_xml_resource(tmp_path):
    (tmp_path / "patient.xml").write_text(PATIENT_XML)

    assert read(tmp_path / "patient.xml") == [("patient.xml", None, "Patient", "p1")]


# An XML Bundle is unpacked like a JSON Bundle
def test_xml_bundle(tmp_path):
    (tmp_path / "bundle.xml").write_text(
        '<Bundle xmlns="http://hl7.org/fhir"><type value="collection"/>'
        '<entry><resource><Patient><id value="p1"/></Patient></resource></entry>'
        '<entry><resource><Patient><id value="p2"/></Patient></resource></entry>'
        '</Bundle>')

    assert read(tmp_path / "bundle.xml") == [
        ("bundle.xml", None, "Patient", "p1"),
        ("bundle.xml", None, "Patient", "p2"),
    ]


# .gz after the extension: the file is read gzip compressed, in all three formats
def test_gzip(tmp_path):
    (tmp_path / "a.json.gz").write_bytes(gzip.compress(b'{"resourceType": "Patient", "id": "a"}'))
    (tmp_path / "b.ndjson.gz").write_bytes(gzip.compress(b'{"resourceType": "Patient", "id": "b"}\n'))
    (tmp_path / "c.xml.gz").write_bytes(gzip.compress(b'<Patient xmlns="http://hl7.org/fhir"><id value="c"/></Patient>'))

    assert read(tmp_path / "a.json.gz", tmp_path / "b.ndjson.gz", tmp_path / "c.xml.gz") == [
        ("a.json.gz", None, "Patient", "a"),
        ("b.ndjson.gz", 1, "Patient", "b"),
        ("c.xml.gz", None, "Patient", "c"),
    ]


# Text is UTF-8, a byte order mark at the start is allowed
def test_byte_order_mark(tmp_path):
    (tmp_path / "patient.json").write_bytes(b"\xef\xbb\xbf" + PATIENT.encode())
    (tmp_path / "Patient.ndjson").write_bytes(b"\xef\xbb\xbf" + PATIENT.encode() + b"\n")

    assert read(tmp_path / "patient.json", tmp_path / "Patient.ndjson") == [
        ("patient.json", None, "Patient", "p1"),
        ("Patient.ndjson", 1, "Patient", "p1"),
    ]


# The extension is case-insensitive
def test_extension_is_case_insensitive(tmp_path):
    (tmp_path / "PATIENT.JSON").write_text(PATIENT)

    assert read(tmp_path / "PATIENT.JSON") == [("PATIENT.JSON", None, "Patient", "p1")]


# Another extension is an error, the format is not guessed
def test_unknown_extension(tmp_path):
    (tmp_path / "patient.txt").write_text(PATIENT)

    with pytest.raises(FHIRFileError, match=r"patient\.txt: unknown file type, expected \.json, \.ndjson or \.xml, "
                                            r"optionally with \.gz"):
        read(tmp_path / "patient.txt")


# Invalid JSON is an error naming the file
def test_invalid_json(tmp_path):
    (tmp_path / "patient.json").write_text('{"resourceType": "Patient",')

    with pytest.raises(FHIRFileError, match=r"patient\.json: invalid JSON: "):
        read(tmp_path / "patient.json")


# Invalid JSON on an NDJSON line is an error naming file and line
def test_invalid_ndjson_line(tmp_path):
    (tmp_path / "Patient.ndjson").write_text(PATIENT + "\nnot json\n")

    with pytest.raises(FHIRFileError, match=r"Patient\.ndjson:2: invalid JSON: "):
        read(tmp_path / "Patient.ndjson")


# JSON without resourceType is not a FHIR resource
def test_missing_resource_type(tmp_path):
    (tmp_path / "data.json").write_text('{"id": "p1"}')

    with pytest.raises(FHIRFileError, match=r"data\.json: not a FHIR resource, resourceType is missing"):
        read(tmp_path / "data.json")


# An unknown resource type is an error, and so is a FHIR data type that isn't a resource
def test_unknown_resource_type(tmp_path):
    (tmp_path / "unknown.json").write_text('{"resourceType": "Patientt"}')
    (tmp_path / "datatype.json").write_text('{"resourceType": "HumanName"}')

    with pytest.raises(FHIRFileError, match=r"unknown\.json: unknown resource type 'Patientt'"):
        read(tmp_path / "unknown.json")
    with pytest.raises(FHIRFileError, match=r"datatype\.json: unknown resource type 'HumanName'"):
        read(tmp_path / "datatype.json")


# A resource that doesn't validate is an error naming file and resource type
def test_invalid_resource(tmp_path):
    (tmp_path / "patient.json").write_text('{"resourceType": "Patient", "birthDate": "yesterday"}')

    with pytest.raises(FHIRFileError) as error:
        read(tmp_path / "patient.json")

    assert str(error.value) == (f"{tmp_path}/patient.json: invalid Patient: birthDate: Date value string does not "
                                "match spec regex.")


# Text that isn't UTF-8 is an error
def test_not_utf8(tmp_path):
    (tmp_path / "patient.json").write_bytes('{"resourceType": "Patient", "id": "Müller"}'.encode("latin-1"))

    with pytest.raises(FHIRFileError, match=r"patient\.json: not UTF-8: "):
        read(tmp_path / "patient.json")


# Invalid XML is an error
def test_invalid_xml(tmp_path):
    (tmp_path / "patient.xml").write_text('<Patient xmlns="http://hl7.org/fhir"><id value="p1"/>')

    with pytest.raises(FHIRFileError, match=r"patient\.xml: invalid XML: "):
        read(tmp_path / "patient.xml")


# XML whose root element isn't in the FHIR namespace is not a FHIR resource
def test_xml_without_fhir_namespace(tmp_path):
    (tmp_path / "patient.xml").write_text('<Patient><id value="p1"/></Patient>')

    with pytest.raises(FHIRFileError, match=r"patient\.xml: not a FHIR resource, the root element is not in the "
                                            r"namespace http://hl7.org/fhir"):
        read(tmp_path / "patient.xml")


# External entities in XML are not resolved, so a file can't make the reader read other files: the XML is invalid
def test_xml_external_entities_are_not_resolved(tmp_path):
    (tmp_path / "secret.txt").write_text("SECRET")
    (tmp_path / "patient.xml").write_text(
        f'<!DOCTYPE Patient [<!ENTITY secret SYSTEM "file://{tmp_path}/secret.txt">]>'
        '<Patient xmlns="http://hl7.org/fhir"><id value="p1"/>'
        '<name><family value="&secret;"/></name></Patient>')

    with pytest.raises(FHIRFileError, match=r"patient\.xml: invalid XML: Attribute references external entity "
                                            r"'secret'") as error:
        read(tmp_path / "patient.xml")

    assert "SECRET" not in str(error.value)


# Reading XML without lxml is an error that names the extra to install, even with on_error 'skip'
def test_xml_without_lxml(tmp_path, monkeypatch):
    (tmp_path / "patient.xml").write_text(PATIENT_XML)
    # an import of lxml fails
    monkeypatch.setitem(sys.modules, "lxml", None)

    with pytest.raises(ImportError, match=r"Reading FHIR XML needs lxml, install dic-helper-toolkit\[xml\]"):
        read(tmp_path / "patient.xml", on_error="skip")


# A missing file is an error
def test_missing_file(tmp_path):
    with pytest.raises(FHIRFileError, match=r"missing\.json: cannot read file: "):
        read(tmp_path / "missing.json")


# A .gz file that isn't gzip compressed is an error
def test_invalid_gzip(tmp_path):
    (tmp_path / "patient.json.gz").write_text(PATIENT)

    with pytest.raises(FHIRFileError, match=r"patient\.json\.gz: cannot read file: "):
        read(tmp_path / "patient.json.gz")


# With on_error 'skip', an invalid NDJSON line is logged as a warning and reading continues with the next line
def test_skip_invalid_ndjson_line(tmp_path, caplog):
    (tmp_path / "Patient.ndjson").write_text(
        '{"resourceType": "Patient", "id": "p1"}\n'
        'not json\n'
        '{"resourceType": "Patient", "id": "p3"}\n')

    result = read(tmp_path / "Patient.ndjson", on_error="skip")

    assert result == [("Patient.ndjson", 1, "Patient", "p1"), ("Patient.ndjson", 3, "Patient", "p3")]
    assert [record.levelname for record in caplog.records] == ["WARNING"]
    assert caplog.messages[0].startswith(f"{tmp_path}/Patient.ndjson:2: invalid JSON: ")


# With on_error 'skip', an invalid or unreadable file is logged as a warning and reading continues with the next file
def test_skip_invalid_files(tmp_path, caplog):
    (tmp_path / "invalid.json").write_text('{"resourceType": "Patient", "birthDate": "yesterday"}')
    (tmp_path / "patient.txt").write_text(PATIENT)
    (tmp_path / "valid.json").write_text(PATIENT)

    result = read(tmp_path / "invalid.json", tmp_path / "patient.txt", tmp_path / "missing.json",
                  tmp_path / "valid.json", on_error="skip")

    assert result == [("valid.json", None, "Patient", "p1")]
    assert [message.split(": ", 2)[1] for message in caplog.messages] == [
        "invalid Patient", "unknown file type, expected .json, .ndjson or .xml, optionally with .gz",
        "cannot read file"]


# on_error is 'raise' or 'skip'
def test_invalid_on_error(tmp_path):
    with pytest.raises(ValueError, match="on_error must be 'raise' or 'skip', not 'ignore'"):
        FHIRFileReader(tmp_path / "patient.json", on_error="ignore")
