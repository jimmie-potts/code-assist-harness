from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from code_assist_harness.loop_limits import (
    ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE,
    DEFAULT_MAX_ASSISTANT_OUTPUT_BYTES,
    DEFAULT_MAX_MODEL_TURNS,
    DEFAULT_MAX_OBSERVED_TOOL_CALLS,
    DEFAULT_PROVIDER_WORK_TIMEOUT_SECONDS,
    LOOP_LIMIT_FAILURE_CODES,
    MAX_ASSISTANT_OUTPUT_BYTES,
    MAX_MODEL_TURNS,
    MAX_OBSERVED_TOOL_CALLS,
    MAX_PROVIDER_WORK_TIMEOUT_SECONDS,
    MODEL_TURN_LIMIT_EXCEEDED_CODE,
    PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,
    TOOL_CALL_LIMIT_EXCEEDED_CODE,
    LoopLimits,
    LoopLimitsObserved,
    LoopLimitTracker,
    loop_limit_failure_code,
)


def _observation(**overrides: object) -> LoopLimitsObserved:
    values: dict[str, object] = {
        "session_id": "ses_limits",
        "max_model_turns": 2,
        "provider_work_timeout_seconds": 30,
        "max_assistant_output_bytes": 8,
        "max_observed_tool_calls": 2,
        "model_turns_started": 1,
        "assistant_output_bytes": 4,
        "tool_calls_observed": 1,
        "exhausted": None,
    }
    values.update(overrides)
    return LoopLimitsObserved(**values)  # type: ignore[arg-type]


def test_loop_limits_are_frozen_and_use_the_locked_defaults() -> None:
    limits = LoopLimits()

    assert limits == LoopLimits(
        max_model_turns=DEFAULT_MAX_MODEL_TURNS,
        provider_work_timeout_seconds=DEFAULT_PROVIDER_WORK_TIMEOUT_SECONDS,
        max_assistant_output_bytes=DEFAULT_MAX_ASSISTANT_OUTPUT_BYTES,
        max_observed_tool_calls=DEFAULT_MAX_OBSERVED_TOOL_CALLS,
    )
    with pytest.raises(FrozenInstanceError):
        limits.max_model_turns = 2  # type: ignore[misc]


def test_loop_limits_accept_each_locked_upper_boundary() -> None:
    limits = LoopLimits(
        max_model_turns=MAX_MODEL_TURNS,
        provider_work_timeout_seconds=MAX_PROVIDER_WORK_TIMEOUT_SECONDS,
        max_assistant_output_bytes=MAX_ASSISTANT_OUTPUT_BYTES,
        max_observed_tool_calls=MAX_OBSERVED_TOOL_CALLS,
    )

    assert limits.max_model_turns == 16
    assert limits.provider_work_timeout_seconds == 3600
    assert limits.max_assistant_output_bytes == 8192
    assert limits.max_observed_tool_calls == 64


