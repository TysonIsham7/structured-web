"""Accept-header decisions, without a socket."""

from __future__ import annotations

import pytest

from protocol.media import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    MANIFEST_CONTENT_TYPE,
    RESOURCE_CONTENT_TYPE,
    RESOURCE_MEDIA_TYPE,
    RESOURCE_VERSION,
)
from protocol.server.negotiate import negotiate_manifest, negotiate_resource


@pytest.mark.parametrize(
    ("header", "kind", "content_type"),
    [
        (None, "html", HTML_CONTENT_TYPE),
        ("", "html", HTML_CONTENT_TYPE),
        ("*/*", "html", HTML_CONTENT_TYPE),
        ("text/html", "html", HTML_CONTENT_TYPE),
        ("text/html, */*; q=0.8", "html", HTML_CONTENT_TYPE),
        ("application/json", "json", JSON_CONTENT_TYPE),
        (
            f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}",
            "vendor",
            RESOURCE_CONTENT_TYPE,
        ),
        (
            f'{RESOURCE_MEDIA_TYPE}; version="{RESOURCE_VERSION}"',
            "vendor",
            RESOURCE_CONTENT_TYPE,
        ),
        (RESOURCE_MEDIA_TYPE, "vendor", RESOURCE_CONTENT_TYPE),
        ("application/*", "vendor", RESOURCE_CONTENT_TYPE),
        (
            f"{RESOURCE_MEDIA_TYPE}; version=0.2",
            "unsupported_version",
            JSON_CONTENT_TYPE,
        ),
        (
            f"{RESOURCE_MEDIA_TYPE}; version=0.1.0",
            "unsupported_version",
            JSON_CONTENT_TYPE,
        ),
        (
            f"{RESOURCE_MEDIA_TYPE}; version=0.10",
            "unsupported_version",
            JSON_CONTENT_TYPE,
        ),
        (
            f"{RESOURCE_MEDIA_TYPE}; version=0.2, application/json; q=0.5",
            "unsupported_version",
            JSON_CONTENT_TYPE,
        ),
        (
            f"{RESOURCE_MEDIA_TYPE}; version=0.2, application/json",
            "json",
            JSON_CONTENT_TYPE,
        ),
        ("text/plain", "not_acceptable", JSON_CONTENT_TYPE),
        ("text/html;q=0", "not_acceptable", JSON_CONTENT_TYPE),
    ],
)
def test_resource_negotiation(header, kind, content_type) -> None:
    decision = negotiate_resource(header)
    assert decision.kind == kind
    assert decision.content_type == content_type


@pytest.mark.parametrize(
    ("header", "content_type"),
    [
        (None, MANIFEST_CONTENT_TYPE),
        ("", MANIFEST_CONTENT_TYPE),
        ("*/*", MANIFEST_CONTENT_TYPE),
        ("text/html", MANIFEST_CONTENT_TYPE),
        ("application/vnd.structured-web.manifest+json", MANIFEST_CONTENT_TYPE),
        ("application/json", JSON_CONTENT_TYPE),
    ],
)
def test_manifest_negotiation(header, content_type) -> None:
    assert negotiate_manifest(header).content_type == content_type
