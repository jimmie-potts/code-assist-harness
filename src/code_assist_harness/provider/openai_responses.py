"""Strict foreground OpenAI Responses adapter for one text-only Luna turn."""

from __future__ import annotations

import asyncio
import json
import os
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from typing import Literal, Protocol, cast

import openai
from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from .models import (
    ProviderCompleted,
    ProviderFailed,
    ProviderFailure,
    ProviderRequest,
    ProviderStreamEvent,
    ProviderTextCompleted,
    ProviderTextDelta,
    ProviderUsageReported,
)
from .openai_config import OpenAIProviderConfiguration, validate_openai_environment
from .port import ProviderCancellationResult, ProviderOperation

OPENAI_RESPONSES_BASE_URL = "https://api.openai.com/v1"
"""Only endpoint the CAH-023 client may address."""

OPENAI_MAX_OUTPUT_TOKENS = 8192
"""Provider-side cap covering visible output and any hidden reasoning tokens."""

MAX_SAFE_INTEGER = 9_007_199_254_740_991
"""Largest integer represented exactly by protocol-adjacent JavaScript consumers."""

REPOSITORY_INSTRUCTIONS_PREFIX = "Repository instructions in precedence order (JSON):\n"
"""Stable preamble for ordered repository guidance in one Responses request."""

_FAILURE_DETAILS: dict[str, tuple[str, bool]] = {
    "authentication_failed": ("OpenAI authentication failed. Check OPENAI_API_KEY.", False),
    "rate_limited": ("OpenAI rate limit was reached. Try again later.", True),
    "unavailable": ("OpenAI is temporarily unavailable. Try again later.", True),
    "request_rejected": ("OpenAI rejected the request.", False),
    "invalid_response": ("OpenAI returned an invalid response.", False),
    "unknown": ("OpenAI request failed.", False),
}

type _FailureCode = Literal[
    "authentication_failed",
    "rate_limited",
    "unavailable",
    "request_rejected",
    "invalid_response",
    "unknown",
]
type _OperationState = Literal[
    "active",
    "resources_closing",
    "terminal_pending",
    "closed",
]
type _OwnedWorkKind = Literal["create", "next"]


class InvalidSDKObservation(ValueError):
    """Identify one malformed or unsupported SDK observation without retaining its value."""


class OpenAIAdapterCleanupError(RuntimeError):
    """Report that adapter resource release could not be confirmed safely."""


class _SDKStream(Protocol):
    """Small public SDK stream surface owned by one adapter operation."""

    def __aiter__(self) -> AsyncIterator[object]: ...

    async def close(self) -> None: ...


class _ResponsesResource(Protocol):
    """Async Responses create surface used by deterministic adapter fakes."""

    async def create(self, **arguments: object) -> _SDKStream: ...


class _SDKClient(Protocol):
    """Small async client surface retained inside the concrete adapter."""

    responses: _ResponsesResource

    async def close(self) -> None: ...


type _ClientFactory = Callable[[], _SDKClient]


class OpenAIResponsesProvider:
    """Create lazy operations for the one allowlisted text-stream model.

    The provider retains validated configuration but creates a fresh SDK client only when an
    operation's iterator is consumed. A client and stream are never shared across model turns.

    Args:
        configuration: SDK-free model and credential validation result.
        client_factory: Adapter-local deterministic seam. Production uses the constrained official
            asynchronous client; callers outside adapter tests should omit it.

    Security:
        The credential never enters a provider-neutral request, event, exception message, or repr.
    """

    def __init__(
        self,
        configuration: OpenAIProviderConfiguration,
        *,
        client_factory: _ClientFactory | None = None,
    ) -> None:
        """Retain validated settings and an optional adapter-local client seam."""
        if not isinstance(configuration, OpenAIProviderConfiguration):
            raise TypeError("OpenAI adapter requires validated provider configuration")
        self._configuration = configuration
        self._client_factory = client_factory or _official_client_factory(configuration)

    def start(self, request: ProviderRequest) -> ProviderOperation:
        """Create one synchronous, lazy, I/O-free provider operation.

        Args:
            request: Harness-owned conversation and ordered repository instructions.

        Returns:
            A single-consumer operation that owns one future client and stream.
        """
        if not isinstance(request, ProviderRequest):
            raise TypeError("OpenAI adapter requires a provider request")
        return OpenAIResponsesOperation(
            request,
            self._configuration.model,
            self._client_factory,
        )


