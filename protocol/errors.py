"""Typed protocol errors.

The body shape is the one in the protocol spec. `details` carries a
path and the language validator's lines when the failure is a document.
"""

from __future__ import annotations

from typing import Any

STATUS_FOR_CODE = {
    "not_found": 404,
    "schema_invalid": 422,
    "unauthorized": 401,
    "forbidden": 403,
    "precondition_failed": 412,
    "rate_limited": 429,
    "unsupported_version": 406,
    "not_acceptable": 406,
    "method_not_allowed": 405,
    "internal_error": 500,
}

REASON_FOR_STATUS = {
    200: "OK",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    414: "URI Too Long",
    422: "Unprocessable Content",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
}


class ProtocolError(Exception):
    """A protocol failure a caller can branch on via `code`."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = STATUS_FOR_CODE.get(code, 0) if status is None else status
        self.details = details or {}


def error_document(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the JSON object returned for a protocol error."""
    error: dict[str, Any] = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def details_from_validator(lines: list[str]) -> dict[str, Any]:
    """Turn language-validator lines into the protocol `details` object."""
    path = "$"
    if lines:
        head, separator, _rest = lines[0].partition(": ")
        if separator and head.startswith("$"):
            path = head
    return {"path": path, "errors": list(lines)}
