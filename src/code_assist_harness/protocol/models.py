"""Strict protocol version 1 wire models shared by the Python boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

PROTOCOL_VERSION = 1
"""The only protocol version accepted by the initial process boundary."""

MAX_SAFE_SEQUENCE = 9_007_199_254_740_991
"""Largest sequence value TypeScript can represent without losing integer precision."""

MAX_PROTOCOL_LINE_BYTES = 64 * 1024
"""Largest encoded JSON object accepted on either protocol stream, excluding its LF."""

_TIMESTAMP_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}Z$"


def _validate_protocol_version_type(value: object) -> object:
    """Prevent JSON booleans from satisfying ``Literal[1]`` through integer equality."""
    if type(value) is not int:
        raise ValueError("protocol_version must be an integer")
    return value


def _validate_timestamp(value: str) -> str:
    """Reject syntactically plausible timestamps that are not real UTC instants."""
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError("timestamp must be a valid UTC instant") from error
    return value


def _validate_safe_message(value: str) -> str:
    """Reject terminal-control characters from user-visible protocol failures."""
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in value):
        raise ValueError("failure messages must not contain terminal controls")
    return value


NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
"""A semantic wire string that must contain at least one character."""

ErrorCode = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,63}$"),
]
"""A bounded machine-readable failure code safe for logs and terminal status text."""

SafeMessage = Annotated[
    str,
    StringConstraints(min_length=1, max_length=1024),
    AfterValidator(_validate_safe_message),
]
"""A bounded single-line failure message without C0 or C1 terminal controls."""

CommandId = Annotated[
    str,
    StringConstraints(pattern=r"^cmd_[A-Za-z0-9_-]{1,64}$"),
]
"""A command identifier whose bounded syntax is safe to use for correlation."""

SessionId = Annotated[
    str,
    StringConstraints(pattern=r"^ses_[A-Za-z0-9_-]{1,64}$"),
]
"""A session identifier whose bounded syntax is safe to use for event grouping."""

Timestamp = Annotated[
    str,
    StringConstraints(pattern=_TIMESTAMP_PATTERN),
    AfterValidator(_validate_timestamp),
]
"""An exact millisecond-precision RFC 3339 timestamp in UTC with a literal ``Z``."""

Sequence = Annotated[int, Field(gt=0, le=MAX_SAFE_SEQUENCE)]
"""A positive session-local sequence that round-trips safely through JavaScript."""

ProtocolVersion = Annotated[Literal[1], BeforeValidator(_validate_protocol_version_type)]
"""The exact integer protocol version, excluding JSON booleans that compare equal to one."""

type RuntimeEventType = Literal["runtime.ready", "runtime.error"]
"""Discriminators for protocol events that do not belong to one session."""

type SessionEventType = Literal[
    "session.started",
    "assistant.delta",
    "assistant.completed",
    "session.completed",
    "session.cancelled",
    "session.failed",
]
"""Discriminators for protocol events ordered within one session."""


class _WireModel(BaseModel):
    """Apply the strict, immutable, extra-forbid policy to every wire object."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RuntimeInitializePayload(_WireModel):
    """Wire payload selecting the runtime's already canonicalized workspace."""

    workspace: NonEmptyString


class SessionStartPayload(_WireModel):
    """Wire payload carrying the user task for a future session implementation."""

    task: NonEmptyString


class SessionCancelPayload(_WireModel):
    """Wire payload identifying the session whose cancellation is requested."""

    session_id: SessionId


class RuntimeShutdownPayload(_WireModel):
    """Empty wire payload requesting orderly runtime shutdown."""


class RuntimeReadyPayload(_WireModel):
    """Wire payload confirming the workspace accepted during initialization."""

    workspace: NonEmptyString


class EmptySessionPayload(_WireModel):
    """Empty wire payload used by lifecycle events that need no additional data."""


class AssistantTextPayload(_WireModel):
    """Wire payload containing one non-empty assistant text value."""

    text: NonEmptyString


class SessionFailedPayload(_WireModel):
    """Wire payload describing a safe, structured terminal session failure."""

    code: ErrorCode
    message: SafeMessage


class RuntimeErrorPayload(_WireModel):
    """Wire payload describing a safe runtime or protocol failure."""

    code: ErrorCode
    message: SafeMessage
    recoverable: bool


class _CommandBase(_WireModel):
    """Fields required on every TUI-to-Python protocol command."""

    protocol_version: ProtocolVersion
    type: str
    command_id: CommandId
    timestamp: Timestamp


