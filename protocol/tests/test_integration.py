"""Cross-layer flow: fetch, validate, render, discover, invoke.

The server is the one CI starts, or a loopback server the fixture
starts when that port is free. The client negotiates the document.
The language validator accepts it. The library renders it and runs
the action through the agent runtime.
"""

from __future__ import annotations

import json

from library._bootstrap import validator_module
from library.documents import loaded_language
from library.render import RenderOptions, render
from protocol.client import Client, SessionOptions
from protocol.media import RESOURCE_CONTENT_TYPE
from protocol.server.resources import EXAMPLES, examples_dir

COMPONENTS = {
    "article": "article-card",
    "form": "form-card",
}


def test_fetch_validate_render_and_invoke(base_url: str) -> None:
    client = Client()
    manifest = client.fetch_manifest(base_url)
    assert manifest["agent_id"] is None
    assert len(manifest["resources"]) == 3
    assert {item["type"] for item in manifest["resources"]} == {"article", "form"}

    module = validator_module()
    schema, vocabulary = loaded_language()
    fetched = []
    for entry in manifest["resources"]:
        got = client.fetch_resource(entry["uri"])
        assert got.content_type == RESOURCE_CONTENT_TYPE
        assert got.rate_limit_limit is not None
        assert module.validate_document(got.document, schema, vocabulary) == []
        assert got.document["type"] == entry["type"]
        assert got.document["title"] == entry["title"]
        source_name = dict(EXAMPLES)[entry["uri"].removeprefix(base_url)]
        assert got.document == json.loads(
            (examples_dir() / source_name).read_text(encoding="utf-8")
        )
        rendered = render(got.document, RenderOptions(medium="screen"))
        assert rendered.component == COMPONENTS[got.document["type"]]
        assert rendered.fallback is False
        assert got.document["title"] in rendered.body
        assert "<script" not in rendered.body.lower()
        assert rendered.body.lstrip().startswith("<!DOCTYPE html>")
        fetched.append(got)

    calls = []

    def perform(action, args, context):
        calls.append((action["name"], args["list"], context["resource_type"]))
        return {"saved": True}

    def consent(action, args, context):
        raise AssertionError("a low-risk action must not ask for consent")

    article = next(
        item.document
        for item in fetched
        if any(action.get("name") == "bookmark" for action in item.document["actions"])
    )
    outcome = client.invoke(
        article,
        "bookmark",
        {"list": "reading"},
        SessionOptions(
            state={"user": {"is_authenticated": True}},
            consent=consent,
            perform=perform,
        ),
    )
    assert [item["name"] for item in outcome.discovered] == ["bookmark"]
    assert outcome.discovered[0]["risk"] == "low"
    assert outcome.discovered[0]["preconditions"] == ["user.is_authenticated"]
    assert outcome.result.ok is True
    assert outcome.result.code == "ok"
    assert outcome.result.output == {"saved": True}
    assert calls == [("bookmark", "reading", "article")]


def test_invoke_reports_precondition_failed(base_url: str) -> None:
    client = Client()
    manifest = client.fetch_manifest(base_url)
    article_uri = next(
        item["uri"] for item in manifest["resources"] if item["type"] == "article"
    )
    document = client.fetch_resource(article_uri).document

    def perform(action, args, context):
        raise AssertionError("precondition failure must happen before perform")

    outcome = client.invoke(
        document,
        "bookmark",
        {"list": "reading"},
        SessionOptions(
            state={"user": {"is_authenticated": False}},
            perform=perform,
        ),
    )
    assert outcome.result.ok is False
    assert outcome.result.code == "precondition_failed"
    assert outcome.result.details == ("user.is_authenticated",)
