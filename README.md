# Structured Web

> A ground-up redesign of the web for an agent-majority world: **structured data and explicit actions as the primary representation**, with human rendering as a high-quality projection of that structure.

## The Thesis

The current web is a human visual medium that agents are forced to reverse-engineer. A ground-up redesign for an agent-majority world inverts that. Instead of HTML and JavaScript as the foundation with machine-readable semantics bolted on as an afterthought, the foundation is typed, schema-validated data and declared actions — and the human-visible interface is generated from that structure, not the other way around.

### Core Principles

1. **Data and actions first, pixels second.** Every meaningful resource has a typed, schema-validated machine representation. The human view is generated from it (or co-generated with it), not the other way around.
2. **Explicit capabilities, not DOM scraping.** Agents do not click buttons or parse HTML. They invoke named, typed actions that the resource has declared.
3. **Stable addressing and state.** Resources have durable URIs. State transitions are explicit and observable. No "the real content is only in the JavaScript heap after three clicks."
4. **Least privilege by default for both humans and agents.** Permissions are capabilities granted to specific agents or sessions, not ambient "whatever a logged-in browser can do."
5. **Human experience is not a second-class citizen.** The system must still produce excellent, accessible, visually rich interfaces. Agents should not force a lowest-common-denominator UI.

### Architecture

**Primary representation.** A resource returns (or is addressable as) a structured document containing:

- Typed content (using something like an evolved JSON-LD + JSON Schema, or a purpose-built resource description language)
- A catalog of available actions with input/output schemas, preconditions, and effects
- Links to related resources
- Provenance and freshness metadata
- Optional human-oriented rendering hints (preferred component, layout priority, media, etc.)

This is closer to a combination of today's schema.org + OpenAPI + A2UI-style component catalogs than to HTML.

**Human rendering layer.** Clients (browsers, apps, voice interfaces, AR) receive the structured payload and render it using a trusted component catalog registered by the application or platform. The agent or server emits *intent* and data; the client owns the actual widgets, styling, and security boundaries. Different clients can render the same resource differently (phone, desktop, screen reader, agent summary) without the resource author writing separate UIs.

**Agent interaction layer.** Agents have a first-class protocol (evolved from MCP-like tool calling or a native web equivalent) that lets them:

- Discover the action catalog for a resource or site
- Invoke actions with typed arguments
- Receive structured results (not "here is some HTML, figure it out")
- Maintain session or long-lived state with explicit scopes
- Request human confirmation for high-impact actions

Navigation becomes "follow this typed link" or "invoke this query action," not "simulate mouse movements until the DOM looks right."

