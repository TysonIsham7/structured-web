"""HTTP behavior of the reference server."""

from __future__ import annotations

import json

import pytest

from protocol.client import Client, SessionOptions
from protocol.errors import ProtocolError, details_from_validator
from protocol.media import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    JSON_MEDIA_TYPE,
    MANIFEST_CONTENT_TYPE,
    RESOURCE_CONTENT_TYPE,
    RESOURCE_MEDIA_TYPE,
    RESOURCE_VERSION,
)
from protocol.server.app import resolve_bind_host, start, ServerConfig
from protocol.server.resources import Resource, examples_dir
from protocol.tests.conftest import http_request

ARTICLE = "/articles/getting-started"
PRODUCT = "/resources/example-product"
FORM = "/forms/contact"
BEARER = "test-bearer"


def test_bind_host_is_loopback_only() -> None:
    assert resolve_bind_host(None) == "127.0.0.1"
    assert resolve_bind_host("127.0.0.1") == "127.0.0.1"
    assert resolve_bind_host("localhost") == "127.0.0.1"
    assert resolve_bind_host("public") is None
    with pytest.raises(ValueError):
        start(ServerConfig(host="public", port=0, resources=()))


def test_manifest_lists_the_three_examples(base_url: str) -> None:
    response = http_request(base_url + "/.well-known/structured-web")
    assert response.status == 200
    assert response.headers["content-type"] == MANIFEST_CONTENT_TYPE
    manifest = response.json()
    assert manifest["version"] == "0.1.0"
    assert manifest["site"] == base_url
    assert manifest["agent_id"] is None
    found = {item["type"]: item for item in manifest["resources"]}
    assert set(found) == {"article", "product", "form"}
    assert found["article"]["uri"] == base_url + ARTICLE
    assert found["product"]["title"] == "Example product"
    assert found["form"]["uri"] == base_url + FORM
    for name in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset"):
        assert int(response.headers[name]) >= 0


def test_vendor_and_json_return_the_same_bytes(base_url: str) -> None:
    url = base_url + ARTICLE
    vendor = http_request(
        url,
        accept=f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}",
    )
    legacy = http_request(url, accept=JSON_MEDIA_TYPE)
    assert vendor.status == 200
    assert legacy.status == 200
    assert vendor.headers["content-type"] == RESOURCE_CONTENT_TYPE
    assert legacy.headers["content-type"] == JSON_CONTENT_TYPE
    assert vendor.body == legacy.body
    assert vendor.body == (examples_dir() / "article.json").read_bytes()
    assert response_vary(vendor)


def test_html_is_the_default_representation(base_url: str) -> None:
    url = base_url + PRODUCT
    absent = http_request(url)
    wildcard = http_request(url, accept="*/*")
    html = http_request(url, accept="text/html")
    for response in (absent, wildcard, html):
        assert response.status == 200
        assert response.headers["content-type"] == HTML_CONTENT_TYPE
        page = response.body.decode("utf-8")
        assert "Example product" in page
        assert "<script" not in page.lower()
        assert page.lstrip().startswith("<!DOCTYPE html>")


def test_each_example_negotiates(base_url: str) -> None:
    expected = {
        ARTICLE: "article",
        PRODUCT: "product",
        FORM: "form",
    }
    for path, resource_type in expected.items():
        response = http_request(
            base_url + path,
            accept=f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}",
        )
        assert response.status == 200
        assert response.json()["type"] == resource_type


def test_unsupported_version_is_typed(base_url: str) -> None:
    response = http_request(
        base_url + ARTICLE,
        accept=f"{RESOURCE_MEDIA_TYPE}; version=0.2",
    )
    assert response.status == 406
    assert response.json()["error"]["code"] == "unsupported_version"
    assert response.json()["error"]["details"]["supported"] == "0.1"


def test_not_found_is_json(base_url: str) -> None:
    response = http_request(base_url + "/missing", accept="text/html")
    assert response.status == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert response.headers["content-type"] == JSON_CONTENT_TYPE
    assert b"<html" not in response.body.lower()


def test_parent_segments_are_not_found(base_url: str) -> None:
    response = http_request(base_url + "/articles/../articles/getting-started")
    assert response.status == 404
    assert response.json()["error"]["code"] == "not_found"


def test_method_not_allowed_is_json(base_url: str) -> None:
    response = http_request(base_url + ARTICLE, method="POST")
    assert response.status == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"]
    assert response.headers["content-type"] == JSON_CONTENT_TYPE


