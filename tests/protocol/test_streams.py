from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from code_assist_harness.protocol import (
    MAX_PROTOCOL_LINE_BYTES,
    AssistantDeltaEvent,
    CommandLineReader,
    EventLineReader,
    OrderedEventWriter,
    ProtocolEncodingError,
    ProtocolParseErrorCode,
    ProtocolParseFailure,
    RuntimeReadyEvent,
    SessionStartedEvent,
    encode_command,
    encode_event,
    parse_event_line,
)

TIMESTAMP = "2026-07-16T12:34:56.789Z"


def _start_command(task: str = "Explain café ☕") -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": "session.start",
        "command_id": "cmd_stream-1",
        "timestamp": TIMESTAMP,
        "payload": {"task": task},
    }


def _ready_event() -> dict[str, object]:
    return {
        "protocol_version": 1,
        "type": "runtime.ready",
        "timestamp": TIMESTAMP,
        "correlation_id": "cmd_stream-1",
        "payload": {"workspace": "/tmp/workspace"},
    }


def _assert_failure(result: object, code: ProtocolParseErrorCode) -> None:
    assert isinstance(result, ProtocolParseFailure)
    assert result.code is code


def test_command_reader_preserves_multibyte_utf8_across_arbitrary_chunks() -> None:
    encoded = encode_command(_start_command())
    reader = CommandLineReader()
    results: list[object] = []

    for byte in encoded:
        results.extend(reader.feed(bytes([byte])))

    assert len(results) == 1
    command = results[0]
    assert command.type == "session.start"
    assert command.payload.task == "Explain café ☕"
    assert reader.finish() == []


def test_reader_contains_a_bad_line_and_processes_the_next_valid_line() -> None:
    valid = encode_command(_start_command("Later valid task"))
    reader = CommandLineReader()

    results = reader.feed(b"{not-json}\n" + valid)

    assert len(results) == 2
    _assert_failure(results[0], ProtocolParseErrorCode.MALFORMED_JSON)
    assert results[1].payload.task == "Later valid task"


def test_reader_rejects_crlf_and_empty_physical_lines() -> None:
    encoded = encode_command(_start_command())
    reader = CommandLineReader()

    results = reader.feed(b"\n" + encoded[:-1] + b"\r\n")

    assert len(results) == 2
    _assert_failure(results[0], ProtocolParseErrorCode.INVALID_FRAMING)
    _assert_failure(results[1], ProtocolParseErrorCode.INVALID_FRAMING)


def test_reader_discards_one_oversized_line_then_recovers_at_lf() -> None:
    valid = encode_command(_start_command("Recovered"))
    max_line_bytes = len(valid) + 16
    reader = CommandLineReader(max_line_bytes=max_line_bytes)

    first_results = reader.feed(b"x" * (max_line_bytes + 1))
    second_results = reader.feed(b"still oversized\n" + valid)

    assert len(first_results) == 1
    _assert_failure(first_results[0], ProtocolParseErrorCode.LINE_TOO_LONG)
    assert len(second_results) == 1
    assert second_results[0].payload.task == "Recovered"


def test_reader_reports_unterminated_final_line_without_parsing_it() -> None:
    encoded = encode_command(_start_command())
    reader = CommandLineReader()

    assert reader.feed(encoded[:-1]) == []
    failures = reader.finish()

    assert len(failures) == 1
    _assert_failure(failures[0], ProtocolParseErrorCode.INVALID_FRAMING)


def test_reader_reports_invalid_utf8_and_rejects_bytes_after_finish() -> None:
    reader = CommandLineReader()

    results = reader.feed(b"\xff\n")
    reader.finish()

    assert len(results) == 1
    _assert_failure(results[0], ProtocolParseErrorCode.INVALID_UTF8)
    with pytest.raises(RuntimeError, match="finished"):
        reader.feed(b"{}\n")


def test_event_reader_distinguishes_unknown_event_and_continues() -> None:
    unknown = (
        b'{"protocol_version":1,"type":"future.event",'
        b'"timestamp":"2026-07-16T12:34:56.789Z","payload":{}}\n'
    )
    reader = EventLineReader()

    results = reader.feed(unknown + encode_event(_ready_event()))

    assert len(results) == 2
    _assert_failure(results[0], ProtocolParseErrorCode.UNKNOWN_TYPE)
    assert isinstance(results[1], RuntimeReadyEvent)


