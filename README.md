# Python DIC Helper Toolkit

This Toolkit contains helper libraries for the daily tasks of Data Integration Centers (DICs) — the data
integration and interoperability platforms operated by German university hospitals, as defined by the German
Medical Informatics Initiative ([Medizininformatik-Initiative, MII](https://www.medizininformatik-initiative.de/))
and used across projects of the Network of University Medicine
([Netzwerk Universitätsmedizin, NUM](https://www.netzwerk-universitaetsmedizin.de/)). DICs provide standardized,
FHIR-based access to clinical and research data for secondary use.

## Installation

Requires **Python 3.13 or newer**: the HTTP client's strict RFC 5280 certificate checks (`rfc5280=True`, the default)
are Python's default from 3.13 on.

```shell
pip install dic-helper-toolkit
```

The package is published on [PyPI](https://pypi.org/project/dic-helper-toolkit/). To use the FHIR XML reader, install
the `xml` extra: `pip install dic-helper-toolkit[xml]`.

## Contents

### HTTP client

A wrapper around the `requests` library which allows to create an object for an endpoint holding all needed
configuration including authentication and certificate verification. It supports Basic Auth and OAuth 2.0.

#### Usage:

```python
from dic_helpers.http_client import HTTPClient

## No authentication or CA certificate at all
client = HTTPClient(base_url="https://example.com")

## Basic Auth with CA certificate
#client = HTTPClient(base_url="https://example.com", username="user", password="P4SSW0RD", ca_file="MyCA.crt")

## OAuth 2.0 with username and password
#client = HTTPClient(base_url="https://example.com", username="user", password="P4SSW0RD",
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

client = FHIRClient(base_url="https://example.com", username="user", password="P4SSW0RD",
                    auth_url="https://keycloak.example.com", realm="MyRealm", client_id="MyClient",
                    client_secret="00000000-00000000-00000000-00000000", ca_file="MyCA.crt")

# Fetch a patient 
patients = client.search("Patient", "identifier=0123456789&_lastUpdated=ge2025-01-01"):
for patient in patients:
    print(patient)
```
*Keep in mind, that this returns an object.* 

### Directory reader

Lists the files of a directory, optionally including all subdirectories, whose names match shell-style patterns.

#### Usage:

```python
from dic_helpers.directory_reader import DirectoryReader

reader = DirectoryReader("/data/export", patterns=["*.json", "*.ndjson"], recursive=True)
for path in reader.list_files():
    print(path)
```

- **Only regular files** are listed, sorted by path, as `pathlib.Path` objects that start with the directory as given.
- **`patterns`** (default `"*"`) are matched case-sensitively against the file names (`*`, `?`, `[seq]`). A single
  pattern can be a string; a file is listed if it matches any pattern. Special characters in the directory's own name
  don't matter.
- **`recursive`** (default `False`) also lists the files of all subdirectories.
- **`include_hidden`** (default `False`): hidden files (names starting with `.`) are skipped and hidden directories
  are not read, unless this is `True`.
- **`follow_symlinks`** (default `False`): symbolic links to directories are only read if this is `True`. Every
  directory is read once at most, so symlink loops end. Symbolic links to files are always listed, broken links never.
- **Errors:** a missing directory raises `FileNotFoundError`, a file instead of a directory `NotADirectoryError`, and
  an unreadable directory `PermissionError`. An empty list therefore always means that no file matched.


### FHIR file reader

Reads FHIR R4B resources from files as `fhir.resources` objects, together with the file and line they were read from.
Combined with the directory reader:

```python
from dic_helpers.directory_reader import DirectoryReader
from dic_helpers.fhir_file_reader import FHIRFileReader

paths = DirectoryReader("/data/export", patterns=["*.json", "*.ndjson", "*.xml", "*.gz"], recursive=True).list_files()
for item in FHIRFileReader(paths).resources():
    print(item.path, item.line, item.resource.get_resource_type(), item.resource.id)
```

**Formats**, by file extension (case-insensitive):

| Extension | Content | `item.line` |
|---|---|---|
| `.json` | one resource | `None` |
| `.ndjson` | one resource per line (FHIR bulk data), empty lines are skipped | line number, from 1 |
| `.xml` | one resource in FHIR XML, the resource type comes from the root element | `None` |
| `.json.gz`, `.ndjson.gz`, `.xml.gz` | the same, gzip compressed | as above |

Other extensions are an error, the format is not guessed. Text is UTF-8, a byte order mark is allowed. Reading XML
needs `lxml`: install `dic-helper-toolkit[xml]`. External entities are not resolved, an XML file that references one is
invalid.

**Parameters:**
- **`paths`**: the files, read in this order; a single path can be given on its own. Resources come in the order they
  appear in each file. NDJSON files are read line by line, also compressed ones; JSON and XML files as a whole.
- **`unpack_bundles`** (default `True`): a Bundle gives the resources of its entries, of any Bundle type. Only the
  outermost Bundle is unpacked, entries without a resource are left out. With `False` the Bundle is returned.
- **`on_error`** (default `"raise"`): an unreadable or invalid file, NDJSON line or resource raises `FHIRFileError`,
  whose message starts with the file and line, e.g. `export/Patient.ndjson:17: invalid JSON: …` or
  `patient.json: invalid Patient: birthDate: Date value string does not match spec regex.`. With `"skip"` the message
  is logged as a warning, and reading continues with the next line (NDJSON) or the next file. A missing `lxml` is
  always an error.
