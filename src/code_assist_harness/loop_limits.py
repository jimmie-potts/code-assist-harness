"""Harness-owned safety budgets for one provider-backed session."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from pydantic import TypeAdapter, ValidationError

from .protocol import SessionId

DEFAULT_MAX_MODEL_TURNS = 1
"""Default number of model turns admitted in one provider-backed session."""

MAX_MODEL_TURNS = 16
"""Largest configurable model-turn budget."""

DEFAULT_PROVIDER_WORK_TIMEOUT_SECONDS = 120
"""Default elapsed provider-work budget in seconds."""

MAX_PROVIDER_WORK_TIMEOUT_SECONDS = 3600
"""Largest configurable provider-work timeout in seconds."""

DEFAULT_MAX_ASSISTANT_OUTPUT_BYTES = 4096
"""Default cumulative accepted assistant-output budget in UTF-8 bytes."""

MAX_ASSISTANT_OUTPUT_BYTES = 8192
"""Largest configurable assistant-output budget allowed by the protocol-fit ceiling."""

DEFAULT_MAX_OBSERVED_TOOL_CALLS = 1
"""Default number of provider tool-call observations admitted in one session."""

MAX_OBSERVED_TOOL_CALLS = 64
"""Largest configurable provider tool-call observation budget."""

type LoopLimitExhaustion = Literal[
    "model_turns",
    "provider_work",
    "assistant_output",
    "tool_calls",
]
"""Stable classifications for the first exhausted loop budget."""

MODEL_TURN_LIMIT_EXCEEDED_CODE = "model_turn_limit_exceeded"
"""Stable failure code for denied model-turn admission."""

PROVIDER_WORK_DEADLINE_EXCEEDED_CODE = "provider_work_deadline_exceeded"
"""Stable failure code for exhausted provider-work time."""

ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE = "assistant_output_limit_exceeded"
"""Stable failure code for a rejected assistant-output reservation."""

TOOL_CALL_LIMIT_EXCEEDED_CODE = "tool_call_limit_exceeded"
"""Stable failure code for an over-budget provider tool-call observation."""

_LOOP_LIMIT_FAILURE_CODES_BY_EXHAUSTION: dict[LoopLimitExhaustion, str] = {
    "model_turns": MODEL_TURN_LIMIT_EXCEEDED_CODE,
    "provider_work": PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,
    "assistant_output": ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE,
    "tool_calls": TOOL_CALL_LIMIT_EXCEEDED_CODE,
}
LOOP_LIMIT_FAILURE_CODES = frozenset(_LOOP_LIMIT_FAILURE_CODES_BY_EXHAUSTION.values())
"""All stable session-failure codes selected by loop-limit exhaustion."""

_EXHAUSTION_VALUES = frozenset({"model_turns", "provider_work", "assistant_output", "tool_calls"})
_SESSION_ID_ADAPTER = TypeAdapter(SessionId)


def loop_limit_failure_code(exhaustion: LoopLimitExhaustion) -> str:
    """Return the stable session-failure code for one exhausted budget.

    Args:
        exhaustion: Validated first-exhaustion classification.

    Returns:
        The matching bounded session-failure code.

    Raises:
        ValueError: If a caller bypasses typing with an unsupported classification.
    """
    try:
        return _LOOP_LIMIT_FAILURE_CODES_BY_EXHAUSTION[exhaustion]
    except KeyError:
        raise ValueError("loop-limit exhaustion is unsupported") from None


def _require_strict_integer(value: object, field_name: str) -> int:
    """Return one exact integer while rejecting booleans and coercible values."""
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer")
    return value


def _require_configured_limit(value: object, field_name: str, maximum: int) -> int:
    """Validate one positive configured limit against its locked maximum."""
    integer = _require_strict_integer(value, field_name)
    if integer < 1 or integer > maximum:
        raise ValueError(f"{field_name} must be between 1 and {maximum}")
    return integer


def _require_counter(value: object, field_name: str, maximum: int) -> int:
    """Validate one non-negative counter that may not exceed its admitted maximum."""
    integer = _require_strict_integer(value, field_name)
    if integer < 0 or integer > maximum:
        raise ValueError(f"{field_name} must be between 0 and {maximum}")
    return integer


def _require_exhaustion(value: object) -> LoopLimitExhaustion | None:
    """Validate the stable first-exhaustion classification."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("loop-limit exhaustion must be a string or None")
    if value not in _EXHAUSTION_VALUES:
        raise ValueError("loop-limit exhaustion is unsupported")
    return cast(LoopLimitExhaustion, value)


