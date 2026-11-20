"""End-to-end proof for the domain-neutral integration fixture.

The reference server, client, language validator, and library runtimes
are used as they are. This module does not reimplement them.
"""

from __future__ import annotations

import json
import sys
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from library._bootstrap import validator_module  # noqa: E402
from library.documents import loaded_language  # noqa: E402
from library.render import RenderOptions, render  # noqa: E402
from protocol.client import Client, SessionOptions  # noqa: E402
from protocol.errors import ProtocolError  # noqa: E402
from protocol.media import (  # noqa: E402
    JSON_CONTENT_TYPE,
    JSON_MEDIA_TYPE,
    RESOURCE_CONTENT_TYPE,
    RESOURCE_MEDIA_TYPE,
    RESOURCE_VERSION,
)
from protocol.server.app import (  # noqa: E402
    DEFAULT_HOST,
    ServerConfig,
    serve,
    wait_until_ready,
)
from protocol.server.resources import Resource, validation_errors  # noqa: E402

FIXTURE = Path(__file__).resolve().parent
RESOURCE_PATH = "/resources/example-resource"
BROKEN_PATH = "/resources/example-resource-invalid"
ACTION = "update_resource"
NOTE = {"note": "fixture note"}
FETCHED_AT = "2026-11-19T00:00:00Z"
PRECONDITIONS = ["user.is_authenticated", "resource.is_published"]
EFFECTS = ["resource.updated"]


def _load(name: str) -> tuple[dict, bytes]:
    source = FIXTURE / name
    body = source.read_bytes()
    document = json.loads(body)
    if not isinstance(document, dict):
        raise AssertionError(f"{name} is not a JSON object")
    return document, body


def _get(url: str, accept: str) -> tuple[int, dict[str, str], bytes]:
    parts = urlsplit(url)
    path = parts.path or "/"
    connection = HTTPConnection(parts.hostname, parts.port or 80, timeout=5)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": accept, "Connection": "close"},
        )
        response = connection.getresponse()
        body = response.read()
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, headers, body
    finally:
        connection.close()


