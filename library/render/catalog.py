"""Load a component catalog.

The catalog is data. Resolving a name means looking it up in
`BUILTIN_RENDERERS`. There is no import step and no evaluation of
document or catalog strings as code.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from library._bootstrap import repo_root
from library.errors import LibraryError
from library.render.components import BUILTIN_RENDERERS

DEFAULT_CATALOG_PATH = repo_root() / "library" / "catalog" / "default.json"


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    version: str
    types: tuple[str, ...]
    capabilities: tuple[str, ...]
    signature: None = None


@dataclass(frozen=True)
class Catalog:
    version: str
    name: str
    entries: tuple[CatalogEntry, ...]
    signature: None = None

    def get(self, component_name: str) -> CatalogEntry | None:
        for entry in self.entries:
            if entry.name == component_name:
                return entry
        return None

    def for_type(self, type_name: str) -> CatalogEntry | None:
        """Return the first entry that lists this resource type.

        The generic entry uses ``*`` and is not returned here. Callers
        fall back to `generic()` when this returns None.
        """
        for entry in self.entries:
            if type_name in entry.types and "*" not in entry.types:
                return entry
        return None

    def generic(self) -> CatalogEntry | None:
        for entry in self.entries:
            if "*" in entry.types or entry.name == "generic":
                return entry
        return None


def load_catalog(path: str | Path = DEFAULT_CATALOG_PATH) -> Catalog:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise LibraryError(
            "catalog_invalid",
            f"could not read {source.name}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise LibraryError(
            "catalog_invalid",
            f"catalog is not JSON ({exc.msg})",
        ) from exc
    return catalog_from_data(raw)


def catalog_from_data(data: object) -> Catalog:
    if not isinstance(data, dict):
        raise LibraryError("catalog_invalid", "catalog must be a JSON object")
    version = data.get("version")
    name = data.get("name")
    if not isinstance(version, str) or not version:
        raise LibraryError("catalog_invalid", "catalog version must be a string")
    if not isinstance(name, str) or not name:
        raise LibraryError("catalog_invalid", "catalog name must be a string")
    if "signature" not in data or data.get("signature") is not None:
        raise LibraryError(
            "catalog_invalid",
            "catalog signature must be null in v0.1; verification is not implemented",
        )
    components = data.get("components")
    if not isinstance(components, list) or not components:
        raise LibraryError(
            "catalog_invalid",
            "catalog components must be a non-empty array",
        )
    seen: set[str] = set()
    entries = tuple(
        _entry(raw, index, seen) for index, raw in enumerate(components)
    )
    return Catalog(version=version, name=name, entries=entries, signature=None)


def _entry(raw: object, index: int, seen: set[str]) -> CatalogEntry:
    where = f"components[{index}]"
    if not isinstance(raw, dict):
        raise LibraryError("catalog_invalid", f"{where} must be an object")
    if "signature" not in raw or raw.get("signature") is not None:
        raise LibraryError(
            "catalog_invalid",
            f"{where}.signature must be null in v0.1; verification is not implemented",
        )
    name = raw.get("name")
    version = raw.get("version")
    types = raw.get("types")
    capabilities = raw.get("capabilities")
    if not isinstance(name, str) or not name:
        raise LibraryError("catalog_invalid", f"{where}.name must be a string")
    if name in seen:
        raise LibraryError("catalog_invalid", f"duplicate component name {name!r}")
    if name not in BUILTIN_RENDERERS:
        raise LibraryError(
            "catalog_invalid",
            f"component {name!r} is not a built-in module; the catalog cannot load code",
        )
    if not isinstance(version, str) or not version:
        raise LibraryError("catalog_invalid", f"{where}.version must be a string")
    if (
        not isinstance(types, list)
        or not types
        or not all(isinstance(item, str) and item for item in types)
    ):
        raise LibraryError(
            "catalog_invalid",
            f"{where}.types must be a non-empty list of strings",
        )
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise LibraryError(
            "catalog_invalid",
            f"{where}.capabilities must be a list of strings",
        )
    seen.add(name)
    return CatalogEntry(
        name=name,
        version=version,
        types=tuple(types),
        capabilities=tuple(capabilities),
        signature=None,
    )
