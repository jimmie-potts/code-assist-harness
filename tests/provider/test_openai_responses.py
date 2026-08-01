from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import dataclass

import httpx
import openai
import pytest

import code_assist_harness.provider.openai_responses as adapter_module
from code_assist_harness.loop_limits import LoopLimits
from code_assist_harness.model_evidence import ModelUsageObserved
from code_assist_harness.protocol import OrderedEventWriter, SessionStartCommand
from code_assist_harness.provider import (
    ProviderCompleted,
    ProviderFailed,
    ProviderMessage,
    ProviderRequest,
    ProviderTextCompleted,
    ProviderTextDelta,
    ProviderUsageReported,
    RepositoryInstruction,
)
from code_assist_harness.provider.openai_config import OpenAIProviderConfiguration
from code_assist_harness.provider.openai_responses import (
    OPENAI_RESPONSES_BASE_URL,
    REPOSITORY_INSTRUCTIONS_PREFIX,
    OpenAIAdapterCleanupError,
    OpenAIResponsesProvider,
)
from code_assist_harness.provider_session import ProviderSession

MODEL = "gpt-4.1-mini-2025-04-14"
API_KEY = "fake-openai-key-for-adapter-tests"
RAW_SECRET = "raw-sdk-secret-that-must-not-cross"


@dataclass
class _FakeResponses:
    stream: _FakeStream | None = None
    error: Exception | None = None
    create_gate: asyncio.Event | None = None
    create_cancel_gate: asyncio.Event | None = None

    def __post_init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def create(self, **arguments: object) -> _FakeStream:
        self.calls.append(arguments)
        self.started.set()
        try:
            if self.create_gate is not None:
                await self.create_gate.wait()
            if self.error is not None:
                raise self.error
            assert self.stream is not None
            return self.stream
        except asyncio.CancelledError:
            self.cancelled.set()
            if self.create_cancel_gate is not None:
                await self.create_cancel_gate.wait()
            raise


class _FakeStream:
    def __init__(
        self,
        events: list[object],
        *,
        next_error: Exception | None = None,
        block_before_index: int | None = None,
        close_error: Exception | None = None,
        close_gate: asyncio.Event | None = None,
        return_event_on_cancel: bool = False,
    ) -> None:
        self._events = events
        self._index = 0
        self._next_error = next_error
        self._block_before_index = block_before_index
        self._close_error = close_error
        self._close_gate = close_gate
        self._return_event_on_cancel = return_event_on_cancel
        self.next_started = asyncio.Event()
        self.blocked_next_started = asyncio.Event()
        self.next_cancelled = asyncio.Event()
        self.close_started = asyncio.Event()
        self.close_finished = asyncio.Event()
        self.close_calls = 0

    def __aiter__(self) -> AsyncIterator[object]:
        return self

    async def __anext__(self) -> object:
        self.next_started.set()
        try:
            if self._block_before_index == self._index:
                self.blocked_next_started.set()
                await asyncio.Event().wait()
            if self._next_error is not None:
                error = self._next_error
                self._next_error = None
                raise error
            if self._index >= len(self._events):
                raise StopAsyncIteration
            event = self._events[self._index]
            self._index += 1
            return event
        except asyncio.CancelledError:
            self.next_cancelled.set()
            if self._return_event_on_cancel and self._index < len(self._events):
                event = self._events[self._index]
                self._index += 1
                return event
            raise

    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        try:
            if self._close_gate is not None:
                await self._close_gate.wait()
            if self._close_error is not None:
                raise self._close_error
        finally:
            self.close_finished.set()


class _MalformedIteratorStream(_FakeStream):
    def __aiter__(self) -> object:
        """Return a value that cannot satisfy the async-iterator contract."""
        return object()


class _FakeClient:
    def __init__(
        self,
        responses: _FakeResponses,
        *,
        close_error: Exception | None = None,
        close_gate: asyncio.Event | None = None,
    ) -> None:
        self.responses = responses
        self._close_error = close_error
        self._close_gate = close_gate
        self.close_calls = 0
        self.close_started = asyncio.Event()
        self.close_finished = asyncio.Event()

    async def close(self) -> None:
        self.close_calls += 1
        self.close_started.set()
        try:
            if self._close_gate is not None:
                await self._close_gate.wait()
            if self._close_error is not None:
                raise self._close_error
        finally:
            self.close_finished.set()


