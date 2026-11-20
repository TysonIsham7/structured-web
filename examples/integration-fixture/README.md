# Integration fixture

Synthetic fixture for a generic resource. The title, note, and image URL are invented. URLs point at `example.com`. Nothing here is a real site, account, address, phone, email, or business.

The document uses the core `article` type so it stays inside the registered vocabulary. The action is not tied to that type: `update_resource` is a high-risk action with the preconditions `user.is_authenticated` and `resource.is_published` and the effect `resource.updated`. `provenance.fetched_at` records when this snapshot was taken. `content_hash` is a fixture label, not a digest of the file.

`resource.invalid.json` is the same document with `actions[0].risk` set to `urgent`, which is not in the risk enum.

## What the integration test proves

`test_integration.py` starts the reference server on an ephemeral loopback port with this fixture and runs one flow:

1. The reference client reads `/.well-known/structured-web` and finds this resource.
2. The same URL is fetched twice: once with the vendor resource media type (what the reference client sends) and once with `Accept: application/json`. Both return the fixture bytes.
3. The language validator accepts `resource.json`. The broken file fails validation, and fetching it returns the protocol error `schema_invalid`.
4. The library renders the resource for `screen` (HTML) and `headless` (JSON).
5. The reference client invokes `update_resource` through the library agent runtime. A stub `perform` handler stands in for the site's own backend. One call is refused because `resource.is_published` is false, before the handler or the high-risk consent check runs. One call is refused because consent returns false, after the preconditions pass and before the handler runs. One call succeeds after the preconditions pass and consent is granted, and the handler returns a result id.

Invocation stays inside the agent runtime. This demo does not add an HTTP action endpoint.

## Run it locally

From the repository root, with Python 3.12:

```bash
pip install -r protocol/requirements.txt
python language/validator/validate.py examples/integration-fixture/resource.json
python language/validator/validate.py examples/integration-fixture/resource.invalid.json
python -m pytest examples/integration-fixture/test_integration.py -v
```

The first validator command prints `VALID`. The second prints `INVALID`. The pytest command is the same one CI runs.

## Out of scope

Catalog signatures, `content_hash` checks, voice and other media renderers, and an HTTP form-submission path are not part of this fixture. The `content_hash` value is a fixture label, not a digest of the file, and this test does not check it.
