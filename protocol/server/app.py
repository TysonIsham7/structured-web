"""HTTP reference server.

Binds to the IPv4 loopback address only. Serves the three language
examples with content negotiation, the well-known site manifest, and
typed JSON errors.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from library.errors import LibraryError
from library.render import RenderOptions, render
from protocol.errors import (
    REASON_FOR_STATUS,
    details_from_validator,
    error_document,
)
from protocol.media import HTML_CONTENT_TYPE, JSON_CONTENT_TYPE, WELL_KNOWN_PATH
from protocol.server.negotiate import negotiate_manifest, negotiate_resource
from protocol.server.resources import (
    Resource,
    load_default_resources,
    manifest_document,
    validation_errors,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_LOOPBACK_NAMES = frozenset({DEFAULT_HOST, "localhost"})


@dataclass(frozen=True)
class ServerConfig:
    """What one server process publishes."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    resources: tuple[Resource, ...] = ()
    tokens: frozenset[str] = field(default_factory=frozenset)
    rate_limit: int = 1000
    rate_window_seconds: int = 60


class RateLimiter:
    """Fixed-window counter keyed by credential hash or client address."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, int]] = {}

    def hit(self, key: str) -> tuple[bool, int, int]:
        """Count one request. Returns allowed, remaining, reset epoch."""
        now = int(time.time())
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now >= start + self.window_seconds:
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            reset = start + self.window_seconds
            remaining = max(0, self.limit - count)
            return count <= self.limit, remaining, reset


class StructuredWebServer(ThreadingHTTPServer):
    """Threading server that keeps the published catalog on itself."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.resources_by_path = {item.path: item for item in config.resources}
        self.limiter = RateLimiter(config.rate_limit, config.rate_window_seconds)
        super().__init__((config.host, config.port), Handler)
        bound_port = self.server_address[1]
        self.origin = f"http://{config.host}:{bound_port}"


class Handler(BaseHTTPRequestHandler):
    """One HTTP request. Errors are JSON, never an HTML error page."""

    protocol_version = "HTTP/1.1"
    server_version = "structured-web-reference/0.1"
    sys_version = ""

    server: StructuredWebServer

    def version_string(self) -> str:
        return self.server_version

    def handle_one_request(self) -> None:
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ""
                self.request_version = "HTTP/1.1"
                self.command = ""
                self._error(
                    500,
                    "internal_error",
                    "The server could not complete the request.",
                )
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                return
            if self.command == "GET":
                self._dispatch(include_body=True)
            elif self.command == "HEAD":
                self._dispatch(include_body=False)
            else:
                self._error(
                    405,
                    "method_not_allowed",
                    "Only GET and HEAD are defined.",
                    extra=(("Allow", "GET, HEAD"),),
                )
            self.wfile.flush()
        except (TimeoutError, ConnectionError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            self.close_connection = True
            try:
                self._error(
                    500,
                    "internal_error",
                    "The server could not complete the request.",
                )
            except Exception:
                return

    def send_error(
        self,
        code: int,
        message: str | None = None,
        explain: str | None = None,
    ) -> None:
        """Replace the base class HTML error page."""
        text = message or "Request failed."
        if code == 404:
            self._error(404, "not_found", text)
        elif code == 405:
            self._error(405, "method_not_allowed", text, extra=(("Allow", "GET, HEAD"),))
        else:
            self._error(code if code >= 400 else 400, "internal_error", text)

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        return

    def _dispatch(self, include_body: bool) -> None:
        allowed, remaining, reset = self.server.limiter.hit(self._identity())
        self._rate = (remaining, reset)
        path = _canonical_path(self.path)
        if not allowed:
            retry = max(0, reset - int(time.time()))
            self._error(
                429,
                "rate_limited",
                "Rate limit exceeded.",
                include_body=include_body,
                extra=(("Retry-After", str(retry)),),
            )
            return
        if path is None:
            self._error(404, "not_found", "Resource not found.", include_body=include_body)
            return
        if path == WELL_KNOWN_PATH:
            self._serve_manifest(include_body)
            return
        resource = self.server.resources_by_path.get(path)
        if resource is None:
            self._error(404, "not_found", "Resource not found.", include_body=include_body)
            return
        denied = self._authorization_failure(resource)
        if denied is not None:
            status, code, message, extra = denied
            self._error(status, code, message, include_body=include_body, extra=extra)
            return
        errors = validation_errors(resource.document)
        if errors:
            self._error(
                422,
                "schema_invalid",
                "Resource document failed validation.",
                include_body=include_body,
                details=details_from_validator(errors),
            )
            return
        decision = negotiate_resource(self.headers.get("Accept"))
        if decision.kind == "unsupported_version":
            self._error(
                406,
                "unsupported_version",
                "Requested resource version is not supported.",
                include_body=include_body,
                details={"supported": "0.1"},
            )
            return
        if decision.kind == "not_acceptable":
            self._error(
                406,
                "not_acceptable",
                "No acceptable representation.",
                include_body=include_body,
            )
            return
        if decision.kind == "html":
            self._serve_html(resource, include_body)
            return
        self._write(200, decision.content_type, resource.body, include_body)

    def _serve_manifest(self, include_body: bool) -> None:
        payload = manifest_document(self.server.origin, self.server.config.resources)
        body = _json_bytes(payload)
        decision = negotiate_manifest(self.headers.get("Accept"))
        self._write(200, decision.content_type, body, include_body)

    def _serve_html(self, resource: Resource, include_body: bool) -> None:
        try:
            rendered = render(resource.document, RenderOptions(medium="screen"))
        except LibraryError:
            self._error(
                422,
                "schema_invalid",
                "Resource document failed validation.",
                include_body=include_body,
            )
            return
        self._write(
            200,
            HTML_CONTENT_TYPE,
            rendered.body.encode("utf-8"),
            include_body,
        )

    def _authorization_failure(
        self,
        resource: Resource,
    ) -> tuple[int, str, str, tuple[tuple[str, str], ...]] | None:
        if not resource.authenticated:
            return None
        presented = _bearer_token(self.headers.get("Authorization"))
        if presented is None:
            return (
                401,
                "unauthorized",
                "Authentication is required.",
                (("WWW-Authenticate", "Bearer"),),
            )
        if not _token_accepted(presented, self.server.config.tokens):
            return (403, "forbidden", "Bearer token was not accepted.", ())
        return None

    def _identity(self) -> str:
        presented = _bearer_token(self.headers.get("Authorization"))
        if presented is not None:
            digest = hashlib.sha256(presented.encode("utf-8")).hexdigest()
            return "bearer:" + digest
        host = self.client_address[0] if self.client_address else ""
        return "ip:" + host

    def _error(
        self,
        status: int,
        code: str,
        message: str,
        include_body: bool = True,
        details: dict | None = None,
        extra: tuple[tuple[str, str], ...] = (),
    ) -> None:
        if not hasattr(self, "_rate"):
            self._rate = (0, int(time.time()))
        body = _json_bytes(error_document(code, message, details))
        self._write(status, JSON_CONTENT_TYPE, body, include_body, extra)

    def _write(
        self,
        status: int,
        content_type: str,
        body: bytes,
        include_body: bool,
        extra: tuple[tuple[str, str], ...] = (),
    ) -> None:
        remaining, reset = self._rate
        reason = REASON_FOR_STATUS.get(status, "Error")
        self.send_response(status, reason)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Accept")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-RateLimit-Limit", str(self.server.limiter.limit))
        self.send_header("X-RateLimit-Remaining", str(remaining))
        self.send_header("X-RateLimit-Reset", str(reset))
        self.send_header("Connection", "close")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()
        if include_body and body:
            self.wfile.write(body)
        self.wfile.flush()
        self.close_connection = True