def _configuration() -> OpenAIProviderConfiguration:
    return OpenAIProviderConfiguration(model=MODEL, api_key=API_KEY)


def _clear_unsupported_openai_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in tuple(adapter_module.os.environ):
        if name.startswith("OPENAI_") and name != "OPENAI_API_KEY":
            monkeypatch.delenv(name, raising=False)


def _request(*, instructions: bool = True) -> ProviderRequest:
    return ProviderRequest(
        conversation=(
            ProviderMessage(role="user", content="Explain the boundary."),
            ProviderMessage(role="assistant", content="The harness owns policy."),
            ProviderMessage(role="user", content="Now summarize it."),
        ),
        repository_instructions=(
            (
                RepositoryInstruction(source="AGENTS.md", content="Preserve provider isolation."),
                RepositoryInstruction(source="docs/guide.md", content="Use café examples."),
            )
            if instructions
            else ()
        ),
    )


def _success_events(
    *,
    base: int = 7,
    queued: bool = False,
    usage: tuple[int, int] | None = (11, 5),
) -> list[dict[str, object]]:
    response_id = "resp_fake_023"
    item_id = "msg_fake_023"
    text = "Bounded answer."
    part = {"type": "output_text", "text": text, "annotations": []}
    message = {
        "type": "message",
        "id": item_id,
        "role": "assistant",
        "status": "completed",
        "content": [part],
    }
    events: list[dict[str, object]] = [
        {
            "type": "response.created",
            "sequence_number": base,
            "response": {"id": response_id},
        }
    ]
    if queued:
        events.append(
            {
                "type": "response.queued",
                "sequence_number": 0,
                "response": {"id": response_id},
            }
        )
    events.extend(
        [
            {
                "type": "response.in_progress",
                "sequence_number": 0,
                "response": {"id": response_id},
            },
            {
                "type": "response.output_item.added",
                "sequence_number": 0,
                "output_index": 0,
                "item": {
                    "type": "message",
                    "id": item_id,
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [],
                },
            },
            {
                "type": "response.content_part.added",
                "sequence_number": 0,
                "output_index": 0,
                "content_index": 0,
                "item_id": item_id,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": 0,
                "output_index": 0,
                "content_index": 0,
                "item_id": item_id,
                "delta": "Bounded ",
                "logprobs": [],
            },
            {
                "type": "response.output_text.delta",
                "sequence_number": 0,
                "output_index": 0,
                "content_index": 0,
                "item_id": item_id,
                "delta": "answer.",
                "logprobs": [],
            },
            {
                "type": "response.output_text.done",
                "sequence_number": 0,
                "output_index": 0,
                "content_index": 0,
                "item_id": item_id,
                "text": text,
                "logprobs": [],
            },
            {
                "type": "response.content_part.done",
                "sequence_number": 0,
                "output_index": 0,
                "content_index": 0,
                "item_id": item_id,
                "part": deepcopy(part),
            },
            {
                "type": "response.output_item.done",
                "sequence_number": 0,
                "output_index": 0,
                "item": deepcopy(message),
            },
            {
                "type": "response.completed",
                "sequence_number": 0,
                "response": {
                    "id": response_id,
                    "model": MODEL,
                    "status": "completed",
                    "error": None,
                    "incomplete_details": None,
                    "output": [deepcopy(message)],
                    "usage": (
                        None
                        if usage is None
                        else {
                            "input_tokens": usage[0],
                            "output_tokens": usage[1],
                            "total_tokens": usage[0] + usage[1],
                        }
                    ),
                },
            },
        ]
    )
    for offset, event in enumerate(events):
        event["sequence_number"] = base + offset
    return events


async def _collect(operation) -> list[object]:
    return [event async for event in operation.events()]


def _provider_with(
    stream: _FakeStream,
    *,
    responses_error: Exception | None = None,
    create_gate: asyncio.Event | None = None,
    create_cancel_gate: asyncio.Event | None = None,
    client_close_error: Exception | None = None,
    client_close_gate: asyncio.Event | None = None,
) -> tuple[OpenAIResponsesProvider, _FakeResponses, _FakeClient, list[_FakeClient]]:
    responses = _FakeResponses(stream, responses_error, create_gate, create_cancel_gate)
    client = _FakeClient(
        responses,
        close_error=client_close_error,
        close_gate=client_close_gate,
    )
    created: list[_FakeClient] = []

    def factory() -> _FakeClient:
        created.append(client)
        return client

    return (
        OpenAIResponsesProvider(_configuration(), client_factory=factory),
        responses,
        client,
        created,
    )


