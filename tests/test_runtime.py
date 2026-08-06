from __future__ import annotations

import asyncio
import json
import os
import select
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

import code_assist_harness.runtime as runtime_module
from code_assist_harness.loop_limits import LoopLimits
from code_assist_harness.mock_session import (
    MOCK_RESPONSE_DELTAS,
    MOCK_RESPONSE_TEXT,
    MockSessionRunner,
)
from code_assist_harness.persistence import (
    SessionTranscript,
    TranscriptFileOperations,
    TranscriptSettings,
    replay_transcript,
)
from code_assist_harness.protocol import (
    Event,
    EventLineReader,
    OrderedEventWriter,
    ProtocolParseFailure,
    SessionStartCommand,
    validate_command,
)
from code_assist_harness.provider import (
    FakeProvider,
    FakeProviderEmit,
    FakeProviderExchange,
    FakeProviderOperation,
    FakeProviderWaitForCancellation,
    ProviderCancellationResult,
    ProviderCompleted,
    ProviderMessage,
    ProviderOperation,
    ProviderRequest,
    ProviderStreamEvent,
    ProviderTextCompleted,
    ProviderTextDelta,
    ProviderUsageReported,
    RepositoryInstruction,
)
from code_assist_harness.runtime import RuntimeConfigurationError
from code_assist_harness.session_state import SessionState
from code_assist_harness.workspace import WorkspaceBoundary

TIMESTAMP = "2026-07-16T12:34:56.789Z"
FAKE_RUNTIME_SECRET = "FAKE_CAH_RUNTIME_SECRET_011"


class _CapturingFakeProvider:
    """Expose the strict fake operation so a command source can await its checkpoints."""

    def __init__(self, fake: FakeProvider) -> None:
        self.fake = fake
        self.operation: FakeProviderOperation | None = None

    def start(self, request: ProviderRequest) -> FakeProviderOperation:
        operation = self.fake.start(request)
        self.operation = operation
        return operation

    def assert_complete(self) -> None:
        self.fake.assert_complete()


class _EarlyReturningOperation:
    """Return successfully while one provider read remains blocked to test local reaping."""

    def __init__(self) -> None:
        self._claimed = False
        self._release_iteration = asyncio.Event()
        self.iteration_started = asyncio.Event()
        self.iteration_finished = asyncio.Event()
        self.cancel_calls = 0

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        if self._claimed:
            raise RuntimeError("early-returning operation stream claimed twice")
        self._claimed = True

        async def generate() -> AsyncIterator[ProviderStreamEvent]:
            self.iteration_started.set()
            try:
                await self._release_iteration.wait()
                yield ProviderCompleted()
            finally:
                self.iteration_finished.set()

        return generate()

    async def cancel(self) -> ProviderCancellationResult:
        self.cancel_calls += 1
        return "cancelled"

    async def wait_closed(self) -> None:
        raise AssertionError("teardown must request cancellation")

    async def force_cancel_cleanup(self) -> None:
        return


class _SingleOperationProvider:
    """Return one controlled provider operation for runtime-boundary tests."""

    def __init__(self, operation: ProviderOperation) -> None:
        self.operation = operation

    def start(self, _request: ProviderRequest) -> ProviderOperation:
        return self.operation


class _NeverStartingProvider:
    """Record and reject any provider start after pre-admission deadline expiry."""

    def __init__(self) -> None:
        self.start_calls = 0

    def start(self, _request: ProviderRequest) -> ProviderOperation:
        self.start_calls += 1
        raise AssertionError("provider start must not run after setup exhausts the deadline")


def _isolated_runtime_environment(
    tmp_path: Path,
    **overrides: str,
) -> dict[str, str]:
    """Return only non-secret process settings plus explicit fake test values."""
    environment = {
        "HOME": str(tmp_path / "isolated-home"),
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", os.defpath),
    }
    environment.update(overrides)
    return environment


def _run_runtime(
    *arguments: str,
    input_bytes: bytes = b"",
    transcript_enabled: bool = False,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    runtime_arguments = list(arguments)
    if not transcript_enabled and "--no-transcript" not in runtime_arguments:
        runtime_arguments.append("--no-transcript")
    return subprocess.run(
        [sys.executable, "-m", "code_assist_harness.runtime", *runtime_arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=5,
        env=environment,
    )


def _command(
    message_type: str,
    command_id: str,
    payload: dict[str, object],
    *,
    protocol_version: int = 1,
) -> bytes:
    value = {
        "protocol_version": protocol_version,
        "type": message_type,
        "command_id": command_id,
        "timestamp": TIMESTAMP,
        "payload": payload,
    }
    return json.dumps(value, separators=(",", ":")).encode() + b"\n"


def _stdout_events(completed: subprocess.CompletedProcess[bytes]) -> list[Event]:
    return _event_lines(completed.stdout)


def _event_lines(lines: bytes) -> list[Event]:
    reader = EventLineReader()
    results = [*reader.feed(lines), *reader.finish()]
    assert all(not isinstance(result, ProtocolParseFailure) for result in results)
    return [result for result in results if not isinstance(result, ProtocolParseFailure)]


def _event_semantics(events: list[Event]) -> list[dict[str, object]]:
    """Drop only nondeterministic timestamps before comparing two runtime tapes."""
    normalized: list[dict[str, object]] = []
    for event in events:
        value = event.model_dump(mode="json")
        value.pop("timestamp")
        normalized.append(value)
    return normalized


def _session_start(command_id: str, task: str = "Explain this repository") -> SessionStartCommand:
    return SessionStartCommand.model_validate_json(
        _command("session.start", command_id, {"task": task})
    )


def _read_process_event(process: subprocess.Popen[bytes]) -> Event:
    assert process.stdout is not None
    readable, _, _ = select.select([process.stdout], [], [], 5)
    assert readable, "runtime did not emit the next event before the test deadline"
    line = process.stdout.readline()
    assert line, "runtime stdout closed before the expected event"
    events = _event_lines(line)
    assert len(events) == 1
    return events[0]


def test_runtime_options_store_one_canonical_workspace_boundary(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)

    options = runtime_module._parse_runtime_options(("--workspace", str(alias)))

    assert isinstance(options.workspace, WorkspaceBoundary)
    assert options.workspace.root == workspace.resolve()


@pytest.mark.parametrize("invalid_kind", ["private-missing-root", "private-file-root"])
def test_runtime_options_map_invalid_roots_to_one_non_leaking_error(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    candidate = tmp_path / invalid_kind
    if invalid_kind == "private-file-root":
        candidate.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RuntimeConfigurationError) as captured:
        runtime_module._parse_runtime_options(("--workspace", str(candidate)))

    assert str(captured.value) == "Workspace root must be an existing directory."
    assert invalid_kind not in str(captured.value)


def test_run_runtime_rechecks_a_stored_boundary_before_reading_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    boundary = WorkspaceBoundary.from_path(workspace)
    workspace.rename(tmp_path / "moved-workspace")

    with pytest.raises(RuntimeConfigurationError) as captured:
        asyncio.run(runtime_module.run_runtime(boundary, transcript_enabled=False))

    assert str(captured.value) == "The selected workspace is no longer available."


def test_runtime_accepts_shutdown_before_initialization_without_stdout(tmp_path: Path) -> None:
    completed = _run_runtime(
        "--workspace",
        str(tmp_path),
        input_bytes=_command("runtime.shutdown", "cmd_shutdown", {}),
    )

    assert completed.returncode == 0
    assert completed.stdout == b""
    assert completed.stderr == b""


def test_runtime_emits_correlated_ready_then_honors_orderly_shutdown(tmp_path: Path) -> None:
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(tmp_path.resolve())},
            ),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime("--workspace", str(tmp_path), input_bytes=input_bytes)
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert len(events) == 1
    ready = events[0]
    assert ready.type == "runtime.ready"
    assert ready.correlation_id == "cmd_initialize"
    assert ready.payload.workspace == str(tmp_path.resolve())


