from __future__ import annotations

import asyncio
import json
import os
import traceback
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

import code_assist_harness.persistence.transcript as transcript_module
from code_assist_harness.model_evidence import (
    MAX_MODEL_USAGE_TOKENS,
    ModelUsageObserved,
)
from code_assist_harness.persistence import (
    SessionTranscript,
    TranscriptFileOperations,
    TranscriptPersistenceError,
    TranscriptReplayError,
    TranscriptSettings,
    configured_sensitive_values,
    replay_transcript,
    stable_workspace_id,
)
from code_assist_harness.protocol import SessionEvent, validate_event
from code_assist_harness.provider import (
    FakeProvider,
    FakeProviderEmit,
    FakeProviderExchange,
    ProviderFailed,
    ProviderFailure,
    ProviderMessage,
    ProviderRequest,
)
from code_assist_harness.session_state import (
    INITIAL_SESSION_STATE,
    ApprovalRequested,
    ApprovalResolved,
    CancelRequested,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
)

TIMESTAMP = "2026-07-30T12:34:56.789Z"
START_COMMAND_ID = "cmd_transcript_start"
CANCEL_COMMAND_ID = "cmd_transcript_cancel"
SESSION_ID = "ses_transcript"
FAKE_SECRET = "FAKE_CAH_SECRET_VALUE_12345"


def _event(
    event_type: str,
    sequence: int,
    *,
    text: str = "",
    correlation_id: str = START_COMMAND_ID,
    failure_code: str = "provider_failed",
    failure_message: str = "The session failed safely.",
) -> SessionEvent:
    if event_type in {"assistant.delta", "assistant.completed"}:
        payload: dict[str, object] = {"text": text}
    elif event_type == "session.failed":
        payload = {"code": failure_code, "message": failure_message}
    else:
        payload = {}
    return cast(
        SessionEvent,
        validate_event(
            {
                "protocol_version": 1,
                "type": event_type,
                "session_id": SESSION_ID,
                "sequence": sequence,
                "timestamp": TIMESTAMP,
                "correlation_id": correlation_id,
                "payload": payload,
            }
        ),
    )


def _accepted_updates(updates: Iterable[SessionUpdate]) -> list[tuple[SessionUpdate, SessionState]]:
    accepted: list[tuple[SessionUpdate, SessionState]] = []
    state = INITIAL_SESSION_STATE
    for update in updates:
        reduction = reduce_session_state(state, update)
        assert reduction.ok
        state = reduction.state
        accepted.append((update, state))
    return accepted


async def _record_updates(
    transcript: SessionTranscript,
    updates: Iterable[SessionUpdate],
) -> tuple[SessionState, list[object | None]]:
    failures: list[object | None] = []
    accepted = _accepted_updates(updates)
    for update, state in accepted:
        failures.append(await transcript.record(update, state))
    return accepted[-1][1], failures


async def _record_completed_turn_with_usage(
    transcript: SessionTranscript,
    observation: ModelUsageObserved,
) -> tuple[SessionState, list[object | None]]:
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Measure one model turn"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
        _event("session.completed", 4),
    ]
    accepted = _accepted_updates(updates)
    failures = [
        *[await transcript.record(update, state) for update, state in accepted[:3]],
        await transcript.record_model_usage(observation),
        *[await transcript.record(update, state) for update, state in accepted[3:]],
    ]
    return accepted[-1][1], failures


def _read_json_records(path: Path) -> list[dict[str, object]]:
    return [cast(dict[str, object], json.loads(line)) for line in path.read_bytes().splitlines()]


def _write_json_records(path: Path, records: Iterable[dict[str, object]]) -> None:
    path.write_bytes(
        b"".join(
            json.dumps(record, separators=(",", ":")).encode("utf-8") + b"\n" for record in records
        )
    )


def _settings(tmp_path: Path, **overrides: object) -> TranscriptSettings:
    values: dict[str, object] = {
        "state_directory": tmp_path / "state" / "code-assist-harness",
        "sensitive_values": (FAKE_SECRET,),
        "text_limit_bytes": 16 * 1024,
    }
    values.update(overrides)
    return TranscriptSettings(**values)  # type: ignore[arg-type]


def _create_transcript(
    tmp_path: Path,
    *,
    settings: TranscriptSettings | None = None,
    operations: TranscriptFileOperations | None = None,
    transcript_id: str = "fixed_transcript_001",
) -> SessionTranscript:
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return asyncio.run(
        SessionTranscript.create(
            settings or _settings(tmp_path),
            workspace.resolve(),
            SESSION_ID,
            operations=operations,
            clock=lambda: TIMESTAMP,
            create_transcript_id=lambda: transcript_id,
        )
    )