def test_each_exhaustion_has_one_shared_stable_failure_code() -> None:
    expected = {
        "model_turns": MODEL_TURN_LIMIT_EXCEEDED_CODE,
        "provider_work": PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,
        "assistant_output": ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE,
        "tool_calls": TOOL_CALL_LIMIT_EXCEEDED_CODE,
    }

    assert {exhaustion: loop_limit_failure_code(exhaustion) for exhaustion in expected} == expected
    assert LOOP_LIMIT_FAILURE_CODES == frozenset(expected.values())

    with pytest.raises(ValueError, match="unsupported"):
        loop_limit_failure_code("tokens")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("max_model_turns", True),
        ("provider_work_timeout_seconds", False),
        ("max_assistant_output_bytes", 1.5),
        ("max_observed_tool_calls", "1"),
    ],
)
def test_loop_limits_reject_booleans_and_other_non_integers(
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(TypeError):
        LoopLimits(**{field_name: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("max_model_turns", 0),
        ("max_model_turns", MAX_MODEL_TURNS + 1),
        ("provider_work_timeout_seconds", -1),
        ("provider_work_timeout_seconds", MAX_PROVIDER_WORK_TIMEOUT_SECONDS + 1),
        ("max_assistant_output_bytes", 0),
        ("max_assistant_output_bytes", MAX_ASSISTANT_OUTPUT_BYTES + 1),
        ("max_observed_tool_calls", 0),
        ("max_observed_tool_calls", MAX_OBSERVED_TOOL_CALLS + 1),
    ],
)
def test_loop_limits_reject_disabled_or_excessive_values(
    field_name: str,
    value: int,
) -> None:
    with pytest.raises(ValueError):
        LoopLimits(**{field_name: value})  # type: ignore[arg-type]


def test_tracker_accepts_valid_seed_state_for_deterministic_boundaries() -> None:
    limits = LoopLimits(
        max_model_turns=2,
        max_assistant_output_bytes=8,
        max_observed_tool_calls=2,
    )
    tracker = LoopLimitTracker(
        limits,
        model_turns_started=1,
        assistant_output_bytes=4,
        tool_calls_observed=2,
    )

    assert tracker.limits is limits
    assert tracker.model_turns_started == 1
    assert tracker.assistant_output_bytes == 4
    assert tracker.tool_calls_observed == 2
    assert tracker.exhausted is None


@pytest.mark.parametrize(
    "factory",
    [
        lambda: LoopLimitTracker(object()),
        lambda: LoopLimitTracker(LoopLimits(), model_turns_started=True),
        lambda: LoopLimitTracker(LoopLimits(), assistant_output_bytes=-1),
        lambda: LoopLimitTracker(LoopLimits(), tool_calls_observed=2),
        lambda: LoopLimitTracker(LoopLimits(), exhausted="tool_calls"),
        lambda: LoopLimitTracker(LoopLimits(max_model_turns=2), exhausted="model_turns"),
        lambda: LoopLimitTracker(LoopLimits(), assistant_output_bytes=1),
        lambda: LoopLimitTracker(
            LoopLimits(),
            model_turns_started=1,
            exhausted="not_a_limit",
        ),
    ],
)
def test_tracker_rejects_invalid_or_inconsistent_seed_state(factory: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()  # type: ignore[operator]


def test_model_turn_admission_never_overflows_and_selects_first_exhaustion() -> None:
    tracker = LoopLimitTracker(LoopLimits(max_model_turns=2))

    assert tracker.admit_model_turn() is True
    assert tracker.admit_model_turn() is True
    assert tracker.admit_model_turn() is False
    assert tracker.model_turns_started == 2
    assert tracker.exhausted == "model_turns"

    assert tracker.admit_model_turn() is False
    assert tracker.reserve_assistant_output(1) is False
    assert tracker.observe_tool_call() is False
    assert tracker.mark_provider_work_exhausted() is None
    assert tracker.model_turns_started == 2
    assert tracker.exhausted == "model_turns"


def test_assistant_output_rejection_never_partially_charges_the_candidate() -> None:
    tracker = LoopLimitTracker(LoopLimits(max_assistant_output_bytes=5))
    assert tracker.admit_model_turn() is True

    assert tracker.reserve_assistant_output(3) is True
    assert tracker.reserve_assistant_output(3) is False
    assert tracker.assistant_output_bytes == 3
    assert tracker.exhausted == "assistant_output"

    assert tracker.reserve_assistant_output(0) is False
    assert tracker.assistant_output_bytes == 3


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_assistant_output_reservation_rejects_non_integer_values(value: object) -> None:
    tracker = LoopLimitTracker(LoopLimits())

    with pytest.raises(TypeError):
        tracker.reserve_assistant_output(value)  # type: ignore[arg-type]


def test_assistant_output_reservation_rejects_negative_values() -> None:
    tracker = LoopLimitTracker(LoopLimits())

    with pytest.raises(ValueError):
        tracker.reserve_assistant_output(-1)


def test_tool_calls_record_exactly_one_rejecting_observation() -> None:
    tracker = LoopLimitTracker(LoopLimits(max_observed_tool_calls=2))
    assert tracker.admit_model_turn() is True

    assert tracker.observe_tool_call() is True
    assert tracker.observe_tool_call() is True
    assert tracker.observe_tool_call() is False
    assert tracker.tool_calls_observed == 3
    assert tracker.exhausted == "tool_calls"

    assert tracker.observe_tool_call() is False
    assert tracker.tool_calls_observed == 3


def test_provider_work_marker_wins_once_without_changing_counters() -> None:
    tracker = LoopLimitTracker(LoopLimits())

    assert tracker.mark_provider_work_exhausted() is None
    assert tracker.mark_provider_work_exhausted() is None
    assert tracker.admit_model_turn() is False
    assert tracker.reserve_assistant_output(1) is False
    assert tracker.observe_tool_call() is False
    assert tracker.exhausted == "provider_work"
    assert tracker.model_turns_started == 0
    assert tracker.assistant_output_bytes == 0
    assert tracker.tool_calls_observed == 0


def test_an_existing_exhaustion_cannot_be_reclassified() -> None:
    tracker = LoopLimitTracker(LoopLimits(max_assistant_output_bytes=1))
    assert tracker.admit_model_turn() is True
    assert tracker.reserve_assistant_output(2) is False

    assert tracker.mark_provider_work_exhausted() is None
    assert tracker.observe_tool_call() is False
    assert tracker.exhausted == "assistant_output"


def test_snapshot_is_flat_frozen_and_matches_the_tracker() -> None:
    limits = LoopLimits(
        max_model_turns=2,
        provider_work_timeout_seconds=30,
        max_assistant_output_bytes=8,
        max_observed_tool_calls=2,
    )
    tracker = LoopLimitTracker(limits)
    assert tracker.admit_model_turn() is True
    assert tracker.reserve_assistant_output(4) is True
    assert tracker.observe_tool_call() is True

    observed = tracker.snapshot("ses_limits")

    assert {field.name for field in fields(LoopLimitsObserved)} == {
        "session_id",
        "max_model_turns",
        "provider_work_timeout_seconds",
        "max_assistant_output_bytes",
        "max_observed_tool_calls",
        "model_turns_started",
        "assistant_output_bytes",
        "tool_calls_observed",
        "exhausted",
    }
    assert observed == LoopLimitsObserved(
        session_id="ses_limits",
        max_model_turns=2,
        provider_work_timeout_seconds=30,
        max_assistant_output_bytes=8,
        max_observed_tool_calls=2,
        model_turns_started=1,
        assistant_output_bytes=4,
        tool_calls_observed=1,
        exhausted=None,
    )
    with pytest.raises(FrozenInstanceError):
        observed.exhausted = "provider_work"  # type: ignore[misc]


@pytest.mark.parametrize("session_id", ["invalid", "", 1, True])
def test_observation_rejects_invalid_session_identity(session_id: object) -> None:
    with pytest.raises(ValueError):
        _observation(session_id=session_id)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_model_turns": True},
        {"model_turns_started": True},
        {"model_turns_started": 3},
        {"assistant_output_bytes": 9},
        {"tool_calls_observed": 3},
        {"exhausted": "unknown"},
        {"exhausted": 1},
        {"exhausted": "model_turns", "model_turns_started": 1},
        {"exhausted": "tool_calls", "tool_calls_observed": 2},
        {
            "model_turns_started": 0,
            "assistant_output_bytes": 1,
            "tool_calls_observed": 0,
        },
        {
            "model_turns_started": 0,
            "assistant_output_bytes": 0,
            "tool_calls_observed": 0,
            "exhausted": "assistant_output",
        },
    ],
)
def test_observation_rejects_invalid_counters_or_exhaustion(
    overrides: dict[str, object],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _observation(**overrides)


def test_observation_accepts_each_legal_exhaustion_shape() -> None:
    model_turns = _observation(exhausted="model_turns", model_turns_started=2)
    provider_work = _observation(
        exhausted="provider_work",
        model_turns_started=0,
        assistant_output_bytes=0,
        tool_calls_observed=0,
    )
    assistant_output = _observation(exhausted="assistant_output", assistant_output_bytes=0)
    tool_calls = _observation(exhausted="tool_calls", tool_calls_observed=3)

    assert model_turns.exhausted == "model_turns"
    assert provider_work.exhausted == "provider_work"
    assert assistant_output.exhausted == "assistant_output"
    assert tool_calls.exhausted == "tool_calls"
    (LOOP_LIMIT_FAILURE_CODES,)
    (MODEL_TURN_LIMIT_EXCEEDED_CODE,)
    (PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,)
    (TOOL_CALL_LIMIT_EXCEEDED_CODE,)
