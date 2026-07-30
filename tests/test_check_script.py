import os
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPOSITORY_ROOT / "scripts" / "check"


def _write_command_stub(bin_directory: Path, name: str) -> None:
    stub = bin_directory / name
    stub.write_text(
        """#!/bin/sh
set -eu
printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\\n' \\
    \"$(basename \"$0\")\" \\
    \"$*\" \\
    \"${OPENAI_API_KEY-unset}\" \\
    \"${NPM_CONFIG_OFFLINE-unset}\" \\
    \"${PYTHONPATH-unset}\" \\
    \"${NODE_OPTIONS-unset}\" \\
    \"${PYTHONDONTWRITEBYTECODE-unset}\" \\
    \"${UV_PROJECT-unset}\" \\
    \"${UV_PROJECT_ENVIRONMENT-unset}\" \\
    \"${UV_PYTHON-unset}\" \\
    \"${UV_WORKING_DIR-unset}\" \\
    \"${UV_NO_PROJECT-unset}\" \\
    \"${UV_ISOLATED-unset}\" \\
    \"$PWD\" >> \"$CHECK_LOG\"
if [ \"${FAIL_COMMAND-}\" = \"$(basename \"$0\") $*\" ]; then
    exit 23
fi
""",
        encoding="utf-8",
    )
    stub.chmod(0o755)


def _run_check_with_stubs(
    tmp_path: Path, *, fail_command: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    for name in ("uv", "npm", "node"):
        _write_command_stub(bin_directory, name)

    log_path = tmp_path / "commands.log"
    environment = os.environ.copy()
    environment.update(
        {
            "CHECK_LOG": str(log_path),
            "OPENAI_API_KEY": "must-not-reach-checks",
            "PATH": f"{bin_directory}:{environment['PATH']}",
            "UV_NO_PROJECT": "true",
            "UV_ISOLATED": "true",
            "UV_PROJECT": "/tmp/other-project",
            "UV_PROJECT_ENVIRONMENT": "/tmp/other-environment",
            "UV_PYTHON": "/tmp/other-python",
            "UV_WORKING_DIR": "/tmp/other-working-directory",
        }
    )
    if fail_command is not None:
        environment["FAIL_COMMAND"] = fail_command

    result = subprocess.run(
        [str(CHECK_SCRIPT)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return result, lines


def test_check_runs_every_layer_without_credentials_or_runtime_selectors(tmp_path: Path) -> None:
    result, commands = _run_check_with_stubs(tmp_path)
    command_fields = [command.split("|", maxsplit=13) for command in commands]

    assert result.returncode == 0
    assert ["|".join(fields[:4]) for fields in command_fields] == [
        "uv|sync --check --locked --offline|unset|true",
        "uv|run --offline --frozen --no-sync ruff check .|unset|true",
        "uv|run --offline --frozen --no-sync ruff format --check .|unset|true",
        (
            "uv|run --offline --frozen --no-sync pytest "
            "--ignore=tests/protocol/test_fixtures.py "
            "--ignore=tests/test_check_script.py "
            "--ignore=tests/test_repository_policy.py|unset|true"
        ),
        ("uv|run --offline --frozen --no-sync pytest tests/protocol/test_fixtures.py|unset|true"),
        (
            "uv|run --offline --frozen --no-sync pytest tests/test_check_script.py "
            "tests/test_repository_policy.py|unset|true"
        ),
        "node|--import=tsx src/check-node-version.ts|unset|true",
        "npm|--offline --prefix tui run typecheck|unset|true",
        "npm|--offline --prefix tui run lint|unset|true",
        (
            "npm|--offline --prefix tui test -- --exclude test/protocol-fixtures.test.ts "
            "--exclude test/runtime-boundary.test.ts|unset|true"
        ),
        "npm|--offline --prefix tui test -- test/protocol-fixtures.test.ts|unset|true",
        "npm|--offline --prefix tui test -- test/runtime-boundary.test.ts|unset|true",
    ]
    assert {fields[4] for fields in command_fields} == {
        str(REPOSITORY_ROOT / "tests" / "network_guard")
    }
    assert {fields[5] for fields in command_fields} == {
        f'--import="{REPOSITORY_ROOT / "scripts" / "deny-network.mjs"}"'
    }
    assert {fields[6] for fields in command_fields} == {"1"}
    assert {tuple(fields[7:13]) for fields in command_fields} == {
        ("unset", "unset", "unset", "unset", "unset", "unset")
    }
    node_command = next(fields for fields in command_fields if fields[0] == "node")
    assert node_command[13] == str(REPOSITORY_ROOT / "tui")
    assert "==> Python lockfile and environment" in result.stdout
    assert "==> Python lint and docstrings" in result.stdout
    assert "==> Node runtime compatibility" in result.stdout
    assert "==> Node-Python integration" in result.stdout
    assert result.stdout.rstrip().endswith("All repository checks passed.")


def test_check_stops_at_first_failed_layer(tmp_path: Path) -> None:
    result, commands = _run_check_with_stubs(
        tmp_path,
        fail_command="uv run --offline --frozen --no-sync ruff format --check .",
    )

    assert result.returncode == 23
    assert ["|".join(command.split("|", maxsplit=5)[:4]) for command in commands] == [
        "uv|sync --check --locked --offline|unset|true",
        "uv|run --offline --frozen --no-sync ruff check .|unset|true",
        "uv|run --offline --frozen --no-sync ruff format --check .|unset|true",
    ]
    assert "==> Python format" in result.stdout
    assert "==> Python tests" not in result.stdout
    assert "All repository checks passed." not in result.stdout


@pytest.mark.parametrize(
    ("failing_command", "label", "next_label"),
    [
        (
            "uv run --offline --frozen --no-sync pytest "
            "--ignore=tests/protocol/test_fixtures.py "
            "--ignore=tests/test_check_script.py --ignore=tests/test_repository_policy.py",
            "Python tests",
            "Protocol fixtures: Python",
        ),
        (
            "uv run --offline --frozen --no-sync pytest tests/protocol/test_fixtures.py",
            "Protocol fixtures: Python",
            "Repository policy",
        ),
        (
            "node --import=tsx src/check-node-version.ts",
            "Node runtime compatibility",
            "TUI typecheck",
        ),
        (
            "npm --offline --prefix tui test -- --exclude test/protocol-fixtures.test.ts "
            "--exclude test/runtime-boundary.test.ts",
            "TUI tests",
            "Protocol fixtures: TypeScript",
        ),
        (
            "npm --offline --prefix tui test -- test/runtime-boundary.test.ts",
            "Node-Python integration",
            "All repository checks passed.",
        ),
    ],
)
def test_check_propagates_each_behavioral_layer_failure(
    tmp_path: Path,
    failing_command: str,
    label: str,
    next_label: str,
) -> None:
    result, commands = _run_check_with_stubs(tmp_path, fail_command=failing_command)

    assert result.returncode == 23
    assert commands[-1].startswith(failing_command.replace(" ", "|", 1))
    assert f"==> {label}" in result.stdout
    assert next_label not in result.stdout
