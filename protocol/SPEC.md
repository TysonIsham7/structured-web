# Protocol Spec: Discovery and Interaction

> **Layer:** Protocol — the rules that make the language and library compound across the web.
- **Status:** Spec v0.1. Build the first milestone below as a single PR.
> **Depends on:** `language/SPEC.md` v0.1 (document format) and `library/SPEC.md` v0.1 (agent runtime with discover/invoke).

## Purpose

Define how agents and clients find, fetch, and interact with structured resources across the open web. Without this layer, the language is a file format and the library is a local tool — nothing compounds. This protocol is what turns per-site adoption into a network.

## Design Constraints (non-negotiable)

1. **HTTP-native.** The protocol rides on existing HTTP semantics (methods, status codes, content negotiation). It does not require new transport infrastructure. This is the adoption play: it layers onto what already exists.
2. **Well-known discovery.** There is exactly one canonical way to find a resource's structured representation from its human URL, with no out-of-band configuration.
3. **Content negotiation, not URL rewriting.** The same URL serves both humans and agents; the `Accept` header selects the representation. Agents ask for the structured form; browsers get HTML.
4. **Explicit error semantics.** Protocol errors are typed and machine-readable, never opaque HTML error pages.
5. **No ambient trust.** Every interaction carries credentials or is explicitly public. There is no "whatever a browser session can do" mode for agents.

## Discovery Mechanism

### Well-known path

For any human-facing URL `https://example.com/path/to/page`, the structured representation is discoverable at:

```
https://example.com/.well-known/structured-web
```

This endpoint returns a **site manifest**: a JSON document listing the structured resources available on this site, each with its resource URI, type, and a link to its canonical document.

Site manifest schema (v0.1):

```json
{
  "version": "0.1.0",
  "site": "https://example.com",
  "resources": [
    {
      "uri": "https://example.com/path/to/page.sw.json",
      "type": "article",
      "title": "..."
    }
  ]
}
```

### Content negotiation

Alternatively (and preferably for individual resources), the resource's own URL responds to content negotiation:

- `Accept: application/json` (or a structured-web media type, TBD in v0.2) → returns the resource document.
- `Accept: text/html` → returns the human-rendered page.
- Missing or `*/*` → human-rendered page (progressive enhancement default).

The `.well-known` manifest is the bootstrap; content negotiation is the steady state.

## Interaction Flow

1. **Agent resolves a URL** (from a link, a search result, or user input).
2. **Agent fetches** `/.well-known/structured-web` or issues a content-negotiated request to the URL.
3. **Agent receives** a resource document (validated against the language schema).
4. **Agent creates a session** with the agent runtime (library layer), passing the document.
5. **Agent calls `discover()`** to see available actions, preconditions, and risk levels.
6. **Agent invokes** actions through the runtime, which enforces schema validation, precondition checks, and risk gating.
7. **Results are structured** — JSON matching the action's output schema — ready for chaining to another agent's input or for rendering.

## Credential Model (v0.1, minimal)

- Public resources: no credentials. Fetch and interact freely (subject to rate limits).
- Authenticated resources: the agent presents a bearer token (OAuth 2.0 access token or equivalent) in the `Authorization` header. The protocol does not define a new auth scheme in v0.1 — it consumes existing ones.
- **Scoped delegation and global agent identity are explicitly out of scope for v0.1.** They are the unsolved dependency identified in the thesis. This protocol must not pretend they are solved; it must leave clean extension points (a `credentials` field in session options, an `agent_id` field in manifests) so a future identity layer can slot in without breaking v0.1.

## Error Semantics

Protocol errors return JSON with a stable shape:

```json
{
  "error": {
    "code": "schema_invalid",
    "message": "Resource document failed validation.",
    "details": { "path": "/actions/0/risk", "expected": "enum" }
  }
}
```

Stable error codes for v0.1: `not_found`, `schema_invalid`, `unauthorized`, `forbidden`, `precondition_failed`, `rate_limited`, `unsupported_version`.

## Rate Limiting

- Agents are identified by credential or IP.
- Rate limit info is returned in standard headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) — compatible with existing API conventions.
- The protocol does not define abuse detection; it defines where the signals live.

## First Milestone (build this PR)

1. **A reference server** (one language — TypeScript or Python, justify in the PR) that: serves the three example documents from `language/examples/` over HTTP with content negotiation, exposes `/.well-known/structured-web` with a valid site manifest, and returns typed JSON errors for the stable error codes. At `protocol/server/`.
2. **A reference client** that: resolves a URL, fetches the manifest or content-negotiates, validates the returned document, creates an agent session, discovers actions, and invokes one action end-to-end. At `protocol/client/`.
3. **An integration test** that runs server + client together: fetch → validate → discover → invoke → assert structured output. This is the first cross-layer test in the repo.
4. **Documentation** of the content negotiation media type proposal (even if marked TBD) so v0.2 has a starting point.

## Deliberately Deferred (do not build)

- Global agent identity and scoped delegation (the unsolved layer — leave extension points only)
- A new auth scheme (consume OAuth 2.0 bearer tokens)
- WebSocket or streaming interaction
- Multi-site federation or cross-origin action chaining
- Formal standardization submission (IETF/W3C) — that comes after real-world usage

## Acceptance Criteria

- [ ] Server serves all three examples via content negotiation and the well-known manifest
- [ ] Client completes the full interaction flow against the server
- [ ] Integration test passes in CI
- [ ] Typed errors returned for at least three of the stable error codes
- [ ] PR description addresses how the design leaves room for a future identity layer without breaking v0.1