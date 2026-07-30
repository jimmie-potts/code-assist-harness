from __future__ import annotations

import asyncio
import json
import select
import subprocess
import sys
from pathlib import Path

import pytest

from code_assist_harness.mock_session import (
    MOCK_RESPONSE_DELTAS,
    MOCK_RESPONSE_TEXT,
    MockSessionRunner,
)
from code_assist_harness.protocol import (
    Event,
    EventLineReader,
    OrderedEventWriter,
    ProtocolParseFailure,
    SessionStartCommand,
)
from code_assist_harness.runtime import RuntimeConfigurationError, resolve_workspace

TIMESTAMP = "2026-07-16T12:34:56.789Z"


def _run_runtime(*arguments: str, input_bytes: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "code_assist_harness.runtime", *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=5,
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


def test_resolve_workspace_returns_canonical_directory(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)

    assert resolve_workspace(alias) == workspace.resolve()


@pytest.mark.parametrize("invalid_kind", ["missing", "file"])
def test_resolve_workspace_rejects_invalid_paths(tmp_path: Path, invalid_kind: str) -> None:
    candidate = tmp_path / invalid_kind
    if invalid_kind == "file":
        candidate.write_text("not a directory", encoding="utf-8")

    with pytest.raises(RuntimeConfigurationError, match="workspace"):
        resolve_workspace(candidate)


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
    async def scenario() -> tuple[list[tuple[int, str]], list[bytes]]:
        lines: list[bytes] = []
        reached: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        releases = [asyncio.Event() for _delta in MOCK_RESPONSE_DELTAS]

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def checkpoint(index: int, delta: str) -> None:
            await reached.put((index, delta))
            await releases[index - 1].wait()

        runner = MockSessionRunner(OrderedEventWriter(sink), checkpoint)
        running = asyncio.create_task(runner.run(_session_start("cmd_session")))
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
        return observations, lines

    observations, lines = asyncio.run(scenario())
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


def test_mock_session_cancels_before_the_first_delta_and_repeats_idempotently() -> None:
    async def scenario() -> tuple[list[bytes], str, str]:
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
        return lines, first_result, repeated_result

    lines, first_result, repeated_result = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert first_result == "accepted"
    assert repeated_result == "already_requested"
    assert [event.type for event in events] == ["session.started", "session.cancelled"]
    assert [event.sequence for event in events] == [1, 2]
    assert [event.correlation_id for event in events] == ["cmd_session", "cmd_cancel"]


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
    async def scenario() -> tuple[list[bytes], str, bool]:
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
        return lines, cancellation_result, cancellation_waited_for_terminal_write

    lines, cancellation_result, cancellation_waited = asyncio.run(scenario())
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
        [sys.executable, "-m", "code_assist_harness.runtime", "--workspace", str(tmp_path)],
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
        [sys.executable, "-m", "code_assist_harness.runtime", "--workspace", str(tmp_path)],
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


def test_runtime_reports_invalid_workspace_only_on_stderr(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    completed = _run_runtime("--workspace", str(missing))

    assert completed.returncode == 2
    assert completed.stdout == b""
    assert b"runtime configuration error" in completed.stderr
    assert b"workspace does not exist" in completed.stderr


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
