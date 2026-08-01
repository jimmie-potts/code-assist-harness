"""One provider-neutral model turn owned by the harness session lifecycle."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from .loop_limits import (
    ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE,
    MODEL_TURN_LIMIT_EXCEEDED_CODE,
    PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,
    TOOL_CALL_LIMIT_EXCEEDED_CODE,
    LoopLimits,
    LoopLimitsObserved,
    LoopLimitTracker,
)
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

PROVIDER_CLEANUP_GRACE_SECONDS = 5.0
"""Fixed local grace for a cancellation-responsive provider cleanup awaitable."""

PROVIDER_INVALID_RESPONSE_CODE = "provider_invalid_response"
PROVIDER_INVALID_RESPONSE_MESSAGE = "The provider returned an invalid response."
TOOL_UNAVAILABLE_CODE = "tool_unavailable"
TOOL_UNAVAILABLE_MESSAGE = "Provider-requested tools are not available."
PROVIDER_CLEANUP_FAILED_CODE = "provider_cleanup_failed"
PROVIDER_CLEANUP_FAILED_MESSAGE = "Provider cleanup could not be confirmed."
MODEL_TURN_LIMIT_EXCEEDED_MESSAGE = "The model-turn limit was reached."
PROVIDER_WORK_DEADLINE_EXCEEDED_MESSAGE = "Provider work exceeded its time limit."
ASSISTANT_OUTPUT_LIMIT_EXCEEDED_MESSAGE = "Assistant output exceeded its byte limit."
TOOL_CALL_LIMIT_EXCEEDED_MESSAGE = "The provider tool-call limit was reached."

type LifecycleObserver = Callable[[SessionUpdate, SessionState], Awaitable[None]]
"""Async observer called after one update enters authoritative lifecycle state."""

type ModelUsageObserver = Callable[[ModelUsageObserved], Awaitable[None]]
"""Async observer for bounded usage evidence outside lifecycle state."""

type LoopLimitsObserver = Callable[[LoopLimitsObserved], Awaitable[None]]
"""Async observer for one terminal-adjacent loop-limit evidence record."""

type MonotonicClock = Callable[[], float]
"""Injected monotonic clock used for provider and cleanup deadlines."""

type MonotonicWaiter = Callable[[float], Awaitable[None]]
"""Injected waiter for one absolute deadline in the clock's domain."""

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


async def _wait_until_monotonic(deadline: float) -> None:
    """Wait until one absolute system-monotonic deadline."""
    await asyncio.sleep(max(0.0, deadline - time.monotonic()))


