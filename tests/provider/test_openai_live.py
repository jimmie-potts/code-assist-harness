from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import cast

import pytest

from code_assist_harness.loop_limits import LoopLimits
from code_assist_harness.protocol import OrderedEventWriter, SessionId, SessionStartCommand
from code_assist_harness.provider_session import ProviderSession

TIMESTAMP = "2026-08-01T12:34:56.789Z"


def _event_types(lines: Sequence[bytes]) -> list[str]:
    return [cast(str, json.loads(line)["type"]) for line in lines]


@pytest.mark.live_provider
def test_openai_responses_live_smoke(live_provider_configuration: object) -> None:
    """Run one deliberately selected request through the bounded provider-neutral session."""
    from code_assist_harness.provider.openai_responses import OpenAIResponsesProvider

    async def run() -> tuple[object, list[bytes]]:
        lines: list[bytes] = []

        async def sink(line: bytes) -> None:
            lines.append(line)

        command = SessionStartCommand.model_validate(
            {
                "protocol_version": 1,
                "type": "session.start",
                "command_id": "cmd_live_openai",
                "timestamp": TIMESTAMP,
                "payload": {"task": "Reply with exactly the word READY."},
            }
        )
        limits = LoopLimits(
            max_model_turns=1,
            provider_work_timeout_seconds=60,
            max_assistant_output_bytes=512,
            max_observed_tool_calls=1,
        )
        session = ProviderSession(
            OrderedEventWriter(sink, lambda: TIMESTAMP),
            OpenAIResponsesProvider(live_provider_configuration),
            command,
            SessionId("ses_live_openai"),
            limits=limits,
        )
        await session.run()
        return session.lifecycle_state, lines

    try:
        state, lines = asyncio.run(run())
    except Exception:
        pytest.fail(
            "live provider smoke escaped bounded provider normalization",
            pytrace=False,
        )

    status = cast(str, getattr(state, "status"))
    if status != "completed":
        failure = getattr(state, "session_failure")
        code = "none" if failure is None else cast(str, getattr(failure, "code"))
        pytest.fail(
            f"live provider smoke ended with bounded status {status} ({code})",
            pytrace=False,
        )
    assert getattr(state, "assistant_text"), "live provider returned no assistant text"
    assert _event_types(lines)[0] == "session.started"
    assert _event_types(lines)[-1] == "session.completed"