def test_success_maps_request_and_stream_without_constructing_resources_early() -> None:
    async def scenario():
        stream = _FakeStream(_success_events(queued=True))
        provider, responses, client, created = _provider_with(stream)
        operation = provider.start(_request())

        assert created == []
        events = await _collect(operation)
        await operation.wait_closed()
        return events, responses, client, stream, created

    events, responses, client, stream, created = asyncio.run(scenario())

    assert events == [
        ProviderTextDelta("Bounded "),
        ProviderTextDelta("answer."),
        ProviderTextCompleted("Bounded answer."),
        ProviderUsageReported(11, 5),
        ProviderCompleted(),
    ]
    assert len(created) == 1
    assert responses.calls == [
        {
            "model": MODEL,
            "input": [
                {"role": "user", "content": "Explain the boundary."},
                {"role": "assistant", "content": "The harness owns policy."},
                {"role": "user", "content": "Now summarize it."},
            ],
            "stream": True,
            "background": False,
            "store": False,
            "instructions": REPOSITORY_INSTRUCTIONS_PREFIX
            + '[{"source":"AGENTS.md","content":"Preserve provider isolation."},'
            '{"source":"docs/guide.md","content":"Use café examples."}]',
        }
    ]
    assert "tools" not in responses.calls[0]
    assert "tool_choice" not in responses.calls[0]
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_empty_repository_instructions_omit_request_field_and_usage() -> None:
    async def scenario():
        stream = _FakeStream(_success_events(usage=None))
        provider, responses, _client, _created = _provider_with(stream)
        events = await _collect(provider.start(_request(instructions=False)))
        return events, responses.calls[0]

    events, arguments = asyncio.run(scenario())

    assert "instructions" not in arguments
    assert events[-1] == ProviderCompleted()
    assert not any(isinstance(event, ProviderUsageReported) for event in events)


@pytest.mark.parametrize("representation", ["omitted", "none", "empty"])
def test_absent_none_or_empty_logprobs_are_compatible(representation: str) -> None:
    async def scenario():
        events = _success_events()
        for event in events:
            if event["type"] not in {"response.output_text.delta", "response.output_text.done"}:
                continue
            if representation == "omitted":
                event.pop("logprobs")
            elif representation == "none":
                event["logprobs"] = None
        stream = _FakeStream(events)
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())

    assert observations[-1] == ProviderCompleted()


@pytest.mark.parametrize(
    ("mutate", "expected_progress"),
    [
        (lambda events: events[1].update(sequence_number=99), []),
        (lambda events: events[1]["response"].update(id="other"), []),
        (lambda events: events[2].update(output_index=1), []),
        (lambda events: events[2]["item"].update(type="reasoning"), []),
        (lambda events: events[2]["item"].update(role="user"), []),
        (lambda events: events[2]["item"].update(content=[{}]), []),
        (lambda events: events[3].update(content_index=1), []),
        (lambda events: events[3]["part"].update(type="refusal"), []),
        (lambda events: events[3]["part"].update(annotations=[{"type": "citation"}]), []),
        (lambda events: events[4].update(delta=""), []),
        (lambda events: events[4].update(logprobs=[{"token": RAW_SECRET}]), []),
        (lambda events: events[4].update(item_id="other"), []),
        (
            lambda events: events[5].update(type="response.function_call_arguments.delta"),
            ["Bounded "],
        ),
        (lambda events: events[6].update(text="mismatch"), ["Bounded ", "answer."]),
        (
            lambda events: events[6].update(logprobs=[{"token": RAW_SECRET}]),
            ["Bounded ", "answer."],
        ),
        (lambda events: events[7]["part"].update(text="mismatch"), ["Bounded ", "answer."]),
        (lambda events: events[8]["item"].update(id="other"), ["Bounded ", "answer."]),
        (
            lambda events: events[8]["item"].update(status="in_progress"),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"].update(model="gpt-4.1-mini"),
            ["Bounded ", "answer."],
        ),
        (lambda events: events[9]["response"].update(status="failed"), ["Bounded ", "answer."]),
        (
            lambda events: events[9]["response"].update(error={"code": RAW_SECRET}),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"].update(incomplete_details={"reason": RAW_SECRET}),
            ["Bounded ", "answer."],
        ),
        (lambda events: events[9]["response"].update(output=[]), ["Bounded ", "answer."]),
        (
            lambda events: events[9]["response"]["output"][0].update(id="other"),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"]["output"][0]["content"][0].update(
                annotations=[{"type": RAW_SECRET}]
            ),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"]["usage"].update(input_tokens=-1),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"]["usage"].update(output_tokens=True),
            ["Bounded ", "answer."],
        ),
        (
            lambda events: events[9]["response"]["usage"].update(total_tokens=17),
            ["Bounded ", "answer."],
        ),
    ],
)
def test_malformed_or_unsupported_streams_fail_closed(mutate, expected_progress: list[str]) -> None:
    async def scenario():
        events = _success_events()
        mutate(events)
        stream = _FakeStream(events)
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())

    assert [event.text for event in observations if isinstance(event, ProviderTextDelta)] == (
        expected_progress
    )
    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == "invalid_response"
    assert observations[-1].failure.message == "OpenAI returned an invalid response."
    assert RAW_SECRET not in repr(observations)


