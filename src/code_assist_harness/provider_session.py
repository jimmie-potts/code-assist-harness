"""One provider-neutral model turn owned by the harness session lifecycle."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .model_evidence import ModelUsageObserved
from .protocol import CommandId, OrderedEventWriter, SessionId, SessionStartCommand
from .provider import (
    Provider,
    ProviderCompleted,
    ProviderFailed,
    ProviderMessage,
    ProviderOperation,
    ProviderRequest,
    ProviderStreamEvent,
    ProviderTextCompleted,
    ProviderTextDelta,
    ProviderToolCallRequested,
    ProviderUsageReported,
    RepositoryInstruction,
)
from .session_state import (
    CancelRequested,
    SessionInvariantFailure,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
)

MAX_PROVIDER_TURN_OUTPUT_BYTES = 8192
"""Fixed protocol-fit ceiling applied before CAH-022 adds a configurable output budget."""

PROVIDER_INVALID_RESPONSE_CODE = "provider_invalid_response"
PROVIDER_INVALID_RESPONSE_MESSAGE = "The provider returned an invalid response."
TOOL_UNAVAILABLE_CODE = "tool_unavailable"
TOOL_UNAVAILABLE_MESSAGE = "Provider-requested tools are not available."
PROVIDER_CLEANUP_FAILED_CODE = "provider_cleanup_failed"
PROVIDER_CLEANUP_FAILED_MESSAGE = "Provider cleanup could not be confirmed."

type LifecycleObserver = Callable[[SessionUpdate, SessionState], Awaitable[None]]
"""Async observer called after one update enters authoritative lifecycle state."""

type ModelUsageObserver = Callable[[ModelUsageObserved], Awaitable[None]]
"""Async observer for bounded usage evidence outside lifecycle state."""

type CancellationRequestResult = Literal["accepted", "already_requested", "terminal"]
"""Result of asking one provider-backed session to select user cancellation."""

type TeardownRequestResult = Literal["accepted", "already_requested", "terminal"]
"""Result of asking one provider-backed session to stop without a user terminal event."""

type _OutcomeKind = Literal["completed", "failed", "cancelled", "teardown"]
type _CleanupMode = Literal["wait_closed", "cancel"]


@dataclass(frozen=True, slots=True)
class _SelectedOutcome:
    kind: _OutcomeKind
    cleanup_mode: _CleanupMode
    failure_code: str | None = None
    failure_message: str | None = None
    correlation_id: CommandId | None = None


async def _settle_shielded[ResultT](awaitable: Awaitable[ResultT]) -> ResultT:
    """Finish one owned transaction before propagating caller cancellation."""
    task = asyncio.ensure_future(awaitable)
    return await _wait_shielded(task)


async def _join_shared[ResultT](task: asyncio.Task[ResultT]) -> ResultT:
    """Join a shared owner task without allowing one cancelled waiter to cancel it."""
    return await _wait_shielded(task)


async def _next_provider_event(
    events: AsyncIterator[ProviderStreamEvent],
) -> ProviderStreamEvent:
    """Claim one general awaitable from an untrusted provider iterator inside owned work."""
    return await anext(events)


async def _wait_shielded[ResultT](task: asyncio.Future[ResultT]) -> ResultT:
    """Settle owned work through repeated caller cancellation, then propagate cancellation."""
    current = asyncio.current_task()
    cancellation_count = 0 if current is None else current.cancelling()
    caller_cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            next_count = 0 if current is None else current.cancelling()
            if next_count > cancellation_count:
                caller_cancelled = True
                cancellation_count = next_count
                continue
            if task.done():
                break
            raise
    result = task.result()
    if caller_cancelled:
        raise asyncio.CancelledError
    return result


class ProviderSession:
    """Own exactly one provider request, stream, cleanup path, and session outcome.

    Provider observations are untrusted until this class admits them under one decision lock. Each
    lifecycle publication settles the protocol write, reducer update, and evidence observer before
    cancellation may compete. Completion, failure, user cancellation, and teardown share one
    selected outcome and one cleanup/finalization task.
    """

    def __init__(
        self,
        writer: OrderedEventWriter,
        provider: Provider,
        command: SessionStartCommand,
        session_id: SessionId,
        repository_instructions: tuple[RepositoryInstruction, ...] = (),
    ) -> None:
        """Create one not-yet-started provider-backed session.

        Args:
            writer: Runtime-owned validated ordered event writer.
            provider: Provider-neutral operation factory injected at composition time.
            command: Accepted task command that correlates normal and failed events.
            session_id: Python-owned identity allocated before work starts.
            repository_instructions: Ordered, already-resolved guidance for this turn.
        """
        if not isinstance(provider, Provider):
            raise TypeError("provider session requires a provider implementation")
        if not isinstance(repository_instructions, tuple):
            raise TypeError("repository instructions must be a tuple")
        if not all(
            isinstance(instruction, RepositoryInstruction)
            for instruction in repository_instructions
        ):
            raise TypeError("repository instructions contain an unsupported value")

        self._writer = writer
        self._provider = provider
        self._command = command
        self._session_id = session_id
        self._request = ProviderRequest(
            conversation=(ProviderMessage(role="user", content=command.payload.task),),
            repository_instructions=repository_instructions,
        )
        self._decision_lock = asyncio.Lock()
        self._session_start_settled = asyncio.Event()
        self._session_started_successfully = False
        self._run_started = False
        self._lifecycle_observer: LifecycleObserver | None = None
        self._usage_observer: ModelUsageObserver | None = None
        self._task_submitted = TaskSubmitted(
            command_id=command.command_id,
            task=command.payload.task,
        )
        initial_reduction = reduce_session_state(SessionState(), self._task_submitted)
        if not initial_reduction.ok:
            raise _lifecycle_invariant_error(initial_reduction.failure)
        self._lifecycle_state = initial_reduction.state
        self._deferred_cancellation: CancelRequested | None = None

        self._operation: ProviderOperation | None = None
        self._events: AsyncIterator[ProviderStreamEvent] | None = None
        self._pending_event_task: asyncio.Task[ProviderStreamEvent] | None = None
        self._selection: _SelectedOutcome | None = None
        self._finalization_task: asyncio.Task[None] | None = None
        self._terminal_emitted = False
        self._cleanup_diagnostic_emitted = False

        self._accepted_text: list[str] = []
        self._accepted_text_bytes = 0
        self._completed_text: str | None = None
        self._usage_observed = False

    @property
    def session_id(self) -> SessionId:
        """Return the stable Python-owned identity used for cancellation routing."""
        return self._session_id

    @property
    def lifecycle_state(self) -> SessionState:
        """Return the immutable state formed from admitted lifecycle updates."""
        return self._lifecycle_state

    async def attach_lifecycle_observer(self, observer: LifecycleObserver) -> None:
        """Attach one lifecycle observer before provider-backed work starts.

        Args:
            observer: Async persistence or evidence boundary called in reducer order.

        Raises:
            RuntimeError: If work started or an observer was already attached.
        """
        if self._run_started:
            raise RuntimeError("a lifecycle observer must be attached before the session starts")
        if self._lifecycle_observer is not None:
            raise RuntimeError("a provider session accepts only one lifecycle observer")
        self._lifecycle_observer = observer
        await self._notify_lifecycle(self._task_submitted)

    async def attach_model_usage_observer(self, observer: ModelUsageObserver) -> None:
        """Attach one transcript-only usage observer before provider work starts.

        Args:
            observer: Async evidence boundary called for at most one admitted usage value.

        Raises:
            RuntimeError: If work started or an observer was already attached.
        """
        if self._run_started:
            raise RuntimeError("a usage observer must be attached before the session starts")
        if self._usage_observer is not None:
            raise RuntimeError("a provider session accepts only one usage observer")
        self._usage_observer = observer

    async def run(self) -> SessionId:
        """Run one provider-neutral turn and settle its selected outcome.

        Returns:
            This session's stable identity after success, failure, cancellation, or teardown.

        Raises:
            RuntimeError: If this session object is run more than once.
            OSError: If the protocol sink cannot publish an admitted event.
            asyncio.CancelledError: After outer cancellation has stopped and joined provider work.
        """
        if self._run_started:
            raise RuntimeError("a provider session can run only once")
        self._run_started = True

        try:
            await _settle_shielded(self._publish_started())
            await self._start_provider_operation()
            if self._selection is None:
                await self._consume_provider_events()
            if self._selection is None:
                await self._select_invalid_response()
            await self._join_finalization()
        except asyncio.CancelledError:
            if not self._session_start_settled.is_set():
                self._session_start_settled.set()
            cleanup = asyncio.create_task(self._settle_outer_teardown())
            try:
                await _wait_shielded(cleanup)
            except asyncio.CancelledError:
                pass
            raise
        except Exception:
            if not self._session_start_settled.is_set():
                self._session_start_settled.set()
            if self._selection is None:
                await _settle_shielded(self._select_teardown())
            task = self._finalization_task
            if task is not None and not task.done():
                try:
                    await _join_shared(task)
                except Exception:
                    pass
            raise
        return self._session_id

    async def request_cancellation(self, command_id: CommandId) -> CancellationRequestResult:
        """Select user cancellation and await the shared provider cleanup path.

        Args:
            command_id: Validated cancellation command that correlates a winning terminal event.

        Returns:
            ``accepted`` when this request won, ``already_requested`` after the same user outcome,
            or ``terminal`` after completion, failure, or teardown already won.
        """
        return await _settle_shielded(self._request_cancellation_and_join(command_id))

    async def request_teardown(self) -> TeardownRequestResult:
        """Stop provider work without fabricating a user-cancelled session event.

        Returns:
            ``accepted`` when teardown won, ``already_requested`` after prior teardown, or
            ``terminal`` when a user-visible outcome already owns finalization.
        """
        return await _settle_shielded(self._request_teardown_and_join())

    async def _request_cancellation_and_join(
        self,
        command_id: CommandId,
    ) -> CancellationRequestResult:
        """Settle one user cancellation request and its selected finalizer as owned work."""
        result = await self._select_user_cancellation(command_id)
        if self._run_started:
            await self._join_finalization()
        return result

    async def _request_teardown_and_join(self) -> TeardownRequestResult:
        """Settle one teardown request and its selected finalizer as owned work."""
        result = await self._select_teardown()
        if self._run_started:
            await self._join_finalization()
        return result

    async def _settle_outer_teardown(self) -> None:
        """Join provider cleanup after cancellation of the session's owning task."""
        await self._select_teardown()
        await self._join_finalization()

    async def _publish_started(self) -> None:
        async with self._decision_lock:
            started = await self._writer.emit_session(
                "session.started",
                self._session_id,
                {},
                correlation_id=self._command.command_id,
            )
            await self._accept_lifecycle_locked(started)
            if self._deferred_cancellation is not None:
                await self._accept_lifecycle_locked(self._deferred_cancellation)
                self._deferred_cancellation = None
            self._session_started_successfully = True
            self._session_start_settled.set()

    async def _start_provider_operation(self) -> None:
        """Atomically start and claim one lazy operation unless an outcome already won."""
        async with self._decision_lock:
            if self._selection is not None:
                return
            try:
                operation = self._provider.start(self._request)
                self._operation = operation
                events = operation.events()
            except (asyncio.CancelledError, Exception):
                self._select_locked(
                    _SelectedOutcome(
                        kind="failed",
                        cleanup_mode="cancel",
                        failure_code=PROVIDER_INVALID_RESPONSE_CODE,
                        failure_message=PROVIDER_INVALID_RESPONSE_MESSAGE,
                        correlation_id=self._command.command_id,
                    )
                )
                return
            self._events = events

    async def _consume_provider_events(self) -> None:
        events = self._events
        if events is None:
            return
        while self._selection is None:
            pending = asyncio.create_task(_next_provider_event(events))
            self._pending_event_task = pending
            try:
                observation = await asyncio.shield(pending)
            except StopAsyncIteration:
                self._pending_event_task = None
                if self._selection is None:
                    await self._select_invalid_response()
                return
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                self._pending_event_task = None
                await self._select_invalid_response()
                return
            except Exception:
                self._pending_event_task = None
                await self._select_invalid_response()
                return
            self._pending_event_task = None
            await _settle_shielded(self._accept_observation(observation))

    async def _accept_observation(self, observation: ProviderStreamEvent) -> None:
        async with self._decision_lock:
            if self._selection is not None:
                return
            if isinstance(observation, ProviderTextDelta):
                if self._completed_text is not None or self._usage_observed:
                    self._select_invalid_response_locked()
                    return
                try:
                    encoded_length = len(observation.text.encode("utf-8"))
                except UnicodeEncodeError:
                    self._select_invalid_response_locked()
                    return
                if self._accepted_text_bytes + encoded_length > MAX_PROVIDER_TURN_OUTPUT_BYTES:
                    self._select_invalid_response_locked()
                    return
                delta = await self._writer.emit_session(
                    "assistant.delta",
                    self._session_id,
                    {"text": observation.text},
                    correlation_id=self._command.command_id,
                )
                await self._accept_lifecycle_locked(delta)
                self._accepted_text.append(observation.text)
                self._accepted_text_bytes += encoded_length
                return

            if isinstance(observation, ProviderTextCompleted):
                if (
                    self._completed_text is not None
                    or self._usage_observed
                    or observation.text != "".join(self._accepted_text)
                ):
                    self._select_invalid_response_locked()
                    return
                self._completed_text = observation.text
                return

            if isinstance(observation, ProviderUsageReported):
                if self._completed_text is None or not self._accepted_text or self._usage_observed:
                    self._select_invalid_response_locked()
                    return
                try:
                    usage = ModelUsageObserved(
                        session_id=self._session_id,
                        input_tokens=observation.input_tokens,
                        output_tokens=observation.output_tokens,
                    )
                except (TypeError, ValueError):
                    self._select_invalid_response_locked()
                    return
                if self._usage_observer is not None:
                    await self._usage_observer(usage)
                self._usage_observed = True
                return

            if isinstance(observation, ProviderCompleted):
                if self._completed_text is None or not self._accepted_text:
                    self._select_invalid_response_locked()
                    return
                self._select_locked(
                    _SelectedOutcome(
                        kind="completed",
                        cleanup_mode="wait_closed",
                        correlation_id=self._command.command_id,
                    )
                )
                return

            if isinstance(observation, ProviderFailed):
                self._select_locked(
                    _SelectedOutcome(
                        kind="failed",
                        cleanup_mode="wait_closed",
                        failure_code=f"provider_{observation.failure.code}",
                        failure_message=observation.failure.message,
                        correlation_id=self._command.command_id,
                    )
                )
                return

            if isinstance(observation, ProviderToolCallRequested):
                self._select_locked(
                    _SelectedOutcome(
                        kind="failed",
                        cleanup_mode="cancel",
                        failure_code=TOOL_UNAVAILABLE_CODE,
                        failure_message=TOOL_UNAVAILABLE_MESSAGE,
                        correlation_id=self._command.command_id,
                    )
                )
                return

            self._select_invalid_response_locked()

    async def _select_user_cancellation(
        self,
        command_id: CommandId,
    ) -> CancellationRequestResult:
        async with self._decision_lock:
            if self._selection is not None:
                return "already_requested" if self._selection.kind == "cancelled" else "terminal"
            cancellation = CancelRequested(command_id=command_id, session_id=self._session_id)
            if self._lifecycle_state.status == "starting":
                self._deferred_cancellation = cancellation
            else:
                await self._accept_lifecycle_locked(cancellation)
            self._select_locked(
                _SelectedOutcome(
                    kind="cancelled",
                    cleanup_mode="cancel",
                    correlation_id=command_id,
                )
            )
            return "accepted"

    async def _select_teardown(self) -> TeardownRequestResult:
        async with self._decision_lock:
            if self._selection is not None:
                return "already_requested" if self._selection.kind == "teardown" else "terminal"
            self._select_locked(
                _SelectedOutcome(
                    kind="teardown",
                    cleanup_mode="cancel",
                )
            )
            return "accepted"

    async def _select_invalid_response(self) -> None:
        await _settle_shielded(self._select_invalid_response_transaction())

    async def _select_invalid_response_transaction(self) -> None:
        async with self._decision_lock:
            self._select_invalid_response_locked()

    def _select_invalid_response_locked(self) -> None:
        self._select_locked(
            _SelectedOutcome(
                kind="failed",
                cleanup_mode="cancel",
                failure_code=PROVIDER_INVALID_RESPONSE_CODE,
                failure_message=PROVIDER_INVALID_RESPONSE_MESSAGE,
                correlation_id=self._command.command_id,
            )
        )

    def _select_locked(self, selection: _SelectedOutcome) -> None:
        if self._selection is not None:
            return
        self._selection = selection
        self._finalization_task = asyncio.create_task(self._finalize(selection))

    async def _join_finalization(self) -> None:
        task = self._finalization_task
        if task is not None:
            await _join_shared(task)

    async def _finalize(self, selection: _SelectedOutcome) -> None:
        if selection.kind != "teardown":
            await self._session_start_settled.wait()
            if not self._session_started_successfully:
                return
        cleanup_failed = await self._finish_provider_work(selection.cleanup_mode)
        if cleanup_failed:
            await self._report_cleanup_failure_once()
        if selection.kind == "teardown":
            return
        await self._emit_selected_terminal(selection)

    async def _finish_provider_work(self, cleanup_mode: _CleanupMode) -> bool:
        operation = self._operation
        cleanup_failed = False
        if operation is not None:
            try:
                if cleanup_mode == "cancel":
                    await operation.cancel()
                else:
                    await operation.wait_closed()
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                cleanup_failed = True
            except Exception:
                cleanup_failed = True
        pending = self._pending_event_task
        if pending is not None:
            if not pending.done():
                pending.cancel()
            try:
                await asyncio.shield(pending)
            except (StopAsyncIteration, asyncio.CancelledError):
                pass
            except Exception:
                cleanup_failed = True
            self._pending_event_task = None
        return cleanup_failed

    async def _report_cleanup_failure_once(self) -> None:
        if self._cleanup_diagnostic_emitted:
            return
        self._cleanup_diagnostic_emitted = True
        await self._writer.emit_runtime(
            "runtime.error",
            {
                "code": PROVIDER_CLEANUP_FAILED_CODE,
                "message": PROVIDER_CLEANUP_FAILED_MESSAGE,
                "recoverable": True,
            },
            correlation_id=self._command.command_id,
        )

    async def _emit_selected_terminal(self, selection: _SelectedOutcome) -> None:
        async with self._decision_lock:
            if self._terminal_emitted or self._selection is not selection:
                return
            if selection.kind == "completed":
                if self._completed_text is None:
                    raise RuntimeError("completed provider session is missing reconciled text")
                assistant_completed = await self._writer.emit_session(
                    "assistant.completed",
                    self._session_id,
                    {"text": self._completed_text},
                    correlation_id=self._command.command_id,
                )
                await self._accept_lifecycle_locked(assistant_completed)
                session_completed = await self._writer.emit_session(
                    "session.completed",
                    self._session_id,
                    {},
                    correlation_id=self._command.command_id,
                )
                await self._accept_lifecycle_locked(session_completed)
            elif selection.kind == "failed":
                if selection.failure_code is None or selection.failure_message is None:
                    raise RuntimeError("failed provider session is missing its safe failure")
                session_failed = await self._writer.emit_session(
                    "session.failed",
                    self._session_id,
                    {
                        "code": selection.failure_code,
                        "message": selection.failure_message,
                    },
                    correlation_id=self._command.command_id,
                )
                await self._accept_lifecycle_locked(session_failed)
            elif selection.kind == "cancelled":
                if selection.correlation_id is None:
                    raise RuntimeError("cancelled provider session is missing command correlation")
                session_cancelled = await self._writer.emit_session(
                    "session.cancelled",
                    self._session_id,
                    {},
                    correlation_id=selection.correlation_id,
                )
                await self._accept_lifecycle_locked(session_cancelled)
            else:
                raise RuntimeError("teardown cannot emit a session terminal event")
            self._terminal_emitted = True

    async def _accept_lifecycle_locked(self, update: SessionUpdate) -> None:
        reduction = reduce_session_state(self._lifecycle_state, update)
        if not reduction.ok:
            raise _lifecycle_invariant_error(reduction.failure)
        self._lifecycle_state = reduction.state
        await self._notify_lifecycle(update)

    async def _notify_lifecycle(self, update: SessionUpdate) -> None:
        if self._lifecycle_observer is not None:
            await self._lifecycle_observer(update, self._lifecycle_state)


