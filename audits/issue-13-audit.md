# Issue 13 audit

Audit of `main` at `38e5639a88fb0d484dda7131f74c77bde2b63c72` against issue 13: the core resource document stays a general delivery contract, unknown fields pass through, and domain shapes stay out of the core.

This branch fixes the two pass-through bugs below. It does not edit `language/SPEC.md`, `library/SPEC.md`, `protocol/SPEC.md`, `protocol/DECISIONS.md`, `protocol/MEDIA_TYPE_PROPOSAL.md`, `language/schema/resource.schema.json`, or `vocabularies/core.json`. Issues 4, 5, 6, 7, 9, 10, and 11 are untouched.

## Counts

| Category | Found | Still open after this branch |
| --- | --- | --- |
| Pass-through | 2 | 0 (both fixed here) |
| Required fields | 0 | 0 |
| Domain vocabulary | 2 | 2 (spec changes; not edited) |

## Files checked

Language: `language/SPEC.md`, `language/schema/resource.schema.json`, `language/validator/validate.py`, `language/validator/tests/test_validate.py`, `language/examples/article.json`, `dataset.json`, `error.json`, `form.json`, `product.json`, `service.json`.

Vocabulary: `vocabularies/core.json`.

Library: `library/SPEC.md`, `library/documents.py`, `library/catalog/default.json`, `library/render/runtime.py`, `library/render/components.py`, `library/render/markup.py`, `library/render/catalog.py`, `library/agent/runtime.py`, `library/agent/preconditions.py`, and the library tests.

Protocol: `protocol/SPEC.md`, `protocol/DECISIONS.md`, `protocol/MEDIA_TYPE_PROPOSAL.md`, `protocol/server/app.py`, `protocol/server/resources.py`, `protocol/server/negotiate.py`, `protocol/client/client.py`, and the protocol tests.

Fixture: `examples/st-george-condo/`. Domain-specific examples belong outside the core spec, vocabulary and reference fixtures. PR #19 replaces this fixture with a domain-neutral one (`examples/integration-fixture/`). Issue #17 removes retail terms from the core word list. Also `README.md`, `CONTRIBUTING.md`, and `.github/workflows/ci.yml`.

Searched the core schema, core vocabulary, and the three layer specs for lodging, medical, legal, retail, cart, inventory, patient, diagnosis, and bedroom wording. Lodging, medical, legal, patient, and diagnosis do not appear there. Bedroom and house-rule wording appears only under `examples/st-george-condo/`.

## 1. Unknown fields

### What already held

The resource schema sets `additionalProperties` to true on the document, action, link, provenance, render, and media objects. Each of the six content schemas does the same. No schema in `resource.schema.json` or `vocabularies/core.json` sets `additionalProperties` to false. Nested objects that omit the keyword (price, image, form field, column, rate limit) use the JSON Schema default, which accepts extra keys.

`validate_document` only collects errors. It does not rewrite the document. The reference server answers a JSON or vendor-type GET with the stored body bytes. The client returns that parsed object after validation. `create_session` deep-copies the validated document. The perform handler receives a deep copy of the full action, so an unknown action field reaches the host.

Screen HTML is a human projection. Issue 13 records that the product card ignores extra content fields, and that those fields stay on the document for agents. This branch does not change that. `protocol/tests/test_passthrough.py` asserts a sentinel content field is absent from the product-card page and present on the headless object.

The headless JSON text is serialized with object keys sorted. Parsed values still match. The headless `value["content"]` object is the document's content object, so insertion order is intact there. Sorting the text does not drop keys or values. That is not counted as a violation.

Headless action summaries still omit `input_schema` and `output_schema`. Those are known fields. `discover()` returns both schemas, including any extra schema keywords, and the fetched document still has them.

### Violations found and fixed

1. **Headless render dropped unknown fields.** `_headless_payload` rebuilt a fixed key set. Extra content fields survived, because `content` was copied whole, but a top-level extension, an extension inside `provenance` or `render`, and an extension on an action were omitted. The payload now copies the document fields through. Action entries still use the short catalog (name, description, risk, idempotency, preconditions, effects) and then copy every other action field except the two embedded schemas. Renderer keys `medium`, `component`, and `fallback` are written after that copy.

