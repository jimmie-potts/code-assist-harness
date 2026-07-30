"""Deterministic mocked session used to prove the first streaming runtime path."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from .protocol import OrderedEventWriter, SessionId, SessionStartCommand

MOCK_RESPONSE_DELTAS = (
    "Mock response: ",
    "the task crossed the process boundary ",
    "and streamed back successfully.",
)
"""Fixed non-empty fragments emitted by every CAH-005 mocked session."""

MOCK_RESPONSE_TEXT = "".join(MOCK_RESPONSE_DELTAS)
"""Complete assistant text formed by the mocked deltas in order."""

_DEFAULT_DELTA_DELAY_SECONDS = 0.05

type MockDeltaCheckpoint = Callable[[int, str], Awaitable[None]]
"""Async scheduling seam invoked immediately before each mocked delta."""


async def _delay_before_delta(_index: int, _delta: str) -> None:
    """Make intermediate output observable without introducing provider behavior."""
    await asyncio.sleep(_DEFAULT_DELTA_DELAY_SECONDS)


class MockSessionRunner:
    """Emit one deterministic, serialized session lifecycle through an ordered writer.

    The runtime creates one runner for its lifetime and starts at most one call to :meth:`run` at a
    time. The runner assigns a fresh readable session ID per accepted command, while the writer owns
    each session's authoritative sequence. An injectable checkpoint lets tests hold and release
    individual deltas without relying on wall-clock sleeps.
    """

    def __init__(
        self,
        writer: OrderedEventWriter,
        checkpoint: MockDeltaCheckpoint = _delay_before_delta,
    ) -> None:
        """Create a mocked session source for one runtime.

        Args:
            writer: The runtime's single validated ordered event writer.
            checkpoint: Async function called with the one-based delta index and text before every
                delta is emitted.
        """
        self._writer = writer
        self._checkpoint = checkpoint
        self._session_count = 0

    async def run(self, command: SessionStartCommand) -> SessionId:
        """Emit the complete successful lifecycle for one accepted task command.

        Args:
            command: Validated command whose ID correlates every resulting session event.

        Returns:
            The distinct session ID assigned to the completed mock lifecycle.

        Raises:
            OSError: If the ordered protocol sink cannot write a complete event line.
            ValueError: If local event construction or encoding violates protocol constraints.
            OverflowError: If the ordered writer exhausts the protocol sequence range.

        Side Effects:
            Emits ``session.started``, three delayed ``assistant.delta`` events,
            ``assistant.completed``, and exactly one ``session.completed`` event.

        Note:
            Caller cancellation may interrupt a checkpoint. CAH-006 will define user-requested
            session cancellation and its terminal-event semantics.
        """
        self._session_count += 1
        session_id = SessionId(f"ses_mock_{self._session_count}")
        correlation_id = command.command_id

        await self._writer.emit_session(
            "session.started",
            session_id,
            {},
            correlation_id=correlation_id,
        )

        accumulated: list[str] = []
        for index, delta in enumerate(MOCK_RESPONSE_DELTAS, start=1):
            await self._checkpoint(index, delta)
            accumulated.append(delta)
            await self._writer.emit_session(
                "assistant.delta",
                session_id,
                {"text": delta},
                correlation_id=correlation_id,
            )

        completed_text = "".join(accumulated)
        await self._writer.emit_session(
            "assistant.completed",
            session_id,
            {"text": completed_text},
            correlation_id=correlation_id,
        )
        await self._writer.emit_session(
            "session.completed",
            session_id,
            {},
            correlation_id=correlation_id,
        )
        return session_id
