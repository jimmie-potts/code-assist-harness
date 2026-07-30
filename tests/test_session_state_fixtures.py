from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from code_assist_harness.protocol import validate_event
from code_assist_harness.session_state import (
    INITIAL_SESSION_STATE,
    ApprovalRequested,
    ApprovalResolved,
    CancelRequested,
    SessionReduction,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
    replay_session_updates,
)

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "protocol" / "fixtures" / "session-lifecycle" / "v1"
)
PROTOCOL_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "protocol" / "fixtures" / "v1" / "manifest.json"
)
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
PROTOCOL_MANIFEST = json.loads(PROTOCOL_MANIFEST_PATH.read_text(encoding="utf-8"))
EXPECTED_CASE_COUNTS = {
    "legal-transitions.json": 16,
    "replay-scenarios.json": 7,
    "invariant-failures.json": 27,
}
WIRE_EVENT_TYPES = frozenset(MANIFEST["input_contract"]["wire_events"])


def _load_fixture(path: str) -> dict[str, Any]:
    return json.loads((FIXTURE_ROOT / path).read_text(encoding="utf-8"))


FIXTURES = {path: _load_fixture(path) for path in EXPECTED_CASE_COUNTS}


def test_manifest_declares_the_exact_fixture_file_and_case_contract() -> None:
    assert MANIFEST["fixture_version"] == 1
    assert MANIFEST["canonical_initial_state"] == _normalize_state(INITIAL_SESSION_STATE)
    assert sorted(path.name for path in FIXTURE_ROOT.glob("*.json")) == [
        "invariant-failures.json",
        "legal-transitions.json",
        "manifest.json",
        "replay-scenarios.json",
    ]

    declared_counts = {entry["path"]: entry["case_count"] for entry in MANIFEST["files"]}
    assert declared_counts == EXPECTED_CASE_COUNTS
    assert sum(declared_counts.values()) == 50

    all_ids: list[str] = []
    for path, expected_count in EXPECTED_CASE_COUNTS.items():
        document = FIXTURES[path]
        assert document["fixture_version"] == MANIFEST["fixture_version"]
        assert len(document["cases"]) == expected_count
        assert all(case["initial_state"] == "idle" for case in document["cases"])
        all_ids.extend(case["id"] for case in document["cases"])
    assert len(all_ids) == len(set(all_ids))


@pytest.mark.parametrize(
    ("fixture_path", "case"),
    [
        (path, case)
        for path in ("legal-transitions.json", "invariant-failures.json")
        for case in FIXTURES[path]["cases"]
    ],
    ids=lambda value: value.get("id", value) if isinstance(value, dict) else value,
)
def test_shared_setup_and_subject_cases_match_python_reducer(
    fixture_path: str, case: dict[str, Any]
) -> None:
    del fixture_path
    setup_inputs = case["setup_inputs"]
    all_inputs = [*setup_inputs, case["input"]]

    state = INITIAL_SESSION_STATE
    for raw_input in setup_inputs:
        setup_result = reduce_session_state(state, _to_update(raw_input))
        assert setup_result.ok, f"fixture setup failed for {case['id']}: {setup_result.failure}"
        state = setup_result.state

    subject_result = reduce_session_state(state, _to_update(case["input"]))
    assert _normalize_result(subject_result) == case["expected_result"]
    _assert_deterministic_replay(all_inputs, case["expected_result"])


@pytest.mark.parametrize(
    "case",
    FIXTURES["replay-scenarios.json"]["cases"],
    ids=lambda case: case["id"],
)
def test_shared_replay_scenarios_match_python_reducer(case: dict[str, Any]) -> None:
    _assert_deterministic_replay(case["inputs"], case["expected_result"])


def test_approval_inputs_remain_domain_facts_outside_protocol_v1() -> None:
    approval_types = {"approval.requested", "approval.resolved"}
    declared_domain_facts = {
        entry["type"]: entry["wire_message"] for entry in MANIFEST["input_contract"]["domain_facts"]
    }
    protocol_types = {entry["type"] for entry in PROTOCOL_MANIFEST["valid"]}

    assert declared_domain_facts.keys() >= approval_types
    assert all(declared_domain_facts[event_type] is False for event_type in approval_types)
    assert approval_types.isdisjoint(WIRE_EVENT_TYPES)
    assert approval_types.isdisjoint(protocol_types)
    for event_type in approval_types:
        with pytest.raises(ValidationError):
            validate_event({"type": event_type, "session_id": "ses_domain_only"})


def test_invariant_failure_does_not_echo_rejected_payload() -> None:
    secret = "PAYLOAD_MUST_NOT_ENTER_THE_DIAGNOSTIC"
    inputs: list[dict[str, Any]] = [
        {
            "type": "task.submitted",
            "command_id": "cmd_fixture_secret",
            "task": "Exercise safe failure output.",
        },
        {
            "protocol_version": 1,
            "type": "session.started",
            "session_id": "ses_fixture_secret",
            "sequence": 1,
            "timestamp": "2026-07-30T17:00:00.000Z",
            "correlation_id": "cmd_fixture_secret",
            "payload": {},
        },
        {
            "protocol_version": 1,
            "type": "assistant.delta",
            "session_id": "ses_fixture_secret",
            "sequence": 2,
            "timestamp": "2026-07-30T17:00:00.100Z",
            "correlation_id": "cmd_foreign_secret",
            "payload": {"text": secret},
        },
    ]

    result = replay_session_updates(_to_updates(inputs))

    assert not result.ok
    assert result.failure is not None
    assert set(asdict(result.failure)) == {"code", "prior_status", "event_type"}
    assert secret not in json.dumps(asdict(result.failure))


def _assert_deterministic_replay(
    raw_inputs: Iterable[dict[str, Any]], expected_result: dict[str, Any]
) -> None:
    inputs = list(raw_inputs)
    first = _normalize_result(replay_session_updates(_to_updates(inputs)))
    second = _normalize_result(replay_session_updates(_to_updates(inputs)))

    assert first == expected_result
    assert second == expected_result
    assert second == first


def _to_updates(raw_inputs: Iterable[dict[str, Any]]) -> list[SessionUpdate]:
    return [_to_update(raw_input) for raw_input in raw_inputs]


def _to_update(raw_input: dict[str, Any]) -> SessionUpdate:
    input_type = raw_input["type"]
    if input_type == "task.submitted":
        return TaskSubmitted(command_id=raw_input["command_id"], task=raw_input["task"])
    if input_type == "cancel.requested":
        return CancelRequested(
            command_id=raw_input["command_id"], session_id=raw_input["session_id"]
        )
    if input_type == "approval.requested":
        return ApprovalRequested(session_id=raw_input["session_id"])
    if input_type == "approval.resolved":
        return ApprovalResolved(session_id=raw_input["session_id"])

    assert input_type in WIRE_EVENT_TYPES
    return validate_event(raw_input)  # type: ignore[return-value]


def _normalize_state(state: SessionState) -> dict[str, Any]:
    return {
        "status": state.status,
        "start_command_id": state.start_command_id,
        "task": state.task,
        "session_id": state.session_id,
        "cancel_command_id": state.cancel_command_id,
        "last_sequence": state.last_sequence,
        "assistant_text": state.assistant_text,
        "assistant_completed": state.assistant_completed,
        "session_failure": (
            None
            if state.session_failure is None
            else {
                "code": state.session_failure.code,
                "message": state.session_failure.message,
            }
        ),
    }


def _normalize_result(result: SessionReduction) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "state": _normalize_state(result.state),
        "failure": None if result.failure is None else asdict(result.failure),
    }
