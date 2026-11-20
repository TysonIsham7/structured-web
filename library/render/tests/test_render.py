"""Acceptance tests for the rendering runtime."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from library._bootstrap import validator_module
from library.errors import LibraryError
from library.render import RenderOptions, load_document, render

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "language" / "examples"
CATALOG_PATH = REPO / "library" / "catalog" / "default.json"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def provenance() -> dict:
    return {
        "source": "https://example.com/resources/sample",
        "fetched_at": "2026-11-19T00:00:00Z",
        "content_hash": "sha256:" + ("ab" * 32),
        "signed_by": None,
    }


def resource(type_name: str, content: dict, title: str) -> dict:
    return {
        "version": "0.1.0",
        "id": f"urn:example:resource:{type_name}:sample",
        "type": type_name,
        "title": title,
        "content": content,
        "actions": [],
        "links": [],
        "provenance": provenance(),
    }


def test_reuses_language_validator() -> None:
    module = validator_module()
    assert Path(module.__file__ or "").resolve() == (
        REPO / "language" / "validator" / "validate.py"
    )


def test_default_catalog_covers_five_types_and_generic() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["signature"] is None
    types: set[str] = set()
    names: set[str] = set()
    for entry in catalog["components"]:
        names.add(entry["name"])
        types.update(entry["types"])
        assert entry["signature"] is None
    assert names == {
        "article-card",
        "form-card",
        "data-table",
        "service-card",
        "error-card",
        "generic",
    }
    assert types == {
        "article",
        "form",
        "dataset",
        "service",
        "error",
        "*",
    }


EXAMPLE_RENDERINGS = [
    ("article.json", "canonical representation", "article-card"),
    ("update.json", "high-risk action", "article-card"),
    ("form.json", "Email", "form-card"),
    ("dataset.json", "Alpha", "data-table"),
    ("service.json", "https://example.com/api/weather", "service-card"),
    ("error.json", "not_found", "error-card"),
]


def test_render_cases_cover_every_example() -> None:
    names = sorted(path.name for path in EXAMPLES.glob("*.json"))
    assert names == sorted(item[0] for item in EXAMPLE_RENDERINGS)


@pytest.mark.parametrize(
    ("name", "snippet", "component"),
    EXAMPLE_RENDERINGS,
)
def test_examples_render_non_empty_html(name: str, snippet: str, component: str) -> None:
    document = load_example(name)
    output = render(document)
    assert output.medium == "screen"
    assert output.fallback is False
    assert output.component == component
    assert output.body.strip()
    assert "<html" in output.body
    assert document["title"] in output.body
    assert snippet in output.body
    assert f'data-component="{component}"' in output.body
    assert "<script" not in output.body.lower()
    assert "javascript:" not in output.body.lower()


def test_load_document_renders_example() -> None:
    document = load_document(EXAMPLES / "article.json")
    output = render(document)
    assert "Getting started with structured resources" in output.body


def test_unregistered_preferred_component_falls_back() -> None:
    document = load_example("article.json")
    document["render"]["preferred_component"] = "<script>alert(1)</script>"
    output = render(document)
    assert output.fallback is True
    assert output.component == "article-card"
    assert output.body.strip()
    assert 'data-component="article-card"' in output.body
    assert "<script" not in output.body.lower()
    assert "alert(1)" not in output.body


def test_strict_rejects_unregistered_component() -> None:
    document = load_example("article.json")
    document["render"]["preferred_component"] = "exfiltrate-widget"
    with pytest.raises(LibraryError) as exc:
        render(document, RenderOptions(strict=True))
    assert exc.value.code == "component_unregistered"


def test_missing_type_component_uses_generic() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog["components"] = [
        entry for entry in catalog["components"] if entry["name"] != "article-card"
    ]
    document = load_example("article.json")
    del document["render"]
    output = render(document, RenderOptions(catalog=catalog))
    assert output.component == "generic"
    assert output.fallback is True
    assert "canonical representation" in output.body
    assert "<script" not in output.body.lower()


def test_catalog_rejects_code_loading_and_signatures() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    renamed = copy.deepcopy(catalog)
    renamed["components"][0]["name"] = "os.system"
    document = load_example("article.json")
    with pytest.raises(LibraryError) as unknown:
        render(document, RenderOptions(catalog=renamed))
    assert unknown.value.code == "catalog_invalid"

    signed = copy.deepcopy(catalog)
    signed["components"][0]["signature"] = "not-checked"
    with pytest.raises(LibraryError) as signature:
        render(document, RenderOptions(catalog=signed))
    assert signature.value.code == "catalog_invalid"


def test_document_text_is_escaped() -> None:
    document = load_example("article.json")
    document["title"] = "<script>alert(1)</script>"
    document["content"]["body"] = "<img src=x onerror=alert(1)>"
    document["render"]["media"] = []
    output = render(document)
    assert "<script>" not in output.body.lower()
    assert "<img" not in output.body.lower()
    assert "&lt;script&gt;" in output.body
    assert "&lt;img src=x onerror=alert(1)&gt;" in output.body


def test_unsafe_link_is_not_emitted() -> None:
    document = load_example("article.json")
    document["links"][0]["href"] = "javascript:alert(1)"
    document["links"].append(
        {
            "rel": "related",
            "href": "https://user:secret@example.com/private",
            "title": "Credential link",
        }
    )
    document["render"]["media"][0]["src"] = "data:text/html,hello"
    output = render(document)
    assert "javascript:" not in output.body.lower()
    assert "data:text/html" not in output.body.lower()
    assert "secret" not in output.body
    assert "Language overview" in output.body
    assert "Credential link" in output.body


def test_invalid_document_is_rejected() -> None:
    document = load_example("article.json")
    del document["title"]
    with pytest.raises(LibraryError) as exc:
        render(document)
    assert exc.value.code == "document_invalid"
    assert any("$.title" in line for line in exc.value.details)


def test_voice_is_not_implemented() -> None:
    document = load_example("article.json")
    with pytest.raises(LibraryError) as exc:
        render(document, RenderOptions(medium="voice"))
    assert exc.value.code == "unsupported_medium"


def test_headless_returns_json() -> None:
    document = load_example("update.json")
    output = render(document, RenderOptions(medium="headless"))
    assert output.medium == "headless"
    assert output.value is not None
    assert output.value["component"] == "article-card"
    assert output.value["title"] == document["title"]
    assert output.value["actions"][0]["name"] == "update_resource"
    parsed = json.loads(output.body)
    assert parsed == output.value


def test_theme_hooks_are_sanitized() -> None:
    document = load_example("article.json")
    themed = render(
        document,
        RenderOptions(theme={"class_name": "night", "accent": "#123456"}),
    )
    assert "night" in themed.body
    assert "#123456" in themed.body
    hostile = render(
        document,
        RenderOptions(theme={"class_name": '"><script>', "accent": "red"}),
    )
    assert "<script>" not in hostile.body
    assert "sw-default" in hostile.body
    assert "#1f4b99" in hostile.body


def test_remaining_core_types_render() -> None:
    documents = [
        (
            "data-table",
            resource(
                "dataset",
                {
                    "columns": [
                        {"name": "name", "type": "string"},
                        {"name": "count", "type": "number"},
                    ],
                    "rows": [["alpha", 1], ["beta", 2]],
                    "total_count": 2,
                },
                "Example dataset",
            ),
            "alpha",
        ),
        (
            "service-card",
            resource(
                "service",
                {
                    "endpoint": "https://example.com/api/status",
                    "method": "GET",
                },
                "Example service",
            ),
            "https://example.com/api/status",
        ),
        (
            "error-card",
            resource(
                "error",
                {
                    "code": "not_found",
                    "message": "The example resource does not exist.",
                },
                "Example error",
            ),
            "not_found",
        ),
    ]
    for component, document, snippet in documents:
        output = render(document)
        assert output.component == component
        assert output.body.strip()
        assert snippet in output.body
        assert "<script" not in output.body.lower()