class OpenAIResponsesOperation:
    """Own one SDK request, strict event automaton, and shared cleanup path.

    Network work begins only while :meth:`events` is consumed. Natural terminals remain buffered
    until both stream and client close have been attempted. Cancellation and natural completion
    select the same shielded cleanup owner under one state lock.
    """

    def __init__(
        self,
        request: ProviderRequest,
        model: str,
        client_factory: _ClientFactory,
    ) -> None:
        """Capture one immutable request without constructing SDK resources."""
        self._request_arguments = _map_request(request, model)
        self._model = model
        self._client_factory = client_factory
        self._automaton = _ResponsesAutomaton(model)
        self._state: _OperationState = "active"
        self._state_lock = asyncio.Lock()
        self._closed = asyncio.Event()
        self._claimed = False
        self._client: _SDKClient | None = None
        self._stream: _SDKStream | None = None
        self._stream_iterator: AsyncIterator[object] | None = None
        self._owned_task: asyncio.Task[object] | None = None
        self._owned_kind: _OwnedWorkKind | None = None
        self._cleanup_task: asyncio.Task[bool] | None = None
        self._cleanup_failed = False
        self._cancel_selected = False
        self._terminal_queue: deque[ProviderStreamEvent] = deque()

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        """Claim the operation's only provider-neutral event iterator.

        Returns:
            An iterator that never exposes structural SDK observations.

        Raises:
            RuntimeError: If the stream was already claimed.
        """
        if self._claimed:
            raise RuntimeError("OpenAI provider operation stream was already claimed")
        self._claimed = True
        return _OpenAIEventIterator(self)

    async def cancel(self) -> ProviderCancellationResult:
        """Suppress pending output and join the one resource-cleanup task.

        Returns:
            ``cancelled`` if this call selected cancellation, otherwise ``already_closed``.

        Raises:
            OpenAIAdapterCleanupError: If resource release could not be confirmed.
            asyncio.CancelledError: If this joiner is cancelled; cleanup continues shielded.
        """
        selected = False
        async with self._state_lock:
            if self._state == "closed":
                cleanup = self._cleanup_task
            else:
                selected = not self._cancel_selected
                self._cancel_selected = True
                self._terminal_queue.clear()
                if self._state == "terminal_pending":
                    self._state = "closed"
                    self._closed.set()
                else:
                    self._state = "resources_closing"
                cleanup = self._ensure_cleanup_locked()

        if cleanup is not None:
            await _join_cleanup(cleanup)
        await self._settle_cancelled_state()
        if self._cleanup_failed:
            raise OpenAIAdapterCleanupError(
                "OpenAI adapter resource cleanup could not be confirmed."
            )
        return "cancelled" if selected else "already_closed"

    async def wait_closed(self) -> None:
        """Wait until no later provider event exists and resource cleanup has settled.

        Raises:
            OpenAIAdapterCleanupError: If logical closure completed but resource release failed.
            asyncio.CancelledError: If this joiner is cancelled; shared cleanup remains active.
        """
        await self._closed.wait()
        cleanup = self._cleanup_task
        if cleanup is not None:
            await _join_cleanup(cleanup)
        if self._cleanup_failed:
            raise OpenAIAdapterCleanupError(
                "OpenAI adapter resource cleanup could not be confirmed."
            )

    async def _next_event(self) -> ProviderStreamEvent:
        while True:
            async with self._state_lock:
                if self._state == "closed":
                    raise StopAsyncIteration
                if self._state == "terminal_pending":
                    if not self._terminal_queue:
                        raise RuntimeError("OpenAI adapter terminal queue is empty")
                    event = self._terminal_queue.popleft()
                    if not self._terminal_queue:
                        self._state = "closed"
                        self._closed.set()
                    return event
                if self._state == "resources_closing":
                    cleanup = self._cleanup_task
                else:
                    cleanup = None

            if cleanup is not None:
                await _join_cleanup(cleanup)
                await self._install_terminal_after_cleanup()
                continue

            observation = await self._read_sdk_observation()
            if observation is _OPERATION_CANCELLED:
                raise StopAsyncIteration
            if isinstance(observation, ProviderStreamEventMarker):
                async with self._state_lock:
                    if self._state != "active":
                        raise StopAsyncIteration
                    return observation.event
            await self._finish_terminal(observation)

    async def _read_sdk_observation(
        self,
    ) -> ProviderStreamEventMarker | tuple[ProviderStreamEvent, ...] | _OperationCancelled:
        try:
            if self._client is None:
                self._client = self._client_factory()
            if self._stream is None:
                created = await self._run_owned(
                    "create",
                    lambda: self._client.responses.create(**self._request_arguments),
                )
                if created is _OPERATION_CANCELLED:
                    return _OPERATION_CANCELLED
                self._stream = cast(_SDKStream, created)
                self._stream_iterator = _claim_stream_iterator(self._stream)

            iterator = self._stream_iterator
            if iterator is None:
                raise InvalidSDKObservation
            raw = await self._run_owned("next", iterator.__anext__)
            if raw is _OPERATION_CANCELLED:
                return _OPERATION_CANCELLED
            mapped = self._automaton.accept(raw)
        except asyncio.CancelledError:
            raise
        except StopAsyncIteration:
            return (_failed("invalid_response"),)
        except Exception as error:
            return (_normalize_exception(error),)

        if not mapped:
            return await self._read_sdk_observation()
        if len(mapped) == 1 and isinstance(mapped[0], (ProviderTextDelta, ProviderTextCompleted)):
            return ProviderStreamEventMarker(mapped[0])
        return mapped

    async def _run_owned(
        self,
        kind: _OwnedWorkKind,
        operation: Callable[[], Awaitable[object]],
    ) -> object | _OperationCancelled:
        async with self._state_lock:
            if self._state != "active":
                return _OPERATION_CANCELLED
            if self._owned_task is not None:
                raise RuntimeError("OpenAI adapter attempted concurrent SDK work")
            task = asyncio.create_task(operation())
            self._owned_task = task
            self._owned_kind = kind
        try:
            return await task
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            async with self._state_lock:
                if self._cancel_selected or self._state != "active":
                    return _OPERATION_CANCELLED
            raise _IndependentSDKCancellation from None
        finally:
            async with self._state_lock:
                if self._owned_task is task:
                    self._owned_task = None
                    self._owned_kind = None

    async def _finish_terminal(self, events: tuple[ProviderStreamEvent, ...]) -> None:
        async with self._state_lock:
            if self._state != "active":
                return
            self._terminal_queue = deque(events)
            self._state = "resources_closing"
            cleanup = self._ensure_cleanup_locked()
        await _join_cleanup(cleanup)
        await self._install_terminal_after_cleanup()

    async def _install_terminal_after_cleanup(self) -> None:
        async with self._state_lock:
            if self._state != "resources_closing":
                return
            if self._cancel_selected:
                self._terminal_queue.clear()
                self._state = "closed"
                self._closed.set()
                return
            if self._cleanup_failed and any(
                isinstance(event, ProviderCompleted) for event in self._terminal_queue
            ):
                self._terminal_queue = deque((_failed("unknown"),))
            if not self._terminal_queue:
                self._terminal_queue = deque((_failed("unknown"),))
            self._state = "terminal_pending"

    def _ensure_cleanup_locked(self) -> asyncio.Task[bool]:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_resources())
        return self._cleanup_task

    async def _cleanup_resources(self) -> bool:
        failed = False
        task: asyncio.Task[object] | None
        kind: _OwnedWorkKind | None
        async with self._state_lock:
            task = self._owned_task
            kind = self._owned_kind
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            try:
                result = await task
            except asyncio.CancelledError:
                if _current_task_is_cancelling():
                    raise
                result = None
            except Exception:
                result = None
            if kind == "create" and result is not None and self._stream is None:
                self._stream = cast(_SDKStream, result)
                try:
                    self._stream_iterator = _claim_stream_iterator(self._stream)
                except InvalidSDKObservation:
                    failed = True

        stream = self._stream
        client = self._client
        try:
            if stream is not None:
                try:
                    await stream.close()
                except asyncio.CancelledError:
                    if _current_task_is_cancelling():
                        raise
                    failed = True
                except Exception:
                    failed = True
        finally:
            if client is not None:
                try:
                    await client.close()
                except asyncio.CancelledError:
                    if _current_task_is_cancelling():
                        raise
                    failed = True
                except Exception:
                    failed = True

        async with self._state_lock:
            self._cleanup_failed = failed
            if self._cancel_selected and self._state == "resources_closing":
                self._terminal_queue.clear()
                self._state = "closed"
                self._closed.set()
        return failed

    async def _settle_cancelled_state(self) -> None:
        async with self._state_lock:
            if self._cancel_selected and self._state != "closed":
                self._terminal_queue.clear()
                self._state = "closed"
                self._closed.set()

    async def _select_consumer_cancellation(self) -> None:
        """Close logically and start resource cleanup when the event consumer is cancelled."""
        async with self._state_lock:
            if self._state == "closed":
                return
            self._cancel_selected = True
            self._terminal_queue.clear()
            self._state = "closed"
            self._closed.set()
            self._ensure_cleanup_locked()


