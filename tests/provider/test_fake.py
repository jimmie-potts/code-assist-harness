from __future__ import annotations

import asyncio

import pytest

from code_assist_harness.provider import (
    FakeProvider,
    FakeProviderDelay,
    FakeProviderEmit,
    FakeProviderExchange,
    FakeProviderMismatch,
    FakeProviderOperation,
    FakeProviderWaitForCancellation,
    ProviderCompleted,
    ProviderFailed,
    ProviderFailure,
    ProviderMessage,
    ProviderRequest,
    ProviderTextCompleted,
    ProviderTextDelta,
    ProviderToolCallRequested,
    ProviderUsageReported,
    RepositoryInstruction,
)


def _request(task: str = "Inspect the provider boundary.") -> ProviderRequest:
    return ProviderRequest(
        conversation=(ProviderMessage(role="user", content=task),),
        repository_instructions=(
            RepositoryInstruction(
                source="AGENTS.md",
                content="Keep provider SDK values behind the adapter.",
            ),
        ),
    )


async def _collect(operation: object) -> tuple[object, ...]:
    return tuple([event async for event in operation.events()])  # type: ignore[attr-defined]


def test_fake_emits_every_success_variant_in_exact_order_and_completes() -> None:
    request = _request()
    expected_events = (
        ProviderTextDelta("hel"),
        ProviderTextDelta("lo"),
        ProviderTextCompleted("hello"),
        ProviderToolCallRequested(
            call_id="call_read",
            name="read_file",
            arguments_json='{"path":"README.md"',
        ),
        ProviderUsageReported(input_tokens=19, output_tokens=7),
        ProviderCompleted(),
    )
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=request,
                steps=tuple(FakeProviderEmit(event) for event in expected_events),
            ),
        )
    )

    operation = fake.start(request)
    actual_events = asyncio.run(_collect(operation))

    assert actual_events == expected_events
    asyncio.run(operation.wait_closed())
    fake.assert_complete()


def test_named_delay_blocks_without_wall_clock_sleep_and_resumes_when_released() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderDelay("before-first-delta"),
                        FakeProviderEmit(ProviderTextDelta("ready")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        operation = fake.start(request)
        events = operation.events()
        first_event = asyncio.create_task(anext(events))

        await operation.wait_for_checkpoint("before-first-delta")
        assert not first_event.done()
        operation.release_checkpoint("before-first-delta")

        assert await first_event == ProviderTextDelta("ready")
        assert await anext(events) == ProviderCompleted()
        await operation.wait_closed()
        fake.assert_complete()

    asyncio.run(scenario())


def test_normalized_provider_failure_is_a_terminal_scripted_event() -> None:
    request = _request()
    failure_event = ProviderFailed(
        ProviderFailure(
            code="unavailable",
            message="The provider is temporarily unavailable.",
            retryable=True,
        )
    )
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=request,
                steps=(FakeProviderEmit(failure_event),),
            ),
        )
    )

    assert asyncio.run(_collect(fake.start(request))) == (failure_event,)
    fake.assert_complete()


def test_request_mismatch_reports_only_bounded_field_paths() -> None:
    expected_secret = "EXPECTED_FAKE_SECRET_123"
    actual_secret = "ACTUAL_FAKE_SECRET_456"
    expected = _request(expected_secret)
    actual = ProviderRequest(
        conversation=(ProviderMessage(role="user", content=actual_secret),),
        repository_instructions=(
            RepositoryInstruction(source="PRIVATE.md", content=actual_secret),
        ),
    )
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=expected,
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
        )
    )

    with pytest.raises(FakeProviderMismatch) as mismatch:
        fake.start(actual)

    diagnostic = str(mismatch.value)
    assert "request 1" in diagnostic
    assert "conversation[0].content" in diagnostic
    assert "repository_instructions[0].source" in diagnostic
    assert "repository_instructions[0].content" in diagnostic
    assert expected_secret not in diagnostic
    assert actual_secret not in diagnostic
    assert "PRIVATE.md" not in diagnostic


def test_extra_request_fails_immediately_after_the_script_is_consumed() -> None:
    request = _request()
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=request,
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
        )
    )
    asyncio.run(_collect(fake.start(request)))

    with pytest.raises(FakeProviderMismatch, match="unexpected request 2"):
        fake.start(request)


