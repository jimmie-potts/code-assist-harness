from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from code_assist_harness.protocol import (
    MAX_PROTOCOL_LINE_BYTES,
    AssistantDeltaEvent,
    ProtocolEncodingError,
    ProtocolParseErrorCode,
    ProtocolParseFailure,
    RuntimeInitializeCommand,
    encode_command,
    encode_event,
    parse_command_line,
    parse_event_line,
    utc_timestamp,
)

TIMESTAMP = "2026-07-16T12:34:56.789Z"


def _json_line(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _command(
    message_type: str = "runtime.initialize",
    payload: object = None,
) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "command_id": "cmd_codec-1",
        "timestamp": TIMESTAMP,
        "payload": {"workspace": "/tmp/workspace"} if payload is None else payload,
    }


def _runtime_event(message_type: str, payload: object) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "timestamp": TIMESTAMP,
        "payload": payload,
    }


def _session_event(message_type: str, payload: object) -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": message_type,
        "session_id": "ses_codec-1",
        "sequence": 1,
        "timestamp": TIMESTAMP,
        "correlation_id": "cmd_codec-1",
        "payload": payload,
    }


def _assert_failure(
    result: object,
    code: ProtocolParseErrorCode,
) -> ProtocolParseFailure:
    assert isinstance(result, ProtocolParseFailure)
    assert result.code is code
    return result


def test_command_codec_round_trips_compact_utf8_with_one_lf() -> None:
    value = _command("session.start", {"task": "Explain café ☕"})

    encoded = encode_command(value)
    parsed = parse_command_line(encoded[:-1])

    assert isinstance(parsed, RuntimeInitializeCommand) is False
    assert parsed.type == "session.start"
    assert parsed.payload.task == "Explain café ☕"
    assert encoded.endswith(b"\n")
    assert encoded.count(b"\n") == 1
    assert b": " not in encoded
    assert "café ☕".encode() in encoded


def test_event_codec_escapes_embedded_newlines_without_breaking_framing() -> None:
    value = _session_event("assistant.delta", {"text": "first\nsecond"})

    encoded = encode_event(value)
    parsed = parse_event_line(encoded[:-1])

    assert isinstance(parsed, AssistantDeltaEvent)
    assert parsed.payload.text == "first\nsecond"
    assert encoded.count(b"\n") == 1
    assert b"first\\nsecond" in encoded


def test_json_integral_number_lexemes_match_javascript_number_semantics() -> None:
    command_line = _json_line(_command()).replace(
        b'"protocol_version":1', b'"protocol_version":1.0'
    )
    event_line = _json_line(_session_event("session.started", {})).replace(
        b'"sequence":1',
        b'"sequence":1e0',
    )

    command = parse_command_line(command_line)
    event = parse_event_line(event_line)

    assert isinstance(command, RuntimeInitializeCommand)
    assert command.protocol_version == 1
    assert event.type == "session.started"
    assert event.sequence == 1


def test_json_number_overflow_is_rejected_at_the_byte_boundary() -> None:
    line = b'{"protocol_version":1e9999}'

    _assert_failure(parse_command_line(line), ProtocolParseErrorCode.MALFORMED_JSON)


@pytest.mark.parametrize(
    ("line", "expected_code"),
    [
        (b"", ProtocolParseErrorCode.INVALID_FRAMING),
        (b"{}\r", ProtocolParseErrorCode.INVALID_FRAMING),
        (b'{"protocol_version":1}\n{}', ProtocolParseErrorCode.INVALID_FRAMING),
        (b"\xff", ProtocolParseErrorCode.INVALID_UTF8),
        (b"{", ProtocolParseErrorCode.MALFORMED_JSON),
        (b"[]", ProtocolParseErrorCode.MALFORMED_ENVELOPE),
        (b'{"protocol_version":true}', ProtocolParseErrorCode.MALFORMED_ENVELOPE),
        (b'{"protocol_version":2}', ProtocolParseErrorCode.UNSUPPORTED_VERSION),
    ],
)
def test_parser_classifies_framing_json_envelope_and_version_failures(
    line: bytes,
    expected_code: ProtocolParseErrorCode,
) -> None:
    _assert_failure(parse_command_line(line), expected_code)


