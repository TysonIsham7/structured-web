#!/usr/bin/env python3
"""Load a resource document, render it, and invoke one action.

    python library/examples/usage.py

Uses the article example. Bookmark is low risk, so the call does not
ask for consent. The host handler returns the action's declared output.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from library.agent import SessionOptions, create_session
from library.render import RenderOptions, load_document, render


def perform(action, args, context):
    if action.get("name") != "bookmark":
        raise RuntimeError("unexpected action")
    if context.get("resource_type") != "article":
        raise RuntimeError("unexpected resource")
    return {"saved": True}


def main() -> int:
    document = load_document(ROOT / "language" / "examples" / "article.json")
    rendered = render(document, RenderOptions(medium="screen"))
    if not rendered.body.strip() or document["title"] not in rendered.body:
        print("render produced empty HTML", file=sys.stderr)
        return 1
    if "<script" in rendered.body.lower():
        print("render emitted a script tag", file=sys.stderr)
        return 1
    session = create_session(
        document,
        SessionOptions(
            state={"user": {"is_authenticated": True}},
            perform=perform,
        ),
    )
    try:
        discovered = session.discover()
        result = session.invoke("bookmark", {"list": "reading"})
    finally:
        session.close()
    if not result.ok:
        print(f"{result.code}: {result.message}", file=sys.stderr)
        return 1
    names = ", ".join(item["name"] for item in discovered)
    print(f"component: {rendered.component}")
    print(f"fallback: {str(rendered.fallback).lower()}")
    print(f"html_bytes: {len(rendered.body.encode('utf-8'))}")
    print(f"actions: {names}")
    print(f"invoke: {result.code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