def test_omitted_request_fails_explicit_completion_verification() -> None:
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=_request(),
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
        )
    )

    with pytest.raises(FakeProviderMismatch, match="expected request 1"):
        fake.assert_complete()


def test_consumer_stopping_early_leaves_an_actionable_unconsumed_step() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderEmit(ProviderTextDelta("partial")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        operation = fake.start(request)
        events = operation.events()

        assert await anext(events) == ProviderTextDelta("partial")
        with pytest.raises(FakeProviderMismatch, match=r"step 2 \(emit:response.completed\)"):
            fake.assert_complete()

        assert await operation.cancel() == "cancelled"
        with pytest.raises(FakeProviderMismatch, match="stopped before step 2"):
            fake.assert_complete()

    asyncio.run(scenario())


def test_cancellation_before_output_closes_stream_and_suppresses_later_events() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderWaitForCancellation("before-output"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                    ),
                ),
            )
        )
        operation = fake.start(request)
        events = operation.events()
        pending_event = asyncio.create_task(anext(events))

        await operation.wait_for_checkpoint("before-output")
        assert await operation.cancel() == "cancelled"
        with pytest.raises(StopAsyncIteration):
            await pending_event
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        await operation.wait_closed()
        assert await operation.cancel() == "already_closed"
        fake.assert_complete()

    asyncio.run(scenario())


def test_cancellation_between_deltas_preserves_only_the_accepted_prefix() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderEmit(ProviderTextDelta("first")),
                        FakeProviderWaitForCancellation("between-deltas"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        operation = fake.start(request)
        events = operation.events()

        assert await anext(events) == ProviderTextDelta("first")
        pending_event = asyncio.create_task(anext(events))
        await operation.wait_for_checkpoint("between-deltas")
        assert await operation.cancel() == "cancelled"
        with pytest.raises(StopAsyncIteration):
            await pending_event
        with pytest.raises(StopAsyncIteration):
            await anext(events)
        fake.assert_complete()

    asyncio.run(scenario())


def test_cancellation_after_natural_completion_is_a_safe_noop() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(FakeProviderEmit(ProviderCompleted()),),
                ),
            )
        )
        operation = fake.start(request)

        assert tuple([event async for event in operation.events()]) == (ProviderCompleted(),)
        assert await operation.cancel() == "already_closed"
        fake.assert_complete()

    asyncio.run(scenario())


def test_event_stream_rejects_a_second_consumer() -> None:
    request = _request()
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=request,
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
        )
    )
    operation = fake.start(request)

    operation.events()
    with pytest.raises(RuntimeError, match="only once"):
        operation.events()
    asyncio.run(operation.cancel())


def test_public_fake_operation_contract_cannot_bypass_exchange_validation() -> None:
    with pytest.raises(TypeError, match="Protocols cannot be instantiated"):
        FakeProviderOperation()  # type: ignore[abstract]


def test_multiple_exchanges_must_start_and_finish_in_order() -> None:
    first_request = _request("First")
    second_request = _request("Second")
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=first_request,
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
            FakeProviderExchange(
                expected_request=second_request,
                steps=(FakeProviderEmit(ProviderCompleted()),),
            ),
        )
    )

    asyncio.run(_collect(fake.start(first_request)))
    asyncio.run(_collect(fake.start(second_request)))
    fake.assert_complete()


def test_consumer_task_cancellation_closes_but_does_not_hide_unconsumed_script() -> None:
    async def scenario() -> None:
        request = _request()
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderDelay("blocked"),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                ),
            )
        )
        operation = fake.start(request)
        pending_event = asyncio.create_task(anext(operation.events()))
        await operation.wait_for_checkpoint("blocked")

        pending_event.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_event
        await operation.wait_closed()
        with pytest.raises(FakeProviderMismatch, match="stopped before step 1"):
            fake.assert_complete()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "steps",
    [
        (),
        (FakeProviderEmit(ProviderTextDelta("unterminated")),),
        (
            FakeProviderEmit(ProviderCompleted()),
            FakeProviderEmit(ProviderTextDelta("after-terminal")),
        ),
        (
            FakeProviderWaitForCancellation("cancel"),
            FakeProviderDelay("unreachable-delay"),
        ),
    ],
)
def test_invalid_or_ambiguous_exchange_scripts_are_rejected(
    steps: tuple[object, ...],
) -> None:
    with pytest.raises(ValueError):
        FakeProviderExchange(
            expected_request=_request(),
            steps=steps,  # type: ignore[arg-type]
        )