def resolve_bind_host(value: str | None) -> str | None:
    """Return the loopback address, or None when `value` is not loopback."""
    if value is None or value.strip() == "":
        return DEFAULT_HOST
    if value.strip().lower() in _LOOPBACK_NAMES:
        return DEFAULT_HOST
    return None


def resolve_port(value: str | None) -> int:
    """Parse a TCP port, defaulting when `value` is empty."""
    if value is None or value.strip() == "":
        return DEFAULT_PORT
    port = int(value)
    if port < 0 or port > 65535:
        raise ValueError("port out of range")
    return port


def default_config(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ServerConfig:
    return ServerConfig(host=host, port=port, resources=load_default_resources())


def start(config: ServerConfig) -> StructuredWebServer:
    """Bind a server. The caller starts its thread or serve loop."""
    if config.host != DEFAULT_HOST:
        raise ValueError("reference server binds to the loopback address only")
    return StructuredWebServer(config)


def serve_forever(config: ServerConfig) -> None:
    """Serve until the process is stopped."""
    server = start(config)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def serve(config: ServerConfig) -> tuple[StructuredWebServer, threading.Thread]:
    """Start a daemon thread and return the bound server."""
    server = start(config)
    thread = threading.Thread(target=server.serve_forever, name="structured-web", daemon=True)
    thread.start()
    return server, thread


def wait_until_ready(
    port: int = DEFAULT_PORT,
    timeout: float = 5.0,
    host: str = DEFAULT_HOST,
) -> None:
    """Block until the well-known manifest responds, or raise."""
    import urllib.request

    url = f"http://{host}:{port}{WELL_KNOWN_PATH}"
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last = exc
            time.sleep(0.05)
    raise RuntimeError(f"server did not become ready: {last}")


def _canonical_path(raw: str) -> str | None:
    path = unquote(urlsplit(raw).path)
    if not path.startswith("/") or "\\" in path or "\x00" in path:
        return None
    if any(part == ".." for part in path.split("/")):
        return None
    return path


def _bearer_token(header: str | None) -> str | None:
    if header is None:
        return None
    scheme, separator, token = header.strip().partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    token = token.strip()
    if token == "":
        return None
    return token


def _token_accepted(presented: str, tokens: frozenset[str]) -> bool:
    presented_hash = hashlib.sha256(presented.encode("utf-8")).digest()
    for token in tokens:
        candidate = hashlib.sha256(token.encode("utf-8")).digest()
        if hmac.compare_digest(presented_hash, candidate):
            return True
    return False


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    )