def test_premature_eof_is_invalid_response() -> None:
    async def scenario():
        stream = _FakeStream(_success_events()[:5])
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())

    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == "invalid_response"


def test_malformed_stream_iterator_is_invalid_and_resources_are_closed() -> None:
    async def scenario():
        stream = _MalformedIteratorStream(_success_events())
        provider, _responses, client, _created = _provider_with(stream)
        observations = await _collect(provider.start(_request()))
        return observations, stream, client

    observations, stream, client = asyncio.run(scenario())

    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == "invalid_response"
    assert stream.close_calls == 1
    assert client.close_calls == 1


@pytest.mark.parametrize(
    ("event_type", "provider_code", "retryable"),
    [
        ("response.incomplete", "request_rejected", False),
        ("response.failed:server_error", "unavailable", True),
        ("response.failed:rate_limit_exceeded", "rate_limited", True),
        ("response.failed:other", "unknown", False),
    ],
)
def test_response_terminals_replace_any_valid_prefix(
    event_type: str, provider_code: str, retryable: bool
) -> None:
    async def scenario():
        events = _success_events()[:5]
        response_id = events[0]["response"]["id"]
        kind, _, code = event_type.partition(":")
        events.append(
            {
                "type": kind,
                "sequence_number": events[-1]["sequence_number"] + 1,
                "response": {
                    "id": response_id,
                    "status": "failed" if kind == "response.failed" else "incomplete",
                    "error": None if kind == "response.incomplete" else {"code": code},
                },
            }
        )
        stream = _FakeStream(events)
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())
    terminal = observations[-1]

    assert isinstance(terminal, ProviderFailed)
    assert terminal.failure.code == provider_code
    assert terminal.failure.retryable is retryable


def test_top_level_error_may_be_first_but_never_exposes_sdk_values() -> None:
    async def scenario():
        stream = _FakeStream(
            [
                {
                    "type": "error",
                    "sequence_number": 42,
                    "code": RAW_SECRET,
                    "message": RAW_SECRET,
                    "param": RAW_SECRET,
                }
            ]
        )
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())

    assert observations == [
        ProviderFailed(
            failure=adapter_module.ProviderFailure(
                code="unknown",
                message="OpenAI request failed.",
                retryable=False,
            )
        )
    ]
    assert RAW_SECRET not in repr(observations)


def _status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(status, request=request)
    if status == 401:
        return openai.AuthenticationError(RAW_SECRET, response=response, body={"raw": RAW_SECRET})
    if status == 429:
        return openai.RateLimitError(RAW_SECRET, response=response, body={"raw": RAW_SECRET})
    return openai.APIStatusError(RAW_SECRET, response=response, body={"raw": RAW_SECRET})


def _response_validation_error() -> openai.APIResponseValidationError:
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(200, request=request)
    return openai.APIResponseValidationError(
        response=response,
        body={"raw": RAW_SECRET},
        message=RAW_SECRET,
    )