def test_head_omits_the_body(base_url: str) -> None:
    response = http_request(
        base_url + ARTICLE,
        accept=JSON_MEDIA_TYPE,
        method="HEAD",
    )
    assert response.status == 200
    assert response.body == b""
    assert int(response.headers["content-length"]) > 0


def test_not_acceptable(base_url: str) -> None:
    response = http_request(base_url + ARTICLE, accept="text/plain")
    assert response.status == 406
    assert response.json()["error"]["code"] == "not_acceptable"


def test_manifest_json_accept_uses_the_legacy_type(base_url: str) -> None:
    response = http_request(
        base_url + "/.well-known/structured-web",
        accept=JSON_MEDIA_TYPE,
    )
    assert response.status == 200
    assert response.headers["content-type"] == JSON_CONTENT_TYPE
    assert response.json()["resources"]


def test_unauthorized_and_forbidden(serve_configured) -> None:
    origin = serve_configured(tokens=(BEARER,), protect=(PRODUCT,))
    missing = http_request(origin + PRODUCT, accept=JSON_MEDIA_TYPE)
    assert missing.status == 401
    assert missing.json()["error"]["code"] == "unauthorized"
    assert missing.headers["www-authenticate"] == "Bearer"
    assert b"Example product" not in missing.body

    rejected = http_request(
        origin + PRODUCT,
        accept=JSON_MEDIA_TYPE,
        authorization="Bearer other-bearer",
    )
    assert rejected.status == 403
    assert rejected.json()["error"]["code"] == "forbidden"

    accepted = http_request(
        origin + PRODUCT,
        accept=JSON_MEDIA_TYPE,
        authorization=f"Bearer {BEARER}",
    )
    assert accepted.status == 200
    assert accepted.json()["type"] == "product"

    public = http_request(origin + ARTICLE, accept=JSON_MEDIA_TYPE)
    assert public.status == 200
    assert public.json()["type"] == "article"


def test_client_sends_session_credentials(serve_configured) -> None:
    origin = serve_configured(tokens=(BEARER,), protect=(PRODUCT,))
    client = Client()
    with pytest.raises(ProtocolError) as missing:
        client.fetch_resource(origin + PRODUCT)
    assert missing.value.code == "unauthorized"

    with pytest.raises(ProtocolError) as rejected:
        client.fetch_resource(
            origin + PRODUCT,
            SessionOptions(credentials="other-bearer"),
        )
    assert rejected.value.code == "forbidden"

    fetched = client.fetch_resource(
        origin + PRODUCT,
        SessionOptions(credentials=BEARER),
    )
    assert fetched.document["type"] == "product"
    assert fetched.content_type == RESOURCE_CONTENT_TYPE


def test_rate_limit(serve_configured) -> None:
    origin = serve_configured(rate_limit=2)
    url = origin + FORM
    first = http_request(url, accept=JSON_MEDIA_TYPE)
    second = http_request(url, accept=JSON_MEDIA_TYPE)
    third = http_request(url, accept=JSON_MEDIA_TYPE)
    assert first.status == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-remaining"] == "1"
    assert second.status == 200
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert third.status == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert third.headers["x-ratelimit-remaining"] == "0"
    assert "retry-after" in third.headers


def test_schema_invalid_is_json_for_html_accept(serve_configured) -> None:
    broken = {"title": "incomplete"}
    origin = serve_configured(
        extra=(
            Resource(
                path="/broken",
                document=broken,
                body=json.dumps(broken).encode("utf-8"),
                list_in_manifest=False,
            ),
        )
    )
    response = http_request(origin + "/broken", accept="text/html")
    assert response.status == 422
    payload = response.json()
    assert payload["error"]["code"] == "schema_invalid"
    assert payload["error"]["details"]["path"].startswith("$")
    assert payload["error"]["details"]["errors"]
    assert response.headers["content-type"] == JSON_CONTENT_TYPE
    assert b"<html" not in response.body.lower()
    listed = http_request(origin + "/.well-known/structured-web").json()
    assert all(item["uri"] != origin + "/broken" for item in listed["resources"])


def test_validator_lines_become_details() -> None:
    details = details_from_validator(["$.title: title is required", "$.type: missing"])
    assert details["path"] == "$.title"
    assert details["errors"][1].startswith("$.type")


def response_vary(response) -> bool:
    return "accept" in response.headers["vary"].lower()
