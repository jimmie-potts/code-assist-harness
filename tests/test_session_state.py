from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from code_assist_harness.protocol import SessionEvent, validate_event
from code_assist_harness.session_state import (
    INITIAL_SESSION_STATE,
    ApprovalRequested,
    ApprovalResolved,
    CancelRequested,
    SessionFailure,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
    replay_session_updates,
)

TIMESTAMP = "2026-07-30T12:34:56.789Z"
START_COMMAND_ID = "cmd_start"
CANCEL_COMMAND_ID = "cmd_cancel"
SESSION_ID = "ses_reducer"


def _event(
    event_type: str,
    sequence: int,
    *,
    session_id: str = SESSION_ID,
    correlation_id: str = START_COMMAND_ID,
    text: str = "",
) -> SessionEvent:
    if event_type in {"assistant.delta", "assistant.completed"}:
        payload: dict[str, object] = {"text": text}
    elif event_type == "session.failed":
        payload = {"code": "provider_failed", "message": "The provider stopped safely."}
    else:
        payload = {}
    event = validate_event(
        {
            "protocol_version": 1,
            "type": event_type,
            "session_id": session_id,
            "sequence": sequence,
            "timestamp": TIMESTAMP,
            "correlation_id": correlation_id,
            "payload": payload,
        }
    )
    return cast(SessionEvent, event)


def _accepted(*updates: SessionUpdate) -> SessionState:
    result = replay_session_updates(updates)
    assert result.ok
    assert result.failure is None
    return result.state


def _running_state() -> SessionState:
    return _accepted(
        TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
        _event("session.started", 1),
    )


def test_idle_state_and_inputs_are_frozen() -> None:
    submission = TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer")

    with pytest.raises(FrozenInstanceError):
        INITIAL_SESSION_STATE.status = "starting"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        submission.task = "Mutated"  # type: ignore[misc]

    assert INITIAL_SESSION_STATE == SessionState()


def test_normal_completion_accumulates_and_confirms_exact_assistant_text() -> None:
    result = replay_session_updates(
        [
            TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
            _event("session.started", 1),
            _event("assistant.delta", 2, text="Pure "),
            _event("assistant.delta", 3, text="state"),
            _event("assistant.completed", 4, text="Pure state"),
            _event("session.completed", 5),
        ]
    )

    assert result.ok
    assert result.state == SessionState(
        status="completed",
        start_command_id=START_COMMAND_ID,
        task="Explain the reducer",
        session_id=SESSION_ID,
        last_sequence=5,
        assistant_text="Pure state",
        assistant_completed=True,
    )


def test_approval_wait_and_resolution_are_domain_facts_without_sequence_changes() -> None:
    running = _running_state()

    waiting = reduce_session_state(running, ApprovalRequested(session_id=SESSION_ID))
    resumed = reduce_session_state(waiting.state, ApprovalResolved(session_id=SESSION_ID))

    assert waiting.ok
    assert waiting.state.status == "awaiting_approval"
    assert waiting.state.last_sequence == 1
    assert resumed.ok
    assert resumed.state.status == "running"
    assert resumed.state.last_sequence == 1


@pytest.mark.parametrize("prior_status", ["running", "awaiting_approval"])
def test_cancellation_request_is_legal_from_each_cancellable_state(prior_status: str) -> None:
    state = _running_state()
    if prior_status == "awaiting_approval":
        state = reduce_session_state(state, ApprovalRequested(session_id=SESSION_ID)).state

    result = reduce_session_state(
        state,
        CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
    )

    assert result.ok
    assert result.state.status == "cancelling"
    assert result.state.cancel_command_id == CANCEL_COMMAND_ID
    assert result.state.last_sequence == 1


def test_cancellation_accepts_in_flight_output_then_cancel_correlated_terminal_event() -> None:
    cancelling = _accepted(
        TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
        _event("session.started", 1),
        CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
        _event("assistant.delta", 2, text="Stopping"),
        _event("assistant.completed", 3, text="Stopping"),
    )

    result = reduce_session_state(
        cancelling,
        _event(
            "session.cancelled",
            4,
            correlation_id=CANCEL_COMMAND_ID,
        ),
    )

    assert result.ok
    assert result.state.status == "cancelled"
    assert result.state.assistant_text == "Stopping"
    assert result.state.assistant_completed


def test_normal_completion_can_win_after_cancellation_is_requested() -> None:
    result = replay_session_updates(
        [
            TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
            _event("session.started", 1),
            CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
            _event("assistant.delta", 2, text="Won"),
            _event("assistant.completed", 3, text="Won"),
            _event("session.completed", 4),
        ]
    )

    assert result.ok
    assert result.state.status == "completed"
    assert result.state.cancel_command_id == CANCEL_COMMAND_ID


@pytest.mark.parametrize("prior_status", ["running", "awaiting_approval", "cancelling"])
def test_session_failure_is_terminal_from_every_legal_active_state(prior_status: str) -> None:
    state = _running_state()
    if prior_status == "awaiting_approval":
        state = reduce_session_state(state, ApprovalRequested(session_id=SESSION_ID)).state
    elif prior_status == "cancelling":
        state = reduce_session_state(
            state,
            CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
        ).state

    result = reduce_session_state(state, _event("session.failed", 2))

    assert result.ok
    assert result.state.status == "failed"
    assert result.state.session_failure == SessionFailure(
        code="provider_failed",
        message="The provider stopped safely.",
    )


