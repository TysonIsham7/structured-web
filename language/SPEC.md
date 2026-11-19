# Language Spec: Resource Document Format (RDF)

> **Layer:** Language — the canonical data representation.
> **Status:** Spec v0.1. Build the first milestone below as a single PR.
> **Depends on:** Nothing. This is the foundation.

## Purpose

Define a typed, schema-validated document format that a resource (a page, an API endpoint, a dataset, a service) returns as its *canonical* representation. Human-visible HTML/CSS/JS is generated *from* this document. Agents consume it directly. The format must be expressive enough to describe real web resources and strict enough that an agent can plan and act on it without guessing.

## Design Constraints (non-negotiable)

1. **JSON-based.** The canonical serialized form is JSON (or JSON-compatible). This is not dogma — it is pragmatism: every language, every agent runtime, and every browser can parse it with zero dependencies. Binary formats (MessagePack, CBOR) may be added later as transport optimizations, never as the canonical form.
2. **Schema-validated.** Every document must validate against a formal schema (JSON Schema draft 2020-12 as the baseline). Invalid documents are a protocol error, not a rendering problem.
3. **Self-describing.** A document should be understandable without out-of-band documentation. Field names, types, and action definitions carry their own meaning.
4. **Extensible without breakage.** Unknown fields must be ignorable (forward-compatible), not fatal. Versioning is explicit via a top-level `version` field.
5. **No executable code.** The document contains data and declarations only. No scripts, no eval targets, no inline logic. Logic lives in declared actions (server-side) or in the rendering library's component catalog.

## Document Structure (v0.1)

A resource document has these top-level fields:

```json
{
  "version": "0.1.0",
  "id": "urn:example:resource:123",
  "type": "article",
  "title": "Human-readable title",
  "content": { },
  "actions": [ ],
  "links": [ ],
  "provenance": { },
  "render": { }
}
```

### Field Definitions

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | string (semver) | yes | Format version. Agents use this to select a compatible parser. |
| `id` | string (URI) | yes | Durable, globally unique identifier for this resource. Stable across updates. |
| `type` | string | yes | Resource type from a registered vocabulary (see `vocabularies/`). Examples: `article`, `product`, `form`, `dataset`, `service`. |
| `title` | string | yes | Human-readable title. Also usable by agents as a display label. |
| `content` | object | yes | Typed content payload. Structure depends on `type` — each type defines its own content schema in the vocabulary. |
| `actions` | array | yes | Declared actions this resource supports. See Action Schema below. May be empty. |
| `links` | array | yes | Related resources. Each link has `rel`, `href`, and optional `title`. |
| `provenance` | object | yes | Where this data came from: source URI, fetched-at timestamp, content hash, signer if signed. |
| `render` | object | no | Human-oriented rendering hints: preferred component from the catalog, layout priority, media references. |

### Action Schema

Each entry in `actions`:

```json
{
  "name": "purchase",
  "description": "Complete a purchase for this product.",
  "input_schema": { },
  "output_schema": { },
  "preconditions": ["user.is_authenticated", "cart.non_empty"],
  "effects": ["order.created", "inventory.decremented"],
  "risk": "high",
  "idempotent": false
}
```

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | string | yes | Unique within the resource. Agents invoke by this name. |
| `description` | string | yes | What the action does. Plain language, also machine-readable. |
| `input_schema` | JSON Schema | yes | Arguments the agent must supply. |
| `output_schema` | JSON Schema | yes | What the action returns on success. |
| `preconditions` | array of strings | no | Conditions that must hold before invocation. Machine-checkable predicates from a standard predicate vocabulary. |
| `effects` | array of strings | no | State changes the action produces. Used for planning and audit. |
| `risk` | enum: `low`, `medium`, `high`, `critical` | yes | Impact classification. High/critical actions require explicit consent or pre-authorization. |
| `idempotent` | boolean | yes | Whether repeated identical calls are safe. |

### Provenance Object

```json
{
  "source": "https://example.com/api/resource/123",
  "fetched_at": "2026-11-19T00:00:00Z",
  "content_hash": "sha256:...",
  "signed_by": null
}
```

`signed_by` is null in v0.1 but the field exists so signed provenance can be added without a format break.

### Render Object

```json
{
  "preferred_component": "article-card",
  "layout_priority": 1,
  "media": [{"type": "image", "src": "...", "alt": "..."}]
}
```

All fields optional. The rendering library uses these as hints; it is not bound by them.

## Vocabulary System

Resource `type` values and action precondition/effect predicates come from versioned vocabularies shipped alongside the format:

- `vocabularies/core.json` — base types: `article`, `product`, `form`, `dataset`, `service`, `error`.
- Each type maps to a content schema.
- Vocabularies are themselves JSON documents with semver, so they can evolve independently of the format version.

## First Milestone (build this PR)

1. **Formal JSON Schema** for the v0.1 document structure above, including the action schema, at `language/schema/resource.schema.json`.
2. **Three example documents** exercising different types: an article, a product with a high-risk purchase action, and a form. At `language/examples/`.
3. **A minimal validator CLI** (Python or TypeScript — pick one, justify in the PR) that takes a file path and prints `VALID` or `INVALID` with specific error paths. At `language/validator/`.
4. **The core vocabulary file** at `vocabularies/core.json` defining at least the five base types with content schemas.
5. **Tests** covering: valid document passes, missing required field fails, unknown field is ignored (forward-compat), action schema validates, risk enum rejects bad values.

## Deliberately Deferred (do not build)

- Binary transport formats
- Signing/verification of provenance
- Streaming or chunked documents
- Multi-resource bundles
- A full vocabulary beyond core
- Any rendering or protocol logic — that belongs to the other layers

## Acceptance Criteria

- [ ] Schema validates all three example documents
- [ ] Validator CLI runs and produces correct output on all examples plus at least three negative test cases
- [ ] All tests pass in CI (GitHub Actions)
- [ ] PR description explains any deviations from this spec and why