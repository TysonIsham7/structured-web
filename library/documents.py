"""Load and validate resource documents with the language layer."""

from __future__ import annotations

import json
from pathlib import Path

from library._bootstrap import validator_module
from library.errors import LibraryError

_schema: dict | None = None
_vocabulary: dict | None = None


def loaded_language() -> tuple[dict, dict]:
    """Load the v0.1 schema and core vocabulary once."""
    global _schema, _vocabulary
    if _schema is None or _vocabulary is None:
        module = validator_module()
        _schema = module.load_schema()
        _vocabulary = module.load_vocabulary()
    return _schema, _vocabulary


def require_document(document: object) -> dict:
    """Return `document` when the language validator accepts it."""
    if not isinstance(document, dict):
        raise LibraryError(
            "document_invalid",
            "document must be a JSON object",
            ("$: document must be a JSON object",),
        )
    module = validator_module()
    schema, vocabulary = loaded_language()
    errors = module.validate_document(document, schema, vocabulary)
    if errors:
        raise LibraryError(
            "document_invalid",
            "document failed language validation",
            tuple(errors),
        )
    return document


def load_document(path: str | Path) -> dict:
    """Read a JSON file and validate it as a resource document."""
    source = Path(path)
    module = validator_module()
    try:
        document = module.load_json(source)
    except OSError as exc:
        raise LibraryError(
            "document_invalid",
            f"could not read {source.name}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise LibraryError(
            "document_invalid",
            f"{source.name}: {exc.msg} (line {exc.lineno}, column {exc.colno})",
        ) from exc
    return require_document(document)
