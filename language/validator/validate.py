#!/usr/bin/env python3
"""Validate a Structured Web v0.1 resource document.

Usage:
    python language/validator/validate.py <file>

Prints VALID, or INVALID followed by one JSONPath error per line.
Exit status is 0 when the document is valid, 1 when it is not, and 2
when the command line is wrong or a validator file cannot be loaded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "language" / "schema" / "resource.schema.json"
VOCABULARY_PATH = REPO_ROOT / "vocabularies" / "core.json"

FORMAT_CHECKER = Draft202012Validator.FORMAT_CHECKER


def load_json(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _missing_property(message: str) -> str | None:
    """Pull the property name out of a jsonschema required-keyword message."""
    if message.startswith("'") and "' " in message:
        return message.split("'", 2)[1]
    if message.startswith('"') and '" ' in message:
        return message.split('"', 2)[1]
    return None


def _with_prefix(json_path: str, prefix: str) -> str:
    if prefix == "$":
        return json_path
    if json_path == "$":
        return prefix
    if json_path.startswith("$"):
        return prefix + json_path[1:]
    return f"{prefix}.{json_path}"


def format_error(error, prefix: str = "$") -> str:
    """Render one ValidationError as '<jsonpath>: <message>'."""
    path = error.json_path or "$"
    if error.validator == "required":
        missing = _missing_property(error.message)
        if missing:
            path = f"{path}.{missing}" if path != "$" else f"$.{missing}"
    path = _with_prefix(path, prefix)
    message = " ".join(str(error.message).split())
    return f"{path}: {message}"


def _validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def vocabulary_errors(document: dict, vocabulary: dict) -> list[str]:
    """Check type membership and content against vocabularies/core.json."""
    errors: list[str] = []
    types = vocabulary.get("types")
    if not isinstance(types, dict):
        return ["$.type: core vocabulary has no types object"]

    resource_type = document.get("type")
    if not isinstance(resource_type, str):
        return errors
    if resource_type not in types:
        return [
            f"$.type: {resource_type!r} is not defined in the core vocabulary"
        ]

    content = document.get("content")
    type_spec = types[resource_type]
    content_schema = (
        type_spec.get("content_schema") if isinstance(type_spec, dict) else None
    )
    if isinstance(content, dict) and isinstance(content_schema, dict):
        for error in _validator(content_schema).iter_errors(content):
            errors.append(format_error(error, prefix="$.content"))
    return errors


def duplicate_action_errors(document: dict) -> list[str]:
    """Action names are unique within one resource."""
    actions = document.get("actions")
    if not isinstance(actions, list):
        return []
    seen: dict[str, int] = {}
    errors: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        name = action.get("name")
        if not isinstance(name, str):
            continue
        if name in seen:
            errors.append(
                f"$.actions[{index}].name: duplicate action name {name!r} "
                f"(also at $.actions[{seen[name]}].name)"
            )
        else:
            seen[name] = index
    return errors


def embedded_schema_errors(document: dict) -> list[str]:
    """input_schema and output_schema must be valid JSON Schemas."""
    actions = document.get("actions")
    if not isinstance(actions, list):
        return []
    errors: list[str] = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        for key in ("input_schema", "output_schema"):
            candidate = action.get(key)
            if not isinstance(candidate, dict):
                continue
            try:
                Draft202012Validator.check_schema(candidate)
            except SchemaError as exc:
                detail = " ".join(str(getattr(exc, "message", exc)).split())
                errors.append(
                    f"$.actions[{index}].{key}: not a valid JSON Schema ({detail})"
                )
    return errors


def validate_document(
    document: object, schema: dict, vocabulary: dict
) -> list[str]:
    """Return error lines. An empty list means the document is valid."""
    errors = [
        format_error(error) for error in _validator(schema).iter_errors(document)
    ]
    if isinstance(document, dict):
        errors.extend(vocabulary_errors(document, vocabulary))
        errors.extend(duplicate_action_errors(document))
        errors.extend(embedded_schema_errors(document))
    errors.sort()
    return errors


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    schema = load_json(path)
    if not isinstance(schema, dict):
        raise SchemaError("resource schema is not a JSON object")
    Draft202012Validator.check_schema(schema)
    return schema


def load_vocabulary(path: Path = VOCABULARY_PATH) -> dict:
    vocabulary = load_json(path)
    if not isinstance(vocabulary, dict):
        raise SchemaError("core vocabulary is not a JSON object")
    types = vocabulary.get("types")
    if not isinstance(types, dict):
        raise SchemaError("core vocabulary is missing a types object")
    for name, spec in types.items():
        content_schema = (
            spec.get("content_schema") if isinstance(spec, dict) else None
        )
        if not isinstance(content_schema, dict):
            raise SchemaError(f"core type {name!r} is missing a content_schema object")
        Draft202012Validator.check_schema(content_schema)
    return vocabulary


def render_result(errors: list[str]) -> tuple[int, str]:
    if errors:
        return 1, "INVALID\n" + "\n".join(errors) + "\n"
    return 0, "VALID\n"


def validate_path(
    path: Path, schema: dict, vocabulary: dict
) -> tuple[int, str]:
    if not path.is_file():
        return 1, f"INVALID\n$: file not found: {path}\n"
    try:
        document = load_json(path)
    except json.JSONDecodeError as exc:
        return 1, (
            f"INVALID\n$: {exc.msg} (line {exc.lineno}, column {exc.colno})\n"
        )
    return render_result(validate_document(document, schema, vocabulary))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print(
            "usage: python language/validator/validate.py <file>",
            file=sys.stderr,
        )
        return 2
    try:
        schema = load_schema()
        vocabulary = load_vocabulary()
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        print(f"validator setup failed: {exc}", file=sys.stderr)
        return 2
    code, text = validate_path(Path(args[0]), schema, vocabulary)
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