def test_mock_session_checkpoints_expose_each_intermediate_delta() -> None:
    async def scenario() -> tuple[list[tuple[int, str]], list[bytes], SessionState]:
        lines: list[bytes] = []
        reached: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        releases = [asyncio.Event() for _delta in MOCK_RESPONSE_DELTAS]

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def checkpoint(index: int, delta: str) -> None:
            await reached.put((index, delta))
            await releases[index - 1].wait()

        session = MockSessionRunner(OrderedEventWriter(sink), checkpoint).create(
            _session_start("cmd_session")
        )
        running = asyncio.create_task(session.run())
        observations: list[tuple[int, str]] = []

        for expected_count, release in enumerate(releases, start=1):
            observations.append(await asyncio.wait_for(reached.get(), timeout=1))
            events = _event_lines(b"".join(lines))
            assert [event.type for event in events] == [
                "session.started",
                *["assistant.delta"] * (expected_count - 1),
            ]
            release.set()

        await asyncio.wait_for(running, timeout=1)
        return observations, lines, session.lifecycle_state

    observations, lines, lifecycle = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert observations == list(enumerate(MOCK_RESPONSE_DELTAS, start=1))
    assert [event.type for event in events] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5, 6]
    assert {event.session_id for event in events} == {"ses_mock_1"}
    assert {event.correlation_id for event in events} == {"cmd_session"}
    assert [event.payload.text for event in events if event.type == "assistant.delta"] == list(
        MOCK_RESPONSE_DELTAS
    )
    completed = next(event for event in events if event.type == "assistant.completed")
    assert completed.payload.text == MOCK_RESPONSE_TEXT
    assert lifecycle.status == "completed"
    assert lifecycle.last_sequence == len(events)
    assert lifecycle.assistant_text == MOCK_RESPONSE_TEXT
    assert lifecycle.assistant_completed is True


def test_mock_session_runner_assigns_a_new_id_and_sequence_for_a_second_session() -> None:
    async def scenario() -> list[bytes]:
        lines: list[bytes] = []

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def immediate_checkpoint(_index: int, _delta: str) -> None:
            return

        runner = MockSessionRunner(OrderedEventWriter(sink), immediate_checkpoint)
        await runner.run(_session_start("cmd_first", "First task"))
        await runner.run(_session_start("cmd_second", "Second task"))
        return lines

    events = _event_lines(b"".join(asyncio.run(scenario())))
    first = [event for event in events if event.session_id == "ses_mock_1"]
    second = [event for event in events if event.session_id == "ses_mock_2"]

    assert len(first) == len(second) == 6
    assert [event.sequence for event in first] == [1, 2, 3, 4, 5, 6]
    assert [event.sequence for event in second] == [1, 2, 3, 4, 5, 6]
    assert {event.correlation_id for event in first} == {"cmd_first"}
    assert {event.correlation_id for event in second} == {"cmd_second"}


def test_mock_session_contains_an_impossible_lifecycle_invariant() -> None:
    async def scenario() -> RuntimeError:
        async def sink(_line: bytes) -> None:
            return

        async def immediate_checkpoint(_index: int, _delta: str) -> None:
            return

        writer = OrderedEventWriter(sink)
        await MockSessionRunner(writer, immediate_checkpoint).run(_session_start("cmd_first"))
        # Two runner allocators must never share one writer: both start at ses_mock_1, so the second
        # started event exposes the impossible integration as a sequence gap.
        conflicting = MockSessionRunner(writer, immediate_checkpoint).create(
            _session_start("cmd_second", "sk-secret-task-must-not-appear")
        )
        with pytest.raises(RuntimeError) as captured:
            await conflicting.run()
        return captured.value

    error = asyncio.run(scenario())

    assert str(error) == (
        "session lifecycle invariant failed: code=sequence_gap "
        "prior_status=starting event_type=session.started"
    )
    assert "secret" not in str(error)


