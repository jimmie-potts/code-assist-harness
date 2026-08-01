"""Provider-neutral values owned by the harness domain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

from ..model_evidence import MAX_MODEL_USAGE_TOKENS

MAX_PROVIDER_FAILURE_MESSAGE_CHARS = 1024
"""Largest normalized provider failure message accepted by the domain."""

MAX_PROVIDER_LABEL_CHARS = 256
"""Largest source, call, tool, or checkpoint label accepted by provider-domain values."""

type ProviderMessageRole = Literal["user", "assistant"]
"""Conversation roles required by the first provider-backed model turn."""

type ProviderFailureCode = Literal[
    "authentication_failed",
    "rate_limited",
    "request_rejected",
    "unavailable",
    "invalid_response",
    "unknown",
]
"""Stable provider-failure categories that never expose an SDK exception type."""


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} must be valid UTF-8") from None
    return value


def _require_non_empty_string(
    value: object,
    field_name: str,
    *,
    maximum_chars: int | None = None,
    reject_controls: bool = False,
) -> str:
    text = _require_string(value, field_name)
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    if maximum_chars is not None and len(text) > maximum_chars:
        raise ValueError(f"{field_name} must contain at most {maximum_chars} characters")
    if reject_controls and any(
        ord(character) < 32 or 127 <= ord(character) <= 159 or character in {"\u2028", "\u2029"}
        for character in text
    ):
        raise ValueError(f"{field_name} must not contain terminal controls or line separators")
    return text


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    """One ordered model-facing conversation message.

    Args:
        role: Harness-owned meaning of the speaker.
        content: Non-empty model-facing text. Context budgeting is owned by a later unit.
    """

    role: ProviderMessageRole
    content: str

    def __post_init__(self) -> None:
        """Validate the small semantic contract without importing a provider SDK."""
        if self.role not in {"user", "assistant"}:
            raise ValueError("provider message role is unsupported")
        _require_non_empty_string(self.content, "provider message content")


@dataclass(frozen=True, slots=True)
class RepositoryInstruction:
    """Caller-supplied repository guidance included in a provider request.

    CAH-020 does not discover instruction files. A later context unit supplies an ordered tuple of
    these values after applying workspace and precedence rules.

    Args:
        source: Non-secret, workspace-relative teaching label such as ``AGENTS.md``.
        content: Non-empty instruction text.
    """

    source: str
    content: str

    def __post_init__(self) -> None:
        """Reject empty or terminal-unsafe labels while preserving instruction text."""
        _require_non_empty_string(
            self.source,
            "repository instruction source",
            maximum_chars=MAX_PROVIDER_LABEL_CHARS,
            reject_controls=True,
        )
        _require_non_empty_string(self.content, "repository instruction content")


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Immutable harness-owned input for exactly one model turn.

    Conversation and repository-instruction order are significant. The request deliberately omits
    SDK response objects, provider credentials, model-specific options, and instruction discovery.

    Args:
        conversation: Non-empty ordered model-facing history.
        repository_instructions: Ordered caller-supplied repository guidance.
    """

    conversation: tuple[ProviderMessage, ...]
    repository_instructions: tuple[RepositoryInstruction, ...] = ()

    def __post_init__(self) -> None:
        """Require immutable tuples and one or more conversation messages."""
        if not isinstance(self.conversation, tuple):
            raise TypeError("provider request conversation must be a tuple")
        if not self.conversation:
            raise ValueError("provider request conversation must not be empty")
        if not all(isinstance(message, ProviderMessage) for message in self.conversation):
            raise TypeError("provider request conversation contains an unsupported value")
        if not isinstance(self.repository_instructions, tuple):
            raise TypeError("provider request repository instructions must be a tuple")
        if not all(
            isinstance(instruction, RepositoryInstruction)
            for instruction in self.repository_instructions
        ):
            raise TypeError("provider request repository instructions contain an unsupported value")


@dataclass(frozen=True, slots=True)
class ProviderTextDelta:
    """One non-empty fragment of assistant text."""

    kind: ClassVar[Literal["text.delta"]] = "text.delta"
    text: str

    def __post_init__(self) -> None:
        """Reject empty deltas so stream progress is always observable."""
        _require_non_empty_string(self.text, "provider text delta")


@dataclass(frozen=True, slots=True)
class ProviderTextCompleted:
    """The provider's complete assistant text observation.

    Empty text is legal for a tool-call-only response. The session may retain that candidate long
    enough to classify the next observation; usage and successful completion still require accepted
    non-empty deltas.
    """

    kind: ClassVar[Literal["text.completed"]] = "text.completed"
    text: str

    def __post_init__(self) -> None:
        """Require text without imposing a later output-budget policy."""
        _require_string(self.text, "provider completed text")