def _read_monotonic_clock(clock: MonotonicClock) -> float:
    """Return one finite numeric monotonic reading from an injected clock."""
    value = clock()
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("provider session monotonic clock must return a number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("provider session monotonic clock must return a finite number")
    return numeric


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
        *,
        limits: LoopLimits | None = None,
        limit_tracker: LoopLimitTracker | None = None,
        monotonic_now: MonotonicClock | None = None,
        monotonic_waiter: MonotonicWaiter | None = None,
    ) -> None:
        """Create one not-yet-started provider-backed session.

        Args:
            writer: Runtime-owned validated ordered event writer.
            provider: Provider-neutral operation factory injected at composition time.
            command: Accepted task command that correlates normal and failed events.
            session_id: Python-owned identity allocated before work starts.
            repository_instructions: Ordered, already-resolved guidance for this turn.
            limits: Immutable provider-loop budgets shared by configuration value.
            limit_tracker: Optional pre-seeded tracker for deterministic boundary tests.
            monotonic_now: Clock used to capture and recheck absolute deadlines.
            monotonic_waiter: Cancellation-responsive waiter for absolute deadlines.
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
        configured_limits = LoopLimits() if limits is None else limits
        if not isinstance(configured_limits, LoopLimits):
            raise TypeError("provider session limits must be LoopLimits")
        tracker = LoopLimitTracker(configured_limits) if limit_tracker is None else limit_tracker
        if not isinstance(tracker, LoopLimitTracker):
            raise TypeError("provider session tracker must be LoopLimitTracker")
        if tracker.limits != configured_limits:
            raise ValueError("provider session tracker limits do not match configuration")
        if tracker.exhausted is not None:
            raise ValueError("provider session tracker must not be pre-exhausted")
        if (monotonic_now is None) != (monotonic_waiter is None):
            raise ValueError(
                "provider session monotonic clock and waiter must be supplied together"
            )
        configured_clock = time.monotonic if monotonic_now is None else monotonic_now
        configured_waiter = _wait_until_monotonic if monotonic_waiter is None else monotonic_waiter
        if not callable(configured_clock):
            raise TypeError("provider session monotonic clock must be callable")
        if not callable(configured_waiter):
            raise TypeError("provider session monotonic waiter must be callable")

        self._writer = writer
        self._provider = provider
        self._command = command
        self._session_id = session_id
        self._request = ProviderRequest(
            conversation=(ProviderMessage(role="user", content=command.payload.task),),
            repository_instructions=repository_instructions,
        )
        self._decision_lock = asyncio.Lock()
        self._deadline_state_lock = asyncio.Lock()
        self._session_start_settled = asyncio.Event()
        self._session_started_successfully = False
        self._run_started = False
        self._lifecycle_observer: LifecycleObserver | None = None
        self._usage_observer: ModelUsageObserver | None = None
        self._limits_observer: LoopLimitsObserver | None = None
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
        self._cleanup_task: asyncio.Task[bool] | None = None
        self._cleanup_mode: _CleanupMode | None = None
        self._selection: _SelectedOutcome | None = None
        self._finalization_task: asyncio.Task[None] | None = None
        self._deadline_watcher_task: asyncio.Task[None] | None = None
        self._deadline_latched = False
        self._terminal_emitted = False
        self._cleanup_diagnostic_emitted = False
        self._limits_observed = False
        self._pending_event_cleanup_failed = False

        self._limits = configured_limits
        self._limit_tracker = tracker
        self._monotonic_now = configured_clock
        self._monotonic_waiter = configured_waiter
        self._provider_work_deadline = (
            _read_monotonic_clock(configured_clock)
            + configured_limits.provider_work_timeout_seconds
        )

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

    async def attach_loop_limits_observer(self, observer: LoopLimitsObserver) -> None:
        """Attach one terminal-adjacent loop-limit evidence observer before work starts.

        Args:
            observer: Async evidence boundary called once immediately before a session terminal.

        Raises:
            RuntimeError: If work started or an observer was already attached.
        """
        if self._run_started:
            raise RuntimeError("a limits observer must be attached before the session starts")
        if self._limits_observer is not None:
            raise RuntimeError("a provider session accepts only one limits observer")
        self._limits_observer = observer

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
        if self._selection is None:
            self._deadline_watcher_task = asyncio.create_task(self._watch_provider_deadline())

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
        """Admit, charge, synchronously start, and claim one lazy provider operation."""
        async with self._decision_lock:
            async with self._deadline_state_lock:
                if self._selection is not None:
                    return
                if self._deadline_latched or self._deadline_is_due():
                    self._latch_provider_deadline_locked()
                    self._select_locked(self._provider_deadline_outcome())
                    return
                if not self._limit_tracker.admit_model_turn():
                    self._select_locked(
                        _SelectedOutcome(
                            kind="failed",
                            cleanup_mode="cancel",
                            failure_code=MODEL_TURN_LIMIT_EXCEEDED_CODE,
                            failure_message=MODEL_TURN_LIMIT_EXCEEDED_MESSAGE,
                            correlation_id=self._command.command_id,
                        )
                    )
                    return
                try:
                    operation = self._provider.start(self._request)
                    self._operation = operation
                    events = operation.events()
                except (asyncio.CancelledError, Exception):
                    if self._deadline_latched or self._deadline_is_due():
                        self._latch_provider_deadline_locked()
                        self._select_locked(self._provider_deadline_outcome())
                    else:
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
                if self._deadline_latched or self._deadline_is_due():
                    self._latch_provider_deadline_locked()
                    self._select_locked(self._provider_deadline_outcome())
                    return
                self._events = events

    async def _consume_provider_events(self) -> None:
        events = self._events
        watcher = self._deadline_watcher_task
        if events is None or watcher is None:
            return
        while self._selection is None:
            pending = asyncio.create_task(_next_provider_event(events))
            self._pending_event_task = pending
            try:
                await asyncio.wait(
                    {pending, watcher},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                await self._select_invalid_response()
                return

            if self._deadline_latched or self._deadline_is_due():
                await self._cancel_and_reap_pending_event()
                await self._select_provider_deadline()
                return

            if not pending.done():
                # Finalization may stop the watcher while this read is still blocked. Retain the
                # operation-owned task so the selected finalizer can cancel and reap it.
                await self._select_invalid_response()
                return

            try:
                observation = pending.result()
            except StopAsyncIteration:
                self._pending_event_task = None
                if self._selection is None:
                    await self._select_invalid_response()
                return
            except asyncio.CancelledError:
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
            if await self._select_deadline_if_due_locked():
                return
            if isinstance(observation, ProviderTextDelta):
                if self._completed_text is not None or self._usage_observed:
                    await self._select_invalid_response_locked()
                    return
                try:
                    encoded_length = len(observation.text.encode("utf-8"))
                except UnicodeEncodeError:
                    await self._select_invalid_response_locked()
                    return
                async with self._deadline_state_lock:
                    if self._selection is not None:
                        return
                    if self._deadline_latched or self._deadline_is_due():
                        self._latch_provider_deadline_locked()
                        self._select_locked(self._provider_deadline_outcome())
                        return
                    if not self._limit_tracker.reserve_assistant_output(encoded_length):
                        self._select_locked(
                            _SelectedOutcome(
                                kind="failed",
                                cleanup_mode="cancel",
                                failure_code=ASSISTANT_OUTPUT_LIMIT_EXCEEDED_CODE,
                                failure_message=ASSISTANT_OUTPUT_LIMIT_EXCEEDED_MESSAGE,
                                correlation_id=self._command.command_id,
                            )
                        )
                        return
                if self._accepted_text_bytes + encoded_length > MAX_PROVIDER_TURN_OUTPUT_BYTES:
                    await self._select_invalid_response_locked()
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
                await self._select_deadline_if_due_locked()
                return

            if isinstance(observation, ProviderTextCompleted):
                if (
                    self._completed_text is not None
                    or self._usage_observed
                    or observation.text != "".join(self._accepted_text)
                ):
                    await self._select_invalid_response_locked()
                    return
                self._completed_text = observation.text
                return

            if isinstance(observation, ProviderUsageReported):
                if self._completed_text is None or not self._accepted_text or self._usage_observed:
                    await self._select_invalid_response_locked()
                    return
                try:
                    usage = ModelUsageObserved(
                        session_id=self._session_id,
                        input_tokens=observation.input_tokens,
                        output_tokens=observation.output_tokens,
                    )
                except (TypeError, ValueError):
                    await self._select_invalid_response_locked()
                    return
                if self._usage_observer is not None:
                    await self._usage_observer(usage)
                self._usage_observed = True
                await self._select_deadline_if_due_locked()
                return

            if isinstance(observation, ProviderCompleted):
                if self._completed_text is None or not self._accepted_text:
                    await self._select_invalid_response_locked()
                    return
                await self._select_candidate_locked(
                    _SelectedOutcome(
                        kind="completed",
                        cleanup_mode="wait_closed",
                        correlation_id=self._command.command_id,
                    )
                )
                return

            if isinstance(observation, ProviderFailed):
                await self._select_candidate_locked(
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
                async with self._deadline_state_lock:
                    if self._selection is not None:
                        return
                    if self._deadline_latched or self._deadline_is_due():
                        self._latch_provider_deadline_locked()
                        self._select_locked(self._provider_deadline_outcome())
                        return
                    if not self._limit_tracker.observe_tool_call():
                        self._select_locked(
                            _SelectedOutcome(
                                kind="failed",
                                cleanup_mode="cancel",
                                failure_code=TOOL_CALL_LIMIT_EXCEEDED_CODE,
                                failure_message=TOOL_CALL_LIMIT_EXCEEDED_MESSAGE,
                                correlation_id=self._command.command_id,
                            )
                        )
                    else:
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

            await self._select_invalid_response_locked()

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
            selected = await self._select_candidate_locked(
                _SelectedOutcome(
                    kind="cancelled",
                    cleanup_mode="cancel",
                    correlation_id=command_id,
                )
            )
            return "accepted" if selected.kind == "cancelled" else "terminal"

    async def _select_teardown(self) -> TeardownRequestResult:
        async with self._decision_lock:
            if self._selection is not None:
                return "already_requested" if self._selection.kind == "teardown" else "terminal"
            selected = await self._select_candidate_locked(
                _SelectedOutcome(
                    kind="teardown",
                    cleanup_mode="cancel",
                )
            )
            return "accepted" if selected.kind == "teardown" else "terminal"

    async def _select_invalid_response(self) -> None:
        await _settle_shielded(self._select_invalid_response_transaction())

    async def _select_invalid_response_transaction(self) -> None:
        async with self._decision_lock:
            await self._select_invalid_response_locked()

    async def _select_invalid_response_locked(self) -> None:
        """Select a safe invalid-response failure unless the provider deadline won."""
        await self._select_candidate_locked(
            _SelectedOutcome(
                kind="failed",
                cleanup_mode="cancel",
                failure_code=PROVIDER_INVALID_RESPONSE_CODE,
                failure_message=PROVIDER_INVALID_RESPONSE_MESSAGE,
                correlation_id=self._command.command_id,
            )
        )

    async def _select_candidate_locked(self, candidate: _SelectedOutcome) -> _SelectedOutcome:
        """Select one candidate under deadline precedence while the decision lock is held."""
        async with self._deadline_state_lock:
            if self._selection is not None:
                return self._selection
            if self._deadline_latched or self._deadline_is_due():
                self._latch_provider_deadline_locked()
                candidate = self._provider_deadline_outcome()
            self._select_locked(candidate)
            return candidate

    async def _select_deadline_if_due_locked(self) -> bool:
        """Select deadline failure when due while the caller owns the decision lock."""
        async with self._deadline_state_lock:
            if self._selection is not None:
                return False
            if not self._deadline_latched and not self._deadline_is_due():
                return False
            self._latch_provider_deadline_locked()
            self._select_locked(self._provider_deadline_outcome())
            return True

    async def _select_provider_deadline(self) -> None:
        """Settle an already-due provider deadline through the shared terminal guard."""
        async with self._decision_lock:
            async with self._deadline_state_lock:
                if self._selection is not None:
                    return
                self._latch_provider_deadline_locked()
                self._select_locked(self._provider_deadline_outcome())

    def _provider_deadline_outcome(self) -> _SelectedOutcome:
        """Build the stable safe failure selected by provider-work expiry."""
        return _SelectedOutcome(
            kind="failed",
            cleanup_mode="cancel",
            failure_code=PROVIDER_WORK_DEADLINE_EXCEEDED_CODE,
            failure_message=PROVIDER_WORK_DEADLINE_EXCEEDED_MESSAGE,
            correlation_id=self._command.command_id,
        )

    def _deadline_is_due(self) -> bool:
        """Return whether the captured provider-work deadline has arrived."""
        return _read_monotonic_clock(self._monotonic_now) >= self._provider_work_deadline

    def _latch_provider_deadline_locked(self) -> None:
        """Latch expiry and begin shared cancellation under the deadline-state guard."""
        if not self._deadline_latched:
            self._deadline_latched = True
            self._limit_tracker.mark_provider_work_exhausted()
        if self._operation is not None:
            self._ensure_provider_cleanup("cancel")

    async def _watch_provider_deadline(self) -> None:
        """Latch provider expiry independently of event publication or stream progress."""
        await self._wait_until(self._provider_work_deadline)
        async with self._deadline_state_lock:
            if self._selection is not None:
                return
            self._latch_provider_deadline_locked()

    async def _wait_until(self, absolute_deadline: float) -> None:
        """Use the paired injected waiter until its clock confirms an absolute deadline."""
        while _read_monotonic_clock(self._monotonic_now) < absolute_deadline:
            await self._monotonic_waiter(absolute_deadline)

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
                await self._stop_deadline_watcher()
                return
        cleanup_failed = await self._finish_provider_work(selection.cleanup_mode)
        if cleanup_failed:
            await self._report_cleanup_failure_once()
        if selection.kind == "teardown":
            return
        await self._emit_selected_terminal(selection)

    async def _finish_provider_work(self, cleanup_mode: _CleanupMode) -> bool:
        await self._stop_deadline_watcher()
        cleanup_failed = self._pending_event_cleanup_failed
        cleanup = self._ensure_provider_cleanup(cleanup_mode)
        if cleanup is not None:
            try:
                cleanup_failed = await _join_shared(cleanup) or cleanup_failed
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                cleanup_failed = True
            except Exception:
                cleanup_failed = True
        await self._cancel_and_reap_pending_event()
        return cleanup_failed or self._pending_event_cleanup_failed

    def _ensure_provider_cleanup(self, cleanup_mode: _CleanupMode) -> asyncio.Task[bool] | None:
        """Return the one loop-owned supervised provider-cleanup task, creating it if needed."""
        if self._operation is None:
            return None
        if self._cleanup_task is not None:
            if self._cleanup_mode != cleanup_mode:
                raise RuntimeError("provider cleanup mode changed after cleanup started")
            return self._cleanup_task
        self._cleanup_mode = cleanup_mode
        self._cleanup_task = asyncio.create_task(self._supervise_provider_cleanup(cleanup_mode))
        return self._cleanup_task

    async def _supervise_provider_cleanup(self, cleanup_mode: _CleanupMode) -> bool:
        """Bound one provider cleanup await by the fixed cancellation-responsive grace."""
        operation = self._operation
        if operation is None:
            return False

        async def invoke_cleanup() -> None:
            if cleanup_mode == "cancel":
                await operation.cancel()
            else:
                await operation.wait_closed()

        cleanup = asyncio.create_task(invoke_cleanup())
        grace_deadline = _read_monotonic_clock(self._monotonic_now) + PROVIDER_CLEANUP_GRACE_SECONDS
        grace = asyncio.create_task(self._wait_until(grace_deadline))
        try:
            await asyncio.wait({cleanup, grace}, return_when=asyncio.FIRST_COMPLETED)
            if cleanup.done():
                try:
                    cleanup.result()
                except asyncio.CancelledError:
                    return True
                except Exception:
                    return True
                return False
            cleanup.cancel()
            try:
                await cleanup
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            return True
        finally:
            if not grace.done():
                grace.cancel()
            try:
                await grace
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    async def _stop_deadline_watcher(self) -> None:
        """Cancel and reap the session-owned deadline watcher after a terminal choice."""
        watcher = self._deadline_watcher_task
        if watcher is None:
            return
        if not watcher.done():
            watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _cancel_and_reap_pending_event(self) -> None:
        """Cancel and await the local read task under the responsive-iterator contract."""
        pending = self._pending_event_task
        if pending is None:
            return
        if not pending.done():
            pending.cancel()
        try:
            await pending
        except (StopAsyncIteration, asyncio.CancelledError):
            pass
        except Exception:
            self._pending_event_cleanup_failed = True
        self._pending_event_task = None

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
                await self._notify_loop_limits_once()
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
                await self._notify_loop_limits_once()
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
                await self._notify_loop_limits_once()
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

    async def _notify_loop_limits_once(self) -> None:
        """Publish one immutable limits snapshot immediately before the session terminal."""
        if self._limits_observed:
            return
        self._limits_observed = True
        if self._limits_observer is not None:
            await self._limits_observer(self._limit_tracker.snapshot(self._session_id))

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
        *,
        limits: LoopLimits | None = None,
        monotonic_now: MonotonicClock | None = None,
        monotonic_waiter: MonotonicWaiter | None = None,
    ) -> None:
        """Create a provider-backed session factory for one runtime.

        Args:
            writer: Runtime-owned validated ordered event writer.
            provider: Provider implementation used by every allocated session.
            repository_instructions: Ordered, already-resolved guidance supplied to each turn.
            limits: Immutable loop budgets copied by value into every allocated session.
            monotonic_now: Clock used to capture session-local provider deadlines.
            monotonic_waiter: Waiter paired with the injected clock domain.
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
        configured_limits = LoopLimits() if limits is None else limits
        if not isinstance(configured_limits, LoopLimits):
            raise TypeError("provider session runner limits must be LoopLimits")
        if (monotonic_now is None) != (monotonic_waiter is None):
            raise ValueError(
                "provider session runner monotonic clock and waiter must be supplied together"
            )
        configured_clock = time.monotonic if monotonic_now is None else monotonic_now
        configured_waiter = _wait_until_monotonic if monotonic_waiter is None else monotonic_waiter
        if not callable(configured_clock):
            raise TypeError("provider session runner monotonic clock must be callable")
        if not callable(configured_waiter):
            raise TypeError("provider session runner monotonic waiter must be callable")
        self._writer = writer
        self._provider = provider
        self._repository_instructions = repository_instructions
        self._limits = configured_limits
        self._monotonic_now = configured_clock
        self._monotonic_waiter = configured_waiter
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
            limits=self._limits,
            limit_tracker=LoopLimitTracker(self._limits),
            monotonic_now=self._monotonic_now,
            monotonic_waiter=self._monotonic_waiter,
        )


__all__ = [
    "MAX_PROVIDER_TURN_OUTPUT_BYTES",
    "CancellationRequestResult",
    "LifecycleObserver",
    "LoopLimitsObserver",
    "MonotonicClock",
    "MonotonicWaiter",
    "ModelUsageObserver",
    "PROVIDER_CLEANUP_GRACE_SECONDS",
    "ProviderSession",
    "ProviderSessionRunner",
    "TeardownRequestResult",
]
