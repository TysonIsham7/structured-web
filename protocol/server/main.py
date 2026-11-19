#!/usr/bin/env python3
"""Run the reference server on the IPv4 loopback address.

    python protocol/server/main.py

Port comes from STRUCTURED_WEB_PORT (default 8765). STRUCTURED_WEB_HOST
is accepted only when it is empty or a loopback name; any other value
exits without binding.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_path() -> None:
    root = Path(__file__).resolve().parents[2]
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)


_prepare_path()

from protocol.server.app import (  # noqa: E402
    default_config,
    resolve_bind_host,
    resolve_port,
    serve_forever,
)


def main() -> int:
    host = resolve_bind_host(os.environ.get("STRUCTURED_WEB_HOST"))
    if host is None:
        print("reference server binds to the loopback address only", file=sys.stderr)
        return 2
    try:
        port = resolve_port(os.environ.get("STRUCTURED_WEB_PORT"))
    except ValueError:
        print("invalid port", file=sys.stderr)
        return 2
    try:
        config = default_config(host, port)
    except (OSError, RuntimeError) as exc:
        print(f"could not load resources: {exc}", file=sys.stderr)
        return 1
    serve_forever(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
