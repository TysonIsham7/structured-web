"""Media types the reference server and client agree on.

See protocol/DECISIONS.md for why these names were chosen. The v0.1
document field `version` ("0.1.0") and the media-type parameter
`version` ("0.1") are different version spaces.
"""

from __future__ import annotations

RESOURCE_MEDIA_TYPE = "application/vnd.structured-web.resource+json"
RESOURCE_VERSION = "0.1"
MANIFEST_MEDIA_TYPE = "application/vnd.structured-web.manifest+json"
JSON_MEDIA_TYPE = "application/json"
HTML_MEDIA_TYPE = "text/html"

RESOURCE_CONTENT_TYPE = (
    f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}; charset=utf-8"
)
MANIFEST_CONTENT_TYPE = f"{MANIFEST_MEDIA_TYPE}; charset=utf-8"
JSON_CONTENT_TYPE = f"{JSON_MEDIA_TYPE}; charset=utf-8"
HTML_CONTENT_TYPE = f"{HTML_MEDIA_TYPE}; charset=utf-8"

# Clients that understand the vendor type prefer it. application/json
# stays available so the v0.1 Accept contract still works.
RESOURCE_ACCEPT = f"{RESOURCE_MEDIA_TYPE}; version={RESOURCE_VERSION}, {JSON_MEDIA_TYPE}; q=0.8"
MANIFEST_ACCEPT = f"{MANIFEST_MEDIA_TYPE}, {JSON_MEDIA_TYPE}; q=0.8"

WELL_KNOWN_PATH = "/.well-known/structured-web"