@dataclass(frozen=True, slots=True)
class LoopLimits:
    """Immutable hard limits applied to one provider-backed session.

    Args:
        max_model_turns: Model turns that may begin, from 1 through 16.
        provider_work_timeout_seconds: Elapsed provider-work budget, from 1 through 3,600 seconds.
        max_assistant_output_bytes: Accepted assistant UTF-8 bytes, from 1 through 8,192.
        max_observed_tool_calls: Provider tool-call observations, from 1 through 64.
    """

    max_model_turns: int = DEFAULT_MAX_MODEL_TURNS
    provider_work_timeout_seconds: int = DEFAULT_PROVIDER_WORK_TIMEOUT_SECONDS
    max_assistant_output_bytes: int = DEFAULT_MAX_ASSISTANT_OUTPUT_BYTES
    max_observed_tool_calls: int = DEFAULT_MAX_OBSERVED_TOOL_CALLS

    def __post_init__(self) -> None:
        """Reject coercion, disabled limits, and values beyond the locked maxima."""
        _require_configured_limit(
            self.max_model_turns,
            "maximum model turns",
            MAX_MODEL_TURNS,
        )
        _require_configured_limit(
            self.provider_work_timeout_seconds,
            "provider work timeout seconds",
            MAX_PROVIDER_WORK_TIMEOUT_SECONDS,
        )
        _require_configured_limit(
            self.max_assistant_output_bytes,
            "maximum assistant output bytes",
            MAX_ASSISTANT_OUTPUT_BYTES,
        )
        _require_configured_limit(
            self.max_observed_tool_calls,
            "maximum observed tool calls",
            MAX_OBSERVED_TOOL_CALLS,
        )


@dataclass(frozen=True, slots=True)
class LoopLimitsObserved:
    """Immutable, replay-safe evidence for one session's loop budgets.

    Assistant bytes and model turns count admitted work and therefore never exceed their configured
    maxima. Tool calls count observations, so only a ``tool_calls`` exhaustion may carry the one
    rejecting observation at maximum plus one. Provider-work exhaustion has no elapsed-time counter.

    Args:
        session_id: Valid harness-owned session identity.
        max_model_turns: Configured model-turn maximum.
        provider_work_timeout_seconds: Configured provider-work timeout.
        max_assistant_output_bytes: Configured assistant-output maximum.
        max_observed_tool_calls: Configured tool-call observation maximum.
        model_turns_started: Model turns admitted before provider start.
        assistant_output_bytes: Cumulative assistant UTF-8 bytes admitted for publication.
        tool_calls_observed: Provider tool calls observed, including a rejecting over-limit call.
        exhausted: First exhausted budget, or ``None`` when no budget selected the outcome.
    """

    session_id: SessionId
    max_model_turns: int
    provider_work_timeout_seconds: int
    max_assistant_output_bytes: int
    max_observed_tool_calls: int
    model_turns_started: int
    assistant_output_bytes: int
    tool_calls_observed: int
    exhausted: LoopLimitExhaustion | None

    def __post_init__(self) -> None:
        """Validate identity, configured ranges, counters, and exhaustion relationships."""
        try:
            _SESSION_ID_ADAPTER.validate_python(self.session_id, strict=True)
        except ValidationError:
            raise ValueError("loop-limits observation session ID is invalid") from None

        limits = LoopLimits(
            max_model_turns=self.max_model_turns,
            provider_work_timeout_seconds=self.provider_work_timeout_seconds,
            max_assistant_output_bytes=self.max_assistant_output_bytes,
            max_observed_tool_calls=self.max_observed_tool_calls,
        )
        exhaustion = _require_exhaustion(self.exhausted)
        model_turns_started = _require_counter(
            self.model_turns_started,
            "model turns started",
            limits.max_model_turns,
        )
        assistant_output_bytes = _require_counter(
            self.assistant_output_bytes,
            "assistant output bytes",
            limits.max_assistant_output_bytes,
        )

        maximum_tool_count = limits.max_observed_tool_calls + (
            1 if exhaustion == "tool_calls" else 0
        )
        tool_calls_observed = _require_counter(
            self.tool_calls_observed,
            "tool calls observed",
            maximum_tool_count,
        )
        if exhaustion == "tool_calls" and tool_calls_observed != maximum_tool_count:
            raise ValueError(
                "tool-call exhaustion requires exactly one rejecting observation beyond the maximum"
            )
        if exhaustion == "model_turns" and model_turns_started != limits.max_model_turns:
            raise ValueError(
                "model-turn exhaustion requires the admitted count to equal the maximum"
            )
        if model_turns_started == 0 and (
            assistant_output_bytes > 0
            or tool_calls_observed > 0
            or exhaustion in {"assistant_output", "tool_calls"}
        ):
            raise ValueError("provider observations require an admitted model turn")


