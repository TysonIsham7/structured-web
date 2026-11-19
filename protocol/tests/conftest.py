"""Shared HTTP helpers for the protocol tests.

The session fixture uses a server that is already listening on the
default loopback port when CI started one. Otherwise it starts one.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from protocol.server.app import (  # noqa: E402
    DEFAULT_HOST,
    DEFAULT_PORT,
    ServerConfig,
    default_config,
    serve,
    wait_until_ready,
)
from protocol.server.resources import Resource, load_default_resources  # noqa: E402


@dataclass
class HttpResult:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> object:
        return json.loads(self.body)


def http_request(
    url: str,
    *,
    accept: str | None = None,
    authorization: str | None = None,
    method: str = "GET",
) -> HttpResult:
    parts = urlsplit(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    headers = {"Connection": "close"}
    if accept is not None:
        headers["Accept"] = accept
    if authorization is not None:
        headers["Authorization"] = authorization
    connection = HTTPConnection(parts.hostname, parts.port or 80, timeout=5)
    try:
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        mapped = {key.lower(): value for key, value in response.getheaders()}
        return HttpResult(response.status, mapped, body)
    finally:
        connection.close()


def _default_origin_ready() -> bool:
    try:
        wait_until_ready(DEFAULT_PORT, timeout=0.4, host=DEFAULT_HOST)
    except Exception:
        return False
    return True


@pytest.fixture(scope="session")
def base_url() -> str:
    if _default_origin_ready():
        yield f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
        return
    server, thread = serve(default_config())
    try:
        wait_until_ready(server.server_address[1], host=DEFAULT_HOST)
        yield server.origin
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.fixture
def serve_configured():
    started: list[tuple] = []

    def start_server(
        *,
        rate_limit: int = 1000,
        tokens: tuple[str, ...] | list[str] = (),
        protect: tuple[str, ...] | list[str] = (),
        extra: tuple[Resource, ...] = (),
    ) -> str:
        protected = set(protect)
        resources = [
            Resource(
                path=item.path,
                document=item.document,
                body=item.body,
                authenticated=item.path in protected,
                list_in_manifest=item.list_in_manifest,
            )
            for item in load_default_resources()
        ]
        resources.extend(extra)
        config = ServerConfig(
            host=DEFAULT_HOST,
            port=0,
            resources=tuple(resources),
            tokens=frozenset(tokens),
            rate_limit=rate_limit,
        )
        server, thread = serve(config)
        started.append((server, thread))
        return server.origin

    yield start_server
    for server, thread in started:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