def test_mock_session_cancels_before_the_first_delta_and_repeats_idempotently() -> None:
    async def scenario() -> tuple[list[bytes], str, str, SessionState]:
        lines: list[bytes] = []
        checkpoint_reached = asyncio.Event()
        blocked_checkpoint = asyncio.Event()

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def checkpoint(_index: int, _delta: str) -> None:
            checkpoint_reached.set()
            await blocked_checkpoint.wait()

        session = MockSessionRunner(OrderedEventWriter(sink), checkpoint).create(
            _session_start("cmd_session")
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(checkpoint_reached.wait(), timeout=1)
        first_result = await session.request_cancellation("cmd_cancel")
        repeated_result = await session.request_cancellation("cmd_cancel")
        await asyncio.wait_for(running, timeout=1)
        return lines, first_result, repeated_result, session.lifecycle_state

    lines, first_result, repeated_result, lifecycle = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert first_result == "accepted"
    assert repeated_result == "already_requested"
    assert [event.type for event in events] == ["session.started", "session.cancelled"]
    assert [event.sequence for event in events] == [1, 2]
    assert [event.correlation_id for event in events] == ["cmd_session", "cmd_cancel"]
    assert lifecycle.status == "cancelled"
    assert lifecycle.last_sequence == len(events)
    assert lifecycle.cancel_command_id == "cmd_cancel"


def test_mock_session_defers_cancellation_requested_before_session_started() -> None:
    async def scenario() -> tuple[list[bytes], str, str, SessionState]:
        lines: list[bytes] = []

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def immediate_checkpoint(_index: int, _delta: str) -> None:
            return

        session = MockSessionRunner(OrderedEventWriter(sink), immediate_checkpoint).create(
            _session_start("cmd_session")
        )
        cancellation_result = await session.request_cancellation("cmd_cancel")
        state_before_start = session.lifecycle_state.status
        await session.run()
        return lines, cancellation_result, state_before_start, session.lifecycle_state

    lines, cancellation_result, state_before_start, lifecycle = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert cancellation_result == "accepted"
    assert state_before_start == "starting"
    assert [event.type for event in events] == ["session.started", "session.cancelled"]
    assert lifecycle.status == "cancelled"
    assert lifecycle.last_sequence == len(events)


def test_mock_session_cancels_between_deltas_without_later_assistant_output() -> None:
    async def scenario() -> list[bytes]:
        lines: list[bytes] = []
        reached: asyncio.Queue[int] = asyncio.Queue()
        releases = [asyncio.Event() for _delta in MOCK_RESPONSE_DELTAS]

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def checkpoint(index: int, _delta: str) -> None:
            await reached.put(index)
            await releases[index - 1].wait()

        session = MockSessionRunner(OrderedEventWriter(sink), checkpoint).create(
            _session_start("cmd_session")
        )
        running = asyncio.create_task(session.run())
        assert await asyncio.wait_for(reached.get(), timeout=1) == 1
        releases[0].set()
        assert await asyncio.wait_for(reached.get(), timeout=1) == 2
        assert await session.request_cancellation("cmd_cancel") == "accepted"
        await asyncio.wait_for(running, timeout=1)
        return lines

    events = _event_lines(b"".join(asyncio.run(scenario())))

    assert [event.type for event in events] == [
        "session.started",
        "assistant.delta",
        "session.cancelled",
    ]
    assert [event.sequence for event in events] == [1, 2, 3]
    assert [event.correlation_id for event in events] == [
        "cmd_session",
        "cmd_session",
        "cmd_cancel",
    ]
    assert events[1].payload.text == MOCK_RESPONSE_DELTAS[0]


def test_mock_session_completion_write_wins_a_concurrent_cancellation_race() -> None:
    async def scenario() -> tuple[list[bytes], str, bool, SessionState]:
        lines: list[bytes] = []
        terminal_write_started = asyncio.Event()
        release_terminal_write = asyncio.Event()

        async def sink(line: bytes) -> None:
            if b'"type":"session.completed"' in line:
                terminal_write_started.set()
                await release_terminal_write.wait()
            lines.append(line)

        async def immediate_checkpoint(_index: int, _delta: str) -> None:
            return

        session = MockSessionRunner(OrderedEventWriter(sink), immediate_checkpoint).create(
            _session_start("cmd_session")
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(terminal_write_started.wait(), timeout=1)
        cancelling = asyncio.create_task(session.request_cancellation("cmd_cancel"))
        await asyncio.sleep(0)
        cancellation_waited_for_terminal_write = not cancelling.done()
        release_terminal_write.set()
        await asyncio.wait_for(running, timeout=1)
        cancellation_result = await asyncio.wait_for(cancelling, timeout=1)
        return (
            lines,
            cancellation_result,
            cancellation_waited_for_terminal_write,
            session.lifecycle_state,
        )

    lines, cancellation_result, cancellation_waited, lifecycle = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert cancellation_waited is True
    assert cancellation_result == "terminal"
    assert [event.type for event in events] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert sum(event.type in {"session.completed", "session.cancelled"} for event in events) == 1
    assert lifecycle.status == "completed"
    assert lifecycle.last_sequence == len(events)
    assert lifecycle.assistant_text == MOCK_RESPONSE_TEXT


def test_runtime_streams_one_session_then_drains_it_before_shutdown(tmp_path: Path) -> None:
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(tmp_path.resolve())},
            ),
            _command("session.start", "cmd_session", {"task": "Explain this repository"}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime("--workspace", str(tmp_path), input_bytes=input_bytes)
    events = _stdout_events(completed)
    session_events = [event for event in events if hasattr(event, "session_id")]

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert events[0].type == "runtime.ready"
    assert [event.type for event in session_events] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [event.sequence for event in session_events] == [1, 2, 3, 4, 5, 6]
    assert {event.correlation_id for event in session_events} == {"cmd_session"}
    assert sum(event.type == "session.completed" for event in session_events) == 1


def test_runtime_rejects_a_second_session_while_the_first_is_active(tmp_path: Path) -> None:
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(tmp_path.resolve())},
            ),
            _command("session.start", "cmd_first", {"task": "First task"}),
            _command("session.start", "cmd_second", {"task": "Second task"}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime("--workspace", str(tmp_path), input_bytes=input_bytes)
    events = _stdout_events(completed)
    errors = [event for event in events if event.type == "runtime.error"]
    session_events = [event for event in events if hasattr(event, "session_id")]

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert len(errors) == 1
    assert errors[0].payload.code == "session_active"
    assert errors[0].payload.recoverable is True
    assert errors[0].correlation_id == "cmd_second"
    assert {event.session_id for event in session_events} == {"ses_mock_1"}
    assert {event.correlation_id for event in session_events} == {"cmd_first"}
    assert sum(event.type == "session.completed" for event in session_events) == 1


def test_runtime_rejects_a_whitespace_only_task_without_starting_a_session(
    tmp_path: Path,
) -> None:
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(tmp_path.resolve())},
            ),
            _command("session.start", "cmd_whitespace", {"task": " \t "}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime("--workspace", str(tmp_path), input_bytes=input_bytes)
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert [event.type for event in events] == ["runtime.ready", "runtime.error"]
    error = events[1]
    assert error.type == "runtime.error"
    assert error.payload.code == "invalid_task"
    assert error.payload.recoverable is True
    assert error.correlation_id == "cmd_whitespace"


def test_runtime_accepts_a_second_session_after_the_first_completes(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "code_assist_harness.runtime",
            "--workspace",
            str(tmp_path),
            "--no-transcript",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    first_events: list[Event] = []
    second_events: list[Event] = []
    try:
        process.stdin.write(
            b"".join(
                [
                    _command(
                        "runtime.initialize",
                        "cmd_initialize",
                        {"workspace": str(tmp_path.resolve())},
                    ),
                    _command("session.start", "cmd_first", {"task": "First task"}),
                ]
            )
        )
        process.stdin.flush()

        ready = _read_process_event(process)
        assert ready.type == "runtime.ready"
        while not first_events or first_events[-1].type != "session.completed":
            first_events.append(_read_process_event(process))

        process.stdin.write(
            b"".join(
                [
                    _command(
                        "session.cancel",
                        "cmd_late_cancel",
                        {"session_id": "ses_mock_1"},
                    ),
                    _command("session.start", "cmd_second", {"task": "Second task"}),
                    _command("runtime.shutdown", "cmd_shutdown", {}),
                ]
            )
        )
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None

        process.wait(timeout=5)
        second_events = _event_lines(process.stdout.read())
        stderr = process.stderr.read()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert process.returncode == 0
    assert stderr == b""
    assert [event.type for event in first_events] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [event.sequence for event in first_events] == [1, 2, 3, 4, 5, 6]
    assert {event.session_id for event in first_events} == {"ses_mock_1"}
    assert {event.correlation_id for event in first_events} == {"cmd_first"}
    assert [event.type for event in second_events] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [event.sequence for event in second_events] == [1, 2, 3, 4, 5, 6]
    assert {event.session_id for event in second_events} == {"ses_mock_2"}
    assert {event.correlation_id for event in second_events} == {"cmd_second"}


def test_runtime_routes_cancellation_and_rejects_a_wrong_active_session(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "code_assist_harness.runtime",
            "--workspace",
            str(tmp_path),
            "--no-transcript",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    observed: list[Event] = []
    try:
        process.stdin.write(
            b"".join(
                [
                    _command(
                        "runtime.initialize",
                        "cmd_initialize",
                        {"workspace": str(tmp_path.resolve())},
                    ),
                    _command("session.start", "cmd_session", {"task": "Cancel this task"}),
                ]
            )
        )
        process.stdin.flush()
        observed.extend([_read_process_event(process), _read_process_event(process)])

        process.stdin.write(
            b"".join(
                [
                    _command(
                        "session.cancel",
                        "cmd_wrong_cancel",
                        {"session_id": "ses_wrong"},
                    ),
                    _command(
                        "session.cancel",
                        "cmd_cancel",
                        {"session_id": "ses_mock_1"},
                    ),
                ]
            )
        )
        process.stdin.flush()
        observed.extend([_read_process_event(process), _read_process_event(process)])

        process.stdin.write(
            b"".join(
                [
                    _command(
                        "session.cancel",
                        "cmd_late_cancel",
                        {"session_id": "ses_mock_1"},
                    ),
                    _command("session.start", "cmd_second", {"task": "Run after cancellation"}),
                    _command("runtime.shutdown", "cmd_shutdown", {}),
                ]
            )
        )
        process.stdin.flush()
        process.stdin.close()
        process.stdin = None
        process.wait(timeout=5)
        remaining = _event_lines(process.stdout.read())
        stderr = process.stderr.read()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)

    assert process.returncode == 0
    assert stderr == b""
    assert [event.type for event in observed] == [
        "runtime.ready",
        "session.started",
        "runtime.error",
        "session.cancelled",
    ]
    mismatch = observed[2]
    assert mismatch.type == "runtime.error"
    assert mismatch.payload.code == "session_mismatch"
    assert mismatch.payload.recoverable is True
    assert mismatch.correlation_id == "cmd_wrong_cancel"
    cancelled = observed[3]
    assert cancelled.type == "session.cancelled"
    assert cancelled.session_id == "ses_mock_1"
    assert cancelled.sequence == 2
    assert cancelled.correlation_id == "cmd_cancel"
    assert [event.type for event in remaining] == [
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert {event.session_id for event in remaining} == {"ses_mock_2"}
    assert {event.correlation_id for event in remaining} == {"cmd_second"}


@pytest.mark.parametrize(
    ("unsafe_workspace", "expected_code", "expected_correlation"),
    [
        ("secret\x00path", "workspace_mismatch", "cmd_initialize"),
        ("secret\ud800path", "invalid_payload", None),
    ],
)
def test_runtime_contains_workspace_values_that_cannot_be_safely_resolved(
    tmp_path: Path,
    unsafe_workspace: str,
    expected_code: str,
    expected_correlation: str | None,
) -> None:
    completed = _run_runtime(
        "--workspace",
        str(tmp_path),
        input_bytes=_command(
            "runtime.initialize",
            "cmd_initialize",
            {"workspace": unsafe_workspace},
        ),
    )
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert len(events) == 1
    error = events[0]
    assert error.type == "runtime.error"
    assert error.correlation_id == expected_correlation
    assert error.payload.code == expected_code
    assert error.payload.recoverable is (expected_code == "invalid_payload")
    assert "secret" not in error.payload.message
    assert b"secret" not in completed.stdout


def test_runtime_contains_bad_lines_and_processes_later_valid_commands(tmp_path: Path) -> None:
    secret = b"sk-secret-must-not-be-echoed"
    malformed = b'{"credential":"' + secret + b'"\n'
    unknown = _command("future.command", "cmd_unknown", {})
    invalid_payload = _command("runtime.initialize", "cmd_invalid", {"workspace": 7})
    unsupported = _command("runtime.shutdown", "cmd_future", {}, protocol_version=2)
    initialize = _command(
        "runtime.initialize",
        "cmd_initialize",
        {"workspace": str(tmp_path.resolve())},
    )
    inactive = _command("session.cancel", "cmd_session", {"session_id": "ses_mock_1"})
    shutdown = _command("runtime.shutdown", "cmd_shutdown", {})

    completed = _run_runtime(
        "--workspace",
        str(tmp_path),
        input_bytes=b"".join(
            [malformed, unsupported, unknown, invalid_payload, initialize, inactive, shutdown]
        ),
    )
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert [event.type for event in events] == [
        "runtime.error",
        "runtime.error",
        "runtime.error",
        "runtime.error",
        "runtime.ready",
        "runtime.error",
    ]
    assert [event.payload.code for event in events if event.type == "runtime.error"] == [
        "malformed_json",
        "unsupported_version",
        "unknown_type",
        "invalid_payload",
        "session_not_active",
    ]
    assert events[4].correlation_id == "cmd_initialize"
    assert events[5].correlation_id == "cmd_session"
    assert secret not in completed.stdout
    assert completed.stdout.endswith(b"\n")
    assert b"\r" not in completed.stdout
    assert all(
        line.startswith(b'{"protocol_version":1,')
        for line in completed.stdout.removesuffix(b"\n").split(b"\n")
    )


def test_openai_runtime_rejects_invalid_unicode_task_before_session_activation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    unsafe_task = "FAKE_UNICODE_TASK_BEFORE\ud800AFTER"
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            ),
            _command("session.start", "cmd_unsafe", {"task": unsafe_task}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime(
        "--workspace",
        str(workspace),
        "--provider",
        "openai",
        "--model",
        "gpt-5.6-luna",
        input_bytes=input_bytes,
        environment=_isolated_runtime_environment(
            tmp_path,
            OPENAI_API_KEY=FAKE_RUNTIME_SECRET,
        ),
    )
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert [event.type for event in events] == ["runtime.ready", "runtime.error"]
    error = events[1]
    assert error.payload.code == "invalid_payload"
    assert error.payload.recoverable is True
    assert error.correlation_id is None
    assert b"FAKE_UNICODE_TASK" not in completed.stdout


def test_runtime_reports_unterminated_input_as_one_safe_protocol_error(tmp_path: Path) -> None:
    unterminated = _command("runtime.shutdown", "cmd_shutdown", {}).removesuffix(b"\n")

    completed = _run_runtime("--workspace", str(tmp_path), input_bytes=unterminated)
    events = _stdout_events(completed)

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert len(events) == 1
    assert events[0].type == "runtime.error"
    assert events[0].payload.code == "invalid_framing"
    assert events[0].payload.recoverable is True


def test_enabled_transcript_excludes_secret_bearing_invalid_wire_input(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    xdg_state = tmp_path / "xdg-state"
    invalid_secret = b"sk-FAKEINVALIDWIRESECRET011"
    malformed = b'{"credential":"' + invalid_secret + b'"\n'
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            ),
            _command("session.start", "cmd_session", {"task": "Record only trusted input"}),
            malformed,
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime(
        "--workspace",
        str(workspace),
        input_bytes=input_bytes,
        transcript_enabled=True,
        environment=_isolated_runtime_environment(
            tmp_path,
            XDG_STATE_HOME=str(xdg_state),
        ),
    )
    events = _stdout_events(completed)
    transcript_directory = xdg_state / "code-assist-harness" / "transcripts"
    transcript_path = next(transcript_directory.glob("*.jsonl"))
    summary_path = next(transcript_directory.glob("*.summary.txt"))
    persisted_bytes = transcript_path.read_bytes() + summary_path.read_bytes()

    assert completed.returncode == 0
    assert [event.payload.code for event in events if event.type == "runtime.error"] == [
        "malformed_json"
    ]
    assert events[-1].type == "session.completed"
    assert replay_transcript(transcript_path).complete
    assert invalid_secret not in persisted_bytes
    assert b"credential" not in persisted_bytes


def test_runtime_persists_and_replays_one_complete_session_under_xdg_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "private-workspace-name"
    workspace.mkdir()
    xdg_state = tmp_path / "xdg-state"
    environment = _isolated_runtime_environment(
        tmp_path,
        OPENAI_API_KEY=FAKE_RUNTIME_SECRET,
        XDG_STATE_HOME=str(xdg_state),
    )
    submitted_task = f"Persist {FAKE_RUNTIME_SECRET} safely"
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            ),
            _command("session.start", "cmd_session", {"task": submitted_task}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime(
        "--workspace",
        str(workspace),
        input_bytes=input_bytes,
        transcript_enabled=True,
        environment=environment,
    )
    events = _stdout_events(completed)
    transcript_directory = xdg_state / "code-assist-harness" / "transcripts"
    transcript_paths = list(transcript_directory.glob("*.jsonl"))
    summary_paths = list(transcript_directory.glob("*.summary.txt"))

    assert completed.returncode == 0
    assert completed.stderr == b""
    assert [event.type for event in events] == [
        "runtime.ready",
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert len(transcript_paths) == 1
    assert len(summary_paths) == 1
    assert "private-workspace-name" not in transcript_paths[0].name
    replay = replay_transcript(transcript_paths[0])
    assert replay.complete
    assert replay.state.status == "completed"
    persisted_bytes = transcript_paths[0].read_bytes() + summary_paths[0].read_bytes()
    assert replay.state.task == "Persist [REDACTED] safely"
    assert FAKE_RUNTIME_SECRET.encode() not in persisted_bytes
    assert list(workspace.iterdir()) == []


def test_no_transcript_preserves_session_tape_without_reading_an_unsafe_state_path(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    unused_state = workspace / "must-not-be-created"
    environment = _isolated_runtime_environment(
        tmp_path,
        XDG_STATE_HOME=str(unused_state),
    )
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            ),
            _command("session.start", "cmd_session", {"task": "Do not persist"}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime(
        "--no-transcript",
        "--workspace",
        str(workspace),
        input_bytes=input_bytes,
        environment=environment,
    )
    events = _stdout_events(completed)
    enabled_state = tmp_path / "comparison-xdg-state"
    enabled_completed = _run_runtime(
        "--workspace",
        str(workspace),
        input_bytes=input_bytes,
        transcript_enabled=True,
        environment=_isolated_runtime_environment(
            tmp_path,
            XDG_STATE_HOME=str(enabled_state),
        ),
    )
    enabled_events = _stdout_events(enabled_completed)

    assert completed.returncode == 0
    assert enabled_completed.returncode == 0
    assert [event.type for event in events] == [
        "runtime.ready",
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert _event_semantics(events) == _event_semantics(enabled_events)
    assert not unused_state.exists()
    assert list(workspace.iterdir()) == []


def test_injected_provider_preserves_wire_tape_and_persists_usage_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[Event], list[Event], Path, Path]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        task = "Explain the provider-backed runtime path."
        instructions = (
            RepositoryInstruction(
                source="AGENTS.md",
                content="Keep orchestration in the Python harness.",
            ),
            RepositoryInstruction(
                source="docs/architecture.md",
                content="Keep provider SDK values behind the provider port.",
            ),
        )
        expected_request = ProviderRequest(
            conversation=(ProviderMessage(role="user", content=task),),
            repository_instructions=instructions,
        )

        async def run_once(
            *,
            transcript_enabled: bool,
            state_directory: Path,
        ) -> list[Event]:
            fake = FakeProvider(
                (
                    FakeProviderExchange(
                        expected_request=expected_request,
                        steps=(
                            FakeProviderEmit(ProviderTextDelta("Provider ")),
                            FakeProviderEmit(ProviderTextDelta("ready.")),
                            FakeProviderEmit(ProviderTextCompleted("Provider ready.")),
                            FakeProviderEmit(
                                ProviderUsageReported(input_tokens=37, output_tokens=5)
                            ),
                            FakeProviderEmit(ProviderCompleted()),
                        ),
                    ),
                )
            )
            output_lines: list[bytes] = []
            commands = (
                validate_command(
                    json.loads(
                        _command(
                            "runtime.initialize",
                            "cmd_initialize",
                            {"workspace": str(workspace)},
                        )
                    )
                ),
                validate_command(
                    json.loads(_command("session.start", "cmd_session", {"task": task}))
                ),
                validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {}))),
            )

            async def read_commands():
                yield commands[0]
                yield commands[1]
                while not any(b'"type":"session.completed"' in line for line in output_lines):
                    await asyncio.sleep(0)
                yield commands[2]

            async def write_stdout_line(line: bytes) -> None:
                output_lines.append(line)

            monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
            monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
            await runtime_module.run_runtime(
                workspace,
                transcript_enabled=transcript_enabled,
                transcript_settings=TranscriptSettings(state_directory=state_directory),
                provider=fake,
                repository_instructions=instructions,
            )
            fake.assert_complete()
            return _event_lines(b"".join(output_lines))

        enabled_state = tmp_path / "enabled-state"
        disabled_state = tmp_path / "disabled-state-must-not-exist"
        enabled_events = await run_once(
            transcript_enabled=True,
            state_directory=enabled_state,
        )
        disabled_events = await run_once(
            transcript_enabled=False,
            state_directory=disabled_state,
        )
        return enabled_events, disabled_events, enabled_state, disabled_state

    enabled_events, disabled_events, enabled_state, disabled_state = asyncio.run(scenario())
    transcript_path = next((enabled_state / "transcripts").glob("*.jsonl"))
    summary_path = next((enabled_state / "transcripts").glob("*.summary.txt"))
    replay = replay_transcript(transcript_path)

    assert [event.type for event in enabled_events] == [
        "runtime.ready",
        "session.started",
        "assistant.delta",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert _event_semantics(enabled_events) == _event_semantics(disabled_events)
    assert {event.session_id for event in enabled_events if hasattr(event, "session_id")} == {
        "ses_provider_1"
    }
    assert replay.complete
    assert replay.state.status == "completed"
    assert replay.state.assistant_text == "Provider ready."
    assert replay.evidence.model_usage is not None
    assert replay.evidence.model_usage.session_id == "ses_provider_1"
    assert replay.evidence.model_usage.input_tokens == 37
    assert replay.evidence.model_usage.output_tokens == 5
    assert replay.evidence.loop_limits is not None
    assert replay.evidence.loop_limits.session_id == "ses_provider_1"
    assert replay.evidence.loop_limits.max_model_turns == 1
    assert replay.evidence.loop_limits.provider_work_timeout_seconds == 120
    assert replay.evidence.loop_limits.max_assistant_output_bytes == 4096
    assert replay.evidence.loop_limits.max_observed_tool_calls == 1
    assert replay.evidence.loop_limits.model_turns_started == 1
    assert replay.evidence.loop_limits.assistant_output_bytes == 15
    assert replay.evidence.loop_limits.tool_calls_observed == 0
    assert replay.evidence.loop_limits.exhausted is None
    assert {record.transcript_version for record in replay.records} == {3}
    assert [record.kind for record in replay.records] == [
        "domain_fact",
        "session_event",
        "session_event",
        "session_event",
        "model.usage_observed",
        "session_event",
        "loop.limits_observed",
        "session_event",
    ]
    summary = summary_path.read_text(encoding="utf-8")
    assert "Model input tokens: 37" in summary
    assert "Model output tokens: 5" in summary
    assert "Maximum model turns: 1" in summary
    assert "Provider work timeout seconds: 120" in summary
    assert "Maximum assistant output bytes: 4096" in summary
    assert "Maximum observed tool calls: 1" in summary
    assert "Model turns started: 1" in summary
    assert "Assistant output bytes: 15" in summary
    assert "Tool calls observed: 0" in summary
    assert "Exhausted loop limit: none" in summary
    assert not disabled_state.exists()


def test_runtime_captures_deadline_before_transcript_setup_and_forwards_clock_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[Event], Path, _NeverStartingProvider]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        state_directory = tmp_path / "setup-expiry-state"
        provider = _NeverStartingProvider()
        output_lines: list[bytes] = []
        terminal_written = asyncio.Event()
        clock_value = 0.0
        clock_observations: list[float] = []
        waiter_deadlines: list[float] = []
        captured_runner_options: dict[str, object] = {}

        def monotonic_now() -> float:
            clock_observations.append(clock_value)
            return clock_value

        async def monotonic_waiter(deadline: float) -> None:
            waiter_deadlines.append(deadline)
            raise AssertionError("an already-expired deadline must not await the clock")

        original_create = SessionTranscript.create

        async def create_then_expire(
            _cls: type[SessionTranscript],
            settings: TranscriptSettings,
            transcript_workspace: Path,
            session_id: str,
        ) -> SessionTranscript:
            nonlocal clock_value
            transcript = await original_create(settings, transcript_workspace, session_id)
            clock_value = 2.0
            return transcript

        original_runner = runtime_module.ProviderSessionRunner

        def capture_runner_options(*args: object, **kwargs: object):
            captured_runner_options.update(kwargs)
            return original_runner(*args, **kwargs)  # type: ignore[arg-type]

        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        start = validate_command(
            json.loads(
                _command(
                    "session.start",
                    "cmd_session",
                    {"task": "Expire while transcript setup is still in progress."},
                )
            )
        )
        shutdown = validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {})))

        async def read_commands():
            yield initialize
            yield start
            await terminal_written.wait()
            yield shutdown

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)
            if b'"type":"session.failed"' in line:
                terminal_written.set()

        monkeypatch.setattr(SessionTranscript, "create", classmethod(create_then_expire))
        monkeypatch.setattr(runtime_module, "ProviderSessionRunner", capture_runner_options)
        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        await runtime_module.run_runtime(
            workspace,
            transcript_settings=TranscriptSettings(state_directory=state_directory),
            provider=provider,
            loop_limits=LoopLimits(provider_work_timeout_seconds=1),
            monotonic_now=monotonic_now,
            monotonic_waiter=monotonic_waiter,
        )

        assert captured_runner_options["monotonic_now"] is monotonic_now
        assert captured_runner_options["monotonic_waiter"] is monotonic_waiter
        assert clock_observations[0] == 0.0
        assert waiter_deadlines == []
        return _event_lines(b"".join(output_lines)), state_directory, provider

    events, state_directory, provider = asyncio.run(scenario())
    transcript_path = next((state_directory / "transcripts").glob("*.jsonl"))
    replay = replay_transcript(transcript_path)

    assert provider.start_calls == 0
    assert [event.type for event in events] == [
        "runtime.ready",
        "session.started",
        "session.failed",
    ]
    assert events[-1].payload.code == "provider_work_deadline_exceeded"
    assert replay.evidence.loop_limits is not None
    assert replay.evidence.loop_limits.model_turns_started == 0
    assert replay.evidence.loop_limits.exhausted == "provider_work"


