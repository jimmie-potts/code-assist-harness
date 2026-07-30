"""Bounded protocol line readers and the ordered asynchronous event writer."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import cast

from .codec import (
    ProtocolParseErrorCode,
    ProtocolParseFailure,
    encode_event,
    parse_command_line,
    parse_event_line,
    utc_timestamp,
    validate_event,
)
from .models import (
    MAX_PROTOCOL_LINE_BYTES,
    MAX_SAFE_SEQUENCE,
    Command,
    CommandId,
    Event,
    RuntimeEvent,
    RuntimeEventType,
    SessionEvent,
    SessionEventType,
    SessionId,
)

DEFAULT_MAX_LINE_BYTES = MAX_PROTOCOL_LINE_BYTES
"""Maximum bytes retained for one protocol JSON object, excluding its LF delimiter."""

type _LineParser[MessageT] = Callable[[bytes], MessageT | ProtocolParseFailure]


class _BoundedLineReader[MessageT]:
    """Frame one byte stream into independently parsed, strictly LF-delimited messages."""

    def __init__(
        self,
        parser: _LineParser[MessageT],
        max_line_bytes: int,
    ) -> None:
        if max_line_bytes <= 0:
            raise ValueError("max_line_bytes must be positive")
        self._parser = parser
        self._max_line_bytes = max_line_bytes
        self._buffer = bytearray()
        self._discarding_oversized_line = False
        self._finished = False

    def feed(self, chunk: bytes) -> list[MessageT | ProtocolParseFailure]:
        """Consume an arbitrary byte chunk and return each complete line result in order.

        An oversized line produces one safe failure as soon as it crosses the limit. Its remaining
        bytes are discarded through the next LF so a later valid line can still be processed.

        Args:
            chunk: Next raw bytes from the process pipe. UTF-8 characters may span calls.

        Returns:
            Validated messages and safe failures for every completed or newly oversized line.

        Raises:
            RuntimeError: If bytes arrive after :meth:`finish` closed the reader.
        """
        if self._finished:
            raise RuntimeError("cannot feed a finished protocol line reader")

        results: list[MessageT | ProtocolParseFailure] = []
        offset = 0
        while offset < len(chunk):
            newline = chunk.find(b"\n", offset)
            segment_end = len(chunk) if newline < 0 else newline
            segment = chunk[offset:segment_end]

            if self._discarding_oversized_line:
                if newline < 0:
                    return results
                self._discarding_oversized_line = False
                offset = newline + 1
                continue

            if len(self._buffer) + len(segment) > self._max_line_bytes:
                self._buffer.clear()
                results.append(_line_failure(ProtocolParseErrorCode.LINE_TOO_LONG))
                if newline < 0:
                    self._discarding_oversized_line = True
                    return results
                offset = newline + 1
                continue

            self._buffer.extend(segment)
            if newline < 0:
                return results

            line = bytes(self._buffer)
            self._buffer.clear()
            results.append(self._parser(line))
            offset = newline + 1

        return results

    def finish(self) -> list[ProtocolParseFailure]:
        """Close the reader and report a final unterminated physical line.

        Returns:
            One ``invalid_framing`` failure when buffered bytes lack their required LF; otherwise an
            empty list. An already-reported oversized unterminated line is not reported twice.
        """
        if self._finished:
            return []
        self._finished = True

        if self._discarding_oversized_line:
            self._discarding_oversized_line = False
            return []
        if not self._buffer:
            return []
        self._buffer.clear()
        return [_line_failure(ProtocolParseErrorCode.INVALID_FRAMING)]


class CommandLineReader(_BoundedLineReader[Command]):
    """Incrementally validate untrusted TUI-to-Python command lines."""

    def __init__(self, max_line_bytes: int = DEFAULT_MAX_LINE_BYTES) -> None:
        """Create a command reader with one authoritative per-line byte bound.

        Args:
            max_line_bytes: Positive maximum JSON-object bytes retained before the LF delimiter.

        Raises:
            ValueError: If ``max_line_bytes`` is not positive.
        """
        super().__init__(parse_command_line, max_line_bytes)


class EventLineReader(_BoundedLineReader[Event]):
    """Incrementally validate untrusted Python-to-TUI event lines."""

    def __init__(self, max_line_bytes: int = DEFAULT_MAX_LINE_BYTES) -> None:
        """Create an event reader with one authoritative per-line byte bound.

        Args:
            max_line_bytes: Positive maximum JSON-object bytes retained before the LF delimiter.

        Raises:
            ValueError: If ``max_line_bytes`` is not positive.
        """
        super().__init__(parse_event_line, max_line_bytes)


class OrderedEventWriter:
    """Validate and serialize complete events through one globally ordered async boundary.

    The writer, rather than event producers, assigns each session's sequence. It holds one lock from
    sequence selection through sink completion so concurrent producers cannot interleave bytes or
    publish duplicate sequence values. A failed validation or sink call does not advance sequence
    state, although a sink that partially writes before raising has already violated its own atomic
    write contract.

    Cancellation cannot leave a successfully written session event unsequenced. If cancellation
    arrives during the sink call, the writer holds its lock until that shielded call settles,
    commits a successful sequence, and only then propagates cancellation.

    Example:
        A runtime can inject one bounded stdout sink and let unrelated producers share the writer::

            lines: list[bytes] = []

            async def sink(line: bytes) -> None:
                lines.append(line)

            writer = OrderedEventWriter(sink, lambda: "2026-07-16T12:34:56.789Z")
            await writer.emit_runtime("runtime.ready", {"workspace": "/workspace"})
    """

    def __init__(
        self,
        sink: Callable[[bytes], Awaitable[None]],
        timestamp_factory: Callable[[], str] = utc_timestamp,
    ) -> None:
        """Create a writer for one protocol stdout sink.

        Args:
            sink: Async callable that writes one supplied byte string as one ordered operation.
            timestamp_factory: Injectable canonical UTC timestamp source for deterministic tests.
        """
        self._sink = sink
        self._timestamp_factory = timestamp_factory
        self._lock = asyncio.Lock()
        self._session_sequences: dict[str, int] = {}

    async def emit_runtime(
        self,
        event_type: RuntimeEventType,
        payload: Mapping[str, object],
        *,
        correlation_id: CommandId | None = None,
    ) -> RuntimeEvent:
        """Validate and write one runtime-level event.

        Args:
            event_type: Supported runtime-level event discriminator.
            payload: Exact payload fields for that discriminator.
            correlation_id: Optional validated command correlation.

        Returns:
            The immutable event model that was written.

        Raises:
            ValidationError: If locally constructed event data violates the wire contract.
            ValueError: If serialization encounters a non-JSON numeric value.
            OSError: If the configured sink cannot write the complete line.

        Side Effects:
            Invokes the configured sink once with a complete validated NDJSON line.

        Note:
            Cancellation waits for an in-progress sink call to settle before it propagates.
        """
        payload_snapshot = dict(payload)
        async with self._lock:
            event_data: dict[str, object] = {
                "protocol_version": 1,
                "type": event_type,
                "timestamp": self._timestamp_factory(),
                "payload": payload_snapshot,
            }
            if correlation_id is not None:
                event_data["correlation_id"] = correlation_id
            event = cast(RuntimeEvent, validate_event(event_data))
            await self._write_line(encode_event(event))
            return event

    async def emit_session(
        self,
        event_type: SessionEventType,
        session_id: SessionId,
        payload: Mapping[str, object],
        *,
        correlation_id: CommandId | None = None,
    ) -> SessionEvent:
        """Assign, validate, and write one session event in authoritative order.

        Args:
            event_type: Supported session event discriminator.
            session_id: Session whose next positive sequence should be assigned.
            payload: Exact payload fields for that discriminator.
            correlation_id: Optional validated command correlation.

        Returns:
            The immutable event model that was written.

        Raises:
            OverflowError: If the session already used JavaScript's largest safe integer.
            ValidationError: If locally constructed event data violates the wire contract.
            ValueError: If serialization encounters a non-JSON numeric value.
            OSError: If the configured sink cannot write the complete line.

        Side Effects:
            Invokes the configured sink once and advances the session sequence only after that call
            succeeds.

        Note:
            Cancellation waits for an in-progress sink call to settle. A completed write advances
            sequence before cancellation propagates; a failed write does not.
        """
        payload_snapshot = dict(payload)
        async with self._lock:
            sequence = self._session_sequences.get(session_id, 0) + 1
            if sequence > MAX_SAFE_SEQUENCE:
                raise OverflowError("session sequence exceeds the protocol maximum")

            event_data: dict[str, object] = {
                "protocol_version": 1,
                "type": event_type,
                "session_id": session_id,
                "sequence": sequence,
                "timestamp": self._timestamp_factory(),
                "payload": payload_snapshot,
            }
            if correlation_id is not None:
                event_data["correlation_id"] = correlation_id
            event = cast(SessionEvent, validate_event(event_data))

            def commit_sequence() -> None:
                self._session_sequences[session_id] = sequence

            await self._write_line(encode_event(event), commit_sequence)
            return event

    async def _write_line(
        self,
        line: bytes,
        commit: Callable[[], None] | None = None,
    ) -> None:
        """Settle one sink operation before releasing order, even under caller cancellation."""
        sink_task = asyncio.ensure_future(self._sink(line))
        try:
            await asyncio.shield(sink_task)
        except asyncio.CancelledError:
            # The sink may already have written the line. Let it establish a definitive outcome so
            # sequence state cannot diverge from bytes published on the protocol stream.
            await sink_task
            if commit is not None:
                commit()
            raise
        if commit is not None:
            commit()


def _line_failure(code: ProtocolParseErrorCode) -> ProtocolParseFailure:
    messages = {
        ProtocolParseErrorCode.INVALID_FRAMING: (
            "Protocol input must be one complete JSON object terminated by LF."
        ),
        ProtocolParseErrorCode.LINE_TOO_LONG: "Protocol line exceeds the byte limit.",
    }
    return ProtocolParseFailure(code=code, message=messages[code])
