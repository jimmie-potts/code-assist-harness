from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from code_assist_harness.protocol import Event, EventLineReader, ProtocolParseFailure
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
    reader = EventLineReader()
    results = [*reader.feed(completed.stdout), *reader.finish()]
    assert all(not isinstance(result, ProtocolParseFailure) for result in results)
    return [result for result in results if not isinstance(result, ProtocolParseFailure)]


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
    unavailable = _command("session.start", "cmd_session", {"task": "Explain this repository"})
    shutdown = _command("runtime.shutdown", "cmd_shutdown", {})

    completed = _run_runtime(
        "--workspace",
        str(tmp_path),
        input_bytes=b"".join(
            [malformed, unsupported, unknown, invalid_payload, initialize, unavailable, shutdown]
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
        "command_unavailable",
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