def _lifecycle_invariant_error(failure: SessionInvariantFailure | None) -> RuntimeError:
    """Build a safe integration error without copying session or provider payloads."""
    if failure is None:
        return RuntimeError("session lifecycle reduction failed without a classification")
    return RuntimeError(
        "session lifecycle invariant failed: "
        f"code={failure.code} prior_status={failure.prior_status} "
        f"event_type={failure.event_type}"
    )


class ProviderSessionRunner:
    """Allocate serialized provider-backed sessions through one injected provider."""

    def __init__(
        self,
        writer: OrderedEventWriter,
        provider: Provider,
        repository_instructions: tuple[RepositoryInstruction, ...] = (),
    ) -> None:
        """Create a provider-backed session factory for one runtime.

        Args:
            writer: Runtime-owned validated ordered event writer.
            provider: Provider implementation used by every allocated session.
            repository_instructions: Ordered, already-resolved guidance supplied to each turn.
        """
        if not isinstance(provider, Provider):
            raise TypeError("provider session runner requires a provider implementation")
        if not isinstance(repository_instructions, tuple):
            raise TypeError("repository instructions must be a tuple")
        if not all(
            isinstance(instruction, RepositoryInstruction)
            for instruction in repository_instructions
        ):
            raise TypeError("repository instructions contain an unsupported value")
        self._writer = writer
        self._provider = provider
        self._repository_instructions = repository_instructions
        self._session_count = 0

    def create(self, command: SessionStartCommand) -> ProviderSession:
        """Allocate one provider-backed session with a fresh runtime-local identity.

        Args:
            command: Accepted task command used to construct the provider request.

        Returns:
            A single-use provider-backed session ready for observer attachment.
        """
        self._session_count += 1
        session_id = SessionId(f"ses_provider_{self._session_count}")
        return ProviderSession(
            self._writer,
            self._provider,
            command,
            session_id,
            self._repository_instructions,
        )


__all__ = [
    "MAX_PROVIDER_TURN_OUTPUT_BYTES",
    "CancellationRequestResult",
    "LifecycleObserver",
    "ModelUsageObserver",
    "ProviderSession",
    "ProviderSessionRunner",
    "TeardownRequestResult",
]
