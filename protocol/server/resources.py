"""The three language examples the reference server publishes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from library._bootstrap import validator_module
from library.documents import loaded_language

EXAMPLES: tuple[tuple[str, str], ...] = (
    ("/articles/getting-started", "article.json"),
    ("/resources/example-product", "product.json"),
    ("/forms/contact", "form.json"),
)


@dataclass(frozen=True)
class Resource:
    """One document the server can negotiate."""

    path: str
    document: dict
    body: bytes
    authenticated: bool = False
    list_in_manifest: bool = True


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def examples_dir() -> Path:
    return repo_root() / "language" / "examples"


def load_default_resources() -> tuple[Resource, ...]:
    """Load and validate the three milestone examples."""
    module = validator_module()
    schema, vocabulary = loaded_language()
    loaded: list[Resource] = []
    for path, filename in EXAMPLES:
        source = examples_dir() / filename
        body = source.read_bytes()
        document = json.loads(body)
        errors = module.validate_document(document, schema, vocabulary)
        if errors:
            joined = "; ".join(errors)
            raise RuntimeError(f"{filename} failed validation: {joined}")
        if not isinstance(document, dict):
            raise RuntimeError(f"{filename} is not a JSON object")
        loaded.append(Resource(path=path, document=document, body=body))
    return tuple(loaded)


def validation_errors(document: object) -> list[str]:
    """Return language-validator lines. Empty means the document is valid."""
    module = validator_module()
    schema, vocabulary = loaded_language()
    return module.validate_document(document, schema, vocabulary)


def manifest_document(origin: str, resources: tuple[Resource, ...]) -> dict:
    """Build the v0.1 site manifest.

    `agent_id` is null until an identity layer exists. Resource URIs are
    the negotiable page URLs on this origin.
    """
    listed = []
    for resource in resources:
        if not resource.list_in_manifest:
            continue
        document = resource.document
        resource_type = document.get("type")
        title = document.get("title")
        if not isinstance(resource_type, str) or not isinstance(title, str):
            continue
        listed.append(
            {
                "uri": origin.rstrip("/") + resource.path,
                "type": resource_type,
                "title": title,
            }
        )
    return {
        "version": "0.1.0",
        "site": origin.rstrip("/"),
        "agent_id": None,
        "resources": listed,
    }
