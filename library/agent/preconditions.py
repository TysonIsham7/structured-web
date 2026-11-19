"""Evaluate precondition strings against a host state snapshot.

The runtime does not fetch state and does not infer a boolean from
neighboring fields. A predicate that the snapshot cannot answer raises
`PreconditionUnknown`.

Rules, for a snapshot that is a JSON object:

- `noun.verb` is true only when the value at that path is a boolean.
- `noun.verb:param` is true only when the value is a string equal to
  `param`, or a list of strings that contains `param`.
- A missing path, a malformed predicate, or any other value shape is
  unknown.
- Boolean false, a string mismatch, or a list that does not contain
  `param` is a failed precondition, not an unknown one.

Host-specific predicates use the same rules. The host registers one by
putting its value in the snapshot. This module does not consult a
separate predicate registry, because the milestone does not define one.
Error text names the predicate and does not include the snapshot value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_PARAM = re.compile(r"^[A-Za-z0-9._-]+$")


class PreconditionUnknown(Exception):
    """The snapshot cannot answer this predicate."""

    def __init__(self, predicate: str) -> None:
        self.predicate = predicate
        super().__init__(predicate)


class PreconditionFailed(Exception):
    """The snapshot answered this predicate with false."""

    def __init__(self, predicate: str) -> None:
        self.predicate = predicate
        super().__init__(predicate)


def evaluate_all(predicates: object, state: Mapping[str, object]) -> None:
    """Raise when any predicate is unknown or false.

    An empty list passes. Predicates are checked in order.
    """
    if predicates is None:
        return
    if not isinstance(predicates, list):
        raise PreconditionUnknown("<preconditions>")
    for predicate in predicates:
        if not isinstance(predicate, str):
            raise PreconditionUnknown("<not-a-string>")
        if evaluate(predicate, state) is not True:
            raise PreconditionFailed(predicate)


def evaluate(predicate: str, state: Mapping[str, object]) -> bool:
    """Return the boolean value of one predicate, or raise if unknown."""
    if not isinstance(state, Mapping):
        raise PreconditionUnknown(predicate)
    name, separator, param = predicate.partition(":")
    if not _NAME.fullmatch(name):
        raise PreconditionUnknown(predicate)
    if separator and not _PARAM.fullmatch(param):
        raise PreconditionUnknown(predicate)
    current: object = state
    for part in name.split("."):
        if not isinstance(current, Mapping) or part not in current:
            raise PreconditionUnknown(predicate)
        current = current[part]
    if not separator:
        if isinstance(current, bool):
            return current
        raise PreconditionUnknown(predicate)
    if isinstance(current, str):
        return current == param
    if isinstance(current, list) and all(isinstance(item, str) for item in current):
        return param in current
    raise PreconditionUnknown(predicate)
