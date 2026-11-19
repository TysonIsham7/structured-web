"""Reference client for discovery, negotiation, and local invocation.

Fetching uses HTTP. Invocation uses the library agent runtime. v0.1
does not define an HTTP action API.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPConnection
from typing import Any
from urllib.parse import urlsplit

from library._bootstrap import validator_module
from library.agent import SessionOptions as RuntimeOptions
from library.agent import create_session
from library.agent.runtime import Result
from library.documents import loaded_language
from library.errors import LibraryError
from protocol.errors import ProtocolError, details_from_validator
from protocol.media import MANIFEST_ACCEPT, RESOURCE_ACCEPT, WELL_KNOWN_PATH

USER_AGENT = "structured-web-reference-client/0.1"


@dataclass(frozen=True)
class SessionOptions:
    """Options for one client session.

    `credentials` is an optional bearer token for the fetch. v0.1 has
    no agent identity. A future identity layer can set this field
    without adding a required argument. The remaining fields are passed
    through to the library runtime and are not sent on the wire.
    """

    credentials: str | None = None
    state: Mapping[str, Any] | None = None
    consent: Any = None
    perform: Any = None
    preauthorized: Any = None


@dataclass(frozen=True)
class FetchedDocument:
    """A resource document the language validator has accepted."""

    url: str
    document: dict
    content_type: str
    rate_limit_limit: int | None
    rate_limit_remaining: int | None
    rate_limit_reset: int | None


@dataclass(frozen=True)
class Invocation:
    """discover() plus one invoke() on a library session."""

    discovered: list[dict[str, Any]]
    result: Result


class Client:
    """Fetch manifests and resource documents, then invoke locally."""

    def __init__(self, timeout: float = 5.0) -> None:
        self.timeout = timeout

    def fetch_manifest(
        self,
        origin: str,
        options: SessionOptions | None = None,
    ) -> dict[str, Any]:
        """GET the well-known site manifest and check its shape."""
        url = _manifest_url(origin)
        status, headers, body = self._get(url, MANIFEST_ACCEPT, options)
        payload = _read_payload(status, body)
        if status != 200:
            raise _error_from_payload(status, payload)
        return _require_manifest(payload)

    def fetch_resource(
        self,
        url: str,
        options: SessionOptions | None = None,
    ) -> FetchedDocument:
        """Content-negotiate `url` and validate the document."""
        status, headers, body = self._get(url, RESOURCE_ACCEPT, options)
        payload = _read_payload(status, body)
        if status != 200:
            raise _error_from_payload(status, payload)
        document = _require_resource(payload)
        return FetchedDocument(
            url=url,
            document=document,
            content_type=headers.get("content-type", ""),
            rate_limit_limit=_header_int(headers, "x-ratelimit-limit"),
            rate_limit_remaining=_header_int(headers, "x-ratelimit-remaining"),
            rate_limit_reset=_header_int(headers, "x-ratelimit-reset"),
        )

    def invoke(
        self,
        document: dict,
        name: str,
        args: object,
        options: SessionOptions | None = None,
    ) -> Invocation:
        """Open a library session, discover actions, and invoke one."""
        options = options or SessionOptions()
        try:
            session = create_session(
                document,
                RuntimeOptions(
                    state=options.state,
                    consent=options.consent,
                    perform=options.perform,
                    preauthorized=options.preauthorized,
                ),
            )
        except LibraryError as exc:
            raise ProtocolError(
                "schema_invalid",
                "Resource document failed validation.",
                details=details_from_validator(list(exc.details)),
            ) from exc
        try:
            discovered = session.discover()
            result = session.invoke(name, args)
            return Invocation(discovered=discovered, result=result)
        finally:
            session.close()

    def _get(
        self,
        url: str,
        accept: str,
        options: SessionOptions | None,
    ) -> tuple[int, dict[str, str], bytes]:
        parts = urlsplit(url)
        if parts.scheme != "http" or not parts.hostname:
            raise ProtocolError(
                "not_found",
                "The reference client fetches http URLs with a host.",
            )
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "Connection": "close",
        }
        token = None if options is None else options.credentials
        if token:
            headers["Authorization"] = f"Bearer {token}"
        connection = HTTPConnection(parts.hostname, parts.port or 80, timeout=self.timeout)
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            body = response.read()
            mapped = {key.lower(): value for key, value in response.getheaders()}
            return response.status, mapped, body
        except ProtocolError:
            raise
        except OSError as exc:
            raise ProtocolError("not_found", "The resource could not be fetched.") from exc
        finally:
            connection.close()


def _manifest_url(origin: str) -> str:
    trimmed = origin.rstrip("/")
    suffix = WELL_KNOWN_PATH
    if trimmed.endswith(suffix):
        return trimmed
    return trimmed + suffix


def _read_payload(status: int, body: bytes) -> object:
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        if status == 200:
            raise ProtocolError(
                "schema_invalid",
                "Response was not JSON.",
            ) from exc
        raise ProtocolError("not_found", "Response was not a protocol error.") from exc


def _error_from_payload(status: int, payload: object) -> ProtocolError:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("code"), str):
            details = error.get("details")
            return ProtocolError(
                error["code"],
                error.get("message") if isinstance(error.get("message"), str) else "",
                status=status,
                details=details if isinstance(details, dict) else {},
            )
    return ProtocolError("not_found", "Request failed.", status=status)


def _require_resource(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ProtocolError(
            "schema_invalid",
            "Resource document failed validation.",
            details={"path": "$"},
        )
    error = payload.get("error")
    if isinstance(error, dict) and "version" not in payload:
        raise _error_from_payload(200, payload)
    module = validator_module()
    schema, vocabulary = loaded_language()
    errors = module.validate_document(payload, schema, vocabulary)
    if errors:
        raise ProtocolError(
            "schema_invalid",
            "Resource document failed validation.",
            details=details_from_validator(errors),
        )
    return payload


def _require_manifest(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProtocolError("schema_invalid", "Site manifest is not a JSON object.")
    version = payload.get("version")
    if version != "0.1.0":
        raise ProtocolError(
            "unsupported_version",
            "Site manifest version is not supported.",
            details={"supported": "0.1.0"},
        )
    site = payload.get("site")
    if not isinstance(site, str) or site == "":
        raise ProtocolError("schema_invalid", "Site manifest is missing site.")
    if "agent_id" in payload and payload["agent_id"] is not None:
        if not isinstance(payload["agent_id"], str):
            raise ProtocolError(
                "schema_invalid",
                "Site manifest agent_id is not a string.",
            )
    resources = payload.get("resources")
    if not isinstance(resources, list):
        raise ProtocolError("schema_invalid", "Site manifest is missing resources.")
    for index, item in enumerate(resources):
        if not isinstance(item, dict):
            raise ProtocolError(
                "schema_invalid",
                f"Site manifest resource {index} is not an object.",
            )
        for key in ("uri", "type", "title"):
            value = item.get(key)
            if not isinstance(value, str) or value == "":
                raise ProtocolError(
                    "schema_invalid",
                    f"Site manifest resource {index} is missing {key}.",
                )
    return payload


def _header_int(headers: dict[str, str], name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
