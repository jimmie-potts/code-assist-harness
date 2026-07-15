from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from code_assist_harness.runtime import RuntimeConfigurationError, resolve_workspace


def _run_runtime(*arguments: str, input_bytes: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "code_assist_harness.runtime", *arguments],
        input=input_bytes,
        capture_output=True,
        check=False,
        timeout=5,
    )


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


def test_runtime_exits_cleanly_on_stdin_eof_without_stdout(tmp_path: Path) -> None:
    completed = _run_runtime(
        "--workspace",
        str(tmp_path),
        input_bytes=b"bytes are discarded until CAH-004 implements commands\n",
    )

    assert completed.returncode == 0
    assert completed.stdout == b""
    assert completed.stderr == b""


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