class LoopLimitTracker:
    """Mutable first-winner accountant for one provider-backed session.

    The tracker owns only harness-admitted counters. Its methods never partially charge rejected
    work, never let a counter overflow its evidence contract, and never replace an earlier exhausted
    limit. Seed arguments exist for deterministic boundary tests until multi-turn and tool
    continuation behavior is implemented.
    """

    __slots__ = (
        "_assistant_output_bytes",
        "_exhausted",
        "_limits",
        "_model_turns_started",
        "_tool_calls_observed",
    )

    def __init__(
        self,
        limits: LoopLimits,
        *,
        model_turns_started: int = 0,
        assistant_output_bytes: int = 0,
        tool_calls_observed: int = 0,
        exhausted: LoopLimitExhaustion | None = None,
    ) -> None:
        """Create one tracker from validated limits and optional deterministic seed state.

        Args:
            limits: Immutable configuration for this session.
            model_turns_started: Seeded admitted model turns.
            assistant_output_bytes: Seeded admitted assistant UTF-8 bytes.
            tool_calls_observed: Seeded provider tool-call observations.
            exhausted: Seeded first exhaustion classification.

        Raises:
            TypeError: If limits, counters, or exhaustion use unsupported types.
            ValueError: If seeded state violates a configured bound or exhaustion invariant.
        """
        if not isinstance(limits, LoopLimits):
            raise TypeError("loop limit tracker requires LoopLimits")
        exhaustion = _require_exhaustion(exhausted)
        validated_model_turns = _require_counter(
            model_turns_started,
            "model turns started",
            limits.max_model_turns,
        )
        validated_output_bytes = _require_counter(
            assistant_output_bytes,
            "assistant output bytes",
            limits.max_assistant_output_bytes,
        )
        maximum_tool_count = limits.max_observed_tool_calls + (
            1 if exhaustion == "tool_calls" else 0
        )
        validated_tool_calls = _require_counter(
            tool_calls_observed,
            "tool calls observed",
            maximum_tool_count,
        )
        if exhaustion == "tool_calls" and validated_tool_calls != maximum_tool_count:
            raise ValueError(
                "tool-call exhaustion requires exactly one rejecting observation beyond the maximum"
            )
        if exhaustion == "model_turns" and validated_model_turns != limits.max_model_turns:
            raise ValueError(
                "model-turn exhaustion requires the admitted count to equal the maximum"
            )
        if validated_model_turns == 0 and (
            validated_output_bytes > 0
            or validated_tool_calls > 0
            or exhaustion in {"assistant_output", "tool_calls"}
        ):
            raise ValueError("provider observations require an admitted model turn")

        self._limits = limits
        self._model_turns_started = validated_model_turns
        self._assistant_output_bytes = validated_output_bytes
        self._tool_calls_observed = validated_tool_calls
        self._exhausted = exhaustion

    @property
    def limits(self) -> LoopLimits:
        """Return the immutable configuration owned by this tracker."""
        return self._limits

    @property
    def model_turns_started(self) -> int:
        """Return the number of model turns admitted before provider start."""
        return self._model_turns_started

    @property
    def assistant_output_bytes(self) -> int:
        """Return cumulative assistant UTF-8 bytes admitted for publication."""
        return self._assistant_output_bytes

    @property
    def tool_calls_observed(self) -> int:
        """Return tool calls observed, including one rejecting over-limit observation."""
        return self._tool_calls_observed

    @property
    def exhausted(self) -> LoopLimitExhaustion | None:
        """Return the first exhausted budget, if any."""
        return self._exhausted

    def admit_model_turn(self) -> bool:
        """Charge one model turn before provider start.

        Returns:
            ``True`` when the turn was admitted. ``False`` leaves the count unchanged and records
            ``model_turns`` only when this attempt is the first exhausted budget.
        """
        if self._exhausted is not None:
            return False
        if self._model_turns_started >= self._limits.max_model_turns:
            self._exhausted = "model_turns"
            return False
        self._model_turns_started += 1
        return True

    def reserve_assistant_output(self, byte_count: int) -> bool:
        """Reserve a complete assistant delta before publication.

        Args:
            byte_count: Non-negative UTF-8 size of the candidate delta.

        Returns:
            ``True`` after charging the complete value. ``False`` performs no partial charge and
            records ``assistant_output`` only when this is the first exhausted budget.

        Raises:
            TypeError: If ``byte_count`` is not an exact integer.
            ValueError: If ``byte_count`` is negative.
        """
        candidate_bytes = _require_strict_integer(byte_count, "assistant output reservation")
        if candidate_bytes < 0:
            raise ValueError("assistant output reservation must be non-negative")
        if self._exhausted is not None:
            return False
        remaining = self._limits.max_assistant_output_bytes - self._assistant_output_bytes
        if candidate_bytes > remaining:
            self._exhausted = "assistant_output"
            return False
        self._assistant_output_bytes += candidate_bytes
        return True

    def observe_tool_call(self) -> bool:
        """Count one provider tool request before unsupported-tool handling.

        Returns:
            ``True`` when the observation is within budget. The first rejecting attempt returns
            ``False``, records exactly maximum plus one observations, and selects ``tool_calls``.
            Later calls after any exhaustion return ``False`` without changing state.
        """
        if self._exhausted is not None:
            return False
        self._tool_calls_observed += 1
        if self._tool_calls_observed > self._limits.max_observed_tool_calls:
            self._exhausted = "tool_calls"
            return False
        return True

    def mark_provider_work_exhausted(self) -> None:
        """Select provider-work expiry only when no earlier budget already won."""
        if self._exhausted is not None:
            return
        self._exhausted = "provider_work"

    def snapshot(self, session_id: SessionId) -> LoopLimitsObserved:
        """Return immutable validated evidence for the current tracker state.

        Args:
            session_id: Harness-owned identity of the session that owns this tracker.

        Returns:
            A flat transcript-ready observation with the configuration, counters, and first
            exhaustion classification.
        """
        return LoopLimitsObserved(
            session_id=session_id,
            max_model_turns=self._limits.max_model_turns,
            provider_work_timeout_seconds=self._limits.provider_work_timeout_seconds,
            max_assistant_output_bytes=self._limits.max_assistant_output_bytes,
            max_observed_tool_calls=self._limits.max_observed_tool_calls,
            model_turns_started=self._model_turns_started,
            assistant_output_bytes=self._assistant_output_bytes,
            tool_calls_observed=self._tool_calls_observed,
            exhausted=self._exhausted,
        )


__all__ = [
    "DEFAULT_MAX_ASSISTANT_OUTPUT_BYTES",
    "DEFAULT_MAX_MODEL_TURNS",
    "DEFAULT_MAX_OBSERVED_TOOL_CALLS",
    "DEFAULT_PROVIDER_WORK_TIMEOUT_SECONDS",
    "MAX_ASSISTANT_OUTPUT_BYTES",
    "MAX_MODEL_TURNS",
    "MAX_OBSERVED_TOOL_CALLS",
    "MAX_PROVIDER_WORK_TIMEOUT_SECONDS",
    "LoopLimitExhaustion",
    "LoopLimitTracker",
    "LoopLimits",
    "LoopLimitsObserved",
]
