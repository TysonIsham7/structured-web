"""Agent session over a resource document's declared actions.

`invoke` validates arguments, evaluates preconditions against the host
snapshot, then applies risk gating. Only after those checks does it
call the host `perform` handler. This runtime does not open a network
connection. The handler is how a host returns the structured output
the action's `output_schema` describes.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from library._bootstrap import validator_module
from library.agent.preconditions import (
    PreconditionFailed,
    PreconditionUnknown,
    evaluate_all,
)
from library.documents import require_document
from library.errors import LibraryError

ActionHandler = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], Any]
ConsentCallback = Callable[[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]], bool]

_KNOWN_RISKS = frozenset({"low", "medium", "high", "critical"})


@dataclass(frozen=True)
class SessionOptions:
    """Host inputs for one session.

    `state` is the precondition snapshot. `consent` is called only for
    `high` and `critical` actions and must return True to allow them.
    `preauthorized` is the critical-action allow-list. An entry of `*`
    allows every action name on this resource. `perform` produces the
    structured output after every gate has passed.
    """

    state: Mapping[str, Any] | None = None
    consent: ConsentCallback | None = None
    preauthorized: list[str] | tuple[str, ...] | set[str] | frozenset[str] | None = None
    perform: ActionHandler | None = None


@dataclass(frozen=True)
class Result:
    """The outcome of `invoke`.

    `code` is `ok` or a stable error name. `details` holds validator
    lines or the predicate that stopped the call. Messages do not
    include the state snapshot.
    """

    ok: bool
    code: str
    output: Any = None
    message: str = ""
    details: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditEvent:
    """One invoke attempt that resolved to a declared action.

    Arguments are omitted. They may carry data the host does not want
    in a log line.
    """

    action: str
    risk: str
    outcome: str
    resource_id: str


@dataclass
class AgentSession:
    """A session bound to one validated document and one snapshot."""

    _document: dict
    _state: dict
    _consent: ConsentCallback | None
    _preauthorized: frozenset[str]
    _perform: ActionHandler | None
    _audit: list[AuditEvent] = field(default_factory=list)
    _closed: bool = False

    def discover(self) -> list[dict[str, Any]]:
        """Return a copy of the declared actions and their schemas."""
        self._require_open()
        catalog: list[dict[str, Any]] = []
        for action in self._document["actions"]:
            catalog.append(
                {
                    "name": action["name"],
                    "description": action["description"],
                    "input_schema": copy.deepcopy(action["input_schema"]),
                    "output_schema": copy.deepcopy(action["output_schema"]),
                    "preconditions": list(action.get("preconditions") or []),
                    "effects": list(action.get("effects") or []),
                    "risk": action["risk"],
                    "idempotent": action["idempotent"],
                }
            )
        return catalog

    def invoke(self, name: str, args: object) -> Result:
        """Validate, gate, and perform one declared action."""
        if self._closed:
            return Result(False, "session_closed", message="session is closed")
        action = self._find(name)
        if action is None:
            shown = name if isinstance(name, str) else "<not-a-string>"
            return Result(
                False,
                "unknown_action",
                message=f"no action named {shown!r}",
            )
        try:
            arguments = _json_copy(args)
        except (TypeError, ValueError):
            result = Result(
                False,
                "invalid_input",
                message="arguments must be JSON data",
            )
            self._record(action, result)
            return result
        input_errors = _schema_errors(
            action.get("input_schema"),
            arguments,
            "$.arguments",
        )
        if input_errors:
            result = Result(
                False,
                "invalid_input",
                message=input_errors[0],
                details=tuple(input_errors),
            )
            self._record(action, result)
            return result
        try:
            evaluate_all(action.get("preconditions") or [], self._state)
        except PreconditionUnknown as exc:
            result = Result(
                False,
                "precondition_unknown",
                message=f"precondition cannot be evaluated: {exc.predicate}",
                details=(exc.predicate,),
            )
            self._record(action, result)
            return result
        except PreconditionFailed as exc:
            result = Result(
                False,
                "precondition_failed",
                message=f"precondition failed: {exc.predicate}",
                details=(exc.predicate,),
            )
            self._record(action, result)
            return result
        gated = self._risk_gate(action, arguments)
        if gated is not None:
            self._record(action, gated)
            return gated
        if self._perform is None:
            result = Result(
                False,
                "handler_missing",
                message="session has no perform handler",
            )
            self._record(action, result)
            return result
        context = self._context(action)
        try:
            produced = self._perform(
                copy.deepcopy(action),
                copy.deepcopy(arguments),
                context,
            )
        except Exception as exc:
            result = Result(
                False,
                "handler_failed",
                message=f"{type(exc).__name__}: {exc}",
            )
            self._record(action, result)
            return result
        try:
            output = _json_copy(produced)
        except (TypeError, ValueError):
            result = Result(
                False,
                "output_invalid",
                message="handler output must be JSON data",
            )
            self._record(action, result)
            return result
        output_errors = _schema_errors(
            action.get("output_schema"),
            output,
            "$.output",
        )
        if output_errors:
            result = Result(
                False,
                "output_invalid",
                message=output_errors[0],
                details=tuple(output_errors),
            )
            self._record(action, result)
            return result
        result = Result(True, "ok", output=output)
        self._record(action, result)
        return result

    def close(self) -> None:
        """Drop the snapshot and the host callbacks.

        The audit trail remains readable.
        """
        self._closed = True
        self._consent = None
        self._perform = None
        self._state = {}

    @property
    def audit(self) -> tuple[AuditEvent, ...]:
        return tuple(self._audit)

    def _require_open(self) -> None:
        if self._closed:
            raise LibraryError("session_closed", "session is closed")

    def _find(self, name: object) -> dict | None:
        if not isinstance(name, str):
            return None
        for action in self._document["actions"]:
            if action.get("name") == name:
                return action
        return None

    def _context(self, action: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "resource_id": self._document.get("id"),
            "resource_type": self._document.get("type"),
            "risk": action.get("risk"),
            "state": copy.deepcopy(self._state),
        }

    def _risk_gate(
        self,
        action: Mapping[str, Any],
        arguments: Mapping[str, Any],
    ) -> Result | None:
        risk = action.get("risk")
        if risk not in _KNOWN_RISKS:
            return Result(
                False,
                "risk_unknown",
                message="action risk is not one of low, medium, high, critical",
            )
        if risk == "critical" and not self._policy_matches(str(action.get("name"))):
            return Result(
                False,
                "policy_required",
                message="critical action is not pre-authorized",
            )
        if risk in {"high", "critical"}:
            if self._consent is None:
                return Result(
                    False,
                    "consent_required",
                    message="high and critical actions require a consent callback",
                )
            try:
                allowed = self._consent(
                    copy.deepcopy(action),
                    copy.deepcopy(arguments),
                    self._context(action),
                )
            except Exception:
                return Result(
                    False,
                    "consent_denied",
                    message="consent callback failed",
                )
            if allowed is not True:
                return Result(
                    False,
                    "consent_denied",
                    message="consent was not granted",
                )
        return None

    def _policy_matches(self, name: str) -> bool:
        return "*" in self._preauthorized or name in self._preauthorized

    def _record(self, action: Mapping[str, Any], result: Result) -> None:
        self._audit.append(
            AuditEvent(
                action=str(action.get("name")),
                risk=str(action.get("risk")),
                outcome=result.code,
                resource_id=str(self._document.get("id")),
            )
        )


def create_session(
    document: object,
    options: SessionOptions | None = None,
) -> AgentSession:
    """Validate `document` and bind a session to a snapshot."""
    checked = require_document(document)
    options = options or SessionOptions()
    return AgentSession(
        _document=copy.deepcopy(checked),
        _state=_copy_state(options.state),
        _consent=options.consent,
        _preauthorized=_copy_policy(options.preauthorized),
        _perform=options.perform,
    )


def _copy_state(state: Mapping[str, Any] | None) -> dict:
    if state is None:
        return {}
    if not isinstance(state, dict):
        raise LibraryError("state_invalid", "state snapshot must be a JSON object")
    try:
        cloned = copy.deepcopy(state)
    except Exception as exc:
        raise LibraryError(
            "state_invalid",
            "state snapshot could not be copied",
        ) from exc
    return cloned


def _copy_policy(value: object) -> frozenset[str]:
    if value is None:
        return frozenset()
    if not isinstance(value, (set, list, tuple, frozenset)):
        raise LibraryError(
            "policy_invalid",
            "preauthorized policy must be a set of action names",
        )
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or item == "":
            raise LibraryError(
                "policy_invalid",
                "preauthorized policy entries must be action names",
            )
        names.append(item)
    return frozenset(names)


def _json_copy(value: object) -> Any:
    return json.loads(json.dumps(value, allow_nan=False))


def _schema_errors(schema: object, instance: object, prefix: str) -> list[str]:
    module = validator_module()
    if not isinstance(schema, dict):
        return [f"{prefix}: schema is not an object"]
    try:
        module.Draft202012Validator.check_schema(schema)
    except module.SchemaError as exc:
        detail = " ".join(str(getattr(exc, "message", exc)).split())
        return [f"{prefix}: not a valid JSON Schema ({detail})"]
    validator = module.Draft202012Validator(
        schema,
        format_checker=module.FORMAT_CHECKER,
    )
    return [
        module.format_error(error, prefix=prefix)
        for error in validator.iter_errors(instance)
    ]
