"""Provider-turn evidence that is intentionally separate from session lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from .protocol import SessionId

MAX_MODEL_USAGE_TOKENS = 9_007_199_254_740_991
"""Largest provider-reported token count that round-trips safely through JavaScript."""

_SESSION_ID_ADAPTER = TypeAdapter(SessionId)


@dataclass(frozen=True, slots=True)
class ModelUsageObserved:
    """One bounded provider-reported usage observation for a model turn.

    Usage is local evidence rather than lifecycle state, billing proof, or permission to perform
    more work. The owning session admits at most one value after a valid text completion candidate.

    Args:
        session_id: Valid harness-owned session identity.
        input_tokens: Non-negative provider-reported input token count.
        output_tokens: Non-negative provider-reported output token count.
    """

    session_id: SessionId
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        """Reject unsafe identities and counters before evidence reaches persistence."""
        try:
            _SESSION_ID_ADAPTER.validate_python(self.session_id, strict=True)
        except ValidationError:
            raise ValueError("model usage session ID is invalid") from None
        for field_name, value in (
            ("model usage input token count", self.input_tokens),
            ("model usage output token count", self.output_tokens),
        ):
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")
            if value < 0 or value > MAX_MODEL_USAGE_TOKENS:
                raise ValueError(f"{field_name} must be between 0 and {MAX_MODEL_USAGE_TOKENS}")


__all__ = ["MAX_MODEL_USAGE_TOKENS", "ModelUsageObserved"]