@pytest.mark.parametrize(
    ("error_factory", "provider_code", "retryable"),
    [
        (lambda: _status_error(401), "authentication_failed", False),
        (lambda: _status_error(429), "rate_limited", True),
        (
            lambda: openai.APITimeoutError(httpx.Request("POST", "https://example.invalid")),
            "unavailable",
            True,
        ),
        (
            lambda: openai.APIConnectionError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            "unavailable",
            True,
        ),
        (lambda: _status_error(408), "unavailable", True),
        (lambda: _status_error(409), "unavailable", True),
        (lambda: _status_error(503), "unavailable", True),
        (lambda: _status_error(400), "request_rejected", False),
        (lambda: _status_error(403), "request_rejected", False),
        (lambda: _status_error(302), "unknown", False),
        (lambda: openai.OpenAIError(RAW_SECRET), "unknown", False),
        (lambda: RuntimeError(RAW_SECRET), "unknown", False),
        (
            lambda: json.JSONDecodeError(RAW_SECRET, RAW_SECRET, 0),
            "invalid_response",
            False,
        ),
        (
            lambda: UnicodeDecodeError("utf-8", b"\xff", 0, 1, RAW_SECRET),
            "invalid_response",
            False,
        ),
    ],
)
def test_sdk_exception_table_is_closed_and_safe(error_factory, provider_code, retryable) -> None:
    async def scenario():
        stream = _FakeStream([])
        provider, _responses, _client, _created = _provider_with(
            stream,
            responses_error=error_factory(),
        )
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())
    terminal = observations[-1]

    assert isinstance(terminal, ProviderFailed)
    assert terminal.failure.code == provider_code
    assert terminal.failure.retryable is retryable
    assert RAW_SECRET not in repr(terminal)


@pytest.mark.parametrize(
    ("error_factory", "provider_code"),
    [
        (_response_validation_error, "invalid_response"),
        (lambda: _status_error(429), "rate_limited"),
        (lambda: RuntimeError(RAW_SECRET), "unknown"),
    ],
)
def test_iteration_exceptions_use_the_same_closed_safe_table(
    error_factory, provider_code: str
) -> None:
    async def scenario():
        stream = _FakeStream([], next_error=error_factory())
        provider, _responses, _client, _created = _provider_with(stream)
        return await _collect(provider.start(_request()))

    observations = asyncio.run(scenario())

    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == provider_code
    assert RAW_SECRET not in repr(observations)


def test_cancellation_before_consumption_is_idempotent_and_constructs_no_client() -> None:
    async def scenario():
        provider, _responses, _client, created = _provider_with(_FakeStream(_success_events()))
        operation = provider.start(_request())
        first = await operation.cancel()
        second = await operation.cancel()
        events = operation.events()
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        await operation.wait_closed()
        return first, second, created

    first, second, created = asyncio.run(scenario())

    assert first == "cancelled"
    assert second == "already_closed"
    assert created == []


def test_cancellation_interrupts_pending_create_and_closes_client() -> None:
    async def scenario():
        gate = asyncio.Event()
        stream = _FakeStream(_success_events())
        provider, responses, client, _created = _provider_with(stream, create_gate=gate)
        operation = provider.start(_request())
        iterator = operation.events()
        pending = asyncio.create_task(anext(iterator))
        await responses.started.wait()
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return result, responses, client, stream

    result, responses, client, stream = asyncio.run(scenario())

    assert result == "cancelled"
    assert responses.cancelled.is_set()
    assert stream.close_calls == 0
    assert client.close_calls == 1