def _failure_case(code: str) -> tuple[SessionState, SessionUpdate]:
    running = _running_state()
    if code == "illegal_transition":
        return INITIAL_SESSION_STATE, CancelRequested(CANCEL_COMMAND_ID, SESSION_ID)
    if code == "correlation_mismatch":
        return running, _event("assistant.delta", 2, correlation_id="cmd_wrong", text="x")
    if code == "session_mismatch":
        return running, _event("assistant.delta", 2, session_id="ses_wrong", text="x")
    if code == "sequence_gap":
        return running, _event("assistant.delta", 3, text="x")
    if code == "sequence_regression":
        return running, _event("assistant.delta", 1, text="x")
    if code == "assistant_after_completion":
        streamed = reduce_session_state(running, _event("assistant.delta", 2, text="done")).state
        completed = reduce_session_state(
            streamed,
            _event("assistant.completed", 3, text="done"),
        ).state
        return completed, _event("assistant.delta", 4, text="late")
    if code == "assistant_already_completed":
        streamed = reduce_session_state(running, _event("assistant.delta", 2, text="done")).state
        completed = reduce_session_state(
            streamed,
            _event("assistant.completed", 3, text="done"),
        ).state
        return completed, _event("assistant.completed", 4, text="done")
    if code == "assistant_completion_mismatch":
        streamed = reduce_session_state(running, _event("assistant.delta", 2, text="exact")).state
        return streamed, _event("assistant.completed", 3, text="different")
    if code == "session_completion_before_assistant":
        return running, _event("session.completed", 2)
    raise AssertionError(f"unknown failure test case: {code}")


@pytest.mark.parametrize(
    "expected_code",
    [
        "illegal_transition",
        "correlation_mismatch",
        "session_mismatch",
        "sequence_gap",
        "sequence_regression",
        "assistant_after_completion",
        "assistant_already_completed",
        "assistant_completion_mismatch",
        "session_completion_before_assistant",
    ],
)
def test_rejections_are_payload_free_and_return_the_exact_prior_state(
    expected_code: str,
) -> None:
    prior_state, update = _failure_case(expected_code)

    result = reduce_session_state(prior_state, update)

    assert not result.ok
    assert result.state is prior_state
    assert result.failure is not None
    assert result.failure.code == expected_code
    assert result.failure.prior_status == prior_state.status
    assert result.failure.event_type in {
        "cancel.requested",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    }
    assert set(result.failure.__dataclass_fields__) == {"code", "prior_status", "event_type"}


def test_wrong_cancellation_target_is_a_session_mismatch() -> None:
    prior_state = _running_state()

    result = reduce_session_state(
        prior_state,
        CancelRequested(command_id=CANCEL_COMMAND_ID, session_id="ses_wrong"),
    )

    assert not result.ok
    assert result.state is prior_state
    assert result.failure is not None
    assert result.failure.code == "session_mismatch"
    assert result.failure.event_type == "cancel.requested"


def test_cancelled_event_must_correlate_to_the_cancel_command() -> None:
    cancelling = _accepted(
        TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
        _event("session.started", 1),
        CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
    )

    result = reduce_session_state(cancelling, _event("session.cancelled", 2))

    assert not result.ok
    assert result.state is cancelling
    assert result.failure is not None
    assert result.failure.code == "correlation_mismatch"


@pytest.mark.parametrize("terminal_status", ["completed", "cancelled", "failed"])
@pytest.mark.parametrize(
    "late_update",
    [
        TaskSubmitted(command_id="cmd_late", task="Late task"),
        ApprovalRequested(session_id=SESSION_ID),
        _event("session.completed", 9),
    ],
)
def test_terminal_states_absorb_every_late_input_category(
    terminal_status: str,
    late_update: SessionUpdate,
) -> None:
    if terminal_status == "completed":
        terminal = _accepted(
            TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
            _event("session.started", 1),
            _event("assistant.delta", 2, text="done"),
            _event("assistant.completed", 3, text="done"),
            _event("session.completed", 4),
        )
    elif terminal_status == "cancelled":
        terminal = _accepted(
            TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
            _event("session.started", 1),
            CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
            _event("session.cancelled", 2, correlation_id=CANCEL_COMMAND_ID),
        )
    else:
        terminal = _accepted(
            TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
            _event("session.started", 1),
            _event("session.failed", 2),
        )

    result = reduce_session_state(terminal, late_update)

    assert not result.ok
    assert result.state is terminal
    assert result.failure is not None
    assert result.failure.code == "terminal_state_absorbing"
    assert result.failure.prior_status == terminal_status


def test_replay_is_deterministic_and_stops_at_the_first_failure() -> None:
    updates: tuple[SessionUpdate, ...] = (
        TaskSubmitted(command_id=START_COMMAND_ID, task="Explain the reducer"),
        _event("session.started", 1),
        _event("assistant.delta", 3, text="gap"),
        _event("assistant.delta", 2, text="must not be reduced"),
    )

    first = replay_session_updates(updates)
    second = replay_session_updates(updates)

    assert first == second
    assert first.state.status == "running"
    assert first.state.last_sequence == 1
    assert first.state.assistant_text == ""
    assert first.failure is not None
    assert first.failure.code == "sequence_gap"
