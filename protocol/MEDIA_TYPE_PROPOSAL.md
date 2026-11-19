# Content Negotiation Media Type Proposal (v0.2 starting point)

> Status: **TBD — proposal only.** This document exists so the first protocol PR has guidance instead of a blank check, and so v0.2 has a concrete starting point. It is not part of v0.1.

## The problem

v0.1 uses generic `Accept: application/json` for structured resources. That works but collides with every other JSON API on the web and gives clients no way to distinguish a Structured Web resource document from an arbitrary JSON response. A dedicated media type solves this.

## Proposal

Register a media type under the `application` tree:

```
application/vnd.structured-web.resource+json; version=0.1
```

### Rationale for the shape

- **`vnd.` prefix:** Signals a vendor-tree type. This is correct while the format is pre-standardization — once (if) it goes through IETF/W3C, it can be promoted to a standards-tree type like `application/structured-web.resource+json`.
- **`.resource+json`:** The suffix `+json` tells generic tools the payload is JSON, so existing JSON parsers and schema validators work without special handling. The `resource` segment names what the payload is.
- **`; version=0.1`:** Version travels in a parameter rather than the type name, so v0.2 can be `version=0.2` without breaking clients that understand v0.1. This mirrors how structured data formats like `application/ld+json` handle evolution loosely, but with an explicit, checkable parameter.

### Acceptance behavior

| Accept header | Server response |
| --- | --- |
| `application/vnd.structured-web.resource+json; version=0.1` | Resource document (v0.1 schema) |
| `application/vnd.structured-web.resource+json; version=0.2` | Resource document (v0.2 schema) if supported; else `406` with typed error `unsupported_version` |
| `application/json` | Resource document (legacy compatibility — v0.1 behavior preserved) |
| `text/html` | Human-rendered page |
| `*/*` or absent | Human-rendered page (progressive enhancement default) |

### Why not a simpler name

Alternatives considered:

- `application/sw+json` — too cryptic, no suffix semantics for tooling.
- `application/structured-web+json` — cleaner but the `+json` suffix attaches to the whole name, making `structured-web` the format identifier rather than `resource`. The `.resource` segment is more precise about payload intent and leaves room for future sibling types (e.g. `application/vnd.structured-web.manifest+json` for site manifests, `application/vnd.structured-web.action-result+json` for invoke responses).
- A custom top-level type like `structured-web/resource` — violates IANA conventions; `application` is the right tree.

### Open questions for v0.2

1. Should the version parameter be required or default to latest-known?
2. Should manifests and action results get their own media types or share the resource type with a `kind` field?
3. Is `vnd.` the right long-term home, or should this go through the standards tree early?
4. Do we want a `profile` parameter (RFC 6906) as an alternative or complement to the version parameter for vocabulary selection?

### What the first protocol PR should do

- Implement content negotiation using `application/json` as specified in v0.1.
- Add this file's proposed media type as a *second*, equivalent Accept value that returns the identical document.
- Note in the PR which of the open questions above it took a position on, if any.
- Do **not** remove `application/json` support — that would break the v0.1 contract.