def test_runtime_uses_a_fresh_limit_tracker_for_each_sequential_provider_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[Event], Path]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        state_directory = tmp_path / "fresh-tracker-state"
        tasks = ("Complete the first provider turn.", "Complete the second provider turn.")
        fake = FakeProvider(
            tuple(
                FakeProviderExchange(
                    expected_request=ProviderRequest(
                        conversation=(ProviderMessage(role="user", content=task),),
                    ),
                    steps=(
                        FakeProviderEmit(ProviderTextDelta(text)),
                        FakeProviderEmit(ProviderTextCompleted(text)),
                        FakeProviderEmit(ProviderCompleted()),
                    ),
                )
                for task, text in zip(tasks, ("first", "second"), strict=True)
            )
        )
        output_lines: list[bytes] = []
        first_transcript_closed = asyncio.Event()
        second_transcript_closed = asyncio.Event()
        transcript_close_count = 0
        original_close = SessionTranscript.close

        async def close_and_signal(transcript: SessionTranscript) -> None:
            nonlocal transcript_close_count
            await original_close(transcript)
            transcript_close_count += 1
            if transcript_close_count == 1:
                first_transcript_closed.set()
            elif transcript_close_count == 2:
                second_transcript_closed.set()

        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        first_start = validate_command(
            json.loads(_command("session.start", "cmd_first", {"task": tasks[0]}))
        )
        second_start = validate_command(
            json.loads(_command("session.start", "cmd_second", {"task": tasks[1]}))
        )
        shutdown = validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {})))

        async def read_commands():
            yield initialize
            yield first_start
            await first_transcript_closed.wait()
            yield second_start
            await second_transcript_closed.wait()
            yield shutdown

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)

        monkeypatch.setattr(SessionTranscript, "close", close_and_signal)
        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        await runtime_module.run_runtime(
            workspace,
            transcript_settings=TranscriptSettings(state_directory=state_directory),
            provider=fake,
            loop_limits=LoopLimits(max_model_turns=1),
        )
        fake.assert_complete()
        return _event_lines(b"".join(output_lines)), state_directory

    events, state_directory = asyncio.run(scenario())
    transcript_paths = sorted((state_directory / "transcripts").glob("*.jsonl"))
    replays = [replay_transcript(path) for path in transcript_paths]

    assert [event.type for event in events] == [
        "runtime.ready",
        "session.started",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
        "session.started",
        "assistant.delta",
        "assistant.completed",
        "session.completed",
    ]
    assert [replay.state.session_id for replay in replays] == ["ses_provider_1", "ses_provider_2"]
    assert all(replay.complete for replay in replays)
    assert all(replay.evidence.loop_limits is not None for replay in replays)
    assert [
        replay.evidence.loop_limits.model_turns_started  # type: ignore[union-attr]
        for replay in replays
    ] == [1, 1]
    assert [
        replay.evidence.loop_limits.exhausted  # type: ignore[union-attr]
        for replay in replays
    ] == [None, None]