def test_settings_use_absolute_xdg_or_an_injected_home_fallback(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    configured = TranscriptSettings.from_environment(
        {
            "XDG_STATE_HOME": str(xdg),
            "OPENAI_API_KEY": FAKE_SECRET,
            "UNRELATED": "must-not-be-retained",
        }
    )
    fallback = TranscriptSettings.from_environment(
        {"XDG_STATE_HOME": "relative/state"},
        home=tmp_path / "home",
    )

    assert configured.state_directory == xdg / "code-assist-harness"
    assert configured.sensitive_values == (FAKE_SECRET,)
    assert FAKE_SECRET not in repr(configured)
    assert fallback.state_directory == tmp_path / "home/.local/state/code-assist-harness"
    assert configured_sensitive_values(
        {
            "TOKEN": "same-secret",
            "SECOND_TOKEN": "same-secret",
            "PATH": "same-secret",
            "DATABASE_URL": "postgresql://fake-credential",
            "SENTRY_DSN": "https://fake-dsn.invalid/1",
            "AWS_ACCESS_KEY_ID": "FAKEACCESSKEY123",
        }
    ) == (
        "postgresql://fake-credential",
        "https://fake-dsn.invalid/1",
        "FAKEACCESSKEY123",
        "same-secret",
    )
    assert configured_sensitive_values({"AUTH": "x"}) == ("x",)
    database_secrets = {
        "PGPASSWORD": "fake-postgres-password",
        "MYSQL_PWD": "fake-mysql-password",
        "REDIS_URL": "redis://fake-credential",
        "MONGODB_URI": "mongodb://fake-credential",
    }
    assert set(configured_sensitive_values(database_secrets)) == set(database_secrets.values())


def test_even_a_one_character_configured_secret_is_redacted(tmp_path: Path) -> None:
    transcript = _create_transcript(
        tmp_path,
        settings=_settings(tmp_path, sensitive_values=("x",)),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="x"),
        _event("session.started", 1),
    ]

    asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert replay.state.task == "[REDACTED]"
    assert b'"task":"x"' not in transcript.transcript_path.read_bytes()


def test_workspace_identifier_is_stable_for_aliases_and_hides_path_names(tmp_path: Path) -> None:
    workspace = tmp_path / "private-user" / "secret-repository-name"
    workspace.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(workspace, target_is_directory=True)
    other = tmp_path / "other"
    other.mkdir()

    workspace_id = stable_workspace_id(workspace)

    assert workspace_id == stable_workspace_id(alias)
    assert workspace_id != stable_workspace_id(other)
    assert "private-user" not in workspace_id
    assert "secret-repository-name" not in workspace_id


def test_completed_transcript_redacts_split_secrets_replays_and_summarizes(
    tmp_path: Path,
) -> None:
    transcript = _create_transcript(tmp_path)
    first_delta = f"Safe prefix {FAKE_SECRET[:14]}"
    second_delta = f"{FAKE_SECRET[14:]} and suffix"
    complete_text = first_delta + second_delta
    updates: list[SessionUpdate] = [
        TaskSubmitted(
            command_id=START_COMMAND_ID,
            task=f"Explain this without exposing {FAKE_SECRET}",
        ),
        _event("session.started", 1),
        _event("assistant.delta", 2, text=first_delta),
        _event("assistant.delta", 3, text=second_delta),
        _event("assistant.completed", 4, text=complete_text),
        _event("session.completed", 5),
    ]

    live_state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)
    transcript_bytes = transcript.transcript_path.read_bytes()
    summary_bytes = transcript.summary_path.read_bytes()
    records = [json.loads(line) for line in transcript_bytes.splitlines()]

    assert failures == [None] * len(updates)
    assert live_state.status == "completed"
    assert replay.complete
    assert replay.state.status == live_state.status
    assert replay.state.assistant_completed
    assert FAKE_SECRET not in replay.state.task
    assert FAKE_SECRET not in replay.state.assistant_text
    assert b"FAKE_CAH_SECRET_VALUE_12345" not in transcript_bytes
    assert b"FAKE_CAH_SECRET_VALUE_12345" not in summary_bytes
    assert FAKE_SECRET[:14].encode() not in transcript_bytes
    assert FAKE_SECRET[14:].encode() not in transcript_bytes
    assert b"[REDACTED]" in transcript_bytes
    assert [record["record_order"] for record in records] == list(range(1, 7))
    assert {record["transcript_version"] for record in records} == {2}
    assert [record["kind"] for record in records] == [
        "domain_fact",
        "session_event",
        "session_event",
        "session_event",
        "session_event",
        "session_event",
    ]
    assert [record["input"].get("sequence") for record in records] == [None, 1, 2, 3, 4, 5]
    stored_deltas = [
        record["input"]["payload"]["text"]
        for record in records
        if record["input"]["type"] == "assistant.delta"
    ]
    stored_completion = next(
        record["input"]["payload"]["text"]
        for record in records
        if record["input"]["type"] == "assistant.completed"
    )
    assert stored_completion == "".join(stored_deltas)
    assert "Outcome: completed" in transcript.summary_path.read_text(encoding="utf-8")
    assert "Model usage: unavailable" in transcript.summary_path.read_text(encoding="utf-8")
    assert "Changed files: unavailable" in transcript.summary_path.read_text(encoding="utf-8")
    assert "Check results: unavailable" in transcript.summary_path.read_text(encoding="utf-8")


