import os
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT = REPOSITORY_ROOT / "scripts" / "check"


def _write_command_stub(bin_directory: Path, name: str) -> None:
    stub = bin_directory / name
    stub.write_text(
        """#!/bin/sh
set -eu
openai_state=\"${OPENAI_ADMIN_KEY-unset},${OPENAI_WEBHOOK_SECRET-unset}\"
openai_state=\"$openai_state,${OPENAI_BASE_URL-unset},${OPENAI_ORGANIZATION-unset}\"
openai_state=\"$openai_state,${OPENAI_ORG_ID-unset},${OPENAI_PROJECT_ID-unset}\"
openai_state=\"$openai_state,${OPENAI_CUSTOM_HEADERS-unset},${OPENAI_LOG-unset}\"
openai_state=\"$openai_state,${OPENAI_API_TYPE-unset},${OPENAI_API_VERSION-unset}\"
openai_state=\"$openai_state,${OPENAI_AD_TOKEN-unset},${OPENAI_ENDPOINT-unset}\"
printf '%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\\n' \\
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
    \"$openai_state\" \\
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
            "OPENAI_ADMIN_KEY": "must-not-reach-checks",
            "OPENAI_AD_TOKEN": "must-not-reach-checks",
            "OPENAI_API_KEY": "must-not-reach-checks",
            "OPENAI_API_TYPE": "must-not-reach-checks",
            "OPENAI_API_VERSION": "must-not-reach-checks",
            "OPENAI_BASE_URL": "must-not-reach-checks",
            "OPENAI_CUSTOM_HEADERS": "must-not-reach-checks",
            "OPENAI_ENDPOINT": "must-not-reach-checks",
            "OPENAI_LOG": "must-not-reach-checks",
            "OPENAI_ORGANIZATION": "must-not-reach-checks",
            "OPENAI_ORG_ID": "must-not-reach-checks",
            "OPENAI_PROJECT_ID": "must-not-reach-checks",
            "OPENAI_WEBHOOK_SECRET": "must-not-reach-checks",
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
    command_fields = [command.split("|", maxsplit=14) for command in commands]

    assert result.returncode == 0
    assert ["|".join(fields[:4]) for fields in command_fields] == [
        "uv|sync --check --locked --offline|unset|true",
        "uv|run --offline --frozen --no-sync ruff check .|unset|true",
        "uv|run --offline --frozen --no-sync ruff format --check .|unset|true",
        (
            "uv|run --offline --frozen --no-sync pytest "
            "-m not live_provider "
            "--ignore=tests/protocol/test_fixtures.py "
            "--ignore=tests/test_check_script.py "
            "--ignore=tests/test_repository_policy.py|unset|true"
        ),
        ("uv|run --offline --frozen --no-sync pytest tests/protocol/test_fixtures.py|unset|true"),
        "node|--import=tsx src/check-node-version.ts|unset|true",
        (
            "uv|run --offline --frozen --no-sync pytest tests/test_check_script.py "
            "tests/test_repository_policy.py|unset|true"
        ),
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
    assert {fields[13] for fields in command_fields} == {",".join(["unset"] * 12)}
    node_command = next(fields for fields in command_fields if fields[0] == "node")
    assert node_command[14] == str(REPOSITORY_ROOT / "tui")
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
            "-m not live_provider "
            "--ignore=tests/protocol/test_fixtures.py "
            "--ignore=tests/test_check_script.py --ignore=tests/test_repository_policy.py",
            "Python tests",
            "Protocol fixtures: Python",
        ),
        (
            "uv run --offline --frozen --no-sync pytest tests/protocol/test_fixtures.py",
            "Protocol fixtures: Python",
            "Node runtime compatibility",
        ),
        (
            "node --import=tsx src/check-node-version.ts",
            "Node runtime compatibility",
            "Repository policy",
        ),
        (
            "uv run --offline --frozen --no-sync pytest tests/test_check_script.py "
            "tests/test_repository_policy.py",
            "Repository policy",
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


def _run_live_test_options(
    *arguments: str,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("OPENAI_")
    }
    if environment_updates is not None:
        environment.update(environment_updates)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-m",
            "live_provider",
            "tests/provider/test_openai_live.py",
            *arguments,
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def test_live_provider_marker_skips_without_explicit_opt_in() -> None:
    result = _run_live_test_options(
        environment_updates={"OPENAI_API_KEY": "ambient-key-must-not-select-network"}
    )

    assert result.returncode == 0
    assert "1 skipped" in result.stdout


@pytest.mark.parametrize(
    ("arguments", "environment_updates", "expected", "untrusted_value"),
    [
        (
            ("--run-live-provider", "--live-provider-model", "unsafe-model-sentinel"),
            {"OPENAI_API_KEY": "syntactically-valid-key"},
            "Unsupported OpenAI model. Use gpt-4.1-mini-2025-04-14.",
            "unsafe-model-sentinel",
        ),
        (
            (
                "--run-live-provider",
                "--live-provider-model",
                "gpt-4.1-mini-2025-04-14",
            ),
            {},
            "OPENAI_API_KEY is required and must be a valid local credential.",
            None,
        ),
        (
            (
                "--run-live-provider",
                "--live-provider-model",
                "gpt-4.1-mini-2025-04-14",
            ),
            {
                "OPENAI_API_KEY": "syntactically-valid-key",
                "OPENAI_BASE_URL": "https://unsafe-endpoint.invalid/sentinel",
            },
            "Unsupported OpenAI configuration is present.",
            "https://unsafe-endpoint.invalid/sentinel",
        ),
    ],
)
def test_live_provider_opt_in_rejects_invalid_configuration_before_test_setup(
    arguments: tuple[str, ...],
    environment_updates: dict[str, str],
    expected: str,
    untrusted_value: str | None,
) -> None:
    result = _run_live_test_options(*arguments, environment_updates=environment_updates)
    output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode != 0
    assert expected in output
    if untrusted_value is not None:
        assert untrusted_value not in output