2. **Action discovery dropped unknown action fields.** `discover()` built a fixed key set. The session document and the perform handler already kept the extra field; the catalog view did not. `discover()` now deep-copies any action field it does not already return, so editing the catalog does not edit the session document.

### Probe

A product document with extra keys at the top level, inside content (including inside `price` and an image), on an action, a link, provenance, and render was validated, served, fetched, rendered headless, and invoked. Validator errors were empty and the in-memory document was unchanged. Both the generic JSON response and the vendor-type response were byte-identical to the stored body. The client document compared equal, including content key order `extension_marker`, `name`, `price`, `extension_list`, `images`. Headless `value["content"]` was that same object. The sorted headless text still compared equal on values; its content key order was alphabetical. After the fix, the headless value contained the top-level extension, the action extension, and the provenance extension. `discover()` contained `extension_flag`. Invoke succeeded and the perform handler saw both the action extension and an extra argument. The screen page did not contain `extension_marker`. It also did not contain the content `name` string: the page heading is the document title, and the product card prints the price rather than repeating `content.name`. That string was still on the fetched document and on the headless content.

Committed coverage:

- `language/validator/tests/test_validate.py::test_unknown_content_fields_are_kept`
- `library/render/tests/test_render.py::test_headless_keeps_unknown_fields`
- `library/agent/tests/test_agent.py::test_discover_keeps_unknown_action_fields`
- `protocol/tests/test_passthrough.py::test_unknown_fields_round_trip`

Those four passed. The full language, library, and protocol suites passed (108), the condo fixture passed (1), and `python library/examples/usage.py` completed.

## 2. Required fields

Envelope (`language/schema/resource.schema.json`):

| Object | Required | Judgment |
| --- | --- | --- |
| Document | `version`, `id`, `type`, `title`, `content`, `actions`, `links`, `provenance` | Universal delivery contract. `render` is optional. |
| Action | `name`, `description`, `input_schema`, `output_schema`, `risk`, `idempotent` | Universal action contract. Preconditions and effects are optional. |
| Link | `rel`, `href` | Universal link. `title` is optional. |
| Provenance | `source`, `fetched_at`, `content_hash` | Universal origin metadata. `signed_by` is optional. |
| Media item | `type`, `src` | Required only when a media object is present. A locator and a type are universal for that object. `alt` is optional here. |

Content (`vocabularies/core.json`). The type set is exactly `article`, `product`, `form`, `dataset`, `service`, `error`. There is no lodging, medical, or legal type.

| Type | Required | Judgment |
| --- | --- | --- |
| article | `body` | Universal for a piece of written content. Summary, author, time, and tags are optional. |
| product | `name`, `price` | `name` identifies the item. `price` is the charge on the general sellable-item type, which issue 13 says to keep. |
| product.price | `amount`, `currency` | Required only on a price object. An amount plus a three-letter currency code is the cross-domain shape of a charge, not one vertical and not one currency. |
| product.images[] | `src`, `alt` | Required only on an image object. A source and a text alternative are universal for an image. |
| form | `fields` | Universal for a form. |
| form.fields[] | `name`, `type` | Required only on a field object. A name and a type are universal for an input. |
| dataset | `columns`, `rows` | Universal for a table. |
| dataset.columns[] | `name`, `type` | Required only on a column object. |
| service | `endpoint` | Universal for a callable capability. Method, health check, and rate limit are optional. |
| error | `code`, `message` | Universal for an error. `details` is an open object. |

`product.price` is the one field that needs a written judgment. The type description says "sellable or referenceable". "Referenceable" describes a stable item you can point at; `id` and `name` do that. It does not mean a product may omit its charge. `sku` and `in_stock` were left optional, which already keeps warehouse details off the required set. Not counted as a violation.

No required field is specific to lodging, medicine, law, or another single vertical.