@pytest.mark.parametrize("boundary", ["eof", "shutdown"])
def test_injected_provider_teardown_does_not_fabricate_a_terminal_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    async def scenario() -> tuple[list[Event], Path]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        state_directory = tmp_path / f"{boundary}-state"
        task = "Stop provider work at the runtime boundary."
        request = ProviderRequest(
            conversation=(ProviderMessage(role="user", content=task),),
        )
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderWaitForCancellation("provider-active"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                    ),
                ),
            )
        )
        provider = _CapturingFakeProvider(fake)
        output_lines: list[bytes] = []
        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        start = validate_command(
            json.loads(_command("session.start", "cmd_session", {"task": task}))
        )
        shutdown = validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {})))

        async def read_commands():
            yield initialize
            yield start
            while provider.operation is None:
                await asyncio.sleep(0)
            await provider.operation.wait_for_checkpoint("provider-active")
            if boundary == "shutdown":
                yield shutdown

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)

        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        await runtime_module.run_runtime(
            workspace,
            transcript_settings=TranscriptSettings(state_directory=state_directory),
            provider=provider,
        )
        provider.assert_complete()
        return _event_lines(b"".join(output_lines)), state_directory

    events, state_directory = asyncio.run(scenario())
    transcript_path = next((state_directory / "transcripts").glob("*.jsonl"))
    replay = replay_transcript(transcript_path)

    assert [event.type for event in events] == ["runtime.ready", "session.started"]
    assert replay.state.status == "running"
    assert not replay.complete
    assert replay.evidence.model_usage is None
    assert not list((state_directory / "transcripts").glob("*.summary.txt"))