def test_replay_accepts_a_complete_version_one_lifecycle_tape(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Replay an older tape"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Compatible"),
        _event("assistant.completed", 3, text="Compatible"),
        _event("session.completed", 4),
    ]
    asyncio.run(_record_updates(transcript, updates))
    records = _read_json_records(transcript.transcript_path)
    for record in records:
        record["transcript_version"] = 1
    _write_json_records(transcript.transcript_path, records)

    replay = replay_transcript(transcript.transcript_path)

    assert replay.complete
    assert replay.state.status == "completed"
    assert replay.state.assistant_text == "Compatible"
    assert replay.evidence.model_usage is None
    assert {record.transcript_version for record in replay.records} == {1}


def test_replay_rejects_mixed_transcript_versions_at_the_first_change(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Reject mixed versions"),
        _event("session.started", 1),
    ]
    asyncio.run(_record_updates(transcript, updates))
    records = _read_json_records(transcript.transcript_path)
    records[1]["transcript_version"] = 1
    _write_json_records(transcript.transcript_path, records)

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(transcript.transcript_path)

    assert replay_error.value.code == "transcript_version_mismatch"
    assert replay_error.value.line_number == 2


@pytest.mark.parametrize("boolean_version", [False, True])
def test_replay_rejects_boolean_transcript_versions(
    tmp_path: Path,
    boolean_version: bool,
) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Reject boolean versions"),
    ]
    asyncio.run(_record_updates(transcript, updates))
    records = _read_json_records(transcript.transcript_path)
    records[0]["transcript_version"] = boolean_version
    _write_json_records(transcript.transcript_path, records)

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(transcript.transcript_path)

    assert replay_error.value.code == "invalid_record"
    assert replay_error.value.line_number == 1


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [(0, 0), (MAX_MODEL_USAGE_TOKENS, MAX_MODEL_USAGE_TOKENS)],
)
def test_model_usage_is_version_two_evidence_and_appears_in_the_summary(
    tmp_path: Path,
    input_tokens: int,
    output_tokens: int,
) -> None:
    transcript = _create_transcript(tmp_path)
    observation = ModelUsageObserved(
        session_id=SESSION_ID,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    live_state, failures = asyncio.run(_record_completed_turn_with_usage(transcript, observation))
    replay = replay_transcript(transcript.transcript_path)
    records = _read_json_records(transcript.transcript_path)
    usage_record = records[3]
    summary = transcript.summary_path.read_text(encoding="utf-8")

    assert failures == [None] * 6
    assert live_state.status == "completed"
    assert replay.complete
    assert replay.evidence.model_usage == observation
    assert usage_record == {
        "transcript_version": 2,
        "record_order": 4,
        "recorded_at": TIMESTAMP,
        "workspace_id": records[0]["workspace_id"],
        "session_id": SESSION_ID,
        "kind": "model.usage_observed",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    assert f"Model input tokens: {input_tokens}" in summary
    assert f"Model output tokens: {output_tokens}" in summary
    assert "Model usage: unavailable" not in summary


@pytest.mark.parametrize(
    ("mutation", "expected_code", "line_number"),
    [
        ("before_text", "lifecycle_invariant_failed", 3),
        ("duplicate", "lifecycle_invariant_failed", 5),
        ("wrong_session", "session_mismatch", 4),
        ("version_one_usage", "invalid_record", 4),
    ],
)
def test_replay_rejects_invalid_model_usage_records(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    line_number: int,
) -> None:
    transcript = _create_transcript(tmp_path)
    observation = ModelUsageObserved(
        session_id=SESSION_ID,
        input_tokens=12,
        output_tokens=4,
    )
    asyncio.run(_record_completed_turn_with_usage(transcript, observation))
    records = _read_json_records(transcript.transcript_path)
    if mutation == "before_text":
        records.insert(2, records.pop(3))
    elif mutation == "duplicate":
        records.insert(4, dict(records[3]))
    elif mutation == "wrong_session":
        records[3]["session_id"] = "ses_other"
    else:
        records[3]["transcript_version"] = 1
    for record_order, record in enumerate(records, start=1):
        record["record_order"] = record_order
    _write_json_records(transcript.transcript_path, records)

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(transcript.transcript_path)

    assert replay_error.value.code == expected_code
    assert replay_error.value.line_number == line_number


def test_replay_rejects_an_assistant_delta_after_model_usage(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    observation = ModelUsageObserved(
        session_id=SESSION_ID,
        input_tokens=12,
        output_tokens=4,
    )
    asyncio.run(_record_completed_turn_with_usage(transcript, observation))
    records = _read_json_records(transcript.transcript_path)
    late_delta = cast(dict[str, object], json.loads(json.dumps(records[2])))
    late_input = cast(dict[str, object], late_delta["input"])
    late_input["sequence"] = 3
    cast(dict[str, object], late_input["payload"])["text"] = " late"
    completed_input = cast(dict[str, object], records[4]["input"])
    completed_input["sequence"] = 4
    cast(dict[str, object], completed_input["payload"])["text"] = "Done late"
    cast(dict[str, object], records[5]["input"])["sequence"] = 5
    records.insert(4, late_delta)
    for record_order, record in enumerate(records, start=1):
        record["record_order"] = record_order
    _write_json_records(transcript.transcript_path, records)

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(transcript.transcript_path)

    assert replay_error.value.code == "lifecycle_invariant_failed"
    assert replay_error.value.line_number == 5


@pytest.mark.parametrize("invalid_case", ["before_text", "after_completion", "wrong_session"])
def test_writer_rejects_model_usage_outside_its_single_valid_window(
    tmp_path: Path,
    invalid_case: str,
) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Keep usage ordered"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
    ]
    accepted = _accepted_updates(updates)
    accepted_count = 2 if invalid_case == "before_text" else 3
    if invalid_case == "after_completion":
        accepted_count = 4

    async def record_invalid_usage() -> object | None:
        for update, state in accepted[:accepted_count]:
            assert await transcript.record(update, state) is None
        return await transcript.record_model_usage(
            ModelUsageObserved(
                session_id="ses_other" if invalid_case == "wrong_session" else SESSION_ID,
                input_tokens=3,
                output_tokens=1,
            )
        )

    failure = asyncio.run(record_invalid_usage())
    replay = replay_transcript(transcript.transcript_path)

    assert failure is not None
    assert failure.code == "transcript_write_failed"
    assert replay.evidence.model_usage is None
    assert len(replay.records) == accepted_count
    assert not transcript.summary_path.exists()


def test_writer_rejects_an_assistant_delta_after_model_usage(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Keep usage after the final delta"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.delta", 3, text=" late"),
    ]
    accepted = _accepted_updates(updates)
    observation = ModelUsageObserved(
        session_id=SESSION_ID,
        input_tokens=8,
        output_tokens=2,
    )

    async def record_late_delta() -> object | None:
        for update, state in accepted[:3]:
            assert await transcript.record(update, state) is None
        assert await transcript.record_model_usage(observation) is None
        return await transcript.record(*accepted[3])

    failure = asyncio.run(record_late_delta())
    replay = replay_transcript(transcript.transcript_path)

    assert failure is not None
    assert failure.code == "transcript_write_failed"
    assert replay.state.assistant_text == "Done"
    assert replay.evidence.model_usage == observation
    assert [record.kind for record in replay.records] == [
        "domain_fact",
        "session_event",
        "session_event",
        "model.usage_observed",
    ]
    assert not transcript.summary_path.exists()


def test_writer_rejects_duplicate_model_usage_and_preserves_the_first_observation(
    tmp_path: Path,
) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Record usage once"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
    ]
    accepted = _accepted_updates(updates)
    observation = ModelUsageObserved(
        session_id=SESSION_ID,
        input_tokens=8,
        output_tokens=2,
    )

    async def record_duplicate() -> tuple[object | None, object | None]:
        for update, state in accepted:
            assert await transcript.record(update, state) is None
        first = await transcript.record_model_usage(observation)
        duplicate = await transcript.record_model_usage(observation)
        return first, duplicate

    first_failure, duplicate_failure = asyncio.run(record_duplicate())
    replay = replay_transcript(transcript.transcript_path)

    assert first_failure is None
    assert duplicate_failure is not None
    assert duplicate_failure.code == "transcript_write_failed"
    assert replay.evidence.model_usage == observation
    assert [record.kind for record in replay.records].count("model.usage_observed") == 1
    assert not transcript.summary_path.exists()


