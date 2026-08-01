from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import cast

import pytest

from code_assist_harness.model_evidence import (
    MAX_MODEL_USAGE_TOKENS,
    ModelUsageObserved,
)
from code_assist_harness.protocol import (
    AssistantDeltaEvent,
    OrderedEventWriter,
    SessionStartCommand,
)
from code_assist_harness.provider import (
    FakeProvider,
    FakeProviderDelay,
    FakeProviderEmit,
    FakeProviderExchange,
    FakeProviderOperation,
    FakeProviderWaitForCancellation,
    ProviderCompleted,
    ProviderFailed,
    ProviderFailure,
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
from code_assist_harness.provider_session import (
    MAX_PROVIDER_TURN_OUTPUT_BYTES,
    ProviderSession,
)
from code_assist_harness.session_state import SessionState, SessionUpdate

TIMESTAMP = "2026-07-31T12:34:56.789Z"


def _session_start(
    command_id: str = "cmd_start",
    task: str = "Explain the repository boundary",
) -> SessionStartCommand:
    return SessionStartCommand.model_validate(
        {
            "protocol_version": 1,
            "type": "session.start",
            "command_id": command_id,
            "timestamp": TIMESTAMP,
            "payload": {"task": task},
        }
    )


def _request(
    task: str = "Explain the repository boundary",
    instructions: tuple[RepositoryInstruction, ...] = (),
) -> ProviderRequest:
    return ProviderRequest(
        conversation=(ProviderMessage(role="user", content=task),),
        repository_instructions=instructions,
    )


def _wire_events(lines: Sequence[bytes]) -> list[dict[str, object]]:
    return [cast(dict[str, object], json.loads(line)) for line in lines]


def _event_types(lines: Sequence[bytes]) -> list[str]:
    return [cast(str, event["type"]) for event in _wire_events(lines)]


class _CapturingProvider:
    def __init__(self, fake: FakeProvider) -> None:
        self.fake = fake
        self.start_calls = 0
        self.requests: list[ProviderRequest] = []
        self.operation: FakeProviderOperation | None = None

    def start(self, request: ProviderRequest) -> ProviderOperation:
        self.start_calls += 1
        self.requests.append(request)
        operation = self.fake.start(request)
        self.operation = operation
        return operation


class _ControlledOperation:
    """Model an early close, delayed cleanup, or broken cleanup contract."""

    def __init__(
        self,
        events: tuple[ProviderStreamEvent, ...],
        *,
        events_error: BaseException | None = None,
        iteration_error: BaseException | None = None,
        block_iteration: bool = False,
        cancel_releases_iteration: bool = False,
        block_wait_closed: bool = False,
        wait_closed_error: str | None = None,
        cancel_error: str | None = None,
    ) -> None:
        self._events = events
        self._events_error = events_error
        self._iteration_error = iteration_error
        self._block_iteration = block_iteration
        self._cancel_releases_iteration = cancel_releases_iteration
        self._block_wait_closed = block_wait_closed
        self._wait_closed_error = wait_closed_error
        self._cancel_error = cancel_error
        self._claimed = False
        self.iteration_started = asyncio.Event()
        self.iteration_finished = asyncio.Event()
        self.release_iteration = asyncio.Event()
        self.wait_closed_started = asyncio.Event()
        self.release_wait_closed = asyncio.Event()
        self.cancel_started = asyncio.Event()
        self.cancel_calls = 0
        self.wait_closed_calls = 0

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        if self._claimed:
            raise RuntimeError("controlled operation stream claimed twice")
        self._claimed = True
        if self._events_error is not None:
            raise self._events_error

        async def generate() -> AsyncIterator[ProviderStreamEvent]:
            self.iteration_started.set()
            try:
                if self._block_iteration:
                    await self.release_iteration.wait()
                if self._iteration_error is not None:
                    raise self._iteration_error
                for event in self._events:
                    yield event
            finally:
                self.iteration_finished.set()

        return generate()

    async def cancel(self) -> str:
        self.cancel_calls += 1
        self.cancel_started.set()
        if self._cancel_releases_iteration:
            self.release_iteration.set()
        if self._cancel_error is not None:
            raise RuntimeError(self._cancel_error)
        return "cancelled"

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1
        self.wait_closed_started.set()
        if self._block_wait_closed:
            await self.release_wait_closed.wait()
        if self._wait_closed_error is not None:
            raise RuntimeError(self._wait_closed_error)


class _FutureBackedIterator:
    """Return Future instances from ``__anext__`` as permitted by the async-iterator port."""

    def __init__(self, events: tuple[ProviderStreamEvent, ...]) -> None:
        self._events = iter(events)

    def __aiter__(self) -> _FutureBackedIterator:
        return self

    def __anext__(self) -> asyncio.Future[ProviderStreamEvent]:
        future = asyncio.get_running_loop().create_future()
        try:
            future.set_result(next(self._events))
        except StopIteration:
            future.set_exception(StopAsyncIteration())
        return future


class _SynchronousFailingIterator:
    """Raise before returning an awaitable to probe the untrusted iterator boundary."""

    def __init__(self, failure: BaseException) -> None:
        self._failure = failure

    def __aiter__(self) -> _SynchronousFailingIterator:
        return self

    def __anext__(self) -> asyncio.Future[ProviderStreamEvent]:
        raise self._failure


class _IteratorBoundaryOperation:
    """Expose an arbitrary iterator-shaped value for boundary normalization tests."""

    def __init__(self, events: object) -> None:
        self._events = events
        self._claimed = False
        self.cancel_calls = 0
        self.wait_closed_calls = 0

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        if self._claimed:
            raise RuntimeError("iterator boundary stream claimed twice")
        self._claimed = True
        return cast(AsyncIterator[ProviderStreamEvent], self._events)

    async def cancel(self) -> str:
        self.cancel_calls += 1
        return "cancelled"

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


class _SingleOperationProvider:
    def __init__(self, operation: ProviderOperation) -> None:
        self.operation = operation
        self.start_calls = 0
        self.requests: list[ProviderRequest] = []

    def start(self, request: ProviderRequest) -> ProviderOperation:
        self.start_calls += 1
        self.requests.append(request)
        return self.operation


def test_one_turn_builds_one_exact_request_and_completes_with_usage() -> None:
    async def scenario() -> tuple[
        list[bytes],
        _CapturingProvider,
        ProviderSession,
        list[ModelUsageObserved],
        list[tuple[SessionUpdate, SessionState]],
    ]:
        lines: list[bytes] = []
        instructions = (
            RepositoryInstruction(source="AGENTS.md", content="Keep the loop explicit."),
            RepositoryInstruction(
                source="docs/LOCAL.md",
                content="Keep provider values behind the port.",
            ),
        )
        expected_request = _request(instructions=instructions)
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=expected_request,
                    steps=(
                        FakeProviderEmit(ProviderTextDelta("A provider-neutral ")),
                        FakeProviderEmit(ProviderTextDelta("answer.")),
                        FakeProviderEmit(ProviderTextCompleted("A provider-neutral answer.")),
                        FakeProviderEmit(ProviderUsageReported(input_tokens=41, output_tokens=7)),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        lifecycle: list[tuple[SessionUpdate, SessionState]] = []
        usage: list[ModelUsageObserved] = []

        async def observe_lifecycle(update: SessionUpdate, state: SessionState) -> None:
            lifecycle.append((update, state))

        async def observe_usage(observation: ModelUsageObserved) -> None:
            usage.append(observation)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_provider_test",
            instructions,
        )
        await session.attach_lifecycle_observer(observe_lifecycle)
        await session.attach_model_usage_observer(observe_usage)
        result = await asyncio.wait_for(session.run(), timeout=1)
        assert result == "ses_provider_test"
        fake.assert_complete()
        return lines, provider, session, usage, lifecycle

    lines, provider, session, usage, lifecycle = asyncio.run(scenario())
    events = _wire_events(lines)

    assert provider.start_calls == 1
    assert provider.requests == [
        _request(
            instructions=(
                RepositoryInstruction(source="AGENTS.md", content="Keep the loop explicit."),
                RepositoryInstruction(
                    source="docs/LOCAL.md",
                    content="Keep provider values behind the port.",
                ),
            )
        )
    ]
    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [event["sequence"] for event in events] == [1, 2, 3, 4, 5]
    assert {event["correlation_id"] for event in events} == {"cmd_start"}
    assert [
        cast(dict[str, str], event["payload"])["text"]
        for event in events
        if event["type"] == "assistant.delta"
    ] == ["A provider-neutral ", "answer."]
    assert usage == [
        ModelUsageObserved(
            session_id="ses_provider_test",
            input_tokens=41,
            output_tokens=7,
        )
    ]
    assert session.lifecycle_state.status == "completed"
    assert session.lifecycle_state.assistant_text == "A provider-neutral answer."
    assert session.lifecycle_state.last_sequence == 5
    assert lifecycle[-1][1] == session.lifecycle_state


def test_candidate_completion_stays_buffered_until_provider_completion() -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderEmit(ProviderTextDelta("buffer me")),
                        FakeProviderEmit(ProviderTextCompleted("buffer me")),
                        FakeProviderDelay("before-provider-completion"),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_buffered",
        )
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await asyncio.wait_for(
            provider.operation.wait_for_checkpoint("before-provider-completion"),
            timeout=1,
        )
        assert _event_types(lines) == ["session.started", "assistant.delta"]
        assert session.lifecycle_state.assistant_completed is False

        provider.operation.release_checkpoint("before-provider-completion")
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())

    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert session.lifecycle_state.status == "completed"