def test_cancellation_interrupts_blocked_next_event_and_closes_both_resources() -> None:
    async def scenario():
        stream = _FakeStream(_success_events(), block_before_index=0)
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        pending = asyncio.create_task(anext(iterator))
        await stream.next_started.wait()
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return result, stream, client

    result, stream, client = asyncio.run(scenario())

    assert result == "cancelled"
    assert stream.next_cancelled.is_set()
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_cancellation_between_text_deltas_suppresses_the_unread_suffix() -> None:
    async def scenario():
        stream = _FakeStream(_success_events(), block_before_index=5)
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        first = await anext(iterator)
        pending = asyncio.create_task(anext(iterator))
        await stream.blocked_next_started.wait()
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return first, result, stream, client

    first, result, stream, client = asyncio.run(scenario())

    assert first == ProviderTextDelta("Bounded ")
    assert result == "cancelled"
    assert stream.next_cancelled.is_set()
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_cancellation_suppresses_a_progress_event_returned_by_cancelled_sdk_work() -> None:
    async def scenario():
        stream = _FakeStream(
            _success_events(),
            block_before_index=4,
            return_event_on_cancel=True,
        )
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        pending = asyncio.create_task(anext(iterator))
        await stream.blocked_next_started.wait()
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return result, stream, client

    result, stream, client = asyncio.run(scenario())

    assert result == "cancelled"
    assert stream.next_cancelled.is_set()
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_consumer_task_cancellation_starts_cleanup_before_propagating() -> None:
    async def scenario():
        stream = _FakeStream(_success_events(), block_before_index=0)
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        pending = asyncio.create_task(anext(operation.events()))
        await stream.blocked_next_started.wait()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await operation.wait_closed()
        later = await operation.cancel()
        return later, stream, client

    later, stream, client = asyncio.run(scenario())

    assert later == "already_closed"
    assert stream.next_cancelled.is_set()
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_cleanup_finishes_before_usage_and_wait_closed_cannot_split_terminal_queue() -> None:
    async def scenario():
        close_gate = asyncio.Event()
        stream = _FakeStream(_success_events(), close_gate=close_gate)
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        first = await anext(iterator)
        second = await anext(iterator)
        text_done = await anext(iterator)
        usage_pending = asyncio.create_task(anext(iterator))
        await stream.close_started.wait()
        closed_pending = asyncio.create_task(operation.wait_closed())
        await asyncio.sleep(0)
        assert not usage_pending.done()
        assert not closed_pending.done()
        close_gate.set()
        usage = await usage_pending
        await asyncio.sleep(0)
        assert not closed_pending.done()
        completed = await anext(iterator)
        await closed_pending
        return first, second, text_done, usage, completed, client

    first, second, text_done, usage, completed, client = asyncio.run(scenario())

    assert first == ProviderTextDelta("Bounded ")
    assert second == ProviderTextDelta("answer.")
    assert text_done == ProviderTextCompleted("Bounded answer.")
    assert usage == ProviderUsageReported(11, 5)
    assert completed == ProviderCompleted()
    assert client.close_calls == 1


def test_cancellation_during_terminal_cleanup_prevents_terminal_queue_installation() -> None:
    async def scenario():
        close_gate = asyncio.Event()
        stream = _FakeStream(_success_events(), close_gate=close_gate)
        provider, _responses, client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        progress = [await anext(iterator) for _index in range(3)]
        pending_terminal = asyncio.create_task(anext(iterator))
        await stream.close_started.wait()
        cancellation = asyncio.create_task(operation.cancel())
        await asyncio.sleep(0)
        assert not cancellation.done()
        close_gate.set()
        result = await cancellation
        with pytest.raises(StopAsyncIteration):
            await pending_terminal
        await operation.wait_closed()
        return progress, result, stream, client

    progress, result, stream, client = asyncio.run(scenario())

    assert progress[-1] == ProviderTextCompleted("Bounded answer.")
    assert result == "cancelled"
    assert stream.close_calls == 1
    assert client.close_calls == 1


def test_cancellation_after_usage_suppresses_provider_completed() -> None:
    async def scenario():
        stream = _FakeStream(_success_events())
        provider, _responses, _client, _created = _provider_with(stream)
        operation = provider.start(_request())
        iterator = operation.events()
        observed = [await anext(iterator) for _index in range(4)]
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
        return observed, result

    observed, result = asyncio.run(scenario())

    assert observed[-1] == ProviderUsageReported(11, 5)
    assert result == "cancelled"


