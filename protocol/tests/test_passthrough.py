"""Unknown document fields survive validate, fetch, and headless render."""

from __future__ import annotations

import json

from library._bootstrap import validator_module
from library.documents import loaded_language
from library.render import RenderOptions, render
from protocol.client import Client
from protocol.media import JSON_MEDIA_TYPE, RESOURCE_MEDIA_TYPE, RESOURCE_VERSION
from protocol.server.resources import Resource
from protocol.tests.conftest import http_request

PROBE_PATH = "/probe"


def _probe() -> dict:
    return {
        "version": "0.1.0",
        "id": "urn:example:resource:article:pass-through",
        "type": "article",
        "title": "Pass-through probe",
        "extension_marker": {"keep": "alpha", "n": 2},
        "content": {
            "extension_marker": "beta",
            "body": "A reference article used to probe unknown fields.",
            "extension_detail": {"extension_note": "kept"},
            "extension_list": [
                {"id": "first", "label": "a"},
                {"id": "second", "label": "z"},
            ],
        },
        "actions": [
            {
                "extension_flag": True,
                "name": "update_resource",
                "description": "Apply a declared update to this resource.",
                "input_schema": {"type": "object"},
                "output_schema": {"type": "object"},
                "preconditions": [
                    "user.is_authenticated",
                    "resource.is_published",
                ],
                "effects": ["resource.updated"],
                "risk": "low",
                "idempotent": True,
            }
        ],
        "links": [
            {
                "extension_hint": "related-extra",
                "rel": "about",
                "href": "urn:example:resource:article:about",
            }
        ],
        "provenance": {
            "extension_source_note": "kept",
            "source": "https://example.com/resources/pass-through",
            "fetched_at": "2026-11-19T00:00:00Z",
            "content_hash": "sha256:" + ("ab" * 32),
            "signed_by": None,
        },
        "render": {
            "extension_hint": "kept",
            "preferred_component": "article-card",
            "media": [
                {
                    "extension_caption": "side",
                    "type": "image",
                    "src": "https://example.com/media/probe.png",
                    "alt": "Reference mark for the probe",
                }
            ],
        },
    }


def test_unknown_fields_round_trip(serve_configured) -> None:
    document = _probe()
    module = validator_module()
    schema, vocabulary = loaded_language()
    before = json.loads(json.dumps(document))
    assert module.validate_document(document, schema, vocabulary) == []
    assert document == before

    body = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    origin = serve_configured(
        extra=(Resource(path=PROBE_PATH, document=document, body=body),)
    )
    url = origin + PROBE_PATH
    client = Client()
    fetched = client.fetch_resource(url)
    json_response = http_request(url, accept=JSON_MEDIA_TYPE)
    vendor = f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}"
    vendor_response = http_request(url, accept=vendor)

    assert json_response.status == 200
    assert vendor_response.status == 200
    assert json_response.body == body
    assert vendor_response.body == body
    assert fetched.document == document
    assert list(fetched.document["content"]) == list(document["content"])
    assert fetched.document["links"][0]["extension_hint"] == "related-extra"

    headless = render(fetched.document, RenderOptions(medium="headless"))
    screen = render(fetched.document, RenderOptions(medium="screen"))
    assert headless.value is not None
    assert headless.value["content"] is fetched.document["content"]
    assert headless.value["content"]["extension_list"][0]["id"] == "first"
    assert headless.value["content"]["extension_detail"]["extension_note"] == "kept"
    assert headless.value["render"]["media"][0]["extension_caption"] == "side"
    assert headless.value["extension_marker"] == {"keep": "alpha", "n": 2}
    assert headless.value["actions"][0]["extension_flag"] is True
    assert headless.value["provenance"]["extension_source_note"] == "kept"
    assert headless.value["render"]["extension_hint"] == "kept"
    assert headless.value["links"][0]["extension_hint"] == "related-extra"
    parsed = json.loads(headless.body)
    assert parsed["content"] == document["content"]
    assert parsed["extension_marker"] == document["extension_marker"]
    assert "extension_marker" not in screen.body
    assert "extension_caption" not in screen.body
