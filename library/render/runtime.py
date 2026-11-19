"""Render a validated resource document through the trusted catalog.

`screen` returns an HTML document. `headless` returns JSON. Voice and
other media are rejected: the spec defers them.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from library.documents import load_document, require_document
from library.errors import LibraryError
from library.render.catalog import (
    DEFAULT_CATALOG_PATH,
    Catalog,
    CatalogEntry,
    catalog_from_data,
    load_catalog,
)
from library.render.components import BUILTIN_RENDERERS
from library.render.markup import document_page

_SUPPORTED_MEDIA = frozenset({"screen", "headless"})


@dataclass(frozen=True)
class RenderOptions:
    """Options for one render call.

    `catalog` may be omitted (the default catalog), a path, a catalog
    JSON object, or a `Catalog`. `strict` fails when a preferred
    component is not in the catalog instead of falling back.
    `theme` accepts `class_name` (a token) and `accent` (a `#rrggbb`
    color). Other theme values are ignored.
    """

    medium: str = "screen"
    catalog: Catalog | str | Path | Mapping[str, object] | None = None
    theme: Mapping[str, object] | None = None
    strict: bool = False


@dataclass(frozen=True)
class RenderedOutput:
    """One projection of a resource document.

    `body` is an HTML document for `screen` and a JSON text for
    `headless`. `value` is the headless object, or None for HTML.
    """

    medium: str
    component: str
    fallback: bool
    body: str
    value: dict | None = None


def render(
    document: object,
    options: RenderOptions | None = None,
) -> RenderedOutput:
    """Validate `document` and project it through the catalog."""
    options = options or RenderOptions()
    checked = require_document(document)
    if options.medium not in _SUPPORTED_MEDIA:
        raise LibraryError(
            "unsupported_medium",
            "v0.1 renders screen and headless only",
        )
    catalog = _resolve_catalog(options.catalog)
    entry, fallback = _select_component(checked, catalog, options.strict)
    if options.medium == "headless":
        payload = _headless_payload(checked, entry.name, fallback)
        try:
            body = json.dumps(
                payload,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise LibraryError(
                "document_invalid",
                "document content is not JSON data",
            ) from exc
        return RenderedOutput(
            medium="headless",
            component=entry.name,
            fallback=fallback,
            body=body + "\n",
            value=payload,
        )
    renderer = BUILTIN_RENDERERS[entry.name]
    fragment = renderer(checked)
    html = document_page(
        checked,
        fragment,
        component=entry.name,
        fallback=fallback,
        theme=options.theme,
    )
    return RenderedOutput(
        medium="screen",
        component=entry.name,
        fallback=fallback,
        body=html,
        value=None,
    )


def _resolve_catalog(catalog: object) -> Catalog:
    if catalog is None:
        return load_catalog(DEFAULT_CATALOG_PATH)
    if isinstance(catalog, Catalog):
        return catalog
    if isinstance(catalog, (str, Path)):
        return load_catalog(catalog)
    if isinstance(catalog, Mapping):
        return catalog_from_data(catalog)
    raise LibraryError(
        "catalog_invalid",
        "catalog must be a path, a JSON object, or a Catalog",
    )


def _select_component(
    document: Mapping[str, object],
    catalog: Catalog,
    strict: bool,
) -> tuple[CatalogEntry, bool]:
    preferred = ""
    hint = document.get("render")
    if isinstance(hint, dict) and isinstance(hint.get("preferred_component"), str):
        preferred = hint["preferred_component"]
    if preferred:
        entry = catalog.get(preferred)
        if entry is not None:
            return entry, False
        if strict:
            raise LibraryError(
                "component_unregistered",
                f"preferred component {preferred!r} is not in the catalog",
            )
    type_name = document.get("type")
    exact = catalog.for_type(type_name) if isinstance(type_name, str) else None
    if exact is not None:
        return exact, bool(preferred)
    generic = catalog.generic()
    if generic is not None:
        return generic, True
    raise LibraryError(
        "catalog_incomplete",
        "no catalog component for this type and no generic fallback",
    )


def _headless_payload(
    document: Mapping[str, object],
    component: str,
    fallback: bool,
) -> dict:
    actions = []
    raw_actions = document.get("actions")
    if isinstance(raw_actions, list):
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            actions.append(
                {
                    "name": action.get("name"),
                    "description": action.get("description"),
                    "risk": action.get("risk"),
                    "idempotent": action.get("idempotent"),
                    "preconditions": list(action.get("preconditions") or []),
                    "effects": list(action.get("effects") or []),
                }
            )
    return {
        "medium": "headless",
        "id": document.get("id"),
        "type": document.get("type"),
        "title": document.get("title"),
        "component": component,
        "fallback": fallback,
        "content": document.get("content"),
        "actions": actions,
        "links": document.get("links"),
    }


__all__ = [
    "RenderOptions",
    "RenderedOutput",
    "load_document",
    "render",
]
