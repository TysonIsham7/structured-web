"""End-to-end proof for the synthetic St. George condo fixture.

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
LISTING_PATH = "/listings/cottonwood-bench-condo"
BROKEN_PATH = "/listings/cottonwood-bench-condo-invalid"
ACTION = "request_to_book"
STAY = {"check_in": "2027-03-04", "check_out": "2027-03-08", "guests": 2}


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


def test_cottonwood_bench_condo_end_to_end() -> None:
    listing, listing_body = _load("listing.json")
    broken, broken_body = _load("listing.invalid.json")
    config = ServerConfig(
        host=DEFAULT_HOST,
        port=0,
        resources=(
            Resource(path=LISTING_PATH, document=listing, body=listing_body),
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
        assert entry["uri"] == origin + LISTING_PATH
        assert entry["type"] == "product"
        assert entry["title"] == listing["title"]
        assert "synthetic fixture" in entry["title"]

        # 2. Content negotiation: vendor type and application/json.
        vendor_accept = f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}"
        fetched = client.fetch_resource(entry["uri"])
        assert fetched.content_type == RESOURCE_CONTENT_TYPE
        assert fetched.document == listing
        vendor_status, vendor_headers, vendor_body = _get(entry["uri"], vendor_accept)
        json_status, json_headers, json_body = _get(entry["uri"], JSON_MEDIA_TYPE)
        assert vendor_status == 200
        assert json_status == 200
        assert vendor_headers["content-type"] == RESOURCE_CONTENT_TYPE
        assert json_headers["content-type"] == JSON_CONTENT_TYPE
        assert "accept" in vendor_headers["vary"].lower()
        assert vendor_body == json_body == listing_body

        # 3. The language validator accepts the listing and rejects the broken one.
        module = validator_module()
        schema, vocabulary = loaded_language()
        assert module.validate_document(listing, schema, vocabulary) == []
        assert validation_errors(listing) == []
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
            raise AssertionError("broken listing must be rejected")

        # 4. Library render: screen HTML and headless JSON.
        screen = render(fetched.document, RenderOptions(medium="screen"))
        headless = render(fetched.document, RenderOptions(medium="headless"))
        assert screen.medium == "screen"
        assert screen.component == "product-card"
        assert screen.fallback is False
        assert screen.body.lstrip().startswith("<!DOCTYPE html>")
        assert "<script" not in screen.body.lower()
        assert listing["title"] in screen.body
        assert "214 USD" in screen.body
        assert "two-bedroom condo in St. George, Utah" in screen.body
        assert "https://example.com/fixtures/cottonwood-bench/living-room.png" in screen.body
        assert ACTION in screen.body
        assert headless.medium == "headless"
        assert headless.component == "product-card"
        assert headless.fallback is False
        assert headless.value is not None
        assert headless.value["title"] == listing["title"]
        content = headless.value["content"]
        assert content["bedrooms"] == 2
        assert content["bathrooms"] == 2
        assert content["price"] == {"amount": 214, "currency": "USD"}
        assert content["price_period"] == "night"
        assert "shared pool" in content["amenities"]
        assert content["availability"][0]["start"] == "2027-03-02"
        assert "No smoking" in content["house_rules"]
        assert content["images"][0]["src"].startswith("https://example.com/")
        assert headless.value["actions"][0]["name"] == ACTION
        assert headless.value["actions"][0]["risk"] == "high"
        assert json.loads(headless.body)["id"] == listing["id"]

        # 5. Agent runtime against a stub host handler.
        calls: list[tuple] = []
        consent_risks: list[str] = []

        def perform(action, args, context):
            calls.append((action["name"], args, context["resource_type"]))
            return {"request_id": "req-fixture-4401", "status": "requested"}

        def consent(action, args, context):
            consent_risks.append(action["risk"])
            return True

        ready = {"user": {"is_authenticated": True}, "stay": {"dates_available": True}}
        blocked = {"user": {"is_authenticated": True}, "stay": {"dates_available": False}}

        refused = client.invoke(
            fetched.document,
            ACTION,
            STAY,
            SessionOptions(state=blocked, consent=consent, perform=perform),
        )
        assert refused.discovered[0]["name"] == ACTION
        assert refused.discovered[0]["risk"] == "high"
        assert refused.discovered[0]["preconditions"] == [
            "user.is_authenticated",
            "stay.dates_available",
        ]
        assert refused.result.ok is False
        assert refused.result.code == "precondition_failed"
        assert refused.result.details == ("stay.dates_available",)
        assert calls == []
        assert consent_risks == []

        accepted = client.invoke(
            fetched.document,
            ACTION,
            STAY,
            SessionOptions(state=ready, consent=consent, perform=perform),
        )
        assert accepted.result.ok is True
        assert accepted.result.code == "ok"
        assert accepted.result.output == {
            "request_id": "req-fixture-4401",
            "status": "requested",
        }
        assert calls == [(ACTION, STAY, "product")]
        assert consent_risks == ["high"]
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