@dataclass(frozen=True, slots=True)
class ProviderToolCallRequested:
    """One provider-requested tool call with deliberately unparsed arguments.

    ``arguments_json`` may be malformed. Parsing, tool lookup, validation, policy, and execution
    remain harness-loop responsibilities rather than provider-boundary behavior.
    """

    kind: ClassVar[Literal["tool.call_requested"]] = "tool.call_requested"
    call_id: str
    name: str
    arguments_json: str

    def __post_init__(self) -> None:
        """Validate safe identifiers while preserving serialized arguments byte-for-byte."""
        _require_non_empty_string(
            self.call_id,
            "provider tool call ID",
            maximum_chars=MAX_PROVIDER_LABEL_CHARS,
            reject_controls=True,
        )
        _require_non_empty_string(
            self.name,
            "provider tool name",
            maximum_chars=MAX_PROVIDER_LABEL_CHARS,
            reject_controls=True,
        )
        _require_string(self.arguments_json, "provider tool arguments")


@dataclass(frozen=True, slots=True)
class ProviderUsageReported:
    """Non-authoritative token counts reported by a provider operation."""

    kind: ClassVar[Literal["usage.reported"]] = "usage.reported"
    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        """Require non-negative integers and reject booleans masquerading as counts."""
        for field_name, value in (
            ("provider input token count", self.input_tokens),
            ("provider output token count", self.output_tokens),
        ):
            if type(value) is not int:
                raise TypeError(f"{field_name} must be an integer")
            if value < 0 or value > MAX_MODEL_USAGE_TOKENS:
                raise ValueError(f"{field_name} must be between 0 and {MAX_MODEL_USAGE_TOKENS}")


@dataclass(frozen=True, slots=True)
class ProviderCompleted:
    """Signal that one provider operation ended normally."""

    kind: ClassVar[Literal["response.completed"]] = "response.completed"


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """Bounded provider failure safe to cross into harness-owned state.

    The shape intentionally has no raw exception, response body, headers, request, environment, or
    credential field. Provider adapters must normalize those values before constructing this type.

    Args:
        code: Stable harness-owned failure category.
        message: Safe single-line explanation bounded to 1,024 characters.
        retryable: Provider-boundary observation, not permission for the loop to retry.
    """

    code: ProviderFailureCode
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        """Validate the normalized safe envelope."""
        if self.code not in {
            "authentication_failed",
            "rate_limited",
            "request_rejected",
            "unavailable",
            "invalid_response",
            "unknown",
        }:
            raise ValueError("provider failure code is unsupported")
        _require_non_empty_string(
            self.message,
            "provider failure message",
            maximum_chars=MAX_PROVIDER_FAILURE_MESSAGE_CHARS,
            reject_controls=True,
        )
        if type(self.retryable) is not bool:
            raise TypeError("provider failure retryable flag must be a boolean")


@dataclass(frozen=True, slots=True)
class ProviderFailed:
    """Signal that one provider operation ended with a normalized failure."""

    kind: ClassVar[Literal["response.failed"]] = "response.failed"
    failure: ProviderFailure

    def __post_init__(self) -> None:
        """Reject raw or otherwise unsupported failure values."""
        if not isinstance(self.failure, ProviderFailure):
            raise TypeError("provider failed event requires a normalized provider failure")


type ProviderStreamEvent = (
    ProviderTextDelta
    | ProviderTextCompleted
    | ProviderToolCallRequested
    | ProviderUsageReported
    | ProviderCompleted
    | ProviderFailed
)
"""One provider-neutral observation emitted while a model turn is active."""

PROVIDER_STREAM_EVENT_TYPES = (
    ProviderTextDelta,
    ProviderTextCompleted,
    ProviderToolCallRequested,
    ProviderUsageReported,
    ProviderCompleted,
    ProviderFailed,
)
"""Runtime event classes accepted by strict fake scripts."""


__all__ = [
    "MAX_MODEL_USAGE_TOKENS",
    "MAX_PROVIDER_FAILURE_MESSAGE_CHARS",
    "PROVIDER_STREAM_EVENT_TYPES",
    "ProviderCompleted",
    "ProviderFailed",
    "ProviderFailure",
    "ProviderFailureCode",
    "ProviderMessage",
    "ProviderMessageRole",
    "ProviderRequest",
    "ProviderStreamEvent",
    "ProviderTextCompleted",
    "ProviderTextDelta",
    "ProviderToolCallRequested",
    "ProviderUsageReported",
    "RepositoryInstruction",
]
