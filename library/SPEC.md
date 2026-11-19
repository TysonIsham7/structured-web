# Library Spec: Rendering and Agent Runtimes

> **Layer:** Library — the runtimes developers import and call.
> **Status:** Spec v0.1. Build the first milestone below as a single PR.
> **Depends on:** `language/SPEC.md` v0.1 (the resource document format and schema).

## Purpose

Provide two runtimes that speak the resource description language:

1. **A rendering runtime** — takes a validated resource document and produces a human-visible interface using a trusted, registered component catalog. The server/agent emits intent and data; the client owns widgets, styling, and the security boundary.
2. **An agent runtime** — takes a validated resource document and exposes its declared actions as invocable, typed tools to an agent, with precondition checking and risk-gated consent.

Both runtimes consume the same document. Neither trusts the document to contain executable code.

## Design Constraints (non-negotiable)

1. **Component catalog is the security boundary.** The rendering runtime may only instantiate components registered in its catalog. An agent or malformed document cannot invent a widget that exfiltrates data. The catalog may be open and signed (allowing third-party components with verification) but never ambiently extensible at runtime from untrusted input.
2. **No eval, no dynamic code loading from documents.** Components are pre-compiled modules resolved by name from the catalog.
3. **Typed invocation only.** The agent runtime exposes actions exactly as declared: name, input schema, output schema. It does not expose raw HTTP, raw DOM, or raw network access.
4. **Risk gating is enforced in the runtime**, not left to the caller. `high` and `critical` actions require an explicit consent callback or a pre-authorized policy before invocation.
5. **Graceful degradation.** If a preferred component is unregistered, the runtime falls back to a generic renderer for that content type rather than failing hard.

## Rendering Runtime

### Interface (conceptual — implement in your chosen language)

```
render(document: ResourceDocument, options: RenderOptions) -> RenderedOutput
```

- `RenderOptions` includes: target medium (`screen`, `voice`, `headless`), catalog reference, theme/styling hooks, and a `strict` flag (fail on unregistered components vs. fall back).
- `RenderedOutput` is medium-dependent: an HTML string or DOM fragment for `screen`, a text/SSML summary for `voice`, structured JSON for `headless`.
- The runtime resolves `document.render.preferred_component` against the catalog. If absent or unregistered, it selects a default component for `document.type`.

### Component Catalog Format

Components are registered as catalog entries:

```json
{
  "name": "article-card",
  "version": "1.0.0",
  "types": ["article"],
  "capabilities": ["text", "media", "links"],
  "signature": null
}

```

`signature` is null in v0.1 (unsigned catalog) but the field exists for signed catalogs later.

Ship a minimal default catalog with at least one component for each of the six core vocabulary types (`article`, `product`, `form`, `dataset`, `service`, and `error`), plus a generic fallback.

## Agent Runtime

### Interface (conceptual)

```
createSession(document: ResourceDocument, options: SessionOptions) -> AgentSession
```

An `AgentSession` exposes:

- `discover() -> ActionCatalog` — returns the declared actions with schemas, preconditions, effects, and risk levels.
- `invoke(name: string, args: object) -> Result` — validates args against the action's input schema, checks preconditions against a provided state snapshot, enforces risk gating, and returns the structured output (or a typed error).
- `close()` — ends the session and releases any held state.

### Precondition Evaluation

Preconditions are strings from the standard predicate vocabulary (defined in `vocabularies/core.json`). The agent runtime evaluates them against a **state snapshot** supplied by the host application — it does not fetch or infer state itself. If a precondition cannot be evaluated, invocation fails with a typed `precondition_unknown` error rather than silently proceeding.

### Risk Gating

| Risk | Behavior |
| --- | --- |
| `low` | Invoke immediately. |
| `medium` | Invoke immediately; log to audit trail. |
| `high` | Require consent callback before invoke. |
| `critical` | Require consent callback **and** a pre-authorized policy match. |

The consent callback is a host-provided function: `(action, args, context) -> Promise<boolean>`.

## First Milestone (build this PR)

1. **Rendering runtime** in one language (TypeScript or Python — pick one, justify in the PR) that: loads and validates a resource document using the language schema, resolves components from a default catalog, and renders at least the three example documents from `language/examples/` to HTML. At `library/render/`.
2. **Agent runtime** in the same language that: creates a session from a document, exposes `discover()` and `invoke()`, enforces input schema validation and risk gating (with a mock consent callback in tests). At `library/agent/`.
3. **A default component catalog** (JSON) with entries for all six core vocabulary types, including `error`, plus a generic fallback. At `library/catalog/default.json`.
4. **Tests** covering: render of all three examples produces non-empty HTML; unregistered preferred component falls back gracefully; agent invoke with valid args succeeds; agent invoke with invalid args fails with a typed error; high-risk action blocks without consent; high-risk action proceeds with consent granted.
5. **A short usage example** (script or notebook) showing end-to-end: load document → render for screen → create agent session → discover → invoke one action.

## Deliberately Deferred (do not build)

- Signed component catalogs and signature verification
- Voice/AR render targets (screen + headless only for v0.1)
- Persistent cross-session agent state
- Distributed precondition state (single snapshot only)
- WASM targets
- Any protocol/network logic — discovery over HTTP belongs to the protocol layer

## Acceptance Criteria

- [ ] All three example documents render to HTML without errors
- [ ] Agent runtime passes all gating and validation tests
- [ ] Usage example runs cleanly end-to-end
- [ ] All tests pass in CI
- [ ] PR description explains language choice and any deviations from this spec