"""Safe parsing, validation, and serialization for protocol version 1 lines."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError, model_validator

from .models import (
    MAX_PROTOCOL_LINE_BYTES,
    PROTOCOL_VERSION,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    Command,
    CommandId,
    Event,
    NonEmptyString,
    RuntimeErrorEvent,
    RuntimeInitializeCommand,
    RuntimeReadyEvent,
    RuntimeShutdownCommand,
    Sequence,
    SessionCancelCommand,
    SessionCancelledEvent,
    SessionCompletedEvent,
    SessionFailedEvent,
    SessionId,
    SessionStartCommand,
    SessionStartedEvent,
    Timestamp,
)


class ProtocolParseErrorCode(StrEnum):
    """Stable failure classes returned by untrusted protocol line parsers."""

    MALFORMED_JSON = "malformed_json"
    MALFORMED_ENVELOPE = "malformed_envelope"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNKNOWN_TYPE = "unknown_type"
    INVALID_PAYLOAD = "invalid_payload"
    INVALID_FRAMING = "invalid_framing"
    INVALID_UTF8 = "invalid_utf8"
    LINE_TOO_LONG = "line_too_long"


_FAILURE_MESSAGES = {
    ProtocolParseErrorCode.MALFORMED_JSON: "Protocol line is not valid JSON.",
    ProtocolParseErrorCode.MALFORMED_ENVELOPE: "Protocol message envelope is invalid.",
    ProtocolParseErrorCode.UNSUPPORTED_VERSION: "Protocol version is not supported.",
    ProtocolParseErrorCode.UNKNOWN_TYPE: "Protocol message type is not supported.",
    ProtocolParseErrorCode.INVALID_PAYLOAD: "Protocol message payload is invalid.",
    ProtocolParseErrorCode.INVALID_FRAMING: (
        "Protocol input must be one complete JSON object terminated by LF."
    ),
    ProtocolParseErrorCode.INVALID_UTF8: "Protocol line is not valid UTF-8.",
    ProtocolParseErrorCode.LINE_TOO_LONG: "Protocol line exceeds the byte limit.",
}


class ProtocolEncodingError(ValueError):
    """Report that a locally constructed message cannot fit the wire contract.

    The exception contains only a stable classification and input-independent message so callers
    cannot accidentally expose payload contents while handling an outbound failure.
    """

    def __init__(self, code: ProtocolParseErrorCode) -> None:
        """Create a safe outbound encoding failure for one stable protocol category."""
        super().__init__(_FAILURE_MESSAGES[code])
        self.code = code


@dataclass(frozen=True, slots=True)
class ProtocolParseFailure:
    """A bounded parse result that never contains raw input or validator details.

    Attributes:
        code: Stable machine-readable failure category.
        message: Input-independent explanation safe for a structured runtime error.
    """

    code: ProtocolParseErrorCode
    message: str


class _EnvelopeModel(BaseModel):
    """Apply strict envelope validation before dispatching to a message payload model."""

    # The probe establishes only fields needed for safe dispatch. The selected strict wire model
    # remains authoritative for unrelated fields and classifies those as invalid message data.
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)


class _CommandEnvelope(_EnvelopeModel):
    """Fields that must be trustworthy before a command discriminator is dispatched."""

    protocol_version: int
    type: NonEmptyString
    command_id: CommandId
    timestamp: Timestamp
    payload: Any


class _EventEnvelope(_EnvelopeModel):
    """Fields that may occur before an event discriminator selects runtime or session scope."""

    protocol_version: int
    type: NonEmptyString
    timestamp: Timestamp
    correlation_id: CommandId | None = None
    session_id: SessionId | None = None
    sequence: Sequence | None = None
    payload: Any

    @model_validator(mode="before")
    @classmethod
    def _reject_explicit_null_optionals(cls, value: object) -> object:
        """Require absent optional fields so null cannot become an alternate wire spelling."""
        if isinstance(value, Mapping):
            for field_name in ("correlation_id", "session_id", "sequence"):
                if field_name in value and value[field_name] is None:
                    raise ValueError(f"{field_name} must be omitted when unavailable")
        return value


_COMMAND_ENVELOPE_ADAPTER = TypeAdapter(_CommandEnvelope)
_EVENT_ENVELOPE_ADAPTER = TypeAdapter(_EventEnvelope)
_COMMAND_ADAPTER = TypeAdapter(Command)
_EVENT_ADAPTER = TypeAdapter(Event)

_COMMAND_MODELS: dict[str, type[BaseModel]] = {
    "runtime.initialize": RuntimeInitializeCommand,
    "session.start": SessionStartCommand,
    "session.cancel": SessionCancelCommand,
    "runtime.shutdown": RuntimeShutdownCommand,
}

_EVENT_MODELS: dict[str, type[BaseModel]] = {
    "runtime.ready": RuntimeReadyEvent,
    "runtime.error": RuntimeErrorEvent,
    "session.started": SessionStartedEvent,
    "assistant.delta": AssistantDeltaEvent,
    "assistant.completed": AssistantCompletedEvent,
    "session.completed": SessionCompletedEvent,
    "session.cancelled": SessionCancelledEvent,
    "session.failed": SessionFailedEvent,
}


def parse_command_line(line: bytes) -> Command | ProtocolParseFailure:
    """Parse one untrusted command line without its terminating LF.

    Args:
        line: One physical line of bytes, excluding its LF delimiter.

    Returns:
        A validated command or a safe failure classification. The result never includes raw input.
    """
    document = _decode_json_object(line)
    if isinstance(document, ProtocolParseFailure):
        return document
    version_failure = _validate_supported_version(document)
    if version_failure is not None:
        return version_failure

    try:
        envelope = _COMMAND_ENVELOPE_ADAPTER.validate_python(document, strict=True)
    except ValidationError:
        return _failure(ProtocolParseErrorCode.MALFORMED_ENVELOPE)

    model = _COMMAND_MODELS.get(envelope.type)
    if model is None:
        return _failure(ProtocolParseErrorCode.UNKNOWN_TYPE)
    try:
        return cast(Command, model.model_validate(document))
    except ValidationError as error:
        return _known_message_failure(error)


def parse_event_line(line: bytes) -> Event | ProtocolParseFailure:
    """Parse one untrusted event line without its terminating LF.

    Args:
        line: One physical line of bytes, excluding its LF delimiter.

    Returns:
        A validated event or a safe failure classification. Unknown event types remain distinct
        from malformed known events and never become trusted event state.
    """
    document = _decode_json_object(line)
    if isinstance(document, ProtocolParseFailure):
        return document
    version_failure = _validate_supported_version(document)
    if version_failure is not None:
        return version_failure

    try:
        envelope = _EVENT_ENVELOPE_ADAPTER.validate_python(document, strict=True)
    except ValidationError:
        return _failure(ProtocolParseErrorCode.MALFORMED_ENVELOPE)

    model = _EVENT_MODELS.get(envelope.type)
    if model is None:
        return _failure(ProtocolParseErrorCode.UNKNOWN_TYPE)
    try:
        return cast(Event, model.model_validate(document))
    except ValidationError as error:
        return _known_message_failure(error)


def validate_command(value: object) -> Command:
    """Validate a local value before it is allowed onto protocol stdin.

    Args:
        value: Candidate command model or Python mapping.

    Returns:
        The strict protocol version 1 command model selected by ``type``.

    Raises:
        ValidationError: If the local value does not satisfy the complete wire contract.
    """
    return _COMMAND_ADAPTER.validate_python(value, strict=True)


def validate_event(value: object) -> Event:
    """Validate a local value before it is allowed onto protocol stdout.

    Args:
        value: Candidate event model or Python mapping.

    Returns:
        The strict protocol version 1 event model selected by ``type``.

    Raises:
        ValidationError: If the local value does not satisfy the complete wire contract.
    """
    return _EVENT_ADAPTER.validate_python(value, strict=True)


def encode_command(value: object) -> bytes:
    """Validate and serialize one command as compact UTF-8 NDJSON.

    Args:
        value: Candidate local command model or mapping.

    Returns:
        Exactly one validated JSON object encoded as UTF-8 and followed by one LF.

    Raises:
        ValidationError: If the candidate is not an exact protocol version 1 command.
        ValueError: If JSON serialization encounters a nonstandard numeric value.
    """
    return _encode_message(validate_command(value))


def encode_event(value: object) -> bytes:
    """Validate and serialize one event as compact UTF-8 NDJSON.

    Args:
        value: Candidate local event model or mapping.

    Returns:
        Exactly one validated JSON object encoded as UTF-8 and followed by one LF.

    Raises:
        ValidationError: If the candidate is not an exact protocol version 1 event.
        ValueError: If JSON serialization encounters a nonstandard numeric value.
    """
    return _encode_message(validate_event(value))


def utc_timestamp(instant: datetime | None = None) -> str:
    """Return the canonical millisecond UTC timestamp used by protocol writers.

    Args:
        instant: Optional timezone-aware instant. Current UTC time is used when omitted.

    Returns:
        A timestamp with exactly three fractional digits and a literal ``Z`` suffix.

    Raises:
        ValueError: If ``instant`` is naive and therefore cannot be converted unambiguously.
    """
    selected = datetime.now(UTC) if instant is None else instant
    if selected.tzinfo is None or selected.utcoffset() is None:
        raise ValueError("protocol timestamps require a timezone-aware datetime")
    return selected.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _decode_json_object(line: bytes) -> dict[str, Any] | ProtocolParseFailure:
    if len(line) == 0 or b"\r" in line or b"\n" in line:
        return _failure(ProtocolParseErrorCode.INVALID_FRAMING)
    try:
        text = line.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _failure(ProtocolParseErrorCode.INVALID_UTF8)

    try:
        value = json.loads(
            text,
            parse_int=_parse_finite_json_number,
            parse_float=_parse_finite_json_number,
            parse_constant=_reject_nonstandard_number,
        )
    except (json.JSONDecodeError, RecursionError, ValueError):
        return _failure(ProtocolParseErrorCode.MALFORMED_JSON)
    if not isinstance(value, dict):
        return _failure(ProtocolParseErrorCode.MALFORMED_ENVELOPE)
    return cast(dict[str, Any], value)


def _reject_nonstandard_number(_value: str) -> None:
    raise ValueError("non-standard JSON number")


def _parse_finite_json_number(value: str) -> int | float:
    """Match JSON.parse number semantics while preserving integral values for strict models."""
    parsed = float(value)
    if not isfinite(parsed):
        raise ValueError("JSON number exceeds the finite wire range")
    return int(parsed) if parsed.is_integer() else parsed


def _validate_supported_version(document: Mapping[str, object]) -> ProtocolParseFailure | None:
    version = document.get("protocol_version")
    if type(version) is not int:
        return _failure(ProtocolParseErrorCode.MALFORMED_ENVELOPE)
    if version != PROTOCOL_VERSION:
        return _failure(ProtocolParseErrorCode.UNSUPPORTED_VERSION)
    return None


def _known_message_failure(error: ValidationError) -> ProtocolParseFailure:
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    invalid_message_data = bool(errors) and all(
        (validation_error["loc"] and validation_error["loc"][0] == "payload")
        or validation_error["type"] == "extra_forbidden"
        for validation_error in errors
    )
    code = (
        ProtocolParseErrorCode.INVALID_PAYLOAD
        if invalid_message_data
        else ProtocolParseErrorCode.MALFORMED_ENVELOPE
    )
    return _failure(code)


def _encode_message(value: BaseModel) -> bytes:
    document = value.model_dump(mode="json", exclude_none=True)
    text = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_PROTOCOL_LINE_BYTES:
        raise ProtocolEncodingError(ProtocolParseErrorCode.LINE_TOO_LONG)
    return encoded + b"\n"


def _failure(code: ProtocolParseErrorCode) -> ProtocolParseFailure:
    return ProtocolParseFailure(code=code, message=_FAILURE_MESSAGES[code])
