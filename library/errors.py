"""Typed failures shared by the rendering and agent runtimes."""

from __future__ import annotations


class LibraryError(Exception):
    """A failure the caller can branch on via `code`.

    `details` holds stable lines (validator paths, for example). The
    message is a short summary and does not include host state.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
