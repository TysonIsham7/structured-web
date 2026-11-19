# Cottonwood Bench Condo

Synthetic fixture for a fictional two-bedroom vacation rental in St. George, Utah. The names, rate, dates, photos, and house rules are invented. Photo URLs point at `example.com`. Nothing here is a real listing, host, address, phone, email, or business.

The document is Resource Document Format v0.1. Its type is `product`, because that is the core type with a name and a price. Bedrooms, bathrooms, amenities, availability, and house rules are extra content fields the vocabulary already allows. The nightly rate is `content.price` with `content.price_period` set to `night`.

`listing.invalid.json` is the same document with `actions[0].risk` set to `urgent`, which is not in the risk enum.

## What the integration test proves

`test_integration.py` starts the reference server on an ephemeral loopback port with this fixture and runs one flow:

1. The reference client reads `/.well-known/structured-web` and finds this listing.
2. The same URL is fetched twice: once with the vendor resource media type (what the reference client sends) and once with `Accept: application/json`. Both return the fixture bytes.
3. The language validator accepts `listing.json`. The broken file fails validation, and fetching it returns the protocol error `schema_invalid`.
4. The library renders the listing for `screen` (HTML) and `headless` (JSON).
5. The reference client invokes `request_to_book` through the library agent runtime. A stub `perform` handler stands in for the host. One call is refused because `stay.dates_available` is false, before the handler or the high-risk consent check runs. One call succeeds after that precondition passes and consent is granted, and the handler returns a request id.

Invocation stays inside the agent runtime. This demo does not add an HTTP action endpoint.

## Run it locally

From the repository root, with Python 3.12:

```bash
pip install -r protocol/requirements.txt
python language/validator/validate.py examples/st-george-condo/listing.json
python language/validator/validate.py examples/st-george-condo/listing.invalid.json
python -m pytest examples/st-george-condo/test_integration.py -v
```

The first validator command prints `VALID`. The second prints `INVALID`. The pytest command is the same one CI runs.

## Out of scope

Catalog signatures, `content_hash` checks, voice and other media renderers, and an HTTP form-submission path are not part of this fixture. The `content_hash` value is a fixture label, not a digest of the file, and this test does not check it.
