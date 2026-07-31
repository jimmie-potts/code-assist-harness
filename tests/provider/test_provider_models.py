from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from code_assist_harness.provider import (
    MAX_PROVIDER_FAILURE_MESSAGE_CHARS,
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


def test_request_is_immutable_and_preserves_caller_supplied_order() -> None:
    first_message = ProviderMessage(role="user", content="Inspect the repository.")
    second_message = ProviderMessage(role="assistant", content="I will inspect it.")
    root_instruction = RepositoryInstruction(source="AGENTS.md", content="Stay in scope.")
    nested_instruction = RepositoryInstruction(
        source="src/AGENTS.md",
        content="Keep provider types neutral.",
    )

    request = ProviderRequest(
        conversation=(first_message, second_message),
        repository_instructions=(root_instruction, nested_instruction),
    )

    assert request.conversation == (first_message, second_message)
    assert request.repository_instructions == (root_instruction, nested_instruction)
    with pytest.raises(FrozenInstanceError):
        request.conversation = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "expected_error"),
    [
        (lambda: ProviderMessage(role="user", content=""), ValueError),
        (lambda: ProviderMessage(role="system", content="x"), ValueError),
        (lambda: RepositoryInstruction(source="", content="x"), ValueError),
        (lambda: RepositoryInstruction(source="AGENTS.md", content=""), ValueError),
        (lambda: ProviderRequest(conversation=()), ValueError),
        (lambda: ProviderRequest(conversation=[]), TypeError),
        (
            lambda: ProviderRequest(
                conversation=(ProviderMessage(role="user", content="x"),),
                repository_instructions=[],
            ),
            TypeError,
        ),
    ],
)
def test_request_values_reject_invalid_semantic_shapes(
    factory: object,
    expected_error: type[Exception],
) -> None:
    with pytest.raises(expected_error):
        factory()  # type: ignore[operator]


def test_every_provider_stream_variant_is_harness_owned_and_constructible() -> None:
    failure = ProviderFailure(
        code="unavailable",
        message="The provider is temporarily unavailable.",
        retryable=True,
    )
    events = (
        ProviderTextDelta("hel"),
        ProviderTextCompleted("hello"),
        ProviderToolCallRequested(
            call_id="call_1",
            name="read_file",
            arguments_json='{"path":"README.md"}',
        ),
        ProviderUsageReported(input_tokens=12, output_tokens=3),
        ProviderCompleted(),
        ProviderFailed(failure),
    )

    assert [event.kind for event in events] == [
        "text.delta",
        "text.completed",
        "tool.call_requested",
        "usage.reported",
        "response.completed",
        "response.failed",
    ]


def test_tool_arguments_preserve_malformed_serialized_input_without_parsing() -> None:
    malformed = '{"path": "README.md"'

    event = ProviderToolCallRequested(
        call_id="call_malformed",
        name="read_file",
        arguments_json=malformed,
    )

    assert event.arguments_json == malformed


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "expected_error"),
    [
        (-1, 0, ValueError),
        (0, -1, ValueError),
        (True, 0, TypeError),
        (0, False, TypeError),
        (1.5, 0, TypeError),
    ],
)
def test_usage_rejects_negative_or_non_integer_counts(
    input_tokens: object,
    output_tokens: object,
    expected_error: type[Exception],
) -> None:
    with pytest.raises(expected_error):
        ProviderUsageReported(
            input_tokens=input_tokens,  # type: ignore[arg-type]
            output_tokens=output_tokens,  # type: ignore[arg-type]
        )


def test_normalized_failure_is_bounded_single_line_and_has_no_raw_payload_field() -> None:
    accepted = ProviderFailure(
        code="rate_limited",
        message="Retry after the provider recovers.",
        retryable=True,
    )

    assert {field.name for field in fields(ProviderFailure)} == {
        "code",
        "message",
        "retryable",
    }
    assert not hasattr(accepted, "raw_payload")
    assert not hasattr(accepted, "exception")

    for line_separator in ("\n", "\r", "\u2028", "\u2029"):
        with pytest.raises(ValueError):
            ProviderFailure(
                code="unknown",
                message=f"unsafe{line_separator}message",
                retryable=False,
            )
    with pytest.raises(ValueError):
        ProviderFailure(
            code="unknown",
            message="x" * (MAX_PROVIDER_FAILURE_MESSAGE_CHARS + 1),
            retryable=False,
        )
    with pytest.raises(ValueError):
        ProviderFailure(code="vendor_secret_code", message="safe", retryable=False)
    with pytest.raises(TypeError):
        ProviderFailure(code="unknown", message="safe", retryable=1)  # type: ignore[arg-type]
