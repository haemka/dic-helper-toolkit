"""Reading FHIR resources from files: JSON, NDJSON and FHIR XML, each optionally gzip compressed."""
import gzip
import json
import logging
import os
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterable, Iterator, Literal, Optional, Tuple, Union

from fhir.resources.R4B import get_fhir_model_class
from fhir.resources.R4B.resource import Resource
from pydantic import ValidationError

logger = logging.getLogger(__name__)

# File formats by extension, before an optional .gz
FORMATS = {".ndjson": "ndjson", ".json": "json", ".xml": "xml"}
FHIR_NAMESPACE = "http://hl7.org/fhir"


class FHIRFileError(Exception):
    """An unreadable or invalid file, NDJSON line or resource. The message starts with the path (and line)."""


@dataclass(frozen=True)
class FHIRFileItem:
    """A resource and where it was read: the file, and for NDJSON the line (from 1), otherwise None."""
    path: Path
    line: Optional[int]
    resource: Resource


class FHIRFileReader:
    """
    Reads FHIR R4B resources from files. The format comes from the file extension (case-insensitive): .json (a
    resource), .ndjson (a resource per line, empty lines are skipped) or .xml (a resource in FHIR XML, needs the extra
    dic-helper-toolkit[xml]), each optionally followed by .gz for gzip compression. Text is UTF-8, optionally with BOM.
    """

    def __init__(self, paths: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]], unpack_bundles: bool = True,
                 on_error: Literal["raise", "skip"] = "raise") -> None:
        """
        Initialize the FHIRFileReader. The files are only read by resources().

        :param paths: The files to read, in this order. A single path can be given on its own.
        :type paths: Union[str, os.PathLike, Iterable[Union[str, os.PathLike]]]
        :param unpack_bundles: Return the resources of a Bundle's entries instead of the Bundle (only the outermost
            Bundle; entries without a resource are left out).
        :type unpack_bundles: bool
        :param on_error: 'raise': an unreadable or invalid file, line or resource raises FHIRFileError. 'skip': it is
            logged as a warning instead, and reading continues with the next line (NDJSON) or the next file.
        :type on_error: Literal["raise", "skip"]
        :raises ValueError: If on_error is neither 'raise' nor 'skip'.
        """
        if on_error not in ("raise", "skip"):
            raise ValueError(f"on_error must be 'raise' or 'skip', not {on_error!r}")
        if isinstance(paths, (str, os.PathLike)):
            paths = [paths]
        self.paths = [Path(path) for path in paths]
        self.unpack_bundles = unpack_bundles
        self.on_error = on_error

    def resources(self) -> Iterator[FHIRFileItem]:
        """
        Read the files.

        :return: The resources with their origin, in the order of the files and within each file.
        :rtype: Iterator[FHIRFileItem]
        :raises FHIRFileError: With on_error 'raise', for an unreadable or invalid file, line or resource.
        :raises ImportError: For an XML file without lxml installed, also with on_error 'skip'.
        """
        for path in self.paths:
            yield from self._read_file(path)

    def _read_file(self, path: Path) -> Iterator[FHIRFileItem]:
        """
        Read the resources of one file in its format. Errors of the whole file go to _fail().

        :param path: The file to read.
        :type path: Path
        :return: The resources of the file with their origin.
        :rtype: Iterator[FHIRFileItem]
        """
        try:
            file_format, compressed = self._format(path)
            with self._open(path, compressed) as file:
                if file_format == "ndjson":
                    yield from self._read_ndjson(path, file)
                else:
                    content = file.read()
                    if file_format == "json":
                        resource = self._from_json(self._decode(content, str(path)), str(path))
                    else:
                        resource = self._from_xml(content, str(path))
                    yield from self._items(path, None, resource)
        except FHIRFileError as error:
            self._fail(error)
        except (OSError, EOFError, zlib.error) as error:
            # Can't be opened, or isn't valid gzip
            self._fail(FHIRFileError(f"{path}: cannot read file: {error}"))

    def _read_ndjson(self, path: Path, file: IO[bytes]) -> Iterator[FHIRFileItem]:
        """
        Read an NDJSON file line by line. Errors of a line go to _fail(), so with on_error 'skip' only that line is
        left out.

        :param path: The file, for the origin and for messages.
        :type path: Path
        :param file: The opened file, binary and already decompressed.
        :type file: IO[bytes]
        :return: The resources of the lines with their origin.
        :rtype: Iterator[FHIRFileItem]
        """
        for number, raw in enumerate(file, start=1):
            location = f"{path}:{number}"
            try:
                text = self._decode(raw, location).strip()
                if not text:
                    continue
                resource = self._from_json(text, location)
            except FHIRFileError as error:
                self._fail(error)
                continue
            yield from self._items(path, number, resource)

    def _items(self, path: Path, line: Optional[int], resource: Resource) -> Iterator[FHIRFileItem]:
        """
        The results for a resource read from a file: the resources of its entries for a Bundle with unpack_bundles,
        otherwise the resource itself.

        :param path: The file the resource was read from.
        :type path: Path
        :param line: The NDJSON line the resource was read from, None for other formats.
        :type line: Optional[int]
        :param resource: The resource.
        :type resource: Resource
        :return: The resources with their origin.
        :rtype: Iterator[FHIRFileItem]
        """
        if self.unpack_bundles and resource.get_resource_type() == "Bundle":
            for entry in resource.entry or []:
                if entry.resource is not None:
                    yield FHIRFileItem(path, line, entry.resource)
        else:
            yield FHIRFileItem(path, line, resource)

    def _fail(self, error: FHIRFileError) -> None:
        """
        Handle an error according to on_error: raise it, or log it as a warning.

        :param error: The error, its message names the file (and line).
        :type error: FHIRFileError
        :raises FHIRFileError: With on_error 'raise'.
        """
        if self.on_error == "raise":
            raise error
        logger.warning(str(error))

    @staticmethod
    def _format(path: Path) -> Tuple[str, bool]:
        """
        The format of a file and whether it is gzip compressed, from its extension (case-insensitive).

        :param path: The file.
        :type path: Path
        :return: The format ('json', 'ndjson' or 'xml') and whether the file ends with .gz.
        :rtype: Tuple[str, bool]
        :raises FHIRFileError: For any other extension.
        """
        name = path.name.lower()
        compressed = name.endswith(".gz")
        if compressed:
            name = name.removesuffix(".gz")
        for extension, file_format in FORMATS.items():
            if name.endswith(extension):
                return file_format, compressed
        raise FHIRFileError(f"{path}: unknown file type, expected .json, .ndjson or .xml, optionally with .gz")

    @staticmethod
    def _open(path: Path, compressed: bool) -> IO[bytes]:
        """
        Open a file for reading bytes, decompressing it if it is gzip compressed.

        :param path: The file.
        :type path: Path
        :param compressed: Whether the file is gzip compressed.
        :type compressed: bool
        :return: The opened file.
        :rtype: IO[bytes]
        :raises OSError: If the file can't be opened.
        """
        return gzip.open(path, "rb") if compressed else open(path, "rb")

    @staticmethod
    def _decode(content: bytes, location: str) -> str:
        """
        Decode UTF-8 text, with or without a byte order mark.

        :param content: The bytes of a file or an NDJSON line.
        :type content: bytes
        :param location: The file (and line) for the error message.
        :type location: str
        :return: The text, without byte order mark.
        :rtype: str
        :raises FHIRFileError: If the content is not UTF-8.
        """
        try:
            # utf-8-sig removes a BOM, and reads text without BOM like utf-8
            return content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise FHIRFileError(f"{location}: not UTF-8: {error}") from None

    @staticmethod
    def _model_class(resource_type: object, location: str) -> type:
        """
        The fhir.resources R4B model class of a resource type.

        :param resource_type: The resource type, e.g. 'Patient'.
        :type resource_type: object
        :param location: The file (and line) for the error message.
        :type location: str
        :return: The model class.
        :rtype: type
        :raises FHIRFileError: If it is not a FHIR resource type, also for data types like 'HumanName'.
        """
        try:
            model_class = get_fhir_model_class(str(resource_type))
        except ValueError:
            model_class = None
        if model_class is None or not model_class.has_resource_base():
            raise FHIRFileError(f"{location}: unknown resource type {resource_type!r}")
        return model_class

    def _from_json(self, text: str, location: str) -> Resource:
        """
        Parse and validate a resource in JSON.

        :param text: The JSON text of a file or an NDJSON line.
        :type text: str
        :param location: The file (and line) for error messages.
        :type location: str
        :return: The resource.
        :rtype: Resource
        :raises FHIRFileError: For invalid JSON, a missing or unknown resourceType, or an invalid resource.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise FHIRFileError(f"{location}: invalid JSON: {error}") from None
        if not isinstance(data, dict) or "resourceType" not in data:
            raise FHIRFileError(f"{location}: not a FHIR resource, resourceType is missing")
        model_class = self._model_class(data["resourceType"], location)
        try:
            return model_class.model_validate(data)
        except ValidationError as error:
            raise FHIRFileError(f"{location}: invalid {data['resourceType']}: {_problems(error)}") from None

    def _from_xml(self, content: bytes, location: str) -> Resource:
        """
        Parse and validate a resource in FHIR XML. The resource type is the name of the root element, which must be in
        the FHIR namespace. External entities are not resolved.

        :param content: The bytes of the file, XML parses the encoding itself.
        :type content: bytes
        :param location: The file for error messages.
        :type location: str
        :return: The resource.
        :rtype: Resource
        :raises FHIRFileError: For invalid XML, a root element outside the FHIR namespace, an unknown resource type or
            an invalid resource.
        :raises ImportError: If lxml is not installed.
        """
        try:
            from lxml import etree
        except ImportError:
            raise ImportError("Reading FHIR XML needs lxml, install dic-helper-toolkit[xml]") from None
        # No external entities and no network access while parsing
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        try:
            root = etree.fromstring(content, parser)
        except etree.XMLSyntaxError as error:
            raise FHIRFileError(f"{location}: invalid XML: {error}") from None
        name = etree.QName(root)
        if name.namespace != FHIR_NAMESPACE:
            raise FHIRFileError(f"{location}: not a FHIR resource, the root element is not in the namespace "
                                f"{FHIR_NAMESPACE}")
        model_class = self._model_class(name.localname, location)
        try:
            return model_class.model_validate_xml(content, xmlparser=parser)
        except ValidationError as error:
            raise FHIRFileError(f"{location}: invalid {name.localname}: {_problems(error)}") from None
        except ValueError as error:
            raise FHIRFileError(f"{location}: invalid {name.localname}: {error}") from None


def _problems(error: ValidationError) -> str:
    """
    The problems of a validation error on one line, e.g. 'birthDate: Date value string does not match spec regex.'.

    :param error: The validation error of a resource.
    :type error: ValidationError
    :return: Every problem as '<element path>: <message>', separated by '; '.
    :rtype: str
    """
    return "; ".join(f"{'.'.join(str(part) for part in problem['loc'])}: {problem['msg'].removeprefix('Value error, ')}"
                     for problem in error.errors())