@pytest.mark.parametrize(
    ("name", "steps", "accepted_deltas"),
    [
        (
            "empty-text-completed-before-provider-completed",
            (
                FakeProviderEmit(ProviderTextCompleted("")),
                FakeProviderEmit(ProviderCompleted()),
            ),
            [],
        ),
        (
            "usage-after-empty-text-completed",
            (
                FakeProviderEmit(ProviderTextCompleted("")),
                FakeProviderEmit(ProviderUsageReported(input_tokens=1, output_tokens=1)),
                FakeProviderWaitForCancellation("reject-usage-after-empty-completion"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            [],
        ),
        (
            "mismatched-completed-text",
            (
                FakeProviderEmit(ProviderTextDelta("safe-prefix")),
                FakeProviderEmit(ProviderTextCompleted("secret-mismatch")),
                FakeProviderWaitForCancellation("reject-mismatch"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["safe-prefix"],
        ),
        (
            "duplicate-text-completed",
            (
                FakeProviderEmit(ProviderTextDelta("complete-once")),
                FakeProviderEmit(ProviderTextCompleted("complete-once")),
                FakeProviderEmit(ProviderTextCompleted("complete-once")),
                FakeProviderWaitForCancellation("reject-duplicate-completion"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["complete-once"],
        ),
        (
            "delta-after-text-completed",
            (
                FakeProviderEmit(ProviderTextDelta("first")),
                FakeProviderEmit(ProviderTextCompleted("first")),
                FakeProviderEmit(ProviderTextDelta("must-not-enter-wire")),
                FakeProviderWaitForCancellation("reject-late-delta"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["first"],
        ),
        (
            "usage-before-text-completed",
            (
                FakeProviderEmit(ProviderTextDelta("first")),
                FakeProviderEmit(ProviderUsageReported(input_tokens=1, output_tokens=1)),
                FakeProviderWaitForCancellation("reject-early-usage"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["first"],
        ),
        (
            "duplicate-usage",
            (
                FakeProviderEmit(ProviderTextDelta("first")),
                FakeProviderEmit(ProviderTextCompleted("first")),
                FakeProviderEmit(ProviderUsageReported(input_tokens=1, output_tokens=1)),
                FakeProviderEmit(ProviderUsageReported(input_tokens=2, output_tokens=2)),
                FakeProviderWaitForCancellation("reject-duplicate-usage"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["first"],
        ),
        (
            "text-completed-after-usage",
            (
                FakeProviderEmit(ProviderTextDelta("first")),
                FakeProviderEmit(ProviderTextCompleted("first")),
                FakeProviderEmit(ProviderUsageReported(input_tokens=1, output_tokens=1)),
                FakeProviderEmit(ProviderTextCompleted("first")),
                FakeProviderWaitForCancellation("reject-completion-after-usage"),
                FakeProviderEmit(ProviderCompleted()),
            ),
            ["first"],
        ),
        (
            "provider-completed-without-text-completed",
            (FakeProviderEmit(ProviderCompleted()),),
            [],
        ),
    ],
)
def test_invalid_stream_grammar_fails_safely_and_reaps_the_operation(
    name: str,
    steps: tuple[object, ...],
    accepted_deltas: list[str],
) -> None:
    del name

    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=_request(),
                    steps=cast(tuple, steps),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_invalid",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())
    events = _wire_events(lines)
    deltas = [
        cast(dict[str, str], event["payload"])["text"]
        for event in events
        if event["type"] == "assistant.delta"
    ]
    failure = events[-1]

    assert deltas == accepted_deltas
    assert failure["type"] == "session.failed"
    assert failure["payload"] == {
        "code": "provider_invalid_response",
        "message": "The provider returned an invalid response.",
    }
    assert "secret-mismatch" not in b"".join(lines).decode()
    assert "must-not-enter-wire" not in b"".join(lines).decode()
    assert "assistant.completed" not in _event_types(lines)
    assert "session.completed" not in _event_types(lines)
    assert session.lifecycle_state.status == "failed"


def test_stream_ending_without_a_provider_terminal_is_invalid_and_cancelled() -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (
                ProviderTextDelta("candidate"),
                ProviderTextCompleted("candidate"),
            )
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_early_close",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())

    assert operation.cancel_calls == 1
    assert operation.wait_closed_calls == 0
    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "session.failed",
    ]
    assert _wire_events(lines)[-1]["payload"] == {
        "code": "provider_invalid_response",
        "message": "The provider returned an invalid response.",
    }
    assert session.lifecycle_state.assistant_completed is False


def test_exact_utf8_output_ceiling_completes() -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        exact = "🙂" * (MAX_PROVIDER_TURN_OUTPUT_BYTES // 4)
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=_request(),
                    steps=(
                        FakeProviderEmit(ProviderTextDelta(exact)),
                        FakeProviderEmit(ProviderTextCompleted(exact)),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_exact_limit",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())

    assert len(session.lifecycle_state.assistant_text.encode("utf-8")) == 8192
    assert session.lifecycle_state.status == "completed"
    assert _event_types(lines)[-2:] == ["assistant.completed", "session.completed"]


def test_delta_crossing_utf8_output_ceiling_is_rejected_in_full() -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        accepted = "🙂" * (MAX_PROVIDER_TURN_OUTPUT_BYTES // 4)
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=_request(),
                    steps=(
                        FakeProviderEmit(ProviderTextDelta(accepted)),
                        FakeProviderEmit(ProviderTextDelta("x-secret-overflow")),
                        FakeProviderWaitForCancellation("reject-overflow"),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_over_limit",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())
    serialized = b"".join(lines).decode()

    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "session.failed",
    ]
    assert session.lifecycle_state.assistant_text.encode("utf-8") == (
        "🙂" * (MAX_PROVIDER_TURN_OUTPUT_BYTES // 4)
    ).encode("utf-8")
    assert "x-secret-overflow" not in serialized


@pytest.mark.parametrize("after_delta", [False, True])
def test_normalized_provider_failure_before_or_after_output_is_authoritative(
    after_delta: bool,
) -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        failure = ProviderFailed(
            ProviderFailure(
                code="rate_limited",
                message="The provider is temporarily busy.",
                retryable=True,
            )
        )
        steps = (
            (FakeProviderEmit(ProviderTextDelta("visible prefix")), FakeProviderEmit(failure))
            if after_delta
            else (FakeProviderEmit(failure),)
        )
        fake = FakeProvider((FakeProviderExchange(_request(), steps),))

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_provider_failure",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())
    events = _wire_events(lines)

    assert _event_types(lines) == (
        ["session.started", "assistant.delta", "session.failed"]
        if after_delta
        else ["session.started", "session.failed"]
    )
    assert events[-1]["payload"] == {
        "code": "provider_rate_limited",
        "message": "The provider is temporarily busy.",
    }
    assert session.lifecycle_state.status == "failed"
    assert session.lifecycle_state.assistant_text == ("visible prefix" if after_delta else "")


def test_failure_after_candidate_completion_never_emits_assistant_completion() -> None:
    async def scenario() -> list[bytes]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("not a success")),
                        FakeProviderEmit(ProviderTextCompleted("not a success")),
                        FakeProviderEmit(
                            ProviderFailed(
                                ProviderFailure(
                                    code="unavailable",
                                    message="Safe normalized failure.",
                                    retryable=True,
                                )
                            )
                        ),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_late_failure",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines

    lines = asyncio.run(scenario())

    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "session.failed",
    ]


@pytest.mark.parametrize("empty_text_candidate", [False, True], ids=["direct", "tool-only-prefix"])
def test_tool_request_uses_fixed_failure_without_exposing_arguments(
    empty_text_candidate: bool,
) -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        prefix = (FakeProviderEmit(ProviderTextCompleted("")),) if empty_text_candidate else ()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        *prefix,
                        FakeProviderEmit(
                            ProviderToolCallRequested(
                                call_id="call_1",
                                name="read_secret",
                                arguments_json='{"token":"sk-secret-must-not-leak"}',
                            )
                        ),
                        FakeProviderWaitForCancellation("reject-tool"),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_tool",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())
    serialized = b"".join(lines).decode()

    assert _event_types(lines) == ["session.started", "session.failed"]
    assert _wire_events(lines)[-1]["payload"] == {
        "code": "tool_unavailable",
        "message": "Provider-requested tools are not available.",
    }
    assert "read_secret" not in serialized
    assert "sk-secret-must-not-leak" not in serialized
    assert session.lifecycle_state.status == "failed"


def test_usage_is_optional_and_accepts_safe_integer_bounds() -> None:
    async def scenario() -> tuple[list[bytes], list[ModelUsageObserved]]:
        lines: list[bytes] = []
        observed: list[ModelUsageObserved] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("bounded")),
                        FakeProviderEmit(ProviderTextCompleted("bounded")),
                        FakeProviderEmit(
                            ProviderUsageReported(
                                input_tokens=0,
                                output_tokens=MAX_MODEL_USAGE_TOKENS,
                            )
                        ),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def observe_usage(usage: ModelUsageObserved) -> None:
            observed.append(usage)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_usage_bounds",
        )
        await session.attach_model_usage_observer(observe_usage)
        await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return lines, observed

    lines, observed = asyncio.run(scenario())

    assert observed == [
        ModelUsageObserved(
            session_id="ses_usage_bounds",
            input_tokens=0,
            output_tokens=MAX_MODEL_USAGE_TOKENS,
        )
    ]
    assert all(event["type"] != "model.usage_observed" for event in _wire_events(lines))
    assert [event["sequence"] for event in _wire_events(lines)] == [1, 2, 3, 4]


def test_cancellation_before_output_closes_provider_and_is_idempotent() -> None:
    async def scenario() -> tuple[list[bytes], str, str, ProviderSession]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderWaitForCancellation("before-output"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                        FakeProviderEmit(ProviderTextCompleted("must-not-appear")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_cancel_before",
        )
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await asyncio.wait_for(
            provider.operation.wait_for_checkpoint("before-output"),
            timeout=1,
        )
        first = await asyncio.wait_for(session.request_cancellation("cmd_cancel"), timeout=1)
        repeated = await asyncio.wait_for(session.request_cancellation("cmd_cancel"), timeout=1)
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, first, repeated, session

    lines, first, repeated, session = asyncio.run(scenario())

    assert first == "accepted"
    assert repeated == "already_requested"
    assert _event_types(lines) == ["session.started", "session.cancelled"]
    assert [event["correlation_id"] for event in _wire_events(lines)] == [
        "cmd_start",
        "cmd_cancel",
    ]
    assert session.lifecycle_state.status == "cancelled"


def test_preselected_cancellation_does_not_hang_when_session_start_cannot_publish() -> None:
    async def scenario() -> tuple[str, ProviderSession]:
        async def failing_sink(_line: bytes) -> None:
            raise OSError("injected protocol sink failure")

        fake = FakeProvider(())
        session = ProviderSession(
            OrderedEventWriter(failing_sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_start_failure",
        )
        result = await session.request_cancellation("cmd_cancel")
        with pytest.raises(OSError, match="protocol sink failure"):
            await asyncio.wait_for(session.run(), timeout=1)
        fake.assert_complete()
        return result, session

    result, session = asyncio.run(scenario())

    assert result == "accepted"
    assert session.lifecycle_state.status == "starting"


def test_conforming_cancel_waits_for_scheduled_iterator_close_without_a_diagnostic() -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (),
            block_iteration=True,
            cancel_releases_iteration=True,
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_scheduled_close",
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(operation.iteration_started.wait(), timeout=1)
        assert await session.request_cancellation("cmd_cancel") == "accepted"
        await asyncio.wait_for(running, timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())

    assert operation.cancel_calls == 1
    assert operation.iteration_finished.is_set()
    assert _event_types(lines) == ["session.started", "session.cancelled"]
    assert session.lifecycle_state.status == "cancelled"


@pytest.mark.parametrize(
    ("request_kind", "expected_types", "expected_status"),
    [
        (
            "user_cancellation",
            ["session.started", "session.cancelled"],
            "cancelled",
        ),
        ("teardown", ["session.started"], "running"),
    ],
)
def test_successful_cleanup_return_reaps_a_still_pending_read(
    request_kind: str,
    expected_types: list[str],
    expected_status: str,
) -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession, str]:
        lines: list[bytes] = []
        operation = _ControlledOperation((), block_iteration=True)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            _SingleOperationProvider(operation),
            _session_start(),
            "ses_early_cleanup_return",
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(operation.iteration_started.wait(), timeout=1)
        if request_kind == "user_cancellation":
            result = await asyncio.wait_for(
                session.request_cancellation("cmd_cancel"),
                timeout=1,
            )
        else:
            result = await asyncio.wait_for(session.request_teardown(), timeout=1)
        await asyncio.wait_for(running, timeout=1)
        return lines, operation, session, result

    lines, operation, session, result = asyncio.run(scenario())
    assert result == "accepted"
    assert operation.cancel_calls == 1
    assert operation.iteration_finished.is_set()
    assert _event_types(lines) == expected_types
    assert session.lifecycle_state.status == expected_status


def test_cancellation_between_deltas_suppresses_the_suffix() -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("kept")),
                        FakeProviderWaitForCancellation("between-deltas"),
                        FakeProviderEmit(ProviderTextDelta("dropped")),
                        FakeProviderEmit(ProviderTextCompleted("keptdropped")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_cancel_between",
        )
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await asyncio.wait_for(
            provider.operation.wait_for_checkpoint("between-deltas"),
            timeout=1,
        )
        assert await session.request_cancellation("cmd_cancel") == "accepted"
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())
    serialized = b"".join(lines).decode()

    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "session.cancelled",
    ]
    assert session.lifecycle_state.assistant_text == "kept"
    assert "dropped" not in serialized


@pytest.mark.parametrize("blocked_boundary", ["sink", "observer"])
def test_delta_transaction_finishes_before_user_cancellation(
    blocked_boundary: str,
) -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession, bool]:
        lines: list[bytes] = []
        transaction_started = asyncio.Event()
        release_transaction = asyncio.Event()
        observer_finished = asyncio.Event()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("committed")),
                        FakeProviderWaitForCancellation("after-committed-delta"),
                        FakeProviderEmit(ProviderTextCompleted("committed")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            if blocked_boundary == "sink" and b'"type":"assistant.delta"' in line:
                transaction_started.set()
                await release_transaction.wait()
            lines.append(line)

        async def observe(update: SessionUpdate, _state: SessionState) -> None:
            if isinstance(update, AssistantDeltaEvent):
                if blocked_boundary == "observer":
                    transaction_started.set()
                    await release_transaction.wait()
                observer_finished.set()

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_blocked_delta",
        )
        await session.attach_lifecycle_observer(observe)
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(transaction_started.wait(), timeout=1)

        cancelling = asyncio.create_task(session.request_cancellation("cmd_cancel"))
        await asyncio.sleep(0)
        cancellation_waited = not cancelling.done()
        release_transaction.set()
        result = await asyncio.wait_for(cancelling, timeout=1)
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        assert result == "accepted"
        assert observer_finished.is_set()
        return lines, session, cancellation_waited

    lines, session, cancellation_waited = asyncio.run(scenario())

    assert cancellation_waited is True
    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "session.cancelled",
    ]
    assert session.lifecycle_state.assistant_text == "committed"
    assert session.lifecycle_state.status == "cancelled"


@pytest.mark.parametrize("terminal_request", ["cancellation", "teardown"])
def test_usage_transaction_finishes_before_competing_terminal_selection(
    terminal_request: str,
) -> None:
    async def scenario() -> tuple[list[bytes], list[ModelUsageObserved], bool, str]:
        lines: list[bytes] = []
        usage_started = asyncio.Event()
        release_usage = asyncio.Event()
        usage_finished = asyncio.Event()
        observed: list[ModelUsageObserved] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("candidate")),
                        FakeProviderEmit(ProviderTextCompleted("candidate")),
                        FakeProviderEmit(ProviderUsageReported(input_tokens=13, output_tokens=2)),
                        FakeProviderWaitForCancellation("after-usage"),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def observe_usage(usage: ModelUsageObserved) -> None:
            usage_started.set()
            await release_usage.wait()
            observed.append(usage)
            usage_finished.set()

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_usage_race",
        )
        await session.attach_model_usage_observer(observe_usage)
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(usage_started.wait(), timeout=1)

        if terminal_request == "cancellation":
            competing = asyncio.create_task(session.request_cancellation("cmd_cancel"))
        else:
            competing = asyncio.create_task(session.request_teardown())
        await asyncio.sleep(0)
        selection_waited = not competing.done()
        release_usage.set()
        result = await asyncio.wait_for(competing, timeout=1)
        assert result == "accepted"
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        assert usage_finished.is_set()
        return lines, observed, selection_waited, session.lifecycle_state.status

    lines, observed, selection_waited, lifecycle_status = asyncio.run(scenario())

    assert selection_waited is True
    assert observed == [
        ModelUsageObserved(
            session_id="ses_usage_race",
            input_tokens=13,
            output_tokens=2,
        )
    ]
    expected_terminal = ["session.cancelled"] if terminal_request == "cancellation" else []
    assert _event_types(lines) == ["session.started", "assistant.delta", *expected_terminal]
    assert lifecycle_status == ("cancelled" if terminal_request == "cancellation" else "running")


@pytest.mark.parametrize("terminal_request", ["cancellation", "teardown"])
def test_terminal_selection_before_usage_suppresses_the_usage_observer(
    terminal_request: str,
) -> None:
    async def scenario() -> tuple[list[bytes], list[ModelUsageObserved], str]:
        lines: list[bytes] = []
        observed: list[ModelUsageObserved] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("candidate")),
                        FakeProviderEmit(ProviderTextCompleted("candidate")),
                        FakeProviderWaitForCancellation("before-usage-admission"),
                        FakeProviderEmit(ProviderUsageReported(input_tokens=13, output_tokens=2)),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def observe_usage(usage: ModelUsageObserved) -> None:
            observed.append(usage)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_usage_loses",
        )
        await session.attach_model_usage_observer(observe_usage)
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await provider.operation.wait_for_checkpoint("before-usage-admission")
        if terminal_request == "cancellation":
            result = await session.request_cancellation("cmd_cancel")
        else:
            result = await session.request_teardown()
        assert result == "accepted"
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, observed, session.lifecycle_state.status

    lines, observed, lifecycle_status = asyncio.run(scenario())

    expected_terminal = ["session.cancelled"] if terminal_request == "cancellation" else []
    assert _event_types(lines) == ["session.started", "assistant.delta", *expected_terminal]
    assert observed == []
    assert lifecycle_status == ("cancelled" if terminal_request == "cancellation" else "running")


def test_teardown_before_output_cleans_up_without_fabricating_terminal() -> None:
    async def scenario() -> tuple[list[bytes], str, str, ProviderSession]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderWaitForCancellation("before-teardown-output"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                        FakeProviderEmit(ProviderTextCompleted("must-not-appear")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_teardown",
        )
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await asyncio.wait_for(
            provider.operation.wait_for_checkpoint("before-teardown-output"),
            timeout=1,
        )
        first = await asyncio.wait_for(session.request_teardown(), timeout=1)
        repeated = await asyncio.wait_for(session.request_teardown(), timeout=1)
        await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, first, repeated, session

    lines, first, repeated, session = asyncio.run(scenario())

    assert first == "accepted"
    assert repeated == "already_requested"
    assert _event_types(lines) == ["session.started"]
    assert session.lifecycle_state.status == "running"


def test_outer_task_cancellation_reaps_provider_without_session_terminal() -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession]:
        lines: list[bytes] = []
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderWaitForCancellation("before-outer-cancel"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                        FakeProviderEmit(ProviderTextCompleted("must-not-appear")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        provider = _CapturingProvider(fake)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_outer_cancel",
        )
        running = asyncio.create_task(session.run())
        while provider.operation is None:
            await asyncio.sleep(0)
        await asyncio.wait_for(
            provider.operation.wait_for_checkpoint("before-outer-cancel"),
            timeout=1,
        )
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        return lines, session

    lines, session = asyncio.run(scenario())

    assert _event_types(lines) == ["session.started"]
    assert session.lifecycle_state.status == "running"


@pytest.mark.parametrize("cancellation_count", [1, 2])
def test_outer_cancellation_waits_for_admitted_delta_transaction(
    cancellation_count: int,
) -> None:
    async def scenario() -> tuple[list[bytes], ProviderSession, bool]:
        lines: list[bytes] = []
        sink_started = asyncio.Event()
        release_sink = asyncio.Event()
        observer_finished = asyncio.Event()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    _request(),
                    (
                        FakeProviderEmit(ProviderTextDelta("committed-before-teardown")),
                        FakeProviderWaitForCancellation("after-outer-delta"),
                        FakeProviderEmit(ProviderTextCompleted("committed-before-teardown")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )

        async def sink(line: bytes) -> None:
            if b'"type":"assistant.delta"' in line:
                sink_started.set()
                await release_sink.wait()
            lines.append(line)

        async def observe(update: SessionUpdate, _state: SessionState) -> None:
            if isinstance(update, AssistantDeltaEvent):
                observer_finished.set()

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            fake,
            _session_start(),
            "ses_outer_delta",
        )
        await session.attach_lifecycle_observer(observe)
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(sink_started.wait(), timeout=1)
        for _request_number in range(cancellation_count):
            running.cancel()
            await asyncio.sleep(0)
        cancellation_waited = not running.done()
        release_sink.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, timeout=1)
        fake.assert_complete()
        assert observer_finished.is_set()
        return lines, session, cancellation_waited

    lines, session, cancellation_waited = asyncio.run(scenario())

    assert cancellation_waited is True
    assert _event_types(lines) == ["session.started", "assistant.delta"]
    assert session.lifecycle_state.status == "running"
    assert session.lifecycle_state.assistant_text == "committed-before-teardown"


def test_completion_wins_cancellation_while_cleanup_is_pending() -> None:
    async def scenario() -> tuple[list[bytes], str, bool, _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (
                ProviderTextDelta("selected completion"),
                ProviderTextCompleted("selected completion"),
                ProviderCompleted(),
            ),
            block_wait_closed=True,
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_completion_race",
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(operation.wait_closed_started.wait(), timeout=1)
        assert _event_types(lines) == ["session.started", "assistant.delta"]

        cancelling = asyncio.create_task(session.request_cancellation("cmd_cancel"))
        await asyncio.sleep(0)
        cancellation_joined_cleanup = not cancelling.done()
        operation.release_wait_closed.set()
        cancellation_result = await asyncio.wait_for(cancelling, timeout=1)
        await asyncio.wait_for(running, timeout=1)
        return lines, cancellation_result, cancellation_joined_cleanup, operation, session

    lines, result, joined_cleanup, operation, session = asyncio.run(scenario())

    assert result == "terminal"
    assert joined_cleanup is True
    assert operation.wait_closed_calls == 1
    assert operation.cancel_calls == 0
    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert session.lifecycle_state.status == "completed"


def test_outer_cancellation_cannot_replace_selected_completion() -> None:
    async def scenario() -> tuple[list[bytes], bool, _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (
                ProviderTextDelta("survives outer cancellation"),
                ProviderTextCompleted("survives outer cancellation"),
                ProviderCompleted(),
            ),
            block_wait_closed=True,
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_selected_before_outer",
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(operation.wait_closed_started.wait(), timeout=1)
        running.cancel()
        await asyncio.sleep(0)
        running.cancel()
        await asyncio.sleep(0)
        cancellation_joined_cleanup = not running.done()
        operation.release_wait_closed.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, timeout=1)
        return lines, cancellation_joined_cleanup, operation, session

    lines, joined_cleanup, operation, session = asyncio.run(scenario())

    assert joined_cleanup is True
    assert operation.wait_closed_calls == 1
    assert operation.cancel_calls == 0
    assert _event_types(lines)[-2:] == ["assistant.completed", "session.completed"]
    assert session.lifecycle_state.status == "completed"


def test_completion_cleanup_failure_emits_one_safe_diagnostic_then_completion() -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession, str, str]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (
                ProviderTextDelta("still completes"),
                ProviderTextCompleted("still completes"),
                ProviderCompleted(),
            ),
            wait_closed_error="sk-secret-cleanup-exception",
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_cleanup_failure",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        teardown = await session.request_teardown()
        cancellation = await session.request_cancellation("cmd_cancel")
        return lines, operation, session, teardown, cancellation

    lines, operation, session, teardown, cancellation = asyncio.run(scenario())
    events = _wire_events(lines)
    diagnostics = [event for event in events if event["type"] == "runtime.error"]

    assert teardown == "terminal"
    assert cancellation == "terminal"
    assert operation.wait_closed_calls == 1
    assert operation.cancel_calls == 0
    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "runtime.error",
        "assistant.completed",
        "session.completed",
    ]
    assert diagnostics == [
        {
            "protocol_version": 1,
            "type": "runtime.error",
            "timestamp": TIMESTAMP,
            "correlation_id": "cmd_start",
            "payload": {
                "code": "provider_cleanup_failed",
                "message": "Provider cleanup could not be confirmed.",
                "recoverable": True,
            },
        }
    ]
    assert "sk-secret-cleanup-exception" not in b"".join(lines).decode()
    assert session.lifecycle_state.status == "completed"


def test_tool_cleanup_failure_does_not_rewrite_tool_failure() -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (
                ProviderToolCallRequested(
                    call_id="call_unsafe",
                    name="unsafe_tool",
                    arguments_json='{"secret":"never-copy-this"}',
                ),
            ),
            cancel_error="raw cleanup failure must remain private",
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_tool_cleanup_failure",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())
    events = _wire_events(lines)

    assert operation.cancel_calls == 1
    assert operation.wait_closed_calls == 0
    assert _event_types(lines) == ["session.started", "runtime.error", "session.failed"]
    assert events[-1]["payload"] == {
        "code": "tool_unavailable",
        "message": "Provider-requested tools are not available.",
    }
    assert "unsafe_tool" not in b"".join(lines).decode()
    assert "never-copy-this" not in b"".join(lines).decode()
    assert "raw cleanup failure" not in b"".join(lines).decode()
    assert session.lifecycle_state.status == "failed"


@pytest.mark.parametrize(
    "failure_point",
    [
        "start",
        "cancelled_start",
        "events",
        "cancelled_events",
        "iteration",
        "cancelled_iteration",
    ],
)
def test_unexpected_provider_boundary_failure_is_normalized_and_cleanup_is_attempted(
    failure_point: str,
) -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation | None]:
        lines: list[bytes] = []
        operation: _ControlledOperation | None = None

        if failure_point in {"start", "cancelled_start"}:

            class RaisingProvider:
                def start(self, _request_value: ProviderRequest) -> ProviderOperation:
                    if failure_point == "cancelled_start":
                        raise asyncio.CancelledError("provider-owned start cancellation")
                    raise RuntimeError("sk-secret-start-failure")

            provider = RaisingProvider()
        else:
            iteration_error: BaseException | None = None
            if failure_point == "iteration":
                iteration_error = RuntimeError("sk-secret-iteration-failure")
            elif failure_point == "cancelled_iteration":
                iteration_error = asyncio.CancelledError("provider-owned cancellation")
            operation = _ControlledOperation(
                (),
                events_error=(
                    asyncio.CancelledError("provider-owned events cancellation")
                    if failure_point == "cancelled_events"
                    else (
                        RuntimeError("sk-secret-events-claim-failure")
                        if failure_point == "events"
                        else None
                    )
                ),
                iteration_error=iteration_error,
            )
            provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_provider_exception",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        assert session.lifecycle_state.status == "failed"
        return lines, operation

    lines, operation = asyncio.run(scenario())
    serialized = b"".join(lines).decode()

    assert _event_types(lines) == ["session.started", "session.failed"]
    assert _wire_events(lines)[-1]["payload"] == {
        "code": "provider_invalid_response",
        "message": "The provider returned an invalid response.",
    }
    assert "secret" not in serialized
    if operation is not None:
        assert operation.cancel_calls == 1