class _OpenAIEventIterator:
    """Custom iterator that closes atomically when returning its final event."""

    def __init__(self, operation: OpenAIResponsesOperation) -> None:
        self._operation = operation

    def __aiter__(self) -> _OpenAIEventIterator:
        return self

    async def __anext__(self) -> ProviderStreamEvent:
        try:
            event = await self._operation._next_event()
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise asyncio.CancelledError
            return event
        except asyncio.CancelledError:
            transition = asyncio.create_task(self._operation._select_consumer_cancellation())
            await _settle_state_transition(transition)
            raise


class ProviderStreamEventMarker:
    """Distinguish one public progress event from a buffered terminal tuple."""

    def __init__(self, event: ProviderTextDelta | ProviderTextCompleted) -> None:
        self.event = event


class _OperationCancelled:
    """Private sentinel for cleanup-selected cancellation of owned SDK work."""


_OPERATION_CANCELLED = _OperationCancelled()


class _IndependentSDKCancellation(RuntimeError):
    """Normalize an SDK awaitable's own cancellation as provider failure, not task control flow."""


class _ResponsesAutomaton:
    """Validate the exact CAH-023 Luna text-stream compatibility subset."""

    def __init__(self, model: str) -> None:
        self._model = model
        self._state = "created"
        self._next_sequence: int | None = None
        self._response_id: str | None = None
        self._reasoning_item_id: str | None = None
        self._item_id: str | None = None
        self._message_output_index = 0
        self._text_fragments: list[str] = []

    def accept(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        """Advance one SDK observation or raise a payload-free contract error."""
        event_type = _required_string(_field(event, "type"))
        self._accept_sequence(_field(event, "sequence_number"))

        if event_type == "error":
            self._state = "terminal"
            return (_failed("unknown"),)
        if self._state == "terminal":
            raise InvalidSDKObservation
        if event_type in {"response.failed", "response.incomplete"}:
            self._accept_response_terminal(event, event_type)
            self._state = "terminal"
            if event_type == "response.incomplete":
                return (_failed("request_rejected"),)
            error = _field(_field(event, "response"), "error")
            code = _optional_string(_optional_field(error, "code"))
            if code == "server_error":
                return (_failed("unavailable"),)
            if code == "rate_limit_exceeded":
                return (_failed("rate_limited"),)
            return (_failed("unknown"),)

        handlers: dict[str, Callable[[object], tuple[ProviderStreamEvent, ...]]] = {
            "response.created": self._created,
            "response.queued": self._queued,
            "response.in_progress": self._in_progress,
            "response.output_item.added": self._output_item_added,
            "response.content_part.added": self._content_part_added,
            "response.output_text.delta": self._text_delta,
            "response.output_text.done": self._text_done,
            "response.content_part.done": self._content_part_done,
            "response.output_item.done": self._output_item_done,
            "response.completed": self._completed,
        }
        handler = handlers.get(event_type)
        if handler is None:
            raise InvalidSDKObservation
        return handler(event)

    def _accept_sequence(self, value: object) -> None:
        sequence = _safe_integer(value)
        if self._next_sequence is None:
            self._next_sequence = sequence + 1
            return
        if sequence != self._next_sequence:
            raise InvalidSDKObservation
        self._next_sequence += 1

    def _created(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("created")
        response = _field(event, "response")
        self._response_id = _required_string(_field(response, "id"))
        self._state = "queued_or_in_progress"
        return ()

    def _queued(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("queued_or_in_progress")
        self._require_response_identity(_field(event, "response"))
        self._state = "in_progress"
        return ()

    def _in_progress(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        if self._state not in {"queued_or_in_progress", "in_progress"}:
            raise InvalidSDKObservation
        self._require_response_identity(_field(event, "response"))
        self._state = "output_item_added"
        return ()

    def _output_item_added(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        if self._state not in {"output_item_added", "message_item_added"}:
            raise InvalidSDKObservation
        item = _field(event, "item")
        if self._state == "output_item_added" and _optional_field(item, "type") == "reasoning":
            _require_index(event, "output_index", 0)
            self._reasoning_item_id = _validate_reasoning_item(item, completed=False)
            self._state = "reasoning_item_done"
            return ()

        self._message_output_index = 1 if self._reasoning_item_id is not None else 0
        _require_index(event, "output_index", self._message_output_index)
        self._item_id = _validate_message(item, content_count=0, completed=False)
        self._state = "content_part_added"
        return ()

    def _content_part_added(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("content_part_added")
        self._require_item_coordinates(event)
        _validate_output_text(_field(event, "part"), expected_text="")
        self._state = "delta"
        return ()

    def _text_delta(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        if self._state not in {"delta", "delta_or_done"}:
            raise InvalidSDKObservation
        self._require_item_coordinates(event)
        _require_absent_or_empty_list(_optional_field(event, "logprobs"))
        delta = _required_string(_field(event, "delta"))
        self._text_fragments.append(delta)
        self._state = "delta_or_done"
        return (ProviderTextDelta(delta),)

    def _text_done(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("delta_or_done")
        self._require_item_coordinates(event)
        _require_absent_or_empty_list(_optional_field(event, "logprobs"))
        text = _required_string(_field(event, "text"), allow_empty=True)
        if text != "".join(self._text_fragments):
            raise InvalidSDKObservation
        self._state = "content_part_done"
        return (ProviderTextCompleted(text),)

    def _content_part_done(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("content_part_done")
        self._require_item_coordinates(event)
        _validate_output_text(_field(event, "part"), expected_text=self._text())
        self._state = "output_item_done"
        return ()

    def _output_item_done(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        if self._state == "reasoning_item_done":
            _require_index(event, "output_index", 0)
            item_id = _validate_reasoning_item(_field(event, "item"), completed=True)
            if item_id != self._reasoning_item_id:
                raise InvalidSDKObservation
            self._state = "message_item_added"
            return ()

        self._require_state("output_item_done")
        _require_index(event, "output_index", self._message_output_index)
        item = _field(event, "item")
        item_id = _validate_message(item, content_count=1, completed=True)
        if item_id != self._item_id:
            raise InvalidSDKObservation
        content = _required_list(_field(item, "content"))
        _validate_output_text(content[0], expected_text=self._text())
        self._state = "completed"
        return ()

    def _completed(self, event: object) -> tuple[ProviderStreamEvent, ...]:
        self._require_state("completed")
        response = _field(event, "response")
        self._require_response_identity(response)
        if _field(response, "status") != "completed":
            raise InvalidSDKObservation
        if _field(response, "model") != self._model:
            raise InvalidSDKObservation
        if _optional_field(response, "error") is not None:
            raise InvalidSDKObservation
        if _optional_field(response, "incomplete_details") is not None:
            raise InvalidSDKObservation
        _validate_reasoning_configuration(_optional_field(response, "reasoning"))
        output = _required_list(_field(response, "output"))
        expected_output_count = 2 if self._reasoning_item_id is not None else 1
        if len(output) != expected_output_count:
            raise InvalidSDKObservation
        if self._reasoning_item_id is not None:
            reasoning_id = _validate_reasoning_item(output[0], completed=True)
            if reasoning_id != self._reasoning_item_id:
                raise InvalidSDKObservation
        message = output[self._message_output_index]
        item_id = _validate_message(message, content_count=1, completed=True)
        if item_id != self._item_id:
            raise InvalidSDKObservation
        content = _required_list(_field(message, "content"))
        _validate_output_text(content[0], expected_text=self._text())

        mapped: list[ProviderStreamEvent] = []
        usage = _optional_field(response, "usage")
        if usage is not None:
            input_tokens = _safe_integer(_field(usage, "input_tokens"))
            output_tokens = _safe_integer(_field(usage, "output_tokens"))
            total_tokens = _safe_integer(_field(usage, "total_tokens"))
            if input_tokens + output_tokens != total_tokens or total_tokens > MAX_SAFE_INTEGER:
                raise InvalidSDKObservation
            output_details = _optional_field(usage, "output_tokens_details")
            if output_details is not None:
                reasoning_tokens = _safe_integer(_field(output_details, "reasoning_tokens"))
                if reasoning_tokens > output_tokens:
                    raise InvalidSDKObservation
            mapped.append(ProviderUsageReported(input_tokens, output_tokens))
        mapped.append(ProviderCompleted())
        self._state = "terminal"
        return tuple(mapped)

    def _accept_response_terminal(self, event: object, event_type: str) -> None:
        if self._response_id is None or self._state == "created":
            raise InvalidSDKObservation
        response = _field(event, "response")
        self._require_response_identity(response)
        expected_status = "failed" if event_type == "response.failed" else "incomplete"
        if _field(response, "status") != expected_status:
            raise InvalidSDKObservation

    def _require_response_identity(self, response: object) -> None:
        if _required_string(_field(response, "id")) != self._response_id:
            raise InvalidSDKObservation

    def _require_item_coordinates(self, event: object) -> None:
        if _required_string(_field(event, "item_id")) != self._item_id:
            raise InvalidSDKObservation
        _require_index(event, "output_index", self._message_output_index)
        _require_index(event, "content_index", 0)

    def _require_state(self, state: str) -> None:
        if self._state != state:
            raise InvalidSDKObservation

    def _text(self) -> str:
        return "".join(self._text_fragments)


def _official_client_factory(configuration: OpenAIProviderConfiguration) -> _ClientFactory:
    """Capture validated configuration in a lazy SDK client builder."""

    def create() -> _SDKClient:
        validate_openai_environment(os.environ)
        http_client = DefaultAsyncHttpxClient(
            trust_env=False,
            follow_redirects=False,
        )
        client = AsyncOpenAI(
            api_key=configuration.api_key,
            base_url=OPENAI_RESPONSES_BASE_URL,
            organization=None,
            project=None,
            max_retries=0,
            http_client=http_client,
        )
        return cast(_SDKClient, client)

    return create


def _map_request(request: ProviderRequest, model: str) -> dict[str, object]:
    mapped: dict[str, object] = {
        "model": model,
        "input": [
            {"role": message.role, "content": message.content} for message in request.conversation
        ],
        "reasoning": {"effort": "none", "context": "current_turn"},
        "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
        "stream": True,
        "background": False,
        "store": False,
    }
    if request.repository_instructions:
        documents = [
            {"source": instruction.source, "content": instruction.content}
            for instruction in request.repository_instructions
        ]
        mapped["instructions"] = REPOSITORY_INSTRUCTIONS_PREFIX + json.dumps(
            documents,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return mapped


def _normalize_exception(error: Exception) -> ProviderFailed:
    if isinstance(
        error,
        (
            InvalidSDKObservation,
            StopAsyncIteration,
            openai.APIResponseValidationError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ),
    ):
        return _failed("invalid_response")
    if isinstance(error, openai.AuthenticationError):
        return _failed("authentication_failed")
    if isinstance(error, openai.RateLimitError):
        return _failed("rate_limited")
    if isinstance(error, (openai.APITimeoutError, openai.APIConnectionError)):
        return _failed("unavailable")
    if isinstance(error, openai.APIStatusError):
        status = error.status_code
        if type(status) is not int:
            return _failed("unknown")
        if status == 401:
            return _failed("authentication_failed")
        if status == 429:
            return _failed("rate_limited")
        if status in {408, 409} or 500 <= status <= 599:
            return _failed("unavailable")
        if 400 <= status <= 499:
            return _failed("request_rejected")
        return _failed("unknown")
    if isinstance(error, openai.OpenAIError):
        return _failed("unknown")
    return _failed("unknown")


def _failed(code: _FailureCode) -> ProviderFailed:
    message, retryable = _FAILURE_DETAILS[code]
    return ProviderFailed(ProviderFailure(code=code, message=message, retryable=retryable))


def _field(value: object, name: str) -> object:
    if isinstance(value, Mapping):
        if name not in value:
            raise InvalidSDKObservation
        return value[name]
    try:
        return getattr(value, name)
    except (AttributeError, TypeError):
        raise InvalidSDKObservation from None


def _claim_stream_iterator(stream: _SDKStream) -> AsyncIterator[object]:
    """Claim one SDK iterator while containing malformed stream implementations."""
    try:
        iterator = stream.__aiter__()
    except Exception:
        raise InvalidSDKObservation from None
    if not hasattr(iterator, "__anext__"):
        raise InvalidSDKObservation
    return iterator


_MISSING = object()


def _optional_field(value: object, name: str, *, default: object = _MISSING) -> object:
    if value is None:
        return None if default is _MISSING else default
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        return None if default is _MISSING else default
    try:
        return getattr(value, name)
    except (AttributeError, TypeError):
        return None if default is _MISSING else default


def _required_string(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise InvalidSDKObservation
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise InvalidSDKObservation from None
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _required_string(value, allow_empty=True)


def _safe_integer(value: object) -> int:
    if type(value) is not int or value < 0 or value > MAX_SAFE_INTEGER:
        raise InvalidSDKObservation
    return value


def _required_list(value: object) -> list[object] | tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise InvalidSDKObservation
    return value


def _require_empty_list(value: object) -> None:
    if _required_list(value):
        raise InvalidSDKObservation


def _require_absent_or_empty_list(value: object) -> None:
    """Accept omitted SDK metadata while rejecting unsupported populated values."""
    if value is not None:
        _require_empty_list(value)


def _require_index(value: object, name: str, expected: int) -> None:
    if _safe_integer(_field(value, name)) != expected:
        raise InvalidSDKObservation


def _validate_output_text(value: object, *, expected_text: str) -> None:
    if _field(value, "type") != "output_text":
        raise InvalidSDKObservation
    if _required_string(_field(value, "text"), allow_empty=True) != expected_text:
        raise InvalidSDKObservation
    _require_empty_list(_field(value, "annotations"))


def _validate_message(value: object, *, content_count: int, completed: bool) -> str:
    if _field(value, "type") != "message" or _field(value, "role") != "assistant":
        raise InvalidSDKObservation
    item_id = _required_string(_field(value, "id"))
    content = _required_list(_field(value, "content"))
    if len(content) != content_count:
        raise InvalidSDKObservation
    expected_status = "completed" if completed else "in_progress"
    status = _field(value, "status")
    if not isinstance(status, str) or status != expected_status:
        raise InvalidSDKObservation
    return item_id


def _validate_reasoning_item(value: object, *, completed: bool) -> str:
    """Validate an opaque Luna reasoning envelope without retaining its encrypted content."""
    if _field(value, "type") != "reasoning":
        raise InvalidSDKObservation
    item_id = _required_string(_field(value, "id"))
    _require_empty_list(_field(value, "summary"))
    _require_absent_or_empty_list(_optional_field(value, "content"))
    status = _optional_field(value, "status")
    expected_status = "completed" if completed else "in_progress"
    if status is not None and (not isinstance(status, str) or status != expected_status):
        raise InvalidSDKObservation
    return item_id


def _validate_reasoning_configuration(value: object) -> None:
    """Confirm any echoed reasoning settings preserve the reviewed Luna request mode."""
    missing = object()
    effort = _field(value, "effort")
    context = _field(value, "context")
    summary = _optional_field(value, "summary", default=missing)
    generate_summary = _optional_field(value, "generate_summary", default=missing)
    mode = _optional_field(value, "mode", default=missing)
    if (
        not isinstance(effort, str)
        or effort != "none"
        or not isinstance(context, str)
        or context != "current_turn"
    ):
        raise InvalidSDKObservation
    if summary is not missing and summary is not None:
        raise InvalidSDKObservation
    if generate_summary is not missing and generate_summary is not None:
        raise InvalidSDKObservation
    if (
        mode is not missing
        and mode is not None
        and (not isinstance(mode, str) or mode != "standard")
    ):
        raise InvalidSDKObservation


def _current_task_is_cancelling() -> bool:
    """Distinguish shared-task cancellation from a close awaitable's own cancellation error."""
    current = asyncio.current_task()
    return current is not None and current.cancelling() > 0


async def _join_cleanup(task: asyncio.Task[bool]) -> bool:
    """Shield the shared cleanup owner from cancellation of any one joiner."""
    return await asyncio.shield(task)


async def _settle_state_transition(task: asyncio.Task[None]) -> None:
    """Finish a short cancellation-state transition despite repeated caller cancellation."""
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            continue
    task.result()


__all__ = [
    "InvalidSDKObservation",
    "OPENAI_MAX_OUTPUT_TOKENS",
    "OPENAI_RESPONSES_BASE_URL",
    "OpenAIAdapterCleanupError",
    "OpenAIResponsesOperation",
    "OpenAIResponsesProvider",
    "REPOSITORY_INSTRUCTIONS_PREFIX",
]
