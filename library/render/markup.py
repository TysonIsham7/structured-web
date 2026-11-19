"""HTML projection helpers.

Text from a document is escaped. URLs are limited to http(s) and
relative references. This module does not emit script, event handlers,
or inline SVG from document data.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

_CLASS_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}")
_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_DEFAULT_ACCENT = "#1f4b99"

_STYLE = """
:root { color-scheme: light; }
body {
  margin: 0;
  font: 16px/1.5 "Segoe UI", "Helvetica Neue", sans-serif;
  color: #1c1c1c;
  background: #f6f5f2;
}
main {
  max-width: 42rem;
  margin: 2rem auto;
  padding: 1.5rem 1.5rem 2rem;
  background: #fff;
  border-top: 4px solid __ACCENT__;
}
h1 { font-size: 1.8rem; line-height: 1.25; margin: 0.2rem 0 1rem; }
h2 { font-size: 1rem; margin: 1.4rem 0 0.4rem; }
.sw-type {
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: __ACCENT__;
  font-size: 0.75rem;
}
a { color: __ACCENT__; }
img { max-width: 100%; height: auto; }
.sw-body, .sw-summary { white-space: pre-wrap; }
.sw-field { margin: 0.6rem 0; }
label { display: block; font-weight: 600; }
input, select, textarea {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  padding: 0.3rem 0.4rem;
}
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.3rem 0.5rem; text-align: left; }
.sw-risk {
  font-size: 0.75rem;
  border: 1px solid #ccc;
  padding: 0 0.35rem;
  margin-left: 0.4rem;
}
pre { overflow: auto; background: #f6f5f2; padding: 0.75rem; }
footer { color: #444; }
""".strip()


def esc(value: object, *, attr: bool = False) -> str:
    """Escape document text for an HTML text node or attribute."""
    if value is None:
        return ""
    return html.escape(str(value), quote=attr)


def safe_url(value: object) -> str | None:
    """Return a URL that is safe to put in href or src, or None.

    Allows http, https, and relative references. Rejects scriptable
    schemes, protocol-relative URLs, credentials in the URL, and
    control characters.
    """
    if not isinstance(value, str) or value == "":
        return None
    if "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    if value.startswith("//"):
        return None
    parts = urlsplit(value)
    if parts.username or parts.password:
        return None
    scheme = parts.scheme.lower()
    if scheme in {"http", "https"} and parts.netloc:
        return value
    if scheme == "" and parts.netloc == "":
        return value
    return None


def theme_class(theme: Mapping[str, object] | None) -> str:
    raw = theme.get("class_name") if theme else None
    if isinstance(raw, str) and _CLASS_NAME.fullmatch(raw):
        return raw
    return "sw-default"


def theme_accent(theme: Mapping[str, object] | None) -> str:
    raw = theme.get("accent") if theme else None
    if isinstance(raw, str) and _HEX_COLOR.fullmatch(raw):
        return raw
    return _DEFAULT_ACCENT


def stylesheet(theme: Mapping[str, object] | None) -> str:
    return _STYLE.replace("__ACCENT__", theme_accent(theme))


def render_links(document: Mapping[str, object]) -> str:
    links = document.get("links")
    if not isinstance(links, list) or not links:
        return ""
    items: list[str] = []
    for link in links:
        if not isinstance(link, dict):
            continue
        href = safe_url(link.get("href"))
        title = link.get("title") if isinstance(link.get("title"), str) else ""
        rel = link.get("rel") if isinstance(link.get("rel"), str) else ""
        label = title or href or rel or "link"
        if href is None:
            items.append(f"<li>{esc(label)}</li>")
            continue
        rel_attr = f' rel="{esc(rel, attr=True)}"' if rel else ""
        items.append(
            f'<li><a href="{esc(href, attr=True)}"{rel_attr}>{esc(label)}</a></li>'
        )
    if not items:
        return ""
    body = "".join(items)
    return (
        '<nav class="sw-links" aria-label="Related">'
        "<h2>Links</h2>"
        f"<ul>{body}</ul></nav>"
    )


def render_actions(document: Mapping[str, object]) -> str:
    actions = document.get("actions")
    if not isinstance(actions, list) or not actions:
        return ""
    items: list[str] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        name = esc(action.get("name"))
        risk = esc(action.get("risk"))
        description = esc(action.get("description"))
        items.append(
            "<li>"
            f'<span class="sw-action-name">{name}</span>'
            f'<span class="sw-risk">{risk}</span>'
            f'<span class="sw-action-desc"> {description}</span>'
            "</li>"
        )
    if not items:
        return ""
    return (
        '<section class="sw-actions">'
        "<h2>Actions</h2>"
        "<p>Declared for the agent runtime. This page does not run them.</p>"
        f'<ul>{"".join(items)}</ul></section>'
    )


def content_image_srcs(document: Mapping[str, object]) -> set[str]:
    content = document.get("content")
    if not isinstance(content, dict):
        return set()
    images = content.get("images")
    if not isinstance(images, list):
        return set()
    srcs: set[str] = set()
    for image in images:
        if isinstance(image, dict) and isinstance(image.get("src"), str):
            srcs.add(image["src"])
    return srcs


def render_media(document: Mapping[str, object], skip_srcs: set[str]) -> str:
    hint = document.get("render")
    if not isinstance(hint, dict):
        return ""
    media = hint.get("media")
    if not isinstance(media, list) or not media:
        return ""
    parts: list[str] = []
    for item in media:
        if not isinstance(item, dict):
            continue
        src_value = item.get("src")
        if isinstance(src_value, str) and src_value in skip_srcs:
            continue
        src = safe_url(src_value)
        if src is None:
            continue
        alt = item.get("alt") if isinstance(item.get("alt"), str) else ""
        if item.get("type") == "image":
            parts.append(
                "<figure>"
                f'<img src="{esc(src, attr=True)}" alt="{esc(alt, attr=True)}">'
                "</figure>"
            )
            continue
        label = alt or (item.get("type") if isinstance(item.get("type"), str) else src)
        parts.append(f'<p><a href="{esc(src, attr=True)}">{esc(label)}</a></p>')
    if not parts:
        return ""
    return f'<div class="sw-media">{"".join(parts)}</div>'


def render_provenance(document: Mapping[str, object]) -> str:
    provenance = document.get("provenance")
    if not isinstance(provenance, dict):
        return ""
    source = provenance.get("source")
    fetched = provenance.get("fetched_at")
    source_html = esc(source)
    safe = safe_url(source)
    if safe is not None:
        source_html = f'<a href="{esc(safe, attr=True)}">{esc(safe)}</a>'
    fetched_html = esc(fetched) if isinstance(fetched, str) else ""
    return (
        '<footer class="sw-provenance">'
        "<h2>Provenance</h2>"
        f"<p>Source: {source_html}</p>"
        f"<p>Fetched: {fetched_html}</p>"
        "</footer>"
    )


def document_page(
    document: Mapping[str, object],
    fragment: str,
    *,
    component: str,
    fallback: bool,
    theme: Mapping[str, object] | None,
) -> str:
    """Wrap a component fragment in a full HTML document."""
    title = esc(document.get("title"))
    resource_type = esc(document.get("type"), attr=True)
    resource_id = esc(document.get("id"), attr=True)
    fallback_attr = "true" if fallback else "false"
    css = stylesheet(theme)
    body_class = esc(f"sw-root {theme_class(theme)}", attr=True)
    skip = content_image_srcs(document)
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title}</title>",
        f"<style>{css}</style>",
        "</head>",
        f'<body class="{body_class}">',
        (
            '<main class="sw-resource"'
            f' data-type="{resource_type}"'
            f' data-component="{esc(component, attr=True)}"'
            f' data-fallback="{fallback_attr}"'
            f' data-resource-id="{resource_id}">'
        ),
        f'<p class="sw-type">{esc(document.get("type"))}</p>',
        f"<h1>{title}</h1>",
        fragment,
        render_media(document, skip),
        render_links(document),
        render_actions(document),
        render_provenance(document),
        "</main>",
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(parts)