@pytest.mark.parametrize("boundary", ["eof", "shutdown"])
def test_runtime_reaps_a_pending_read_after_successful_provider_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    async def scenario() -> tuple[list[Event], Path, _EarlyReturningOperation]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        state_directory = tmp_path / f"{boundary}-early-cleanup-state"
        operation = _EarlyReturningOperation()
        provider = _SingleOperationProvider(operation)
        output_lines: list[bytes] = []
        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        start = validate_command(
            json.loads(
                _command(
                    "session.start",
                    "cmd_session",
                    {"task": "Contain an early cleanup return."},
                )
            )
        )
        shutdown = validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {})))

        async def read_commands():
            yield initialize
            yield start
            await operation.iteration_started.wait()
            if boundary == "shutdown":
                yield shutdown

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)

        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        await asyncio.wait_for(
            runtime_module.run_runtime(
                workspace,
                transcript_settings=TranscriptSettings(state_directory=state_directory),
                provider=provider,
            ),
            timeout=1,
        )
        return _event_lines(b"".join(output_lines)), state_directory, operation

    events, state_directory, operation = asyncio.run(scenario())
    transcript_path = next((state_directory / "transcripts").glob("*.jsonl"))
    replay = replay_transcript(transcript_path)

    assert operation.cancel_calls == 1
    assert operation.iteration_finished.is_set()
    assert [event.type for event in events] == [
        "runtime.ready",
        "session.started",
    ]
    assert replay.state.status == "running"
    assert not replay.complete
    assert not list((state_directory / "transcripts").glob("*.summary.txt"))


