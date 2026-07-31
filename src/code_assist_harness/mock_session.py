"""Deterministic mocked session used to prove the first streaming runtime path."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from .protocol import CommandId, OrderedEventWriter, SessionId, SessionStartCommand
from .session_state import (
    CancelRequested,
    SessionInvariantFailure,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
)

MOCK_RESPONSE_DELTAS = (
    "Mock response: ",
    "the task crossed the process boundary ",
    "and streamed back successfully.",
)
"""Fixed non-empty fragments emitted by every CAH-005 mocked session."""

MOCK_RESPONSE_TEXT = "".join(MOCK_RESPONSE_DELTAS)
"""Complete assistant text formed by the mocked deltas in order."""

_DEFAULT_DELTA_DELAY_SECONDS = 0.5

type MockDeltaCheckpoint = Callable[[int, str], Awaitable[None]]
"""Async scheduling seam invoked immediately before each mocked delta."""

type LifecycleObserver = Callable[[SessionUpdate, SessionState], Awaitable[None]]
"""Async observer called after one update enters authoritative lifecycle state."""

type CancellationRequestResult = Literal["accepted", "already_requested", "terminal"]
"""Result of asking one mock session to select cancellation as its terminal outcome."""

type _TerminalOutcome = Literal["completed", "cancelled"]


async def _delay_before_delta(_index: int, _delta: str) -> None:
    """Keep each learning-only fragment visible long enough for interactive cancellation."""
    await asyncio.sleep(_DEFAULT_DELTA_DELAY_SECONDS)


class MockSession:
    """Own one mock session's work, cancellation signal, and terminal transition.

    The state lock serializes cancellation acceptance with assistant and terminal event writes.
    Therefore a cancellation request cannot become authoritative in the middle of a delta write,
    and a ``session.completed`` write already in progress wins its race without a later
    ``session.cancelled`` event. Cancellation remains cooperative: it interrupts the learning-only
    delay checkpoints, but never uses task cancellation as the user-facing lifecycle mechanism.
    """

    def __init__(
        self,
        writer: OrderedEventWriter,
        checkpoint: MockDeltaCheckpoint,
        command: SessionStartCommand,
        session_id: SessionId,
    ) -> None:
        """Create one not-yet-started mock session.

        Args:
            writer: Runtime-owned validated ordered event writer.
            checkpoint: Cancellable scheduling seam called before every assistant delta.
            command: Accepted task command that correlates non-cancellation session events.
            session_id: Python-owned identity allocated before the session task starts.
        """
        self._writer = writer
        self._checkpoint = checkpoint
        self._command = command
        self._session_id = session_id
        self._state_lock = asyncio.Lock()
        self._cancellation_requested = asyncio.Event()
        self._cancel_command_id: CommandId | None = None
        self._terminal_outcome: _TerminalOutcome | None = None
        self._terminal_emitted = False
        self._run_started = False
        self._lifecycle_observer: LifecycleObserver | None = None
        self._task_submitted = TaskSubmitted(
            command_id=command.command_id,
            task=command.payload.task,
        )
        initial_reduction = reduce_session_state(
            SessionState(),
            self._task_submitted,
        )
        if not initial_reduction.ok:
            raise _lifecycle_invariant_error(initial_reduction.failure)
        self._lifecycle_state = initial_reduction.state
        self._deferred_cancellation: CancelRequested | None = None

    @property
    def session_id(self) -> SessionId:
        """Return the stable Python-owned session identity used for cancellation routing."""
        return self._session_id

    @property
    def lifecycle_state(self) -> SessionState:
        """Return the immutable state derived from accepted commands and emitted events."""
        return self._lifecycle_state

    async def attach_lifecycle_observer(self, observer: LifecycleObserver) -> None:
        """Attach the one observer that will receive accepted updates in reducer order.

        Args:
            observer: Async persistence or evidence boundary. It is called only after the reducer
                accepts an update and must not mutate lifecycle state.

        Raises:
            RuntimeError: If work has started or an observer was already attached.
        """
        if self._run_started:
            raise RuntimeError("a lifecycle observer must be attached before the session starts")
        if self._lifecycle_observer is not None:
            raise RuntimeError("a mock session accepts only one lifecycle observer")
        self._lifecycle_observer = observer
        await self._notify_lifecycle(self._task_submitted)

    async def request_cancellation(
        self,
        command_id: CommandId,
    ) -> CancellationRequestResult:
        """Attempt to select cancellation as this session's sole terminal outcome.

        Args:
            command_id: ID of the validated ``session.cancel`` command that should correlate a
                winning ``session.cancelled`` event.

        Returns:
            ``accepted`` when this request selects cancellation, ``already_requested`` when the
            same session is already cancelling, or ``terminal`` when completion already won.

        Side Effects:
            Wakes a checkpoint-blocked :meth:`run` call after cancellation is accepted.

        Note:
            The method may wait for an event write already holding the state lock. That write is
            authoritative before cancellation is accepted, so no post-acceptance delta can appear.
        """
        async with self._state_lock:
            if self._cancel_command_id is not None:
                return "already_requested"
            if self._terminal_outcome is not None:
                return "terminal"

            cancellation = CancelRequested(command_id=command_id, session_id=self._session_id)
            if self._lifecycle_state.status == "starting":
                # A direct caller may cancel after allocation but before ``run`` publishes
                # session.started. Preserve the legal matrix by reducing this fact immediately
                # after the started event rather than inventing starting -> cancelling.
                self._deferred_cancellation = cancellation
            else:
                await self._reduce_lifecycle(cancellation)
            self._cancel_command_id = command_id
            self._terminal_outcome = "cancelled"
            self._cancellation_requested.set()
            return "accepted"

    async def run(self) -> SessionId:
        """Emit this session's successful or cooperatively cancelled lifecycle.

        Returns:
            This session's stable ID after its one terminal event has been written.

        Raises:
            RuntimeError: If the same session object is run more than once.
            OSError: If the ordered protocol sink cannot write a complete event line.
            ValueError: If local event construction or encoding violates protocol constraints.
            OverflowError: If the ordered writer exhausts the protocol sequence range.

        Side Effects:
            Emits ``session.started`` followed by either the complete deterministic success tape or
            one ``session.cancelled`` event correlated to the winning cancellation command.
        """
        if self._run_started:
            raise RuntimeError("a mock session can run only once")
        self._run_started = True

        started = await self._writer.emit_session(
            "session.started",
            self._session_id,
            {},
            correlation_id=self._command.command_id,
        )
        async with self._state_lock:
            await self._reduce_lifecycle(started)
            if self._deferred_cancellation is not None:
                await self._reduce_lifecycle(self._deferred_cancellation)
                self._deferred_cancellation = None

        accumulated: list[str] = []
        for index, delta in enumerate(MOCK_RESPONSE_DELTAS, start=1):
            checkpoint_completed = await self._wait_for_checkpoint(index, delta)
            if not checkpoint_completed or not await self._emit_delta(delta):
                await self._emit_selected_cancellation()
                return self._session_id
            accumulated.append(delta)

        if not await self._emit_completion("".join(accumulated)):
            await self._emit_selected_cancellation()
        return self._session_id

    async def _wait_for_checkpoint(self, index: int, delta: str) -> bool:
        """Return early when cancellation wins while a scheduling checkpoint is blocked."""
        if self._cancellation_requested.is_set():
            return False

        checkpoint_task = asyncio.create_task(self._checkpoint(index, delta))
        cancellation_task = asyncio.create_task(self._cancellation_requested.wait())
        try:
            completed, _pending = await asyncio.wait(
                {checkpoint_task, cancellation_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            checkpoint_task.cancel()
            cancellation_task.cancel()
            await asyncio.gather(checkpoint_task, cancellation_task, return_exceptions=True)
            raise

        if cancellation_task in completed:
            if not checkpoint_task.done():
                checkpoint_task.cancel()
            await asyncio.gather(checkpoint_task, return_exceptions=True)
            return False

        cancellation_task.cancel()
        await asyncio.gather(cancellation_task, return_exceptions=True)
        await checkpoint_task
        return not self._cancellation_requested.is_set()

    async def _emit_delta(self, delta: str) -> bool:
        """Write one delta only while no terminal outcome has been selected."""
        async with self._state_lock:
            if self._terminal_outcome is not None:
                return False
            event = await self._writer.emit_session(
                "assistant.delta",
                self._session_id,
                {"text": delta},
                correlation_id=self._command.command_id,
            )
            await self._reduce_lifecycle(event)
            return True

    async def _emit_completion(self, completed_text: str) -> bool:
        """Atomically select and publish normal completion unless cancellation won first."""
        async with self._state_lock:
            if self._terminal_outcome is not None:
                return False
            assistant_completed = await self._writer.emit_session(
                "assistant.completed",
                self._session_id,
                {"text": completed_text},
                correlation_id=self._command.command_id,
            )
            await self._reduce_lifecycle(assistant_completed)
            # Selection precedes the shielded terminal write. A cancellation waiting on the lock
            # must observe that completion already won even if the sink has not returned yet.
            self._terminal_outcome = "completed"
            session_completed = await self._writer.emit_session(
                "session.completed",
                self._session_id,
                {},
                correlation_id=self._command.command_id,
            )
            await self._reduce_lifecycle(session_completed)
            self._terminal_emitted = True
            return True

    async def _emit_selected_cancellation(self) -> None:
        """Publish cancellation once after the winning request stopped assistant output."""
        async with self._state_lock:
            if self._terminal_outcome != "cancelled" or self._terminal_emitted:
                return
            if self._cancel_command_id is None:
                raise RuntimeError("cancelled session is missing its command correlation")
            session_cancelled = await self._writer.emit_session(
                "session.cancelled",
                self._session_id,
                {},
                correlation_id=self._cancel_command_id,
            )
            await self._reduce_lifecycle(session_cancelled)
            self._terminal_emitted = True

    async def _reduce_lifecycle(self, update: SessionUpdate) -> None:
        """Accept one integration fact or raise a bounded payload-free invariant error."""
        reduction = reduce_session_state(self._lifecycle_state, update)
        if not reduction.ok:
            raise _lifecycle_invariant_error(reduction.failure)
        self._lifecycle_state = reduction.state
        await self._notify_lifecycle(update)

    async def _notify_lifecycle(self, update: SessionUpdate) -> None:
        """Publish one accepted update without granting the observer lifecycle authority."""
        if self._lifecycle_observer is not None:
            await self._lifecycle_observer(update, self._lifecycle_state)


def _lifecycle_invariant_error(failure: SessionInvariantFailure | None) -> RuntimeError:
    """Build a safe integration error without copying state or event payload values."""
    if failure is None:
        return RuntimeError("session lifecycle reduction failed without a classification")
    return RuntimeError(
        "session lifecycle invariant failed: "
        f"code={failure.code} prior_status={failure.prior_status} "
        f"event_type={failure.event_type}"
    )


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

    def create(self, command: SessionStartCommand) -> MockSession:
        """Allocate one distinct mock session before its asynchronous work starts.

        Args:
            command: Accepted task command that owns the session's successful event correlation.

        Returns:
            A single-use session whose ID is immediately available for cancellation routing.
        """
        self._session_count += 1
        session_id = SessionId(f"ses_mock_{self._session_count}")
        return MockSession(self._writer, self._checkpoint, command, session_id)

    async def run(self, command: SessionStartCommand) -> SessionId:
        """Allocate and emit the complete lifecycle for one accepted task command.

        Args:
            command: Validated command whose ID correlates every resulting session event.

        Returns:
            The distinct session ID assigned to the completed mock lifecycle.

        Raises:
            OSError: If the ordered protocol sink cannot write a complete event line.
            ValueError: If local event construction or encoding violates protocol constraints.
            OverflowError: If the ordered writer exhausts the protocol sequence range.

        Side Effects:
            Emits the normal successful tape unless the returned session is managed separately
            through :meth:`create` and receives a cancellation request.
        """
        return await self.create(command).run()
