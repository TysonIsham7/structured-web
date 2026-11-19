"""Import the language validator from its own source file.

The library does not copy the validator. Schema, vocabulary, and format
checks stay in `language/validator/validate.py`.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
_VALIDATOR: ModuleType | None = None


def repo_root() -> Path:
    return REPO_ROOT


def validator_module() -> ModuleType:
    """Return the language validator module, loaded from this repo."""
    global _VALIDATOR
    if _VALIDATOR is not None:
        return _VALIDATOR
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module("language.validator.validate")
    expected = REPO_ROOT / "language" / "validator" / "validate.py"
    loaded = Path(getattr(module, "__file__", "") or "")
    if loaded.resolve() != expected.resolve():
        raise ImportError("language validator did not resolve to validate.py")
    _VALIDATOR = module
    return module