def test_cancelling_injected_provider_runtime_joins_provider_teardown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[Event], bool]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        task = "Cancel the supervising runtime task."
        request = ProviderRequest(
            conversation=(ProviderMessage(role="user", content=task),),
        )
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=request,
                    steps=(
                        FakeProviderWaitForCancellation("provider-active"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                    ),
                ),
            )
        )
        provider = _CapturingFakeProvider(fake)
        output_lines: list[bytes] = []
        keep_reading = asyncio.Event()
        command_source_closed = False
        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        start = validate_command(
            json.loads(_command("session.start", "cmd_session", {"task": task}))
        )

        async def read_commands():
            nonlocal command_source_closed
            try:
                yield initialize
                yield start
                await keep_reading.wait()
            finally:
                command_source_closed = True

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)

        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        running = asyncio.create_task(
            runtime_module.run_runtime(
                workspace,
                transcript_enabled=False,
                provider=provider,
            )
        )
        while provider.operation is None:
            await asyncio.sleep(0)
        await provider.operation.wait_for_checkpoint("provider-active")
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, timeout=1)
        provider.assert_complete()
        return _event_lines(b"".join(output_lines)), command_source_closed

    events, command_source_closed = asyncio.run(scenario())

    assert [event.type for event in events] == ["runtime.ready", "session.started"]
    assert command_source_closed is True