def test_unsupported_version_is_identified_before_version_specific_fields() -> None:
    result = parse_command_line(b'{"protocol_version":999,"future":"shape"}')

    _assert_failure(result, ProtocolParseErrorCode.UNSUPPORTED_VERSION)


def test_unknown_type_is_distinct_from_an_invalid_known_payload() -> None:
    unknown = _command("future.command", {"opaque": True})
    invalid_known = _command("runtime.initialize", {"workspace": 7})

    _assert_failure(parse_command_line(_json_line(unknown)), ProtocolParseErrorCode.UNKNOWN_TYPE)
    _assert_failure(
        parse_command_line(_json_line(invalid_known)),
        ProtocolParseErrorCode.INVALID_PAYLOAD,
    )


def test_missing_known_envelope_field_is_not_misreported_as_payload_failure() -> None:
    value = _command()
    del value["command_id"]

    _assert_failure(
        parse_command_line(_json_line(value)),
        ProtocolParseErrorCode.MALFORMED_ENVELOPE,
    )


@pytest.mark.parametrize(
    "value",
    [
        {**_command(), "unexpected": True},
        _command(payload={"workspace": "/tmp/workspace", "unexpected": True}),
    ],
)
def test_extra_fields_are_rejected_by_the_selected_strict_model(
    value: dict[str, object],
) -> None:
    _assert_failure(
        parse_command_line(_json_line(value)),
        ProtocolParseErrorCode.INVALID_PAYLOAD,
    )


def test_nonstandard_json_numbers_are_rejected_before_schema_validation() -> None:
    line = (
        b'{"protocol_version":1,"type":"runtime.initialize","command_id":"cmd_codec-1",'
        b'"timestamp":"2026-07-16T12:34:56.789Z","payload":{"workspace":NaN}}'
    )

    _assert_failure(parse_command_line(line), ProtocolParseErrorCode.MALFORMED_JSON)


def test_unknown_event_remains_distinct_from_a_malformed_known_event() -> None:
    unknown = _runtime_event("future.event", {})
    malformed_known = _session_event("assistant.delta", {"text": "delta"})
    del malformed_known["sequence"]

    _assert_failure(parse_event_line(_json_line(unknown)), ProtocolParseErrorCode.UNKNOWN_TYPE)
    _assert_failure(
        parse_event_line(_json_line(malformed_known)),
        ProtocolParseErrorCode.MALFORMED_ENVELOPE,
    )


def test_failures_never_echo_raw_input_or_validator_details() -> None:
    secret = "sk-super-secret-value"
    value = _command(payload={"workspace": secret, "unexpected": secret})

    failure = _assert_failure(
        parse_command_line(_json_line(value)),
        ProtocolParseErrorCode.INVALID_PAYLOAD,
    )

    assert secret not in failure.message
    assert "workspace" not in failure.message
    assert "unexpected" not in failure.message


def test_encode_rejects_invalid_or_non_json_event_data_before_writing() -> None:
    value = _runtime_event("runtime.ready", {"workspace": float("nan")})

    with pytest.raises(ValidationError):
        encode_event(value)


def test_command_encoder_rejects_a_valid_object_that_exceeds_the_wire_line_limit() -> None:
    value = _command("session.start", {"task": "x" * MAX_PROTOCOL_LINE_BYTES})

    with pytest.raises(ProtocolEncodingError) as raised:
        encode_command(value)

    assert raised.value.code is ProtocolParseErrorCode.LINE_TOO_LONG
    assert "x" * 100 not in str(raised.value)


def test_failure_messages_reject_terminal_controls_before_entering_trusted_state() -> None:
    value = _runtime_event(
        "runtime.error",
        {"code": "unsafe_error", "message": "unsafe\x1b[31m", "recoverable": False},
    )

    _assert_failure(parse_event_line(_json_line(value)), ProtocolParseErrorCode.INVALID_PAYLOAD)


def test_utc_timestamp_normalizes_an_aware_instant_to_millisecond_z() -> None:
    eastern = timezone(timedelta(hours=-4))
    instant = datetime(2026, 7, 16, 8, 34, 56, 789_999, tzinfo=eastern)

    assert utc_timestamp(instant) == TIMESTAMP


def test_utc_timestamp_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_timestamp(datetime(2026, 7, 16, 12, 34, 56))
