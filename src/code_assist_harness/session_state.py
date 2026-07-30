"""Pure, replayable lifecycle state for one harness session."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Literal

from .protocol import (
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    SessionCancelledEvent,
    SessionCompletedEvent,
    SessionEvent,
    SessionFailedEvent,
    SessionStartedEvent,
)

type SessionStatus = Literal[
    "idle",
    "starting",
    "running",
    "awaiting_approval",
    "cancelling",
    "completed",
    "cancelled",
    "failed",
]
"""Lifecycle states owned by the harness for one session."""

type InvariantFailureCode = Literal[
    "illegal_transition",
    "terminal_state_absorbing",
    "correlation_mismatch",
    "session_mismatch",
    "sequence_gap",
    "sequence_regression",
    "assistant_after_completion",
    "assistant_already_completed",
    "assistant_completion_mismatch",
    "session_completion_before_assistant",
]
"""Payload-free reasons that an update could not enter trusted state."""

TERMINAL_SESSION_STATUSES = frozenset[SessionStatus]({"completed", "cancelled", "failed"})
"""States that cannot accept another update for the same session."""


@dataclass(frozen=True, slots=True)
class SessionFailure:
    """Safe terminal failure copied from a validated ``session.failed`` event."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class SessionState:
    """Immutable authoritative projection for exactly one session.

    The reducer creates every non-idle value. ``last_sequence`` advances only after an accepted
    validated wire event; command-originated domain facts do not consume protocol sequence values.
    Terminal states are absorbing, so a conversation owner must create a fresh state for a later
    task rather than reusing this object.
    """

    status: SessionStatus = "idle"
    start_command_id: str | None = None
    task: str | None = None
    session_id: str | None = None
    cancel_command_id: str | None = None
    last_sequence: int = 0
    assistant_text: str = ""
    assistant_completed: bool = False
    session_failure: SessionFailure | None = None


INITIAL_SESSION_STATE = SessionState()
"""Canonical empty state used before a task is submitted."""


@dataclass(frozen=True, slots=True)
class TaskSubmitted:
    """Trusted domain fact recording a local task submission."""

    command_id: str
    task: str


@dataclass(frozen=True, slots=True)
class CancelRequested:
    """Trusted domain fact recording a cancellation sent for the active session."""

    command_id: str
    session_id: str


@dataclass(frozen=True, slots=True)
class ApprovalRequested:
    """Trusted domain fact recording that the active session is waiting for approval.

    This is a harness-owned lifecycle fact, not a protocol-v1 wire message. A later unit can attach
    approval request details without expanding the reducer's lifecycle vocabulary.
    """

    session_id: str


@dataclass(frozen=True, slots=True)
class ApprovalResolved:
    """Trusted domain fact recording that an approval wait has ended."""

    session_id: str


type SessionUpdate = (
    TaskSubmitted | CancelRequested | ApprovalRequested | ApprovalResolved | SessionEvent
)
"""One validated fact accepted by the session reducer."""


@dataclass(frozen=True, slots=True)
class SessionInvariantFailure:
    """Safe explanation for a rejected update.

    The diagnostic deliberately excludes command IDs, session IDs, task text, assistant text, and
    event payloads. That makes it suitable for a transcript or user-visible status without turning
    an invariant failure into a secret-exfiltration path.
    """

    code: InvariantFailureCode
    prior_status: SessionStatus
    event_type: str


@dataclass(frozen=True, slots=True)
class SessionReduction:
    """Result of reducing one update or replaying an ordered update stream.

    ``failure`` is absent for an accepted reduction. When it is present, ``state`` is the exact
    prior object supplied to the failing reduction.
    """

    state: SessionState
    failure: SessionInvariantFailure | None = None

    @property
    def ok(self) -> bool:
        """Return whether every attempted update was accepted."""
        return self.failure is None


def reduce_session_state(state: SessionState, update: SessionUpdate) -> SessionReduction:
    """Reduce one trusted domain fact or validated session event without side effects.

    Correlation, session identity, and contiguous sequence checks run before a legal wire event can
    alter the projection. The reducer performs no I/O, clock reads, randomness, mutation, provider
    work, or protocol parsing. Callers must validate raw wire values before constructing this API's
    ``SessionEvent`` input.

    Args:
        state: Current immutable state for one session.
        update: One trusted local fact or validated protocol-v1 session event.

    Returns:
        The accepted next state, or the exact prior state plus a payload-free invariant failure.
    """
    event_type = _event_type(update)
    if state.status in TERMINAL_SESSION_STATUSES:
        return _reject(state, "terminal_state_absorbing", event_type)

    if isinstance(update, TaskSubmitted):
        if state.status != "idle":
            return _reject(state, "illegal_transition", event_type)
        return _accept(
            SessionState(
                status="starting",
                start_command_id=update.command_id,
                task=update.task,
            )
        )

    if isinstance(update, CancelRequested):
        if state.status not in {"running", "awaiting_approval"}:
            return _reject(state, "illegal_transition", event_type)
        if update.session_id != state.session_id:
            return _reject(state, "session_mismatch", event_type)
        return _accept(replace(state, status="cancelling", cancel_command_id=update.command_id))

    if isinstance(update, ApprovalRequested):
        if state.status != "running":
            return _reject(state, "illegal_transition", event_type)
        if update.session_id != state.session_id:
            return _reject(state, "session_mismatch", event_type)
        return _accept(replace(state, status="awaiting_approval"))

    if isinstance(update, ApprovalResolved):
        if state.status != "awaiting_approval":
            return _reject(state, "illegal_transition", event_type)
        if update.session_id != state.session_id:
            return _reject(state, "session_mismatch", event_type)
        return _accept(replace(state, status="running"))

    return _reduce_session_event(state, update)