def test_command_source_failure_still_joins_provider_and_closes_transcript(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[list[Event], Path]:
        workspace = (tmp_path / "workspace").resolve()
        workspace.mkdir()
        state_directory = tmp_path / "command-failure-state"
        task = "Keep cleanup reliable when stdin fails."
        fake = FakeProvider(
            (
                FakeProviderExchange(
                    expected_request=ProviderRequest(
                        conversation=(ProviderMessage(role="user", content=task),),
                    ),
                    steps=(
                        FakeProviderWaitForCancellation("provider-active"),
                        FakeProviderEmit(ProviderTextDelta("must-not-appear")),
                    ),
                ),
            )
        )
        provider = _CapturingFakeProvider(fake)
        output_lines: list[bytes] = []
        initialize = validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace)},
                )
            )
        )
        start = validate_command(
            json.loads(_command("session.start", "cmd_session", {"task": task}))
        )

        async def read_commands():
            yield initialize
            yield start
            while provider.operation is None:
                await asyncio.sleep(0)
            await provider.operation.wait_for_checkpoint("provider-active")
            raise OSError("injected command source failure")

        async def write_stdout_line(line: bytes) -> None:
            output_lines.append(line)

        monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
        monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
        with pytest.raises(OSError, match="command source failure"):
            await runtime_module.run_runtime(
                workspace,
                transcript_settings=TranscriptSettings(state_directory=state_directory),
                provider=provider,
            )
        provider.assert_complete()
        return _event_lines(b"".join(output_lines)), state_directory

    events, state_directory = asyncio.run(scenario())
    transcript_path = next((state_directory / "transcripts").glob("*.jsonl"))
    replay = replay_transcript(transcript_path)

    assert [event.type for event in events] == ["runtime.ready", "session.started"]
    assert replay.state.status == "running"
    assert not replay.complete
    assert not list((state_directory / "transcripts").glob("*.summary.txt"))


def test_runtime_reports_one_recoverable_persistence_error_and_completes_session(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    environment = _isolated_runtime_environment(
        tmp_path,
        XDG_STATE_HOME=str(workspace),
    )
    input_bytes = b"".join(
        [
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            ),
            _command("session.start", "cmd_session", {"task": "Continue safely"}),
            _command("runtime.shutdown", "cmd_shutdown", {}),
        ]
    )

    completed = _run_runtime(
        "--workspace",
        str(workspace),
        input_bytes=input_bytes,
        transcript_enabled=True,
        environment=environment,
    )
    events = _stdout_events(completed)
    errors = [event for event in events if event.type == "runtime.error"]

    assert completed.returncode == 0
    assert len(errors) == 1
    assert errors[0].payload.code == "transcript_persistence_failed"
    assert errors[0].payload.recoverable is True
    assert errors[0].correlation_id == "cmd_session"
    assert events[-1].type == "session.completed"
    assert not (workspace / "code-assist-harness").exists()


def test_runtime_reports_one_mid_session_flush_failure_without_changing_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = TranscriptSettings(state_directory=tmp_path / "state" / "code-assist-harness")
    commands = [
        validate_command(
            json.loads(
                _command(
                    "runtime.initialize",
                    "cmd_initialize",
                    {"workspace": str(workspace.resolve())},
                )
            )
        ),
        validate_command(
            json.loads(
                _command("session.start", "cmd_session", {"task": "Keep running after fsync"})
            )
        ),
        validate_command(json.loads(_command("runtime.shutdown", "cmd_shutdown", {}))),
    ]
    output_lines: list[bytes] = []
    transcripts: list[SessionTranscript] = []
    flush_count = 0
    original_create = SessionTranscript.create

    def flush(descriptor: int) -> None:
        nonlocal flush_count
        flush_count += 1
        if flush_count == 3:
            raise OSError("injected fsync failure whose details must remain private")
        os.fsync(descriptor)

    async def read_commands():
        for command in commands:
            yield command

    async def write_stdout_line(line: bytes) -> None:
        output_lines.append(line)

    async def create_transcript(
        transcript_settings: TranscriptSettings,
        canonical_workspace: Path,
        session_id: str,
    ) -> SessionTranscript:
        transcript = await original_create(
            transcript_settings,
            canonical_workspace,
            session_id,
            operations=TranscriptFileOperations(flush=flush),
            create_transcript_id=lambda: "runtime_failure_tape_011",
        )
        transcripts.append(transcript)
        return transcript

    monkeypatch.setattr(runtime_module, "_read_commands", read_commands)
    monkeypatch.setattr(runtime_module, "_write_stdout_line", write_stdout_line)
    monkeypatch.setattr(
        runtime_module.SessionTranscript,
        "create",
        staticmethod(create_transcript),
    )

    asyncio.run(
        runtime_module.run_runtime(
            workspace.resolve(),
            transcript_settings=settings,
        )
    )
    events = _event_lines(b"".join(output_lines))
    errors = [event for event in events if event.type == "runtime.error"]

    assert len(transcripts) == 1
    assert len(errors) == 1
    assert errors[0].payload.code == "transcript_persistence_failed"
    assert errors[0].payload.recoverable is True
    assert errors[0].correlation_id == "cmd_session"
    assert events[-1].type == "session.completed"
    replay = replay_transcript(transcripts[0].transcript_path)
    assert replay.state.status == "running"
    assert not replay.complete


def test_interrupted_runtime_retains_a_valid_incomplete_jsonl_prefix(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    xdg_state = tmp_path / "xdg-state"
    environment = _isolated_runtime_environment(
        tmp_path,
        XDG_STATE_HOME=str(xdg_state),
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "code_assist_harness.runtime",
            "--workspace",
            str(workspace),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        bufsize=0,
    )

    try:
        assert process.stdin is not None
        process.stdin.write(
            _command(
                "runtime.initialize",
                "cmd_initialize",
                {"workspace": str(workspace.resolve())},
            )
        )
        process.stdin.flush()
        assert _read_process_event(process).type == "runtime.ready"
        process.stdin.write(_command("session.start", "cmd_session", {"task": "Interrupt me"}))
        process.stdin.flush()
        assert _read_process_event(process).type == "session.started"
        assert _read_process_event(process).type == "assistant.delta"
        # Observing the next event proves the previous delta's awaited transcript fsync returned.
        assert _read_process_event(process).type == "assistant.delta"

        transcript_directory = xdg_state / "code-assist-harness" / "transcripts"
        deadline = time.monotonic() + 2
        transcript_paths: list[Path] = []
        while time.monotonic() < deadline:
            transcript_paths = list(transcript_directory.glob("*.jsonl"))
            if transcript_paths and len(transcript_paths[0].read_bytes().splitlines()) >= 3:
                break
            time.sleep(0.01)
        assert len(transcript_paths) == 1

        process.terminate()
        process.wait(timeout=5)
        replay = replay_transcript(transcript_paths[0])

        assert len(replay.records) >= 3
        assert not replay.complete
        assert replay.state.status == "running"
        assert transcript_paths[0].read_bytes().endswith(b"\n")
        assert not list(transcript_directory.glob("*.summary.txt"))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_runtime_reports_invalid_workspace_only_on_stderr(tmp_path: Path) -> None:
    missing = tmp_path / "private-missing-workspace"

    completed = _run_runtime("--workspace", str(missing))

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert completed.stderr == (
        b"runtime configuration error: Workspace root must be an existing directory.\n"
    )
    assert b"private-missing-workspace" not in completed.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        (),
        ("--workspace", ".", "--workspace", "."),
    ],
)
def test_runtime_requires_exactly_one_workspace(arguments: tuple[str, ...]) -> None:
    completed = _run_runtime(*arguments)

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert b"--workspace PATH" in completed.stderr
    assert b"exactly once" in completed.stderr