@pytest.mark.parametrize(
    ("stream_fails", "client_fails"), [(True, False), (False, True), (True, True)]
)
def test_cleanup_failure_replaces_completion_and_attempts_both_closes(
    stream_fails: bool, client_fails: bool
) -> None:
    async def scenario():
        stream = _FakeStream(
            _success_events(),
            close_error=RuntimeError(RAW_SECRET) if stream_fails else None,
        )
        provider, _responses, client, _created = _provider_with(
            stream,
            client_close_error=RuntimeError(RAW_SECRET) if client_fails else None,
        )
        operation = provider.start(_request())
        observations = await _collect(operation)
        with pytest.raises(OpenAIAdapterCleanupError) as first:
            await operation.wait_closed()
        with pytest.raises(OpenAIAdapterCleanupError) as second:
            await operation.cancel()
        return observations, stream, client, first.value, second.value

    observations, stream, client, first, second = asyncio.run(scenario())

    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == "unknown"
    assert not any(isinstance(event, ProviderUsageReported) for event in observations)
    assert stream.close_calls == 1
    assert client.close_calls == 1
    assert str(first) == str(second) == "OpenAI adapter resource cleanup could not be confirmed."
    assert RAW_SECRET not in repr(observations) + str(first) + str(second)


def test_cleanup_failure_preserves_already_buffered_provider_failure() -> None:
    async def scenario():
        events = [
            _success_events()[0],
            {
                "type": "response.failed",
                "sequence_number": 8,
                "response": {
                    "id": "resp_fake_023",
                    "status": "failed",
                    "error": {"code": "rate_limit_exceeded"},
                },
            },
        ]
        stream = _FakeStream(events, close_error=RuntimeError(RAW_SECRET))
        provider, _responses, _client, _created = _provider_with(stream)
        operation = provider.start(_request())
        observations = await _collect(operation)
        with pytest.raises(OpenAIAdapterCleanupError):
            await operation.wait_closed()
        return observations

    observations = asyncio.run(scenario())

    assert observations[-1].failure.code == "rate_limited"


@pytest.mark.parametrize("pending_stage", ["create", "stream_close", "client_close"])
def test_cancelling_one_cleanup_joiner_does_not_cancel_shared_cleanup(
    pending_stage: str,
) -> None:
    async def scenario():
        stage_gate = asyncio.Event()
        create_gate = asyncio.Event() if pending_stage == "create" else None
        stream = _FakeStream(
            _success_events(),
            block_before_index=None if pending_stage == "create" else 0,
            close_gate=stage_gate if pending_stage == "stream_close" else None,
        )
        provider, responses, client, _created = _provider_with(
            stream,
            create_gate=create_gate,
            create_cancel_gate=stage_gate if pending_stage == "create" else None,
            client_close_gate=stage_gate if pending_stage == "client_close" else None,
        )
        operation = provider.start(_request())
        iterator = operation.events()
        pending = asyncio.create_task(anext(iterator))
        if pending_stage == "create":
            await responses.started.wait()
        else:
            await stream.blocked_next_started.wait()
        first_joiner = asyncio.create_task(operation.cancel())
        if pending_stage == "create":
            await responses.cancelled.wait()
        elif pending_stage == "stream_close":
            await stream.close_started.wait()
        else:
            await client.close_started.wait()
        first_joiner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_joiner
        if pending_stage == "stream_close":
            assert not stream.close_finished.is_set()
        else:
            assert not client.close_finished.is_set()
        stage_gate.set()
        await operation.wait_closed()
        second = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return second, responses, stream, client

    second, responses, stream, client = asyncio.run(scenario())

    assert second == "already_closed"
    if pending_stage == "create":
        assert responses.cancelled.is_set()
        assert stream.close_calls == 0
    else:
        assert stream.close_finished.is_set()
        assert stream.close_calls == 1
    assert client.close_calls == 1
    assert client.close_finished.is_set()


def test_official_client_construction_fixes_endpoint_routing_and_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_unsupported_openai_environment(monkeypatch)
    http_arguments: list[dict[str, object]] = []
    client_arguments: list[dict[str, object]] = []
    stream = _FakeStream(_success_events())
    fake_responses = _FakeResponses(stream)
    fake_client = _FakeClient(fake_responses)
    http_client = object()

    def fake_http_client(**arguments: object) -> object:
        http_arguments.append(arguments)
        return http_client

    def fake_async_openai(**arguments: object) -> _FakeClient:
        client_arguments.append(arguments)
        return fake_client

    monkeypatch.setattr(adapter_module, "DefaultAsyncHttpxClient", fake_http_client)
    monkeypatch.setattr(adapter_module, "AsyncOpenAI", fake_async_openai)

    async def scenario():
        provider = OpenAIResponsesProvider(_configuration())
        await _collect(provider.start(_request()))

    asyncio.run(scenario())

    assert http_arguments == [{"trust_env": False, "follow_redirects": False}]
    assert client_arguments == [
        {
            "api_key": API_KEY,
            "base_url": OPENAI_RESPONSES_BASE_URL,
            "organization": None,
            "project": None,
            "max_retries": 0,
            "http_client": http_client,
        }
    ]