def replay_session_updates(
    updates: Iterable[SessionUpdate],
    initial_state: SessionState = INITIAL_SESSION_STATE,
) -> SessionReduction:
    """Replay an ordered update stream into the same result on every invocation.

    Replay stops at the first invariant failure because that update and every later update are
    outside the trusted projection. It never resumes work or re-executes a side effect.

    Args:
        updates: Ordered trusted facts and validated session events.
        initial_state: Immutable state from which replay begins.

    Returns:
        The final accepted state, or the state immediately before the first rejected update and its
        safe failure.
    """
    state = initial_state
    for update in updates:
        result = reduce_session_state(state, update)
        if not result.ok:
            return result
        state = result.state
    return _accept(state)


def _reduce_session_event(state: SessionState, event: SessionEvent) -> SessionReduction:
    event_type = event.type
    legal_statuses: dict[str, frozenset[SessionStatus]] = {
        "session.started": frozenset({"starting"}),
        "assistant.delta": frozenset({"running", "cancelling"}),
        "assistant.completed": frozenset({"running", "cancelling"}),
        "session.completed": frozenset({"running", "cancelling"}),
        "session.cancelled": frozenset({"cancelling"}),
        "session.failed": frozenset({"running", "awaiting_approval", "cancelling"}),
    }
    if state.status not in legal_statuses[event_type]:
        return _reject(state, "illegal_transition", event_type)

    expected_correlation = (
        state.cancel_command_id
        if isinstance(event, SessionCancelledEvent)
        else state.start_command_id
    )
    if event.correlation_id != expected_correlation:
        return _reject(state, "correlation_mismatch", event_type)

    if isinstance(event, SessionStartedEvent):
        sequence_failure = _sequence_failure(state, event.sequence, event_type)
        if sequence_failure is not None:
            return sequence_failure
        return _accept(
            replace(
                state,
                status="running",
                session_id=event.session_id,
                last_sequence=event.sequence,
            )
        )

    if event.session_id != state.session_id:
        return _reject(state, "session_mismatch", event_type)

    sequence_failure = _sequence_failure(state, event.sequence, event_type)
    if sequence_failure is not None:
        return sequence_failure

    if isinstance(event, AssistantDeltaEvent):
        if state.assistant_completed:
            return _reject(state, "assistant_after_completion", event_type)
        return _accept(
            replace(
                state,
                last_sequence=event.sequence,
                assistant_text=state.assistant_text + event.payload.text,
            )
        )

    if isinstance(event, AssistantCompletedEvent):
        if state.assistant_completed:
            return _reject(state, "assistant_already_completed", event_type)
        if event.payload.text != state.assistant_text:
            return _reject(state, "assistant_completion_mismatch", event_type)
        return _accept(replace(state, last_sequence=event.sequence, assistant_completed=True))

    if isinstance(event, SessionCompletedEvent):
        if not state.assistant_completed:
            return _reject(state, "session_completion_before_assistant", event_type)
        return _accept(replace(state, status="completed", last_sequence=event.sequence))

    if isinstance(event, SessionCancelledEvent):
        return _accept(replace(state, status="cancelled", last_sequence=event.sequence))

    if isinstance(event, SessionFailedEvent):
        return _accept(
            replace(
                state,
                status="failed",
                last_sequence=event.sequence,
                session_failure=SessionFailure(
                    code=event.payload.code,
                    message=event.payload.message,
                ),
            )
        )

    raise AssertionError(f"unhandled validated session event: {event_type}")


def _sequence_failure(
    state: SessionState, sequence: int, event_type: str
) -> SessionReduction | None:
    expected_sequence = state.last_sequence + 1
    if sequence < expected_sequence:
        return _reject(state, "sequence_regression", event_type)
    if sequence > expected_sequence:
        return _reject(state, "sequence_gap", event_type)
    return None


def _accept(state: SessionState) -> SessionReduction:
    return SessionReduction(state=state)


def _reject(state: SessionState, code: InvariantFailureCode, event_type: str) -> SessionReduction:
    return SessionReduction(
        state=state,
        failure=SessionInvariantFailure(
            code=code,
            prior_status=state.status,
            event_type=event_type,
        ),
    )


def _event_type(update: SessionUpdate) -> str:
    if isinstance(update, TaskSubmitted):
        return "task.submitted"
    if isinstance(update, CancelRequested):
        return "cancel.requested"
    if isinstance(update, ApprovalRequested):
        return "approval.requested"
    if isinstance(update, ApprovalResolved):
        return "approval.resolved"
    return update.type


__all__ = [
    "INITIAL_SESSION_STATE",
    "TERMINAL_SESSION_STATUSES",
    "ApprovalRequested",
    "ApprovalResolved",
    "CancelRequested",
    "InvariantFailureCode",
    "SessionFailure",
    "SessionInvariantFailure",
    "SessionReduction",
    "SessionState",
    "SessionStatus",
    "SessionUpdate",
    "TaskSubmitted",
    "reduce_session_state",
    "replay_session_updates",
]
