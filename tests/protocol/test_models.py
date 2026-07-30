from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from code_assist_harness.protocol import (
    MAX_SAFE_SEQUENCE,
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    RuntimeErrorEvent,
    RuntimeInitializeCommand,
    RuntimeReadyEvent,
    RuntimeShutdownCommand,
    SessionCancelCommand,
    SessionCancelledEvent,
    SessionCompletedEvent,
    SessionFailedEvent,
    SessionStartCommand,
    SessionStartedEvent,
    validate_command,
    validate_event,
)

TIMESTAMP = "2026-07-16T12:34:56.789Z"


def _command(message_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "command_id": "cmd_test-1",
        "timestamp": TIMESTAMP,
        "payload": payload,
    }


def _runtime_event(message_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "timestamp": TIMESTAMP,
        "correlation_id": "cmd_test-1",
        "payload": payload,
    }


def _session_event(message_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "session_id": "ses_test-1",
        "sequence": 1,
        "timestamp": TIMESTAMP,
        "correlation_id": "cmd_test-1",
        "payload": payload,
    }


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (
            _command("runtime.initialize", {"workspace": "/tmp/workspace"}),
            RuntimeInitializeCommand,
        ),
        (_command("session.start", {"task": "Explain the protocol"}), SessionStartCommand),
        (_command("session.cancel", {"session_id": "ses_test-1"}), SessionCancelCommand),
        (_command("runtime.shutdown", {}), RuntimeShutdownCommand),
    ],
)
def test_all_command_variants_validate(
    value: dict[str, object], expected_type: type[object]
) -> None:
    assert isinstance(validate_command(value), expected_type)


@pytest.mark.parametrize(
    ("value", "expected_type"),
    [
        (_runtime_event("runtime.ready", {"workspace": "/tmp/workspace"}), RuntimeReadyEvent),
        (
            _runtime_event(
                "runtime.error",
                {
                    "code": "invalid_command",
                    "message": "Command was rejected.",
                    "recoverable": True,
                },
            ),
            RuntimeErrorEvent,
        ),
        (_session_event("session.started", {}), SessionStartedEvent),
        (_session_event("assistant.delta", {"text": "A"}), AssistantDeltaEvent),
        (_session_event("assistant.completed", {"text": "Answer"}), AssistantCompletedEvent),
        (_session_event("session.completed", {}), SessionCompletedEvent),
        (_session_event("session.cancelled", {}), SessionCancelledEvent),
        (
            _session_event("session.failed", {"code": "provider_failed", "message": "Try again."}),
            SessionFailedEvent,
        ),
    ],
)
def test_all_event_variants_validate(value: dict[str, object], expected_type: type[object]) -> None:
    assert isinstance(validate_event(value), expected_type)


@pytest.mark.parametrize(
    "timestamp",
    [
        "0001-01-01T00:00:00.000Z",
        "9999-12-31T23:59:59.999Z",
    ],
)
def test_timestamp_accepts_the_documented_year_range(timestamp: str) -> None:
    value = _command("runtime.shutdown", {})
    value["timestamp"] = timestamp

    assert validate_command(value).timestamp == timestamp


@pytest.mark.parametrize(
    "timestamp",
    [
        "0000-01-01T00:00:00.000Z",
        "2026-02-30T00:00:00.000Z",
        "2026-07-16T12:34:56Z",
        "2026-07-16T12:34:56.7890Z",
        "2026-07-16T12:34:56.789+00:00",
        "2026-07-16 12:34:56.789Z",
    ],
)
def test_timestamp_rejects_noncanonical_or_impossible_values(timestamp: str) -> None:
    value = _command("runtime.shutdown", {})
    value["timestamp"] = timestamp

    with pytest.raises(ValidationError):
        validate_command(value)


@pytest.mark.parametrize("sequence", [0, -1, MAX_SAFE_SEQUENCE + 1, True, 1.0])
def test_session_sequence_is_positive_strict_and_javascript_safe(sequence: object) -> None:
    value = _session_event("session.started", {})
    value["sequence"] = sequence

    with pytest.raises(ValidationError):
        validate_event(value)


def test_session_sequence_accepts_the_largest_javascript_safe_integer() -> None:
    value = _session_event("session.started", {})
    value["sequence"] = MAX_SAFE_SEQUENCE

    assert validate_event(value).sequence == MAX_SAFE_SEQUENCE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command_id", "cmd_"),
        ("command_id", f"cmd_{'a' * 65}"),
        ("command_id", "command_1"),
        ("command_id", "cmd_not.allowed"),
    ],
)
def test_command_id_uses_the_bounded_wire_syntax(field: str, value: str) -> None:
    command = _command("runtime.shutdown", {})
    command[field] = value

    with pytest.raises(ValidationError):
        validate_command(command)


@pytest.mark.parametrize("session_id", ["ses_", f"ses_{'a' * 65}", "session_1", "ses_no.dot"])
def test_session_id_uses_the_bounded_wire_syntax(session_id: str) -> None:
    event = _session_event("session.started", {})
    event["session_id"] = session_id

    with pytest.raises(ValidationError):
        validate_event(event)


def test_identifiers_accept_exactly_sixty_four_suffix_characters() -> None:
    command = _command("session.cancel", {"session_id": f"ses_{'s' * 64}"})
    command["command_id"] = f"cmd_{'c' * 64}"

    validated = validate_command(command)

    assert validated.command_id == f"cmd_{'c' * 64}"
    assert validated.payload.session_id == f"ses_{'s' * 64}"


@pytest.mark.parametrize(
    "value",
    [
        _command("runtime.initialize", {"workspace": ""}),
        _command("session.start", {"task": ""}),
        _session_event("assistant.delta", {"text": ""}),
        _session_event("session.failed", {"code": "", "message": "Failure"}),
        _runtime_event(
            "runtime.error",
            {"code": "invalid_command", "message": "", "recoverable": True},
        ),
    ],
)
def test_semantic_string_fields_reject_empty_values(value: dict[str, object]) -> None:
    validator = validate_command if "command_id" in value else validate_event
    with pytest.raises(ValidationError):
        validator(value)


def test_wire_models_forbid_extra_envelope_and_payload_fields() -> None:
    envelope_extra = _command("runtime.shutdown", {})
    envelope_extra["unexpected"] = True
    payload_extra = _command("runtime.shutdown", {"unexpected": True})

    with pytest.raises(ValidationError):
        validate_command(envelope_extra)
    with pytest.raises(ValidationError):
        validate_command(payload_extra)


def test_strict_models_reject_coercion_and_explicit_null_correlation() -> None:
    command = _command("runtime.shutdown", {})
    boolean_version_command = {**command, "protocol_version": True}
    float_version_command = {**command, "protocol_version": 1.0}
    runtime_error = _runtime_event(
        "runtime.error",
        {"code": "failure", "message": "Failure", "recoverable": "true"},
    )
    runtime_ready = _runtime_event("runtime.ready", {"workspace": "/tmp/workspace"})
    runtime_ready["correlation_id"] = None

    with pytest.raises(ValidationError):
        validate_command(boolean_version_command)
    with pytest.raises(ValidationError):
        validate_command(float_version_command)
    with pytest.raises(ValidationError):
        validate_event(runtime_error)
    with pytest.raises(ValidationError):
        validate_event(runtime_ready)


def test_validation_does_not_mutate_caller_owned_nested_data() -> None:
    value = _command("session.start", {"task": "Keep the source unchanged"})
    original = deepcopy(value)

    validate_command(value)

    assert value == original