def test_lazy_client_construction_rejects_a_post_start_environment_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_unsupported_openai_environment(monkeypatch)
    http_arguments: list[dict[str, object]] = []
    client_arguments: list[dict[str, object]] = []

    monkeypatch.setattr(
        adapter_module,
        "DefaultAsyncHttpxClient",
        lambda **arguments: http_arguments.append(arguments),
    )
    monkeypatch.setattr(
        adapter_module,
        "AsyncOpenAI",
        lambda **arguments: client_arguments.append(arguments),
    )
    provider = OpenAIResponsesProvider(_configuration())
    operation = provider.start(_request())
    monkeypatch.setenv("OPENAI_BASE_URL", RAW_SECRET)

    observations = asyncio.run(_collect(operation))

    assert isinstance(observations[-1], ProviderFailed)
    assert observations[-1].failure.code == "unknown"
    assert http_arguments == []
    assert client_arguments == []
    assert RAW_SECRET not in repr(observations)


def test_validated_configuration_repr_never_contains_api_key() -> None:
    assert API_KEY not in repr(_configuration())


def test_provider_session_consumes_adapter_events_and_records_usage_without_sdk_values() -> None:
    async def scenario():
        lines: list[bytes] = []
        usage: list[ModelUsageObserved] = []
        provider, _responses, _client, _created = _provider_with(_FakeStream(_success_events()))

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def observe(value: ModelUsageObserved) -> None:
            usage.append(value)

        command = SessionStartCommand.model_validate(
            {
                "protocol_version": 1,
                "type": "session.start",
                "command_id": "cmd_openai_fake",
                "timestamp": "2026-08-01T12:34:56.789Z",
                "payload": {"task": "Use the fake Responses stream."},
            }
        )
        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: "2026-08-01T12:34:56.789Z"),
            provider,
            command,
            "ses_openai_fake",
            limits=LoopLimits(),
        )
        await session.attach_model_usage_observer(observe)
        await session.run()
        return lines, usage, session

    lines, usage, session = asyncio.run(scenario())
    wire = [json.loads(line) for line in lines]

    assert [event["type"] for event in wire] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert session.lifecycle_state.assistant_text == "Bounded answer."
    assert [(value.input_tokens, value.output_tokens) for value in usage] == [(11, 5)]
    serialized = b"".join(lines).decode()
    assert MODEL not in serialized
    assert API_KEY not in serialized


def test_adapter_cleanup_failure_is_diagnostic_without_rewriting_session_failure() -> None:
    async def scenario():
        lines: list[bytes] = []
        stream = _FakeStream(
            [
                {
                    "type": "error",
                    "sequence_number": 0,
                    "code": RAW_SECRET,
                    "message": RAW_SECRET,
                    "param": RAW_SECRET,
                }
            ],
            close_error=RuntimeError(RAW_SECRET),
        )
        provider, _responses, _client, _created = _provider_with(stream)

        async def sink(line: bytes) -> None:
            lines.append(line)

        command = SessionStartCommand.model_validate(
            {
                "protocol_version": 1,
                "type": "session.start",
                "command_id": "cmd_openai_failure",
                "timestamp": "2026-08-01T12:34:56.789Z",
                "payload": {"task": "Fail safely."},
            }
        )
        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: "2026-08-01T12:34:56.789Z"),
            provider,
            command,
            "ses_openai_failure",
            limits=LoopLimits(),
        )
        await session.run()
        return lines

    lines = asyncio.run(scenario())
    wire = [json.loads(line) for line in lines]

    assert [event["type"] for event in wire] == [
        "session.started",
        "runtime.error",
        "session.failed",
    ]
    assert wire[-2]["payload"]["code"] == "provider_cleanup_failed"
    assert wire[-1]["payload"] == {
        "code": "provider_unknown",
        "message": "OpenAI request failed.",
    }
    assert RAW_SECRET not in b"".join(lines).decode()