def test_unicode_content_is_bounded_before_json_and_remains_replayable(tmp_path: Path) -> None:
    settings = _settings(tmp_path, text_limit_bytes=64)
    transcript = _create_transcript(tmp_path, settings=settings)
    delta = "🛡️" * 100
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="T" * 200),
        _event("session.started", 1),
        _event("assistant.delta", 2, text=delta),
        _event("assistant.delta", 3, text=delta),
        _event("assistant.delta", 4, text=delta),
        _event("assistant.completed", 5, text=delta * 3),
        _event("session.completed", 6),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert failures == [None] * len(updates)
    assert replay.complete
    assert replay.state.task is not None
    assert len(replay.state.task.encode("utf-8")) <= 64
    assert "[TRUNCATED]" in replay.state.task
    assert "[TRUNCATED]" in replay.state.assistant_text
    assert "~" in replay.state.assistant_text
    assert len(replay.state.assistant_text.encode("utf-8")) < 128
    transcript.transcript_path.read_text(encoding="utf-8", errors="strict")


@pytest.mark.parametrize(
    ("token", "first_fragment", "second_fragment"),
    [
        ("Bearer fakeTokenValue123456", "Bearer ", "fakeTokenValue123456"),
        ("github_pat_FAKE1234567890", "github_pat_", "FAKE1234567890"),
    ],
)
def test_recognized_credential_split_across_deltas_is_not_reconstructed(
    tmp_path: Path,
    token: str,
    first_fragment: str,
    second_fragment: str,
) -> None:
    transcript = _create_transcript(
        tmp_path,
        settings=_settings(tmp_path, sensitive_values=()),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Keep credentials private"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text=first_fragment),
        _event("assistant.delta", 3, text=second_fragment),
        _event("assistant.completed", 4, text=token),
        _event("session.completed", 5),
    ]

    asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert token not in replay.state.assistant_text
    assert "[REDACTED]" in replay.state.assistant_text
    assert token.encode() not in transcript.transcript_path.read_bytes()