def test_writer_serializes_runtime_event_as_one_valid_compact_line() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []

        async def sink(line: bytes) -> None:
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)

        event = await writer.emit_runtime(
            "runtime.ready",
            {"workspace": "/tmp/workspace"},
            correlation_id="cmd_stream-1",
        )

        assert isinstance(event, RuntimeReadyEvent)
        assert writes == [encode_event(_ready_event())]
        assert writes[0].count(b"\n") == 1
        assert b": " not in writes[0]

    asyncio.run(scenario())


def test_writer_assigns_monotonic_sequences_while_concurrent_producers_wait() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []

        async def sink(line: bytes) -> None:
            await asyncio.sleep(0)
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)
        events = await asyncio.gather(
            *(
                writer.emit_session(
                    "assistant.delta",
                    "ses_stream-1",
                    {"text": f"delta-{index}"},
                    correlation_id="cmd_stream-1",
                )
                for index in range(50)
            )
        )

        assert sorted(event.sequence for event in events) == list(range(1, 51))
        parsed = [parse_event_line(line[:-1]) for line in writes]
        assert all(isinstance(event, AssistantDeltaEvent) for event in parsed)
        assert [event.sequence for event in parsed] == list(range(1, 51))
        assert all(line.count(b"\n") == 1 for line in writes)

    asyncio.run(scenario())


def test_writer_tracks_each_session_sequence_independently() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []

        async def sink(line: bytes) -> None:
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)

        first_a = await writer.emit_session("session.started", "ses_a", {})
        first_b = await writer.emit_session("session.started", "ses_b", {})
        second_a = await writer.emit_session("session.completed", "ses_a", {})

        assert isinstance(first_a, SessionStartedEvent)
        assert isinstance(first_b, SessionStartedEvent)
        assert (first_a.sequence, first_b.sequence, second_a.sequence) == (1, 1, 2)

    asyncio.run(scenario())


def test_failed_sink_does_not_consume_a_session_sequence() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []
        attempts = 0

        async def sink(line: bytes) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OSError("sink unavailable")
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)

        with pytest.raises(OSError, match="sink unavailable"):
            await writer.emit_session("session.started", "ses_stream-1", {})
        event = await writer.emit_session("session.started", "ses_stream-1", {})

        assert event.sequence == 1
        assert len(writes) == 1

    asyncio.run(scenario())


def test_cancellation_waits_for_sink_and_commits_a_published_sequence() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []
        sink_started = asyncio.Event()
        release_sink = asyncio.Event()

        async def sink(line: bytes) -> None:
            sink_started.set()
            await release_sink.wait()
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)
        first = asyncio.create_task(writer.emit_session("session.started", "ses_stream-1", {}))
        await sink_started.wait()

        first.cancel()
        await asyncio.sleep(0)
        assert not first.done()
        release_sink.set()
        with pytest.raises(asyncio.CancelledError):
            await first

        second = await writer.emit_session("session.completed", "ses_stream-1", {})

        assert second.sequence == 2
        assert len(writes) == 2
        parsed_first = parse_event_line(writes[0][:-1])
        assert parsed_first.sequence == 1

    asyncio.run(scenario())


def test_invalid_or_non_json_payload_is_never_written_or_sequenced() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []

        async def sink(line: bytes) -> None:
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)

        with pytest.raises(ValidationError):
            await writer.emit_session(
                "assistant.delta",
                "ses_stream-1",
                {"text": float("nan")},
            )
        event = await writer.emit_session(
            "assistant.delta",
            "ses_stream-1",
            {"text": "valid"},
        )

        assert event.sequence == 1
        assert len(writes) == 1

    asyncio.run(scenario())


def test_oversized_event_is_never_written_or_sequenced() -> None:
    async def scenario() -> None:
        writes: list[bytes] = []

        async def sink(line: bytes) -> None:
            writes.append(line)

        writer = OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP)

        with pytest.raises(ProtocolEncodingError) as raised:
            await writer.emit_session(
                "assistant.delta",
                "ses_stream-1",
                {"text": "x" * MAX_PROTOCOL_LINE_BYTES},
            )
        event = await writer.emit_session(
            "assistant.delta",
            "ses_stream-1",
            {"text": "valid"},
        )

        assert raised.value.code is ProtocolParseErrorCode.LINE_TOO_LONG
        assert event.sequence == 1
        assert len(writes) == 1

    asyncio.run(scenario())
