"""Accept-header negotiation for resource documents and site manifests.

Rules are fixed in protocol/DECISIONS.md. Short version: an absent
header or `*/*` is the human page; the vendor resource type and
`application/json` both return the document; an explicit vendor
version other than 0.1 loses to nothing we can serve.
"""

from __future__ import annotations

from dataclasses import dataclass

from protocol.media import (
    HTML_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    MANIFEST_CONTENT_TYPE,
    MANIFEST_MEDIA_TYPE,
    RESOURCE_CONTENT_TYPE,
    RESOURCE_MEDIA_TYPE,
    RESOURCE_VERSION,
)

_VENDOR_SUBTYPE = RESOURCE_MEDIA_TYPE.split("/", 1)[1]
_MANIFEST_SUBTYPE = MANIFEST_MEDIA_TYPE.split("/", 1)[1]
_IGNORED_PARAMETERS = frozenset({"charset"})


@dataclass(frozen=True)
class Negotiation:
    """The representation to send, or a refusal."""

    kind: str
    content_type: str


HTML = Negotiation("html", HTML_CONTENT_TYPE)
JSON = Negotiation("json", JSON_CONTENT_TYPE)
VENDOR = Negotiation("vendor", RESOURCE_CONTENT_TYPE)
UNSUPPORTED_VERSION = Negotiation("unsupported_version", JSON_CONTENT_TYPE)
NOT_ACCEPTABLE = Negotiation("not_acceptable", JSON_CONTENT_TYPE)
MANIFEST = Negotiation("manifest", MANIFEST_CONTENT_TYPE)


@dataclass(frozen=True)
class _Range:
    type: str
    subtype: str
    parameters: dict[str, str]
    q: float

    @property
    def specific(self) -> bool:
        return self.type != "*"


def negotiate_resource(header: str | None) -> Negotiation:
    """Pick a resource representation for an Accept header."""
    if header is None or header.strip() == "":
        return HTML
    ranges = _parse_accept(header)
    if not ranges:
        return NOT_ACCEPTABLE

    vendor_q = _best_q(ranges, "application", _VENDOR_SUBTYPE, version=RESOURCE_VERSION)
    json_q = _best_q(ranges, "application", "json")
    html_q = _best_q(ranges, "text", "html")
    star_q = _star_q(ranges)
    unsupported_q = _unsupported_version_q(ranges)

    specific = {"vendor": vendor_q, "json": json_q, "html": html_q}
    effective = {name: max(score, star_q) for name, score in specific.items()}
    best = max(effective.values())
    if unsupported_q > best and unsupported_q > 0:
        return UNSUPPORTED_VERSION
    if best <= 0:
        if unsupported_q > 0:
            return UNSUPPORTED_VERSION
        return NOT_ACCEPTABLE

    contenders = [name for name, score in effective.items() if score == best]
    specific_hits = [name for name in contenders if specific[name] == best]
    if specific_hits:
        for name in ("vendor", "json", "html"):
            if name in specific_hits:
                return {"vendor": VENDOR, "json": JSON, "html": HTML}[name]
    return HTML


def negotiate_manifest(header: str | None) -> Negotiation:
    """Pick a manifest representation.

    The well-known endpoint is a JSON document. It has no HTML
    representation, including when the header is absent or `*/*`.
    """
    if header is None or header.strip() == "":
        return MANIFEST
    ranges = _parse_accept(header)
    manifest_q = _best_q(ranges, "application", _MANIFEST_SUBTYPE)
    json_q = _best_q(ranges, "application", "json")
    if manifest_q > 0 or _star_q(ranges) > 0 or _application_star_q(ranges) > 0:
        if json_q > manifest_q and _star_q(ranges) == 0 and _application_star_q(ranges) == 0:
            return JSON
        return MANIFEST
    if json_q > 0:
        return JSON
    return MANIFEST


def _parse_accept(header: str) -> list[_Range]:
    ranges: list[_Range] = []
    for part in _split_csv(header):
        parsed = _parse_range(part)
        if parsed is not None and parsed.q > 0:
            ranges.append(parsed)
    return ranges


def _parse_range(part: str) -> _Range | None:
    pieces = _split_semicolon(part)
    if not pieces:
        return None
    media = pieces[0].strip().lower()
    if "/" not in media:
        return None
    media_type, _, subtype = media.partition("/")
    if not media_type or not subtype or "/" in subtype:
        return None
    if media_type == "*" and subtype != "*":
        return None
    parameters: dict[str, str] = {}
    quality = 1.0
    for raw in pieces[1:]:
        if "=" not in raw:
            return None
        name, _, value = raw.partition("=")
        name = name.strip().lower()
        value = _unquote(value.strip())
        if not name or value == "":
            return None
        if name == "q":
            try:
                quality = float(value)
            except ValueError:
                return None
            if quality < 0 or quality > 1:
                return None
        else:
            parameters[name] = value
    return _Range(media_type, subtype, parameters, quality)


def _best_q(
    ranges: list[_Range],
    media_type: str,
    subtype: str,
    *,
    version: str | None = None,
) -> float:
    """Highest q among specific ranges that match this representation.

    `*/*` is not counted here. `version` set means a vendor type: a
    range with no version parameter matches, and any other version
    does not.
    """
    best = 0.0
    for item in ranges:
        if not item.specific:
            continue
        if not _type_matches(item, media_type, subtype):
            continue
        if not _parameters_match(item, version=version, vendor=version is not None):
            continue
        if item.q > best:
            best = item.q
    return best


def _parameters_match(_range: _Range, *, version: str | None, vendor: bool) -> bool:
    for name, value in _range.parameters.items():
        if name in _IGNORED_PARAMETERS:
            continue
        if name == "version" and vendor:
            if value != version:
                return False
            continue
        if name == "version" and not vendor:
            continue
        return False
    return True


def _unsupported_version_q(ranges: list[_Range]) -> float:
    best = 0.0
    for item in ranges:
        if not _type_matches(item, "application", _VENDOR_SUBTYPE):
            continue
        version = item.parameters.get("version")
        if version is None or version == RESOURCE_VERSION:
            continue
        if any(
            name not in _IGNORED_PARAMETERS and name != "version"
            for name in item.parameters
        ):
            continue
        if item.q > best:
            best = item.q
    return best


def _star_q(ranges: list[_Range]) -> float:
    best = 0.0
    for item in ranges:
        if item.type == "*" and item.subtype == "*" and item.q > best:
            best = item.q
    return best


def _application_star_q(ranges: list[_Range]) -> float:
    best = 0.0
    for item in ranges:
        if item.type == "application" and item.subtype == "*" and item.q > best:
            best = item.q
    return best


def _type_matches(item: _Range, media_type: str, subtype: str) -> bool:
    if item.type == "*" and item.subtype == "*":
        return True
    if item.type != media_type:
        return False
    return item.subtype in {"*", subtype}


def _split_csv(value: str) -> list[str]:
    return _split_on(value, ",")


def _split_semicolon(value: str) -> list[str]:
    return _split_on(value, ";")


def _split_on(value: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quoted = False
    for char in value:
        if char == '"':
            quoted = not quoted
            current.append(char)
            continue
        if char == separator and not quoted:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value
