# Protocol decisions

Decisions made while implementing the v0.1 protocol milestone. The spec files are unchanged. Where this implementation fills a gap the spec left open, the reason is here.

## Media type

**Decision:** the structured representation's media type is

```
application/vnd.structured-web.resource+json; version=0.1
```

`Accept: application/json` remains an equivalent request. It returns the same document bytes with `Content-Type: application/json`. Nothing removes the v0.1 `application/json` behavior.

**Why this name:** a dedicated type is the only way a client can tell a resource document from every other JSON body on the web. The `vnd.` tree is the honest place for a format that is not registered. The `+json` suffix lets existing JSON parsers run without a new decoder. `resource` names the payload and leaves room for a sibling manifest type. The version sits in a parameter so a later revision does not mint a new type name.

The parameter value is `0.1`, taken from the media-type proposal. The document field `version` stays the semver string `0.1.0`. Those are different version spaces: one selects a representation, the other is data inside that representation.

### Open questions from the proposal

1. **Version parameter.** Optional on input. A vendor type with no version parameter means `0.1`, the only version this server implements. An explicit version other than `0.1` is not served. If that range is a strictly higher preference than any representation the server can produce, the response is `406` with `unsupported_version`. An equal-preference type the server can produce (for example `application/json` at the same `q`) is still served.
2. **Manifests and action results.** Manifests get their own type, `application/vnd.structured-web.manifest+json`. A client can tell a site manifest from a resource document. `Accept: application/json` still returns the manifest, with `Content-Type: application/json`. Action results do not get a media type in this milestone. Invocation is a call on the library runtime after the document has been fetched, not an HTTP representation.
3. **`vnd.` versus the standards tree.** Stay on `vnd.` This milestone does not register a type with IANA and does not pretend the format is a standards-tree type.
4. **`profile` parameter.** Not implemented. The document `type` field and the core vocabulary already say which content schema applies. A profile parameter would be a second way to say that.

### Negotiation defaults

| Accept | Resource URL | Well-known manifest |
| --- | --- | --- |
| absent | HTML page from the library renderer | manifest JSON, vendor manifest type |
| `*/*` | HTML page | manifest JSON, vendor manifest type |
| `text/html` | HTML page | manifest JSON (the endpoint has no HTML form) |
| `application/json` | resource document, `application/json` | manifest, `application/json` |
| vendor resource type, no version or `version=0.1` | resource document, vendor type | n/a |
| vendor resource type, any other version, strictly preferred | `406` `unsupported_version` | n/a |
| vendor manifest type | n/a | manifest, vendor manifest type |
| anything else with no match | `406` `not_acceptable` | manifest JSON |

`application/*` on a resource URL selects the vendor resource type. The client asked for an application payload and did not name `text/html`.

The well-known path always returns the manifest. Content negotiation on that path only chooses which JSON media type to label it with. The spec says that endpoint returns a JSON document, and the HTML default is defined for a resource's own URL.

## Language

Python, same interpreter as the language validator and the library. The server renders HTML by calling the library renderer. The client validates with the language validator and invokes through the library agent runtime. A second language would have copied both.

## Identity extension points

Global agent identity and scoped delegation are not implemented.

- Site manifests include `agent_id`. The reference server sets it to `null`.
- Client session options include `credentials`. When set, the client sends `Authorization: Bearer`. When unset, the fetch is anonymous. The field is not required, and it is not an agent identifier.
- The server consumes bearer tokens on resources marked authenticated. It defines no new authentication scheme. The three shipped examples are public. Tests cover a protected resource.
- Library session options are unchanged. Credentials are a fetch concern. The runtime never sees the token.

## What the manifest lists

Each entry's `uri` is the page URL that negotiates HTML and the resource document. The server does not publish a second `*.sw.json` URL. The spec's discovery section says the same URL serves humans and agents, and that content negotiation replaces URL rewriting.

`site` is the origin the server is bound to. The reference server binds to the IPv4 loopback address and refuses any other host.

## Errors

Stable codes the server returns: `not_found`, `schema_invalid`, `unauthorized`, `forbidden`, `rate_limited`, `unsupported_version`.

`precondition_failed` is returned by the library runtime when the client invokes an action whose snapshot does not satisfy a precondition. The server has no action-invocation route, so it does not emit that code itself.

Two codes are not in the v0.1 list. They exist so a failure is still a JSON body:

- `method_not_allowed` for anything other than GET or HEAD (`405`, `Allow: GET, HEAD`).
- `not_acceptable` when Accept matches none of the representations (`406`).
- `internal_error` for an unexpected server failure (`500`). The body stays JSON.

`details` for `schema_invalid` is `{ "path", "errors" }`. `path` is the first validator line's JSON path. `errors` is the validator's full line list. The spec's sketch uses `expected`; the validator reports a path and a message, and this server does not invent an expected keyword the validator did not emit.

Rate-limit signals are `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` (window end, Unix seconds) on every response, including errors. The identity is the SHA-256 of the bearer token when one is present, otherwise the client address. The token itself is not logged.

## Deliberately not built

Catalog signature verification, provenance `content_hash` checks, voice and other non-screen renderers, and an HTTP form-submission or action-invocation route. Those are later milestones. Screen HTML comes from the existing library renderer. Invocation runs in the library runtime on the client side.