class RuntimeInitializeCommand(_CommandBase):
    """Ask the runtime to accept the selected workspace and become ready."""

    type: Literal["runtime.initialize"]
    payload: RuntimeInitializePayload


class SessionStartCommand(_CommandBase):
    """Ask the runtime to start one task after initialization."""

    type: Literal["session.start"]
    payload: SessionStartPayload


class SessionCancelCommand(_CommandBase):
    """Ask the runtime to cancel the named active session."""

    type: Literal["session.cancel"]
    payload: SessionCancelPayload


class RuntimeShutdownCommand(_CommandBase):
    """Ask the runtime to flush protocol output and exit cleanly."""

    type: Literal["runtime.shutdown"]
    payload: RuntimeShutdownPayload


class _RuntimeEventBase(_WireModel):
    """Fields required on every Python-to-TUI runtime-level event."""

    protocol_version: ProtocolVersion
    type: str
    timestamp: Timestamp
    correlation_id: CommandId | None = None

    @field_validator("correlation_id", mode="before")
    @classmethod
    def _reject_explicit_null_correlation(cls, value: object) -> object:
        """Keep optional correlation absent rather than introducing a second null spelling."""
        if value is None:
            raise ValueError("correlation_id must be omitted when unavailable")
        return value


class RuntimeReadyEvent(_RuntimeEventBase):
    """Report that initialization succeeded and commands may now be accepted."""

    type: Literal["runtime.ready"]
    payload: RuntimeReadyPayload


class RuntimeErrorEvent(_RuntimeEventBase):
    """Report a structured problem that is not a normal session event."""

    type: Literal["runtime.error"]
    payload: RuntimeErrorPayload


class _SessionEventBase(_WireModel):
    """Fields required on every authoritative session event."""

    protocol_version: ProtocolVersion
    type: str
    session_id: SessionId
    sequence: Sequence
    timestamp: Timestamp
    correlation_id: CommandId | None = None

    @field_validator("correlation_id", mode="before")
    @classmethod
    def _reject_explicit_null_correlation(cls, value: object) -> object:
        """Keep optional correlation absent rather than introducing a second null spelling."""
        if value is None:
            raise ValueError("correlation_id must be omitted when unavailable")
        return value


class SessionStartedEvent(_SessionEventBase):
    """Report that Python accepted a task and established its session."""

    type: Literal["session.started"]
    payload: EmptySessionPayload


class AssistantDeltaEvent(_SessionEventBase):
    """Append one ordered fragment to the in-progress assistant response."""

    type: Literal["assistant.delta"]
    payload: AssistantTextPayload


class AssistantCompletedEvent(_SessionEventBase):
    """Publish the complete accumulated assistant response."""

    type: Literal["assistant.completed"]
    payload: AssistantTextPayload


class SessionCompletedEvent(_SessionEventBase):
    """End a session successfully."""

    type: Literal["session.completed"]
    payload: EmptySessionPayload


class SessionCancelledEvent(_SessionEventBase):
    """End a session because cancellation won its terminal race."""

    type: Literal["session.cancelled"]
    payload: EmptySessionPayload


class SessionFailedEvent(_SessionEventBase):
    """End a session with one safe structured failure."""

    type: Literal["session.failed"]
    payload: SessionFailedPayload


type Command = Annotated[
    RuntimeInitializeCommand | SessionStartCommand | SessionCancelCommand | RuntimeShutdownCommand,
    Field(discriminator="type"),
]
"""Validated union of all protocol version 1 command wire shapes."""

type RuntimeEvent = RuntimeReadyEvent | RuntimeErrorEvent
"""Validated union of runtime-level protocol version 1 event wire shapes."""

type SessionEvent = (
    SessionStartedEvent
    | AssistantDeltaEvent
    | AssistantCompletedEvent
    | SessionCompletedEvent
    | SessionCancelledEvent
    | SessionFailedEvent
)
"""Validated union of session-scoped protocol version 1 event wire shapes."""

type Event = Annotated[
    RuntimeReadyEvent
    | RuntimeErrorEvent
    | SessionStartedEvent
    | AssistantDeltaEvent
    | AssistantCompletedEvent
    | SessionCompletedEvent
    | SessionCancelledEvent
    | SessionFailedEvent,
    Field(discriminator="type"),
]
"""Validated union of all protocol version 1 event wire shapes."""