**Identity and authorization.** Agents have identities (or are delegated subsets of a human's identity). Authorization is capability-based: a resource grants a specific agent the right to call particular actions for a period of time, with an audit log. This replaces the current mess of cookies, localStorage, and bot-detection theater.

### What Changes for Humans

- Pages still look and feel like modern websites or apps. The rendering layer can be extremely rich.
- Progressive enhancement is the default: even a minimal client can show the data and available actions.
- Users can inspect or export the structured form of any page ("show me the data and actions behind this view").
- Agents acting on a user's behalf can surface what they are about to do and why, because the actions are explicit.
- Semantic structure helps accessibility, but accessible interaction still requires deliberate work on focus order, announcements, and keyboard flows — structure alone does not give you that for free.

### What Changes for Agents

- No more brittle scraping, CSS selector breakage, or SPA hydration races.
- Actions are discoverable and typed, so agents can plan reliably.
- Results are structured, so chaining (agent A does something, agent B consumes the result) is straightforward.
- Anti-bot measures largely disappear for legitimate agents that present proper credentials or capabilities. Rate limits and abuse prevention still exist, but they are applied to agent identities rather than to "looks like a browser."

### Security Model

- No arbitrary client-side code execution by default. Logic lives in declared actions (server-side or in tightly sandboxed, capability-limited modules).
- The component catalog is the security boundary for UI: an agent cannot invent a new widget that exfiltrates data; it can only use what the client already trusts. The catalog does not have to be closed — it can be open and signed, which preserves room for creative, unanticipated uses without giving up the security boundary.
- High-impact actions require explicit user consent or pre-authorized policies.
- Provenance is attached to content so agents and humans can see where data came from.

This is stricter than today's web in some ways (less "any script can do anything") and more flexible in others (agents can be granted precise powers).

### Practical Path

You would not throw away HTTP or browsers. You would:

- Make the structured resource description the canonical form and generate HTML/CSS/JS (or a Wasm + component payload) from it.
- Standardize an action catalog format and a discovery mechanism (a well-known path or link relation).
- Evolve browser developer tools and agent runtimes to consume the structured form preferentially.
- Treat existing HTML sites as legacy views that can be gradually annotated or wrapped with structured descriptions.
- Encourage platforms and major sites to expose action catalogs first for the most valuable interactions (search, booking, purchase, form fill, data export).

The structured form only becomes canonical when the tooling and incentives make it cheaper than raw markup. That is the adoption problem, and it is the single biggest thing that decides whether this happens. The realistic path is a decade of legacy HTML wrapped with structured annotations, not a clean break.

### What This Optimizes For

It optimizes for **reliable composition**. Humans get good interfaces because rendering is separated from data. Agents get reliable interfaces because they never have to guess. Code-writing agents become more effective because they are generating or modifying structured descriptions and action definitions rather than fragile visual markup and event handlers. The same artifact serves both audiences instead of forcing one to approximate the other.

### Honest Assessment

The architecture is sound and the security model is directionally right. Two things could sink it, and they are not equal in weight:

1. **Adoption economics.** Network effects are why the messy web won — HTML and JavaScript are free, universal, and every developer already knows them. This is the load-bearing risk.
2. **Agent identity.** Decentralized capability-based identity across the open web is a genuinely unsolved problem. OAuth is a patchwork mess today, and a global agent-identity layer with audit trails and scoped delegation does not exist. If that layer fails, you get either ambient trust again or a permission hell that kills usability. This is a real dependency, not a solved feature.

The expressiveness tradeoff — safety versus the web's open-ended creativity — is real but softer than it first appears, because a signed, open component catalog can preserve unexpected uses without surrendering the security boundary. Latency from splitting data and rendering is an engineering problem with known solutions (co-location, streaming), not a structural flaw.

This is a semi-hard thesis. It will be molded as this project is built out — what holds up, what conflicts — but it is the direction to build from.

---

## Repository Structure: Three Layers

This project is not one thing. It is three layers that only work together:

### 1. Language (`/language`)

The resource description format. Typed content, action schemas, links, provenance. This is the data layer — the canonical representation everything else hangs off. **If this format is not good enough to be canonical, nothing else matters.**

→ See `language/SPEC.md` for the build spec.

### 2. Library (`/library`)

The rendering and agent runtimes. Trusted component catalogs on the client side, MCP-style tool protocols on the agent side. These are what developers actually import and call. The library is what makes the language usable without everyone reinventing parsing and invocation.

→ See `library/SPEC.md` for the build spec.

### 3. Protocol (`/protocol`)

The discovery and interaction rules. How an agent finds a resource's action catalog, how it invokes something, how permissions and audit trails flow. This is the part that has to be standardized across the whole web or none of it compounds.

→ See `protocol/SPEC.md` for the build spec.

### Why All Three

A language without a protocol is just a file format nobody agrees on. A protocol without a language has nothing to carry. A library without either is just another framework that dies when the hype moves on. The web only ever changed when all three arrived together — HTML, HTTP, and browsers showed up as one package, not as separate ideas.

## Getting Started for Agent Builders

Each folder contains a `SPEC.md` written as build instructions for a coding agent (Cursor Cloud, Claude Code, or equivalent). The intended workflow:

1. An agent reads one `SPEC.md`.
2. It implements the first milestone described in that spec.
3. It opens a pull request with the implementation, tests, and a short note on what it built and what it deliberately deferred.
4. Human review merges or redirects.

Start with `/language` — the format is the foundation. The library and protocol specs assume the language spec's output exists.

## Status

- [x] Language spec → first implementation PR
- [ ] Library spec → first implementation PR
- [ ] Protocol spec → first implementation PR
- [ ] Cross-layer integration test (resource → render → agent invoke → structured result)
- [ ] Comparison against existing WebKit project: what holds up, what conflicts

## License

MIT. See `LICENSE`. Contributions welcome in the form of spec feedback and implementation PRs.