## 3. Domain vocabulary

The core schema does not define a domain type. The validator checks `type` against the six names in `vocabularies/core.json` and rejects any other name. That is type membership, not stripping of extra fields. A lodging document uses `product` (or another core type) and puts bedrooms, availability, and house rules in extra content fields. The condo fixture does that. Nothing in the schema, validator, catalog, or server imports that fixture. The protocol CI job runs it as a test. The core does not depend on it.

The agent runtime does not keep a predicate allow-list. `library/agent/preconditions.py` evaluates whatever string the document declares against the host snapshot. A host predicate such as `stay.dates_available` works when the snapshot answers it. Unknown predicates fail closed. The starter list in the vocabulary file is documentation, not an enum the validator enforces.

### Violations (open, spec-only)

1. **`vocabularies/core.json` predicates.** `examples` and `starter_set` include `cart.non_empty` and `inventory.available`. The same object says hosts may register domain-specific predicates alongside the starter set. Those two entries are retail predicates inside the set that is supposed to be the cross-domain baseline. The other starter entries (`user.is_authenticated`, `user.has_role:{role}`, `resource.is_published`, `session.not_expired`, `quota.remaining`) are account, publication, session, and quota checks. They are not one vertical.

2. **`language/SPEC.md` action example.** The only fully written action sample uses preconditions `user.is_authenticated` and `cart.non_empty`, and effects `order.created` and `inventory.decremented`. That puts the same retail vocabulary in the language spec. The purchase action name itself is the milestone's high-risk example, not a core type. The predicate strings are the problem.

Not counted, on purpose:

- `sku` and `in_stock` are optional product fields, not required, and not a separate vertical type. The product card prints them when present. A document may omit them.
- `language/examples/product.json` and `language/examples/dataset.json` use purchase, cart, inventory, and sku data. Domain-specific examples belong outside the core spec, vocabulary and reference fixtures. The core schema does not import them. Issue #17 removes retail terms from the core word list.
- `examples/st-george-condo/` is a domain-specific fixture. Domain-specific examples belong outside the core spec, vocabulary and reference fixtures. PR #19 replaces it with a domain-neutral fixture (`examples/integration-fixture/`).
- `README.md` compares the architecture to existing structured-data and API-description practice and names booking and purchase as interactions worth exposing. It does not define types or predicates.

### Proposed spec-change issue

Do not apply this in a pull request until it is filed and accepted. Suggested title and body:

**Title:** `[spec] Take retail predicates out of the core starter set`

**Body:**

**Layer:** language

**Section:** `vocabularies/core.json` predicate starter set; `language/SPEC.md` Action Schema sample

**Current text**

The core vocabulary starter set and its examples list include `cart.non_empty` and `inventory.available`, next to a sentence that says hosts register domain-specific predicates alongside that set. The language spec's action sample uses `cart.non_empty`, `order.created`, and `inventory.decremented`.

**Proposed text**

Keep the dotted predicate syntax. Keep these starter predicates: `user.is_authenticated`, `user.has_role:{role}`, `resource.is_published`, `session.not_expired`, `quota.remaining`. Remove `cart.non_empty` and `inventory.available` from both the examples list and the starter set.

In the language spec sample, keep a high-risk action so the milestone story still has one, and replace the retail predicate and effect strings with cross-domain ones (`user.is_authenticated`, `resource.is_published`, and an effect such as `resource.updated`).

Domain-specific examples belong outside the core spec, vocabulary and reference fixtures, so `language/examples/product.json` does not stay in that set as a purchase sample. Issue #17 removes retail terms from the core word list. The runtime already evaluates any predicate against the host snapshot and does not treat the starter set as an allow-list.

**Rationale**

Issue 13 keeps domain vocabulary in optional libraries. Shopping-cart and inventory predicates are retail vocabulary presented as part of the standard starter set. Removing them from the vocabulary file and from the spec sample does not reject existing documents, because those strings are not an enum.

**Breaking change?** No. No schema field, document version, or media type changes. Documents that still declare `cart.non_empty` stay valid.