def test_unbounded_credential_continuation_remains_redacted_beyond_lookbehind(
    tmp_path: Path,
) -> None:
    transcript = _create_transcript(
        tmp_path,
        settings=_settings(tmp_path, sensitive_values=()),
    )
    fragments = ["Bearer ", "a" * 1_000, "b" * 100, "LEAKED_SUFFIX", " safe text"]
    token = "".join(fragments[:-1])
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Keep long credentials private"),
        _event("session.started", 1),
        *[
            _event("assistant.delta", sequence, text=fragment)
            for sequence, fragment in enumerate(fragments, start=2)
        ],
        _event("assistant.completed", 7, text="".join(fragments)),
        _event("session.completed", 8),
    ]

    asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)
    persisted = transcript.transcript_path.read_text(encoding="utf-8")

    assert replay.complete
    assert token not in replay.state.assistant_text
    assert "LEAKED_SUFFIX" not in persisted
    assert replay.state.assistant_text.endswith(" safe text")


def test_many_small_deltas_remain_replayable_after_content_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    transcript = _create_transcript(
        tmp_path,
        settings=_settings(tmp_path, text_limit_bytes=64),
    )
    delta_count = 1_000
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Bound many fragments"),
        _event("session.started", 1),
        *[_event("assistant.delta", sequence, text="x") for sequence in range(2, delta_count + 2)],
        _event("assistant.completed", delta_count + 2, text="x" * delta_count),
        _event("session.completed", delta_count + 3),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert failures == [None] * len(updates)
    assert replay.complete
    assert replay.state.assistant_text.count("x") == 64
    assert "[TRUNCATED]" in replay.state.assistant_text
    assert len(replay.state.assistant_text.encode("utf-8")) < 1_100


def test_domain_fact_order_supports_approval_and_cancellation_replay(tmp_path: Path) -> None:
    approval_transcript = _create_transcript(tmp_path, transcript_id="approval_tape_001")
    approval_updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Review"),
        _event("session.started", 1),
        ApprovalRequested(session_id=SESSION_ID),
        ApprovalResolved(session_id=SESSION_ID),
        _event("assistant.delta", 2, text="Approved"),
        _event("assistant.completed", 3, text="Approved"),
        _event("session.completed", 4),
    ]
    asyncio.run(_record_updates(approval_transcript, approval_updates))

    cancellation_transcript = _create_transcript(tmp_path, transcript_id="cancel_tape_001")
    cancellation_updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Stop"),
        _event("session.started", 1),
        CancelRequested(command_id=CANCEL_COMMAND_ID, session_id=SESSION_ID),
        _event("session.cancelled", 2, correlation_id=CANCEL_COMMAND_ID),
    ]
    asyncio.run(_record_updates(cancellation_transcript, cancellation_updates))

    approval_replay = replay_transcript(approval_transcript.transcript_path)
    cancellation_replay = replay_transcript(cancellation_transcript.transcript_path)
    cancellation_records = [
        json.loads(line)
        for line in cancellation_transcript.transcript_path.read_bytes().splitlines()
    ]

    assert approval_replay.state.status == "completed"
    assert cancellation_replay.state.status == "cancelled"
    assert [record["input"]["type"] for record in cancellation_records] == [
        "task.submitted",
        "session.started",
        "cancel.requested",
        "session.cancelled",
    ]
    assert [record["input"].get("sequence") for record in cancellation_records] == [
        None,
        1,
        None,
        2,
    ]


def test_failed_summary_uses_only_safe_persisted_values(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task=f"Keep {FAKE_SECRET} private"),
        _event("session.started", 1),
        _event(
            "session.failed",
            2,
            failure_message=f"Provider rejected {FAKE_SECRET}",
        ),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)
    summary = transcript.summary_path.read_text(encoding="utf-8")

    assert failures == [None, None, None]
    assert replay.state.status == "failed"
    assert replay.state.session_failure is not None
    assert FAKE_SECRET not in replay.state.session_failure.message
    assert FAKE_SECRET not in summary
    assert "Outcome: failed" in summary
    assert "Failure code: provider_failed" in summary


def test_transcript_records_only_normalized_failure_not_raw_provider_detail(
    tmp_path: Path,
) -> None:
    class RawAdapterFailure:
        def __init__(self) -> None:
            self.response_body = "RAW_PROVIDER_BODY_FAKE_TOKEN_98765"
            self.authorization = "Bearer RAW_FAKE_CREDENTIAL_12345"

    raw_failure = RawAdapterFailure()
    normalized = ProviderFailure(
        code="unavailable",
        message="The provider is temporarily unavailable.",
        retryable=True,
    )
    with pytest.raises(TypeError):
        ProviderFailed(raw_failure)  # type: ignore[arg-type]

    request = ProviderRequest(
        conversation=(ProviderMessage(role="user", content="Handle a provider failure."),)
    )
    normalized_event = ProviderFailed(normalized)
    fake = FakeProvider(
        (
            FakeProviderExchange(
                expected_request=request,
                steps=(FakeProviderEmit(normalized_event),),
            ),
        )
    )

    async def collect_failure() -> ProviderFailed:
        operation = fake.start(request)
        events = tuple([event async for event in operation.events()])
        fake.assert_complete()
        assert events == (normalized_event,)
        return cast(ProviderFailed, events[0])

    collected_failure = asyncio.run(collect_failure()).failure
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Handle a provider failure."),
        _event("session.started", 1),
        _event(
            "session.failed",
            2,
            failure_code=f"provider_{collected_failure.code}",
            failure_message=collected_failure.message,
        ),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    persisted = transcript.transcript_path.read_text(encoding="utf-8")

    assert failures == [None, None, None]
    assert "provider_unavailable" in persisted
    assert collected_failure.message in persisted
    assert raw_failure.response_body not in persisted
    assert raw_failure.authorization not in persisted
    assert type(raw_failure).__name__ not in persisted


