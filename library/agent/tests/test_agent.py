"""Acceptance tests for the agent runtime."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from library.agent import SessionOptions, create_session
from library.errors import LibraryError

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "language" / "examples"


def load_example(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


ACTION = "update_resource"
VALID_ARGS = {"note": "apply update"}
INVALID_ARGS = {"note": ""}


def action_output(action, args, context):
    return {"result_id": "result-100", "status": "updated"}


def ready_state() -> dict:
    return {
        "user": {"is_authenticated": True},
        "resource": {"is_published": True},
    }


def allow(action, args, context) -> bool:
    return True


def refuse_if_called(*_args):
    raise AssertionError("handler must not run")


def test_discover_returns_declared_actions() -> None:
    session = create_session(load_example("update.json"))
    catalog = session.discover()
    assert catalog[0]["name"] == ACTION
    assert catalog[0]["risk"] == "high"
    assert catalog[0]["input_schema"]["required"] == ["note"]
    assert catalog[0]["preconditions"] == [
        "user.is_authenticated",
        "resource.is_published",
    ]
    catalog[0]["name"] = "mutated"
    assert session.discover()[0]["name"] == ACTION


def test_discover_keeps_unknown_action_fields() -> None:
    document = load_example("update.json")
    document["actions"][0]["extension_flag"] = {"keep": True}
    seen = {}

    def perform(action, args, context):
        seen["flag"] = copy.deepcopy(action["extension_flag"])
        return action_output(action, args, context)

    session = create_session(
        document,
        SessionOptions(state=ready_state(), consent=allow, perform=perform),
    )
    catalog = session.discover()
    assert catalog[0]["extension_flag"] == {"keep": True}
    catalog[0]["extension_flag"]["keep"] = False
    assert session.discover()[0]["extension_flag"] == {"keep": True}
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.ok is True
    assert seen["flag"] == {"keep": True}


def test_invoke_with_valid_args_succeeds() -> None:
    seen = {}

    def perform(action, args, context):
        seen["name"] = action["name"]
        seen["note"] = args["note"]
        seen["risk"] = context["risk"]
        return {"result_id": "result-100", "status": "updated"}

    session = create_session(
        load_example("update.json"),
        SessionOptions(state=ready_state(), consent=allow, perform=perform),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.ok is True
    assert result.code == "ok"
    assert result.output == {"result_id": "result-100", "status": "updated"}
    assert seen == {"name": ACTION, "note": "apply update", "risk": "high"}


def test_invoke_with_invalid_args_is_a_typed_error() -> None:
    consent_called = False

    def consent(action, args, context):
        nonlocal consent_called
        consent_called = True
        return True

    session = create_session(
        load_example("update.json"),
        SessionOptions(
            state=ready_state(),
            consent=consent,
            perform=refuse_if_called,
        ),
    )
    result = session.invoke(ACTION, INVALID_ARGS)
    assert result.ok is False
    assert result.code == "invalid_input"
    assert any("note" in line for line in result.details)
    assert consent_called is False
    assert session.audit[-1].outcome == "invalid_input"


def test_high_risk_blocks_without_consent() -> None:
    session = create_session(
        load_example("update.json"),
        SessionOptions(state=ready_state(), perform=refuse_if_called),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.ok is False
    assert result.code == "consent_required"
    assert session.audit[-1].risk == "high"
    assert session.audit[-1].outcome == "consent_required"


def test_high_risk_blocks_when_consent_is_denied() -> None:
    session = create_session(
        load_example("update.json"),
        SessionOptions(
            state=ready_state(),
            consent=lambda action, args, context: False,
            perform=refuse_if_called,
        ),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.code == "consent_denied"


def test_high_risk_proceeds_with_consent() -> None:
    session = create_session(
        load_example("update.json"),
        SessionOptions(
            state=ready_state(),
            consent=allow,
            perform=action_output,
        ),
    )
    result = session.invoke(ACTION, {"note": "second update"})
    assert result.ok is True
    assert result.code == "ok"
    assert result.output["status"] == "updated"


def test_precondition_unknown_when_snapshot_cannot_answer() -> None:
    consent_called = False

    def consent(action, args, context):
        nonlocal consent_called
        consent_called = True
        return True

    session = create_session(
        load_example("update.json"),
        SessionOptions(
            state={},
            consent=consent,
            perform=refuse_if_called,
        ),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.code == "precondition_unknown"
    assert result.details == ("user.is_authenticated",)
    assert "user.is_authenticated" in result.message
    assert consent_called is False


def test_precondition_failed_when_boolean_is_false() -> None:
    state = {"user": {"is_authenticated": False}, "resource": {"is_published": True}}
    session = create_session(
        load_example("update.json"),
        SessionOptions(state=state, consent=allow, perform=refuse_if_called),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.code == "precondition_failed"
    assert result.details == ("user.is_authenticated",)


def test_non_boolean_snapshot_value_is_unknown() -> None:
    state = {"user": {"is_authenticated": "yes"}, "resource": {"is_published": True}}
    session = create_session(
        load_example("update.json"),
        SessionOptions(state=state, consent=allow, perform=refuse_if_called),
    )
    result = session.invoke(ACTION, VALID_ARGS)
    assert result.code == "precondition_unknown"


def test_low_risk_does_not_ask_for_consent() -> None:
    def consent(action, args, context):
        raise AssertionError("low risk must not ask for consent")

    def perform(action, args, context):
        return {"saved": True}

    session = create_session(
        load_example("article.json"),
        SessionOptions(
            state={"user": {"is_authenticated": True}},
            consent=consent,
            perform=perform,
        ),
    )
    result = session.invoke("bookmark", {"list": "reading"})
    assert result.ok is True
    assert result.output == {"saved": True}


def test_medium_is_audited_without_consent() -> None:
    def consent(action, args, context):
        raise AssertionError("medium risk must not ask for consent")

    def perform(action, args, context):
        return {"received": True}

    session = create_session(
        load_example("form.json"),
        SessionOptions(consent=consent, perform=perform),
    )
    result = session.invoke(
        "submit",
        {
            "email": "reader@example.com",
            "topic": "general",
            "message": "hello",
        },
    )
    assert result.ok is True
    assert session.audit[-1].risk == "medium"
    assert session.audit[-1].outcome == "ok"
    assert session.audit[-1].action == "submit"


def test_invalid_email_fails_input_schema() -> None:
    session = create_session(
        load_example("form.json"),
        SessionOptions(perform=refuse_if_called),
    )
    result = session.invoke(
        "submit",
        {
            "email": "not-an-email",
            "topic": "general",
            "message": "hello",
        },
    )
    assert result.code == "invalid_input"


def test_critical_requires_policy_before_consent() -> None:
    document = copy.deepcopy(load_example("update.json"))
    document["actions"][0]["risk"] = "critical"
    consent_called = False

    def consent(action, args, context):
        nonlocal consent_called
        consent_called = True
        return True

    session = create_session(
        document,
        SessionOptions(
            state=ready_state(),
            consent=consent,
            perform=refuse_if_called,
        ),
    )
    blocked = session.invoke(ACTION, VALID_ARGS)
    assert blocked.code == "policy_required"
    assert consent_called is False

    authorized = create_session(
        document,
        SessionOptions(
            state=ready_state(),
            preauthorized={ACTION},
            perform=refuse_if_called,
        ),
    )
    needs_consent = authorized.invoke(ACTION, VALID_ARGS)
    assert needs_consent.code == "consent_required"

    allowed = create_session(
        document,
        SessionOptions(
            state=ready_state(),
            preauthorized={ACTION},
            consent=allow,
            perform=action_output,
        ),
    )
    result = allowed.invoke(ACTION, VALID_ARGS)
    assert result.ok is True
    assert result.code == "ok"


def test_host_predicate_uses_snapshot_without_inference() -> None:
    document = copy.deepcopy(load_example("article.json"))
    document["actions"][0]["preconditions"] = ["user.has_role:admin"]

    def perform(action, args, context):
        return {"saved": True}

    matched = create_session(
        document,
        SessionOptions(
            state={"user": {"has_role": "admin"}},
            perform=perform,
        ),
    )
    assert matched.invoke("bookmark", {}).ok is True

    listed = create_session(
        document,
        SessionOptions(
            state={"user": {"has_role": ["editor"]}},
            perform=perform,
        ),
    )
    missed = listed.invoke("bookmark", {})
    assert missed.code == "precondition_failed"

    unknown = create_session(
        document,
        SessionOptions(
            state={"user": {"role": "admin"}},
            perform=refuse_if_called,
        ),
    )
    result = unknown.invoke("bookmark", {})
    assert result.code == "precondition_unknown"
    assert result.message == "precondition cannot be evaluated: user.has_role:admin"
    assert "user.role" not in result.message


def test_domain_predicate_in_snapshot_can_pass() -> None:
    document = copy.deepcopy(load_example("article.json"))
    document["actions"][0]["preconditions"] = ["weather.is_clear"]

    def perform(action, args, context):
        return {"saved": True}

    session = create_session(
        document,
        SessionOptions(state={"weather": {"is_clear": True}}, perform=perform),
    )
    assert session.invoke("bookmark", {}).ok is True


def test_unknown_action_and_closed_session() -> None:
    session = create_session(
        load_example("article.json"),
        SessionOptions(
            state={"user": {"is_authenticated": True}},
            perform=lambda action, args, context: {"saved": True},
        ),
    )
    missing = session.invoke("nope", {})
    assert missing.code == "unknown_action"
    assert session.audit == ()
    session.close()
    closed = session.invoke("bookmark", {})
    assert closed.code == "session_closed"
    with pytest.raises(LibraryError) as exc:
        session.discover()
    assert exc.value.code == "session_closed"


def test_output_must_match_schema() -> None:
    session = create_session(
        load_example("article.json"),
        SessionOptions(
            state={"user": {"is_authenticated": True}},
            perform=lambda action, args, context: {"saved": "yes"},
        ),
    )
    result = session.invoke("bookmark", {})
    assert result.code == "output_invalid"


def test_missing_handler_is_typed() -> None:
    session = create_session(
        load_example("article.json"),
        SessionOptions(state={"user": {"is_authenticated": True}}),
    )
    result = session.invoke("bookmark", {})
    assert result.code == "handler_missing"


def test_invalid_document_is_rejected() -> None:
    document = load_example("form.json")
    del document["type"]
    with pytest.raises(LibraryError) as exc:
        create_session(document)
    assert exc.value.code == "document_invalid"


def test_usage_example_runs() -> None:
    script = REPO / "library" / "examples" / "usage.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "component: article-card" in result.stdout
    assert "invoke: ok" in result.stdout
    assert result.stderr == ""