def test_provider_iterator_accepts_a_general_awaitable_from_anext() -> None:
    async def scenario() -> tuple[list[bytes], _IteratorBoundaryOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _IteratorBoundaryOperation(
            _FutureBackedIterator(
                (
                    ProviderTextDelta("future-backed"),
                    ProviderTextCompleted("future-backed"),
                    ProviderCompleted(),
                )
            )
        )

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            _SingleOperationProvider(operation),
            _session_start(),
            "ses_future_iterator",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())

    assert _event_types(lines) == [
        "session.started",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert operation.cancel_calls == 0
    assert operation.wait_closed_calls == 1
    assert session.lifecycle_state.status == "completed"


@pytest.mark.parametrize("boundary", ["synchronous_eof", "synchronous_error", "not_iterator"])
def test_provider_iterator_setup_failure_is_normalized_and_cancelled(boundary: str) -> None:
    async def scenario() -> tuple[list[bytes], _IteratorBoundaryOperation, ProviderSession]:
        lines: list[bytes] = []
        if boundary == "synchronous_eof":
            events: object = _SynchronousFailingIterator(StopAsyncIteration())
        elif boundary == "synchronous_error":
            events = _SynchronousFailingIterator(RuntimeError("sk-secret-sync-anext-failure"))
        else:
            events = object()
        operation = _IteratorBoundaryOperation(events)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            _SingleOperationProvider(operation),
            _session_start(),
            "ses_invalid_iterator",
        )
        await asyncio.wait_for(session.run(), timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())

    assert _event_types(lines) == ["session.started", "session.failed"]
    assert _wire_events(lines)[-1]["payload"] == {
        "code": "provider_invalid_response",
        "message": "The provider returned an invalid response.",
    }
    assert "secret" not in b"".join(lines).decode()
    assert operation.cancel_calls == 1
    assert operation.wait_closed_calls == 0
    assert session.lifecycle_state.status == "failed"


def test_teardown_cleanup_failure_emits_only_the_safe_runtime_diagnostic() -> None:
    async def scenario() -> tuple[list[bytes], _ControlledOperation, ProviderSession]:
        lines: list[bytes] = []
        operation = _ControlledOperation(
            (),
            block_iteration=True,
            cancel_error="sk-secret-teardown-cleanup-failure",
        )
        provider = _SingleOperationProvider(operation)

        async def sink(line: bytes) -> None:
            lines.append(line)

        session = ProviderSession(
            OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
            provider,
            _session_start(),
            "ses_teardown_cleanup_failure",
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(operation.iteration_started.wait(), timeout=1)
        assert await asyncio.wait_for(session.request_teardown(), timeout=1) == "accepted"
        await asyncio.wait_for(running, timeout=1)
        return lines, operation, session

    lines, operation, session = asyncio.run(scenario())

    assert operation.cancel_calls == 1
    assert _event_types(lines) == ["session.started", "runtime.error"]
    assert _wire_events(lines)[-1]["payload"] == {
        "code": "provider_cleanup_failed",
        "message": "Provider cleanup could not be confirmed.",
        "recoverable": True,
    }
    assert "secret" not in b"".join(lines).decode()
    assert session.lifecycle_state.status == "running"