def test_files_are_private_unique_and_outside_the_workspace(tmp_path: Path) -> None:
    prior_umask = os.umask(0)
    try:
        first = _create_transcript(tmp_path, transcript_id="unique_tape_001")
        second = _create_transcript(tmp_path, transcript_id="unique_tape_002")
        updates: list[SessionUpdate] = [
            TaskSubmitted(command_id=START_COMMAND_ID, task="Complete"),
            _event("session.started", 1),
            _event("assistant.delta", 2, text="Done"),
            _event("assistant.completed", 3, text="Done"),
            _event("session.completed", 4),
        ]
        asyncio.run(_record_updates(first, updates))
        asyncio.run(_record_updates(second, updates))
    finally:
        os.umask(prior_umask)

    assert first.transcript_path != second.transcript_path
    assert first.transcript_path.read_bytes() == second.transcript_path.read_bytes()
    assert not first.transcript_path.is_relative_to(tmp_path / "workspace")
    assert first.transcript_path.stat().st_mode & 0o777 == 0o600
    assert first.summary_path.stat().st_mode & 0o777 == 0o600
    assert first.transcript_path.parent.stat().st_mode & 0o777 == 0o700
    assert first.transcript_path.parent.parent.stat().st_mode & 0o777 == 0o700
    assert (
        replay_transcript(first.transcript_path).state
        == replay_transcript(second.transcript_path).state
    )


def test_unsafe_location_symlink_and_identifier_collision_fail_closed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside_workspace = TranscriptSettings(workspace / "state")

    with pytest.raises(TranscriptPersistenceError) as location_error:
        asyncio.run(SessionTranscript.create(inside_workspace, workspace, SESSION_ID))
    assert location_error.value.code == "transcript_open_failed"

    target = tmp_path / "target"
    target.mkdir()
    state_alias = tmp_path / "state-alias"
    state_alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(TranscriptPersistenceError) as symlink_error:
        asyncio.run(
            SessionTranscript.create(TranscriptSettings(state_alias), workspace, SESSION_ID)
        )
    assert symlink_error.value.code == "transcript_open_failed"

    settings = _settings(tmp_path)
    first = asyncio.run(
        SessionTranscript.create(
            settings,
            workspace,
            SESSION_ID,
            create_transcript_id=lambda: "colliding_tape_001",
        )
    )
    with pytest.raises(TranscriptPersistenceError) as collision_error:
        asyncio.run(
            SessionTranscript.create(
                settings,
                workspace,
                SESSION_ID,
                create_transcript_id=lambda: "colliding_tape_001",
            )
        )
    asyncio.run(first.close())
    assert collision_error.value.code == "transcript_open_failed"