def test_integration_fixture_end_to_end() -> None:
    resource, resource_body = _load("resource.json")
    broken, broken_body = _load("resource.invalid.json")
    config = ServerConfig(
        host=DEFAULT_HOST,
        port=0,
        resources=(
            Resource(path=RESOURCE_PATH, document=resource, body=resource_body),
            Resource(
                path=BROKEN_PATH,
                document=broken,
                body=broken_body,
                list_in_manifest=False,
            ),
        ),
    )
    server, thread = serve(config)
    try:
        wait_until_ready(server.server_address[1], host=DEFAULT_HOST)
        origin = server.origin
        client = Client()

        # 1. Discovery through the well-known manifest.
        manifest = client.fetch_manifest(origin)
        assert manifest["version"] == "0.1.0"
        assert manifest["site"] == origin
        assert manifest["agent_id"] is None
        assert len(manifest["resources"]) == 1
        entry = manifest["resources"][0]
        assert entry["uri"] == origin + RESOURCE_PATH
        assert entry["type"] == "article"
        assert entry["title"] == resource["title"]
        assert "synthetic fixture" in entry["title"]

        # 2. Content negotiation: vendor type and application/json.
        vendor_accept = f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}"
        fetched = client.fetch_resource(entry["uri"])
        assert fetched.content_type == RESOURCE_CONTENT_TYPE
        assert fetched.document == resource
        assert fetched.document["provenance"]["fetched_at"] == FETCHED_AT
        vendor_status, vendor_headers, vendor_body = _get(entry["uri"], vendor_accept)
        json_status, json_headers, json_body = _get(entry["uri"], JSON_MEDIA_TYPE)
        assert vendor_status == 200
        assert json_status == 200
        assert vendor_headers["content-type"] == RESOURCE_CONTENT_TYPE
        assert json_headers["content-type"] == JSON_CONTENT_TYPE
        assert "accept" in vendor_headers["vary"].lower()
        assert vendor_body == json_body == resource_body

        # 3. The language validator accepts the resource and rejects the broken one.
        module = validator_module()
        schema, vocabulary = loaded_language()
        assert module.validate_document(resource, schema, vocabulary) == []
        assert validation_errors(resource) == []
        invalid_lines = module.validate_document(broken, schema, vocabulary)
        assert invalid_lines
        assert any("risk" in line for line in invalid_lines)
        broken_status, broken_headers, broken_body_response = _get(
            origin + BROKEN_PATH,
            JSON_MEDIA_TYPE,
        )
        assert broken_status == 422
        assert broken_headers["content-type"] == JSON_CONTENT_TYPE
        broken_payload = json.loads(broken_body_response)
        assert broken_payload["error"]["code"] == "schema_invalid"
        assert broken_payload["error"]["details"]["path"].startswith("$.actions")
        assert broken_payload["error"]["details"]["errors"]
        try:
            client.fetch_resource(origin + BROKEN_PATH)
        except ProtocolError as exc:
            assert exc.code == "schema_invalid"
        else:
            raise AssertionError("broken resource must be rejected")

        # 4. Library render: screen HTML and headless JSON.
        screen = render(fetched.document, RenderOptions(medium="screen"))
        headless = render(fetched.document, RenderOptions(medium="headless"))
        assert screen.medium == "screen"
        assert screen.component == "article-card"
        assert screen.fallback is False
        assert screen.body.lstrip().startswith("<!DOCTYPE html>")
        assert "<script" not in screen.body.lower()
        assert resource["title"] in screen.body
        assert "generic resource" in screen.body
        assert "https://example.com/fixtures/integration/mark.png" in screen.body
        assert ACTION in screen.body
        assert FETCHED_AT in screen.body
        assert headless.medium == "headless"
        assert headless.component == "article-card"
        assert headless.fallback is False
        assert headless.value is not None
        assert headless.value["title"] == resource["title"]
        content = headless.value["content"]
        assert content["summary"].startswith("A domain-neutral resource")
        assert "generic resource" in content["body"]
        assert content["author"] == "example-publisher"
        assert content["published_at"] == FETCHED_AT
        assert content["tags"] == ["fixture", "integration"]
        assert headless.value["actions"][0]["name"] == ACTION
        assert headless.value["actions"][0]["risk"] == "high"
        assert headless.value["actions"][0]["preconditions"] == PRECONDITIONS
        assert headless.value["actions"][0]["effects"] == EFFECTS
        assert json.loads(headless.body)["id"] == resource["id"]

        # 5. Agent runtime against a stub perform handler.
        calls: list[tuple] = []
        consent_risks: list[str] = []
        consent_grants = iter((False, True))

        def perform(action, args, context):
            calls.append((action["name"], args, context["resource_type"]))
            return {"result_id": "result-fixture-4401", "status": "updated"}

        def consent(action, args, context):
            consent_risks.append(action["risk"])
            return next(consent_grants)

        ready = {
            "user": {"is_authenticated": True},
            "resource": {"is_published": True},
        }
        blocked = {
            "user": {"is_authenticated": True},
            "resource": {"is_published": False},
        }

        refused = client.invoke(
            fetched.document,
            ACTION,
            NOTE,
            SessionOptions(state=blocked, consent=consent, perform=perform),
        )
        assert refused.discovered[0]["name"] == ACTION
        assert refused.discovered[0]["risk"] == "high"
        assert refused.discovered[0]["preconditions"] == PRECONDITIONS
        assert refused.discovered[0]["effects"] == EFFECTS
        assert refused.result.ok is False
        assert refused.result.code == "precondition_failed"
        assert refused.result.details == ("resource.is_published",)
        assert calls == []
        assert consent_risks == []

        denied = client.invoke(
            fetched.document,
            ACTION,
            NOTE,
            SessionOptions(state=ready, consent=consent, perform=perform),
        )
        assert denied.result.ok is False
        assert denied.result.code == "consent_denied"
        assert calls == []
        assert consent_risks == ["high"]

        accepted = client.invoke(
            fetched.document,
            ACTION,
            NOTE,
            SessionOptions(state=ready, consent=consent, perform=perform),
        )
        assert accepted.result.ok is True
        assert accepted.result.code == "ok"
        assert accepted.result.output == {
            "result_id": "result-fixture-4401",
            "status": "updated",
        }
        assert calls == [(ACTION, NOTE, "article")]
        assert consent_risks == ["high", "high"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
