"""Strict programmable provider for deterministic model-free tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from .models import (
    PROVIDER_STREAM_EVENT_TYPES,
    ProviderCompleted,
    ProviderFailed,
    ProviderRequest,
    ProviderStreamEvent,
)
from .port import ProviderCancellationResult, ProviderOperation

_MAX_MISMATCH_PATHS = 8


class FakeProviderMismatch(AssertionError):
    """Report a bounded content-safe deviation from a fake-provider script."""


@dataclass(frozen=True, slots=True)
class FakeProviderEmit:
    """Emit one provider-neutral stream event."""

    event: ProviderStreamEvent

    def __post_init__(self) -> None:
        """Reject values outside the public provider stream union."""
        if not isinstance(self.event, PROVIDER_STREAM_EVENT_TYPES):
            raise TypeError("fake provider emit step requires a provider stream event")


@dataclass(frozen=True, slots=True)
class FakeProviderDelay:
    """Pause at a named deterministic gate until a test releases it.

    This is a logical delay rather than a wall-clock sleep. Tests can await the checkpoint and
    release it without timing assumptions. Checkpoint names are static, non-secret test labels.
    """

    checkpoint: str

    def __post_init__(self) -> None:
        """Validate the content-safe checkpoint label."""
        _validate_checkpoint_name(self.checkpoint)


@dataclass(frozen=True, slots=True)
class FakeProviderWaitForCancellation:
    """Pause at a named checkpoint until operation cancellation wins.

    Events after this step describe output that cancellation must suppress. Reaching the
    checkpoint and cancelling deliberately consumes that suffix; stopping iteration without
    cancellation leaves it unconsumed and fails :meth:`FakeProvider.assert_complete`. Checkpoint
    names are static, non-secret test labels.
    """

    checkpoint: str

    def __post_init__(self) -> None:
        """Validate the content-safe checkpoint label."""
        _validate_checkpoint_name(self.checkpoint)


type FakeProviderStep = FakeProviderEmit | FakeProviderDelay | FakeProviderWaitForCancellation
"""One ordered action in a deterministic fake-provider exchange."""


@dataclass(frozen=True, slots=True)
class FakeProviderExchange:
    """One expected request and the exact stream behavior it unlocks.

    Example:
        A cancellation race between two deltas is scripted explicitly::

            FakeProviderExchange(
                expected_request=request,
                steps=(
                    FakeProviderEmit(ProviderTextDelta("first")),
                    FakeProviderWaitForCancellation("between-deltas"),
                    FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                ),
            )

    Args:
        expected_request: Exact harness-owned request expected at this position.
        steps: Non-empty ordered emit, delay, and cancellation-checkpoint actions.
    """

    expected_request: ProviderRequest
    steps: tuple[FakeProviderStep, ...]

    def __post_init__(self) -> None:
        """Reject ambiguous or unreachable fake scripts before a test runs."""
        if not isinstance(self.expected_request, ProviderRequest):
            raise TypeError("fake provider exchange requires a provider request")
        _validate_steps(self.steps)


@dataclass(slots=True)
class _CheckpointState:
    kind: Literal["delay", "cancellation"]
    reached: asyncio.Event
    released: asyncio.Event


class FakeProviderOperation(ProviderOperation, Protocol):
    """Fake-specific operation controls returned by :class:`FakeProvider`.

    This public protocol makes checkpoint coordination type-safe without exposing the private
    operation constructor. Tests obtain an instance only through :meth:`FakeProvider.start`.

    Example:
        Consume toward a logical delay in one task, await the named checkpoint, and then release it
        without a wall-clock sleep::

            pending_event = asyncio.create_task(anext(operation.events()))
            await operation.wait_for_checkpoint("before-output")
            operation.release_checkpoint("before-output")
            event = await pending_event
    """

    @property
    def closed(self) -> bool:
        """Return whether the operation can no longer emit an event."""
        ...

    async def wait_for_checkpoint(self, checkpoint: str) -> None:
        """Wait until event consumption reaches a named scripted checkpoint.

        Args:
            checkpoint: Static non-secret name configured by a delay or cancellation step.

        Raises:
            ValueError: If the exchange has no checkpoint with that name.
            FakeProviderMismatch: If the operation closes before reaching the checkpoint.
        """
        ...

    def release_checkpoint(self, checkpoint: str) -> None:
        """Release one reached :class:`FakeProviderDelay` checkpoint.

        Args:
            checkpoint: Static non-secret name of the reached delay.

        Raises:
            ValueError: If the exchange has no checkpoint with that name.
            RuntimeError: If the checkpoint is for cancellation, has not been reached, was already
                released, or belongs to a closed operation.
        """
        ...


class _ScriptedProviderOperation:
    """Single-use operation that executes one validated fake exchange.

    The operation marks an emitted step consumed before returning it. Consequently a caller may
    stop after the final terminal event without making one extra ``anext`` call, while stopping
    earlier remains visible to :meth:`FakeProvider.assert_complete`.
    """

    def __init__(
        self,
        *,
        exchange_number: int,
        steps: tuple[FakeProviderStep, ...],
    ) -> None:
        """Create an inactive operation from one validated exchange."""
        if type(exchange_number) is not int or exchange_number < 1:
            raise ValueError("fake provider exchange number must be a positive integer")
        _validate_steps(steps)
        self._exchange_number = exchange_number
        self._steps = steps
        self._step_index = 0
        self._events_claimed = False
        self._closed = False
        self._next_active = False
        self._cancel_requested = asyncio.Event()
        self._closed_event = asyncio.Event()
        self._state_lock = asyncio.Lock()
        self._next_lock = asyncio.Lock()
        self._cancelled_at: str | None = None
        self._checkpoints: dict[str, _CheckpointState] = {}
        for step in steps:
            if isinstance(step, FakeProviderDelay):
                self._checkpoints[step.checkpoint] = _CheckpointState(
                    kind="delay",
                    reached=asyncio.Event(),
                    released=asyncio.Event(),
                )
            elif isinstance(step, FakeProviderWaitForCancellation):
                self._checkpoints[step.checkpoint] = _CheckpointState(
                    kind="cancellation",
                    reached=asyncio.Event(),
                    released=asyncio.Event(),
                )

    @property
    def closed(self) -> bool:
        """Return whether the operation can no longer emit an event."""
        return self._closed

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        """Claim and return this operation's single-consumer event stream.

        Returns:
            This operation as an asynchronous iterator.

        Raises:
            RuntimeError: If an event consumer already claimed the stream.
        """
        if self._events_claimed:
            raise RuntimeError("fake provider operation events may be claimed only once")
        self._events_claimed = True
        return self

    def __aiter__(self) -> FakeProviderOperation:
        """Return the already-claimed asynchronous iterator."""
        if not self._events_claimed:
            raise RuntimeError("claim fake provider events before iterating")
        return self

    async def __anext__(self) -> ProviderStreamEvent:
        """Return the next emitted event while consuming control steps internally."""
        if not self._events_claimed:
            raise RuntimeError("claim fake provider events before iterating")
        async with self._next_lock:
            async with self._state_lock:
                if self._closed:
                    raise StopAsyncIteration
                self._next_active = True
            try:
                return await self._next_event()
            except asyncio.CancelledError:
                await self._close_incomplete()
                raise
            finally:
                async with self._state_lock:
                    self._next_active = False
                    if self._cancel_requested.is_set() and not self._closed:
                        self._finish_idle_cancellation_locked()

    async def cancel(self) -> ProviderCancellationResult:
        """Cancel active work and wait until the stream cannot emit again.

        Returns:
            ``cancelled`` when this call closed active work, or ``already_closed`` after a prior
            terminal event or cancellation.
        """
        async with self._state_lock:
            if self._closed:
                return "already_closed"
            self._cancel_requested.set()
            if not self._next_active:
                self._finish_idle_cancellation_locked()
        await self._closed_event.wait()
        return "cancelled"

    async def wait_closed(self) -> None:
        """Wait until completion, failure, cancellation, or consumer abort closes the stream."""
        await self._closed_event.wait()

    async def wait_for_checkpoint(self, checkpoint: str) -> None:
        """Wait until event consumption reaches a named delay or cancellation checkpoint.

        Args:
            checkpoint: Name configured by the exchange script.

        Raises:
            ValueError: If the exchange has no checkpoint with that name.
            FakeProviderMismatch: If the operation closes before reaching the checkpoint.
        """
        state = self._checkpoint(checkpoint)
        if state.reached.is_set():
            return
        if self._closed:
            raise FakeProviderMismatch(
                f"fake provider exchange {self._exchange_number} closed before "
                "the requested checkpoint"
            )
        reached_task = asyncio.create_task(state.reached.wait())
        closed_task = asyncio.create_task(self._closed_event.wait())
        try:
            completed, _pending = await asyncio.wait(
                {reached_task, closed_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reached_task in completed:
                return
            raise FakeProviderMismatch(
                f"fake provider exchange {self._exchange_number} closed before "
                "the requested checkpoint"
            )
        finally:
            for task in (reached_task, closed_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(reached_task, closed_task, return_exceptions=True)

    def release_checkpoint(self, checkpoint: str) -> None:
        """Release one reached deterministic delay.

        Args:
            checkpoint: Name of a configured :class:`FakeProviderDelay`.

        Raises:
            ValueError: If the checkpoint does not exist.
            RuntimeError: If it is a cancellation checkpoint, has not been reached, was already
                released, or belongs to a closed operation.
        """
        state = self._checkpoint(checkpoint)
        if state.kind != "delay":
            raise RuntimeError("cancellation checkpoints can only be released by cancellation")
        if self._closed:
            raise RuntimeError("cannot release a checkpoint after the operation closed")
        if not state.reached.is_set():
            raise RuntimeError("cannot release a checkpoint before the stream reaches it")
        if state.released.is_set():
            raise RuntimeError("fake provider delay checkpoint was already released")
        state.released.set()

    def verification_failure(self) -> str | None:
        """Return a bounded script-exhaustion diagnostic, if any."""
        if not self._closed:
            return (
                f"fake provider exchange {self._exchange_number} is still active at "
                f"step {self._step_index + 1} ({self._step_label()})"
            )
        if self._step_index < len(self._steps):
            return (
                f"fake provider exchange {self._exchange_number} stopped before "
                f"step {self._step_index + 1} ({self._step_label()})"
            )
        return None

    async def _next_event(self) -> ProviderStreamEvent:
        while True:
            async with self._state_lock:
                if self._closed:
                    raise StopAsyncIteration
                if self._cancel_requested.is_set():
                    self._finish_idle_cancellation_locked()
                    raise StopAsyncIteration

                step = self._steps[self._step_index]
                if isinstance(step, FakeProviderEmit):
                    self._step_index += 1
                    if self._step_index == len(self._steps):
                        self._mark_closed_locked()
                    return step.event

                checkpoint = self._checkpoints[step.checkpoint]
                checkpoint.reached.set()

            if isinstance(step, FakeProviderDelay):
                released = await self._wait_for_delay(checkpoint)
                if not released:
                    raise StopAsyncIteration
                async with self._state_lock:
                    if self._closed:
                        raise StopAsyncIteration
                    self._step_index += 1
                continue

            await self._cancel_requested.wait()
            async with self._state_lock:
                self._cancelled_at = step.checkpoint
                self._step_index = len(self._steps)
                self._mark_closed_locked()
            raise StopAsyncIteration

    async def _wait_for_delay(self, checkpoint: _CheckpointState) -> bool:
        released_task = asyncio.create_task(checkpoint.released.wait())
        cancelled_task = asyncio.create_task(self._cancel_requested.wait())
        try:
            completed, _pending = await asyncio.wait(
                {released_task, cancelled_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled_task in completed:
                async with self._state_lock:
                    self._mark_closed_locked()
                return False
            return True
        finally:
            for task in (released_task, cancelled_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(released_task, cancelled_task, return_exceptions=True)

    async def _close_incomplete(self) -> None:
        async with self._state_lock:
            self._mark_closed_locked()

    def _finish_idle_cancellation_locked(self) -> None:
        if self._closed:
            return
        if self._step_index < len(self._steps) and isinstance(
            self._steps[self._step_index],
            FakeProviderWaitForCancellation,
        ):
            checkpoint = self._steps[self._step_index].checkpoint
            self._checkpoints[checkpoint].reached.set()
            self._cancelled_at = checkpoint
            self._step_index = len(self._steps)
        self._mark_closed_locked()

    def _mark_closed_locked(self) -> None:
        self._closed = True
        self._closed_event.set()

    def _checkpoint(self, checkpoint: str) -> _CheckpointState:
        try:
            return self._checkpoints[checkpoint]
        except KeyError:
            raise ValueError("unknown fake provider checkpoint") from None

    def _step_label(self) -> str:
        if self._step_index >= len(self._steps):
            return "end-of-script"
        step = self._steps[self._step_index]
        if isinstance(step, FakeProviderEmit):
            return f"emit:{step.event.kind}"
        if isinstance(step, FakeProviderDelay):
            return "delay-checkpoint"
        return "cancellation-checkpoint"


class FakeProvider:
    """Verify ordered requests and execute their deterministic event scripts.

    Example:
        The caller must consume the terminal event and then verify the complete interaction::

            fake = FakeProvider((FakeProviderExchange(request, steps),))
            operation = fake.start(request)
            events = [event async for event in operation.events()]
            fake.assert_complete()

    Request mismatch diagnostics contain only exchange numbers and differing field paths. They
    never include conversation text, repository instructions, tool arguments, failure payloads, or
    credentials.
    """

    def __init__(self, exchanges: Sequence[FakeProviderExchange]) -> None:
        """Copy an ordered fake script into immutable storage.

        Args:
            exchanges: Expected request/stream exchanges in exact call order.
        """
        self._exchanges = tuple(exchanges)
        if not all(isinstance(exchange, FakeProviderExchange) for exchange in self._exchanges):
            raise TypeError("fake provider exchanges contain an unsupported value")
        self._next_exchange_index = 0
        self._operations: list[_ScriptedProviderOperation] = []

    def start(self, request: ProviderRequest) -> FakeProviderOperation:
        """Match one request and return its single-use scripted operation.

        Args:
            request: Actual harness-owned request made by the caller.

        Returns:
            Operation for the matching exchange.

        Raises:
            FakeProviderMismatch: If a prior stream is incomplete, the script is exhausted, or the
                request differs from the next expectation.
        """
        if self._operations:
            prior_failure = self._operations[-1].verification_failure()
            if prior_failure is not None:
                raise FakeProviderMismatch(
                    f"{prior_failure}; cannot start another provider request"
                )
        exchange_number = self._next_exchange_index + 1
        if self._next_exchange_index >= len(self._exchanges):
            raise FakeProviderMismatch(
                f"fake provider received unexpected request {exchange_number}; "
                "the script has no remaining exchanges"
            )
        if not isinstance(request, ProviderRequest):
            raise TypeError("fake provider requires a provider request")

        exchange = self._exchanges[self._next_exchange_index]
        mismatch_paths = _request_mismatch_paths(exchange.expected_request, request)
        if mismatch_paths:
            paths = ", ".join(mismatch_paths[:_MAX_MISMATCH_PATHS])
            remaining = len(mismatch_paths) - _MAX_MISMATCH_PATHS
            suffix = "" if remaining <= 0 else f", and {remaining} more field(s)"
            raise FakeProviderMismatch(
                f"fake provider request {exchange_number} differed at {paths}{suffix}"
            )

        operation = _ScriptedProviderOperation(
            exchange_number=exchange_number,
            steps=exchange.steps,
        )
        self._next_exchange_index += 1
        self._operations.append(operation)
        return operation

    def assert_complete(self) -> None:
        """Assert that every expected request and stream step was consumed exactly once.

        Raises:
            FakeProviderMismatch: If a started operation is unfinished, a consumer stopped early,
                or one or more expected requests were omitted.
        """
        for operation in self._operations:
            failure = operation.verification_failure()
            if failure is not None:
                raise FakeProviderMismatch(failure)
        if self._next_exchange_index < len(self._exchanges):
            remaining = len(self._exchanges) - self._next_exchange_index
            raise FakeProviderMismatch(
                f"fake provider expected request {self._next_exchange_index + 1}, "
                f"but {remaining} exchange(s) were never started"
            )


def _request_mismatch_paths(
    expected: ProviderRequest,
    actual: ProviderRequest,
) -> list[str]:
    paths: list[str] = []
    if len(expected.conversation) != len(actual.conversation):
        paths.append("conversation.length")
    for index, (expected_message, actual_message) in enumerate(
        zip(expected.conversation, actual.conversation, strict=False)
    ):
        if expected_message.role != actual_message.role:
            paths.append(f"conversation[{index}].role")
        if expected_message.content != actual_message.content:
            paths.append(f"conversation[{index}].content")

    if len(expected.repository_instructions) != len(actual.repository_instructions):
        paths.append("repository_instructions.length")
    for index, (expected_instruction, actual_instruction) in enumerate(
        zip(
            expected.repository_instructions,
            actual.repository_instructions,
            strict=False,
        )
    ):
        if expected_instruction.source != actual_instruction.source:
            paths.append(f"repository_instructions[{index}].source")
        if expected_instruction.content != actual_instruction.content:
            paths.append(f"repository_instructions[{index}].content")
    return paths


def _validate_steps(steps: object) -> None:
    if not isinstance(steps, tuple):
        raise TypeError("fake provider exchange steps must be a tuple")
    if not steps:
        raise ValueError("fake provider exchange steps must not be empty")
    if not all(
        isinstance(
            step,
            FakeProviderEmit | FakeProviderDelay | FakeProviderWaitForCancellation,
        )
        for step in steps
    ):
        raise TypeError("fake provider exchange contains an unsupported step")

    checkpoint_names = [
        step.checkpoint
        for step in steps
        if isinstance(step, FakeProviderDelay | FakeProviderWaitForCancellation)
    ]
    if len(checkpoint_names) != len(set(checkpoint_names)):
        raise ValueError("fake provider checkpoint names must be unique within an exchange")

    cancellation_indexes = [
        index
        for index, step in enumerate(steps)
        if isinstance(step, FakeProviderWaitForCancellation)
    ]
    if len(cancellation_indexes) > 1:
        raise ValueError("fake provider exchange may contain only one cancellation checkpoint")

    terminal_indexes = [
        index
        for index, step in enumerate(steps)
        if isinstance(step, FakeProviderEmit)
        and isinstance(step.event, ProviderCompleted | ProviderFailed)
    ]
    if cancellation_indexes:
        cancellation_index = cancellation_indexes[0]
        if any(index < cancellation_index for index in terminal_indexes):
            raise ValueError("fake provider terminal event cannot precede cancellation")
        if any(not isinstance(step, FakeProviderEmit) for step in steps[cancellation_index + 1 :]):
            raise ValueError(
                "only cancellation-suppressed emit steps may follow a cancellation checkpoint"
            )
        return

    if terminal_indexes != [len(steps) - 1]:
        raise ValueError("fake provider non-cancellation exchange must end with one terminal event")


def _validate_checkpoint_name(checkpoint: object) -> None:
    if not isinstance(checkpoint, str):
        raise TypeError("fake provider checkpoint must be a string")
    if not checkpoint:
        raise ValueError("fake provider checkpoint must not be empty")
    if len(checkpoint) > 256:
        raise ValueError("fake provider checkpoint must contain at most 256 characters")
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in checkpoint):
        raise ValueError("fake provider checkpoint must not contain terminal controls")


__all__ = [
    "FakeProvider",
    "FakeProviderDelay",
    "FakeProviderEmit",
    "FakeProviderExchange",
    "FakeProviderMismatch",
    "FakeProviderOperation",
    "FakeProviderStep",
    "FakeProviderWaitForCancellation",
]