@pytest.mark.parametrize(
    ("failing_operation", "expected_code"),
    [("write", "transcript_write_failed"), ("flush", "transcript_flush_failed")],
)
def test_append_failure_preserves_valid_prefix_and_reports_only_once(
    tmp_path: Path,
    failing_operation: str,
    expected_code: str,
) -> None:
    write_count = 0
    flush_count = 0

    def write(descriptor: int, contents: bytes) -> int:
        nonlocal write_count
        write_count += 1
        if failing_operation == "write" and write_count == 3:
            return os.write(descriptor, contents[: max(1, len(contents) // 2)])
        if failing_operation == "write" and write_count == 4:
            raise OSError("injected write failure with a payload that must stay private")
        return os.write(descriptor, contents)

    def flush(descriptor: int) -> None:
        nonlocal flush_count
        flush_count += 1
        if failing_operation == "flush" and flush_count == 3:
            raise OSError("injected flush failure with a payload that must stay private")
        os.fsync(descriptor)

    operations = TranscriptFileOperations(write=write, flush=flush)
    transcript = _create_transcript(tmp_path, operations=operations)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Keep the prefix"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="This append fails"),
        _event("assistant.completed", 3, text="This append fails"),
        _event("session.completed", 4),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    reported = [failure for failure in failures if failure is not None]
    assert len(reported) == 1
    assert reported[0].code == expected_code
    assert len(replay.records) == 2
    assert replay.state.status == "running"
    assert not replay.complete
    assert transcript.transcript_path.read_bytes().endswith(b"\n")
    assert not transcript.summary_path.exists()


@pytest.mark.parametrize(
    ("failing_operation", "expected_code"),
    [("write", "transcript_write_failed"), ("flush", "transcript_flush_failed")],
)
def test_model_usage_append_failure_rolls_back_to_the_lifecycle_prefix(
    tmp_path: Path,
    failing_operation: str,
    expected_code: str,
) -> None:
    write_count = 0
    flush_count = 0

    def write(descriptor: int, contents: bytes) -> int:
        nonlocal write_count
        write_count += 1
        if failing_operation == "write" and write_count == 4:
            return os.write(descriptor, contents[: max(1, len(contents) // 2)])
        if failing_operation == "write" and write_count == 5:
            raise OSError("injected model usage write failure")
        return os.write(descriptor, contents)

    def flush(descriptor: int) -> None:
        nonlocal flush_count
        flush_count += 1
        if failing_operation == "flush" and flush_count == 4:
            raise OSError("injected model usage flush failure")
        os.fsync(descriptor)

    transcript = _create_transcript(
        tmp_path,
        operations=TranscriptFileOperations(write=write, flush=flush),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Preserve usage prefix"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
    ]
    accepted = _accepted_updates(updates)

    async def record_usage_failure() -> object | None:
        for update, state in accepted:
            assert await transcript.record(update, state) is None
        return await transcript.record_model_usage(
            ModelUsageObserved(
                session_id=SESSION_ID,
                input_tokens=21,
                output_tokens=5,
            )
        )

    failure = asyncio.run(record_usage_failure())
    replay = replay_transcript(transcript.transcript_path)

    assert failure is not None
    assert failure.code == expected_code
    assert len(replay.records) == 3
    assert replay.state.status == "running"
    assert replay.state.assistant_text == "Done"
    assert replay.evidence.model_usage is None
    assert transcript.transcript_path.read_bytes().endswith(b"\n")
    assert not transcript.summary_path.exists()


def test_writer_stops_before_crossing_its_own_replay_record_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcript_module, "_MAX_TRANSCRIPT_RECORDS", 2)
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Bound this tape"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Must not be written"),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert [failure.code for failure in failures if failure is not None] == [
        "transcript_write_failed"
    ]
    assert len(replay.records) == 2
    assert replay.state.status == "running"


def test_writer_stops_before_crossing_replay_assistant_cost_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transcript_module, "_MAX_REPLAY_ASSISTANT_BYTES", 16)
    transcript = _create_transcript(
        tmp_path,
        settings=_settings(tmp_path, text_limit_bytes=128),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Bound replay cost"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="x" * 17),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    assert [failure.code for failure in failures if failure is not None] == [
        "transcript_write_failed"
    ]
    assert len(replay.records) == 2
    assert replay.state.assistant_text == ""


def test_writer_rejects_authoritative_metadata_drift_before_append(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    task = TaskSubmitted(command_id=START_COMMAND_ID, task="Keep identities aligned")
    started = _event("session.started", 1)
    accepted = _accepted_updates([task, started])
    assert asyncio.run(transcript.record(*accepted[0])) is None
    mismatched_state = replace(accepted[1][1], last_sequence=99)

    failure = asyncio.run(transcript.record(started, mismatched_state))
    replay = replay_transcript(transcript.transcript_path)

    assert failure is not None
    assert failure.code == "transcript_write_failed"
    assert len(replay.records) == 1
    assert replay.state.status == "starting"


def test_summary_failure_keeps_complete_transcript_and_terminal_state(tmp_path: Path) -> None:
    open_count = 0

    def open_file(path: Path, flags: int, mode: int) -> int:
        nonlocal open_count
        open_count += 1
        if open_count == 2:
            raise OSError("injected summary failure")
        return os.open(path, flags, mode)

    transcript = _create_transcript(
        tmp_path,
        operations=TranscriptFileOperations(open_file=open_file),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Complete despite summary failure"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
        _event("session.completed", 4),
    ]

    live_state, failures = asyncio.run(_record_updates(transcript, updates))
    replay = replay_transcript(transcript.transcript_path)

    reported = [failure for failure in failures if failure is not None]
    assert len(reported) == 1
    assert reported[0].code == "transcript_summary_failed"
    assert live_state.status == "completed"
    assert replay.complete
    assert replay.state.status == "completed"
    assert not transcript.summary_path.exists()


def test_partial_summary_is_removed_before_failure_is_reported(tmp_path: Path) -> None:
    opened_summary_descriptor: int | None = None

    def open_file(path: Path, flags: int, mode: int) -> int:
        nonlocal opened_summary_descriptor
        descriptor = os.open(path, flags, mode)
        if path.name.endswith(".summary.txt.tmp"):
            opened_summary_descriptor = descriptor
        return descriptor

    def write(descriptor: int, contents: bytes) -> int:
        if descriptor == opened_summary_descriptor:
            os.write(descriptor, contents[:10])
            raise OSError("injected partial summary write")
        return os.write(descriptor, contents)

    transcript = _create_transcript(
        tmp_path,
        operations=TranscriptFileOperations(open_file=open_file, write=write),
    )
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Do not leave a partial summary"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
        _event("session.completed", 4),
    ]

    _state, failures = asyncio.run(_record_updates(transcript, updates))

    assert [failure.code for failure in failures if failure is not None] == [
        "transcript_summary_failed"
    ]
    assert replay_transcript(transcript.transcript_path).complete
    assert not transcript.summary_path.exists()
    assert not transcript.summary_path.with_suffix(".txt.tmp").exists()


@pytest.mark.parametrize(
    ("mutation", "expected_code", "line_number"),
    [
        ("unterminated", "invalid_framing", 5),
        ("record_order", "record_order_mismatch", 2),
        ("extra_field", "invalid_record", 1),
        ("session_identity", "session_mismatch", 2),
        ("whitespace_task", "invalid_record", 1),
    ],
)
def test_replay_stops_at_first_untrusted_line(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    line_number: int,
) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Replay safely"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
        _event("session.completed", 4),
    ]
    asyncio.run(_record_updates(transcript, updates))
    lines = transcript.transcript_path.read_bytes().splitlines(keepends=True)
    if mutation == "unterminated":
        lines[-1] = lines[-1].removesuffix(b"\n")
    else:
        target = 1 if mutation in {"record_order", "session_identity"} else 0
        value = json.loads(lines[target])
        if mutation == "record_order":
            value["record_order"] = 99
        elif mutation == "extra_field":
            value["unexpected"] = True
        elif mutation == "whitespace_task":
            value["input"]["task"] = " \t "
        else:
            value["session_id"] = "ses_other"
        lines[target] = json.dumps(value, separators=(",", ":")).encode() + b"\n"
    transcript.transcript_path.write_bytes(b"".join(lines))

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(transcript.transcript_path)

    assert replay_error.value.code == expected_code
    assert replay_error.value.line_number == line_number
    assert FAKE_SECRET not in str(replay_error.value)


def test_replay_binds_nested_session_and_optional_workspace_scope(tmp_path: Path) -> None:
    transcript = _create_transcript(tmp_path)
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Bind replay identity"),
        _event("session.started", 1),
        _event("assistant.delta", 2, text="Done"),
        _event("assistant.completed", 3, text="Done"),
        _event("session.completed", 4),
    ]
    asyncio.run(_record_updates(transcript, updates))
    workspace = tmp_path / "workspace"
    other_workspace = tmp_path / "other-workspace"
    other_workspace.mkdir()

    assert replay_transcript(transcript.transcript_path, expected_workspace=workspace).complete
    with pytest.raises(TranscriptReplayError) as workspace_error:
        replay_transcript(transcript.transcript_path, expected_workspace=other_workspace)
    assert workspace_error.value.code == "workspace_mismatch"
    assert workspace_error.value.line_number == 1

    lines = transcript.transcript_path.read_bytes().splitlines()
    mutated: list[bytes] = []
    for line in lines:
        record = json.loads(line)
        record["session_id"] = "ses_uniformly_wrong"
        mutated.append(json.dumps(record, separators=(",", ":")).encode() + b"\n")
    transcript.transcript_path.write_bytes(b"".join(mutated))

    with pytest.raises(TranscriptReplayError) as session_error:
        replay_transcript(transcript.transcript_path)
    assert session_error.value.code == "session_mismatch"
    assert session_error.value.line_number == 2


def test_replay_rejects_nonregular_and_oversized_inputs_without_unbounded_reads(
    tmp_path: Path,
) -> None:
    fifo = tmp_path / "transcript.fifo"
    os.mkfifo(fifo)

    with pytest.raises(TranscriptReplayError) as fifo_error:
        replay_transcript(fifo)
    assert fifo_error.value.code == "not_regular_file"

    oversized_line = tmp_path / "oversized.jsonl"
    oversized_line.write_bytes(
        b"{" + b"x" * (transcript_module.MAX_TRANSCRIPT_LINE_BYTES + 1) + b"\n"
    )
    with pytest.raises(TranscriptReplayError) as line_error:
        replay_transcript(oversized_line)
    assert line_error.value.code == "line_too_large"
    assert line_error.value.line_number == 1


def test_replay_traceback_suppresses_secret_bearing_validation_causes(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.jsonl"
    unsafe.write_text(
        json.dumps({"unexpected": FAKE_SECRET}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(unsafe)

    rendered = "".join(
        traceback.format_exception(
            type(replay_error.value),
            replay_error.value,
            replay_error.value.__traceback__,
        )
    )
    assert replay_error.value.code == "invalid_record"
    assert replay_error.value.__cause__ is None
    assert FAKE_SECRET not in rendered


def test_replay_rejects_crafted_quadratic_assistant_growth_before_full_fold(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    updates: list[SessionUpdate] = [
        TaskSubmitted(command_id=START_COMMAND_ID, task="Reject costly replay"),
        _event("session.started", 1),
    ]
    updates.extend(
        _event("assistant.delta", sequence, text="x" * 1_250) for sequence in range(2, 180)
    )
    lines = [
        transcript_module._encode_record(  # noqa: SLF001 - craft a schema-valid hostile tape.
            transcript_module._build_record(  # noqa: SLF001
                update,
                record_order=record_order,
                recorded_at=TIMESTAMP,
                workspace_id=stable_workspace_id(workspace),
                session_id=SESSION_ID,
            )
        )
        for record_order, update in enumerate(updates, start=1)
    ]
    hostile = tmp_path / "hostile.jsonl"
    hostile.write_bytes(b"".join(lines))

    with pytest.raises(TranscriptReplayError) as replay_error:
        replay_transcript(hostile)

    assert replay_error.value.code == "transcript_too_large"
    assert replay_error.value.line_number is not None
    assert replay_error.value.line_number < len(lines)
