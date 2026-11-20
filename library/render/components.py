"""Built-in component renderers.

Names in this mapping are the only components the runtime can
instantiate. A catalog entry selects one of these names. It cannot point
at a file, a module path, or source text.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from library.render.markup import esc, safe_url

Renderer = Callable[[Mapping[str, object]], str]

_TEXT_INPUTS = {
    "email": "email",
    "url": "url",
    "date": "date",
    "number": "number",
    "file": "file",
    "text": "text",
}


def _content(document: Mapping[str, object]) -> dict:
    content = document.get("content")
    if isinstance(content, dict):
        return content
    return {}


def _json_block(value: object) -> str:
    try:
        dumped = json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        dumped = str(value)
    return f'<pre class="sw-content">{esc(dumped)}</pre>'


def render_generic(document: Mapping[str, object]) -> str:
    return _json_block(_content(document))


def render_article(document: Mapping[str, object]) -> str:
    content = _content(document)
    parts: list[str] = []
    summary = content.get("summary")
    if isinstance(summary, str) and summary:
        parts.append(f'<p class="sw-summary">{esc(summary)}</p>')
    byline: list[str] = []
    if isinstance(content.get("author"), str):
        byline.append(esc(content["author"]))
    if isinstance(content.get("published_at"), str):
        byline.append(esc(content["published_at"]))
    if byline:
        parts.append(f'<p class="sw-byline">{" · ".join(byline)}</p>')
    body = content.get("body")
    if isinstance(body, str) and body.strip():
        for paragraph in body.split("\n\n"):
            if paragraph.strip():
                parts.append(f'<p class="sw-body">{esc(paragraph)}</p>')
    tags = content.get("tags")
    if isinstance(tags, list):
        items = "".join(
            f"<li>{esc(tag)}</li>" for tag in tags if isinstance(tag, str)
        )
        if items:
            parts.append(f'<ul class="sw-tags">{items}</ul>')
    if not parts:
        return render_generic(document)
    return "".join(parts)


def render_form(document: Mapping[str, object]) -> str:
    content = _content(document)
    fields = content.get("fields")
    if not isinstance(fields, list):
        return render_generic(document)
    controls = [
        _field(field, index)
        for index, field in enumerate(fields)
        if isinstance(field, dict)
    ]
    submit = content.get("submit_action")
    note = ""
    if isinstance(submit, str) and submit:
        note = (
            '<p class="sw-submit">Submits the action '
            f'<span class="sw-action-name">{esc(submit)}</span>. '
            "This page does not post the form.</p>"
        )
    return (
        '<div class="sw-form" role="group" aria-label="Form fields">'
        f'{"".join(controls)}{note}</div>'
    )


def _field(field: Mapping[str, object], index: int) -> str:
    name = field.get("name") if isinstance(field.get("name"), str) else ""
    label_text = field.get("label") if isinstance(field.get("label"), str) else ""
    label = label_text or name or f"Field {index + 1}"
    field_id = f"sw-field-{index}"
    required = " required" if field.get("required") is True else ""
    kind = field.get("type")
    control = _control(field, field_id, name, kind, required)
    return (
        '<div class="sw-field">'
        f'<label for="{field_id}">{esc(label)}</label>'
        f"{control}</div>"
    )


def _control(
    field: Mapping[str, object],
    field_id: str,
    name: str,
    kind: object,
    required: str,
) -> str:
    name_attr = esc(name, attr=True)
    default = field.get("default")
    if kind == "textarea":
        text = esc(default) if isinstance(default, str) else ""
        return (
            f'<textarea id="{field_id}" name="{name_attr}"{required}>'
            f"{text}</textarea>"
        )
    if kind == "select":
        options = field.get("options")
        items = ""
        if isinstance(options, list):
            rendered: list[str] = []
            for option in options:
                if not isinstance(option, str):
                    continue
                selected = " selected" if option == default else ""
                rendered.append(
                    f'<option value="{esc(option, attr=True)}"{selected}>'
                    f"{esc(option)}</option>"
                )
            items = "".join(rendered)
        return (
            f'<select id="{field_id}" name="{name_attr}"{required}>{items}</select>'
        )
    if kind == "boolean":
        checked = " checked" if default is True else ""
        return (
            f'<input id="{field_id}" type="checkbox" name="{name_attr}"{checked}>'
        )
    input_type = _TEXT_INPUTS.get(kind, "text") if isinstance(kind, str) else "text"
    value = ""
    if isinstance(default, str) or (
        isinstance(default, (int, float)) and not isinstance(default, bool)
    ):
        value = f' value="{esc(default, attr=True)}"'
    return (
        f'<input id="{field_id}" type="{input_type}" '
        f'name="{name_attr}"{required}{value}>'
    )


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        try:
            dumped = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            dumped = str(value)
        return esc(dumped)
    return esc(value)


def render_dataset(document: Mapping[str, object]) -> str:
    content = _content(document)
    columns = content.get("columns")
    rows = content.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return render_generic(document)
    headers = []
    for column in columns:
        if isinstance(column, dict):
            headers.append(esc(column.get("name")))
        else:
            headers.append("")
    head = "".join(f'<th scope="col">{header}</th>' for header in headers)
    body_rows: list[str] = []
    width = len(headers)
    for row in rows:
        cells = row if isinstance(row, list) else [row]
        rendered = [_cell(cells[index]) if index < len(cells) else "" for index in range(width)]
        extra = [_cell(value) for value in cells[width:]]
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in rendered + extra) + "</tr>")
    notes: list[str] = []
    total = content.get("total_count")
    if isinstance(total, int) and not isinstance(total, bool):
        notes.append(f"<p>{total} rows</p>")
    next_page = safe_url(content.get("next_page"))
    if next_page is not None:
        notes.append(
            f'<p><a href="{esc(next_page, attr=True)}">Next page</a></p>'
        )
    return (
        "<table>"
        f"<thead><tr>{head}</tr></thead>"
        f'<tbody>{"".join(body_rows)}</tbody>'
        "</table>"
        + "".join(notes)
    )


def render_service(document: Mapping[str, object]) -> str:
    content = _content(document)
    endpoint = content.get("endpoint")
    parts: list[str] = []
    if isinstance(endpoint, str):
        safe = safe_url(endpoint)
        shown = (
            f'<a href="{esc(safe, attr=True)}">{esc(endpoint)}</a>'
            if safe is not None
            else esc(endpoint)
        )
        method = content.get("method") if isinstance(content.get("method"), str) else ""
        method_html = f"{esc(method)} " if method else ""
        parts.append(f"<p>{method_html}{shown}</p>")
    health = safe_url(content.get("health_check"))
    if health is not None:
        parts.append(
            f'<p>Health: <a href="{esc(health, attr=True)}">{esc(health)}</a></p>'
        )
    limit = content.get("rate_limit")
    if isinstance(limit, dict):
        rate = limit.get("requests_per_minute")
        if isinstance(rate, int) and not isinstance(rate, bool):
            parts.append(f"<p>{rate} requests per minute</p>")
    if not parts:
        return render_generic(document)
    return "".join(parts)


def render_error(document: Mapping[str, object]) -> str:
    content = _content(document)
    parts: list[str] = []
    if isinstance(content.get("code"), str):
        parts.append(f'<p class="sw-error-code">{esc(content["code"])}</p>')
    if isinstance(content.get("message"), str):
        parts.append(f'<p class="sw-error-message">{esc(content["message"])}</p>')
    details = content.get("details")
    if isinstance(details, dict) and details:
        parts.append(_json_block(details))
    if not parts:
        return render_generic(document)
    return "".join(parts)


BUILTIN_RENDERERS: dict[str, Renderer] = {
    "article-card": render_article,
    "form-card": render_form,
    "data-table": render_dataset,
    "service-card": render_service,
    "error-card": render_error,
    "generic": render_generic,
}
