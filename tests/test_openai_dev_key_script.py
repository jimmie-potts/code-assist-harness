from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
HELPER_SOURCE = REPOSITORY_ROOT / "scripts" / "with-openai-dev-key"
FAKE_API_KEY = "FAKE_CAH_OPENAI_DEV_KEY_023"
FORMAT_ERROR = (
    "dev.env must contain exactly one OPENAI_API_KEY assignment; "
    "blank lines and comments are allowed."
)


def _prepare_helper(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    helper = scripts / "with-openai-dev-key"
    shutil.copyfile(HELPER_SOURCE, helper)
    helper.chmod(0o755)
    return repository, helper


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _environment(**updates: str) -> dict[str, str]:
    environment = {
        "HOME": os.environ.get("HOME", str(Path.home())),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PATH": os.environ.get("PATH", os.defpath),
    }
    environment.update(updates)
    return environment


def _run(helper: Path, command: Path, *arguments: str, environment: dict[str, str] | None = None):
    return subprocess.run(
        [str(helper), str(command), *arguments],
        capture_output=True,
        check=False,
        env=environment or _environment(),
        text=True,
    )


def test_helper_imports_only_the_key_and_preserves_command_arguments(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_text(
        f"# Local credential only.\n\nOPENAI_API_KEY={FAKE_API_KEY}\n",
        encoding="utf-8",
    )
    dev_environment.chmod(0o600)
    child = tmp_path / "inspect-environment"
    _write_executable(
        child,
        "#!/bin/sh\n"
        f"[ \"${{OPENAI_API_KEY-}}\" = '{FAKE_API_KEY}' ] || exit 41\n"
        '[ "${UNEXPECTED_DEV_VALUE+x}" != x ] || exit 42\n'
        "printf 'credential=present\\n'\n"
        'for argument in "$@"; do\n'
        "    printf 'argument=<%s>\\n' \"$argument\"\n"
        "done\n",
    )

    result = _run(helper, child, "argument with spaces", "--literal")

    assert result.returncode == 0
    assert result.stdout == (
        "credential=present\nargument=<argument with spaces>\nargument=<--literal>\n"
    )
    assert result.stderr == ""
    assert FAKE_API_KEY not in result.stdout
    assert FAKE_API_KEY not in result.stderr


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "OPENAI_API_KEY=\n",
        f"OPENAI_API_KEY={FAKE_API_KEY}\nOPENAI_API_KEY=second-key\n",
        f"OPENAI_BASE_URL=https://example.invalid\nOPENAI_API_KEY={FAKE_API_KEY}\n",
        f"export OPENAI_API_KEY={FAKE_API_KEY}\n",
        f" OPENAI_API_KEY={FAKE_API_KEY}\n",
        "OPENAI_API_KEY=key with spaces\n",
        "OPENAI_API_KEY=key\twith-tab\n",
        "OPENAI_API_KEY=key\u00a0with-nonbreaking-space\n",
        "OPENAI_API_KEY=key\u200bwith-zero-width-space\n",
    ],
)
def test_helper_rejects_invalid_files_without_starting_the_command(
    tmp_path: Path,
    contents: str,
) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_text(contents, encoding="utf-8")
    dev_environment.chmod(0o600)
    invoked = tmp_path / "command-invoked"
    child = tmp_path / "must-not-run"
    _write_executable(child, f"#!/bin/sh\ntouch '{invoked}'\n")

    result = _run(helper, child)

    assert result.returncode == 1
    assert result.stdout == ""
    assert not invoked.exists()
    assert FAKE_API_KEY not in result.stderr
    assert "https://example.invalid" not in result.stderr
    if contents == "" or contents == "OPENAI_API_KEY=\n":
        assert "exactly one non-empty OPENAI_API_KEY assignment" in result.stderr
    elif any(
        marker in contents
        for marker in ("with spaces", "with-tab", "nonbreaking-space", "zero-width-space")
    ):
        assert "must not contain whitespace or control characters" in result.stderr
    else:
        assert FORMAT_ERROR in result.stderr


def test_helper_treats_an_injection_shaped_key_as_literal_data(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    injected_marker = tmp_path / "injected-marker"
    literal_key = f"$(touch${{IFS}}{injected_marker})"
    dev_environment = repository / "dev.env"
    dev_environment.write_text(f"OPENAI_API_KEY={literal_key}\n", encoding="utf-8")
    dev_environment.chmod(0o600)
    child = tmp_path / "inspect-literal"
    _write_executable(
        child,
        "#!/bin/sh\n"
        f"[ \"${{OPENAI_API_KEY-}}\" = '{literal_key}' ] || exit 43\n"
        "printf 'literal=preserved\\n'\n",
    )

    result = _run(helper, child)

    assert result.returncode == 0
    assert result.stdout == "literal=preserved\n"
    assert result.stderr == ""
    assert not injected_marker.exists()
    assert literal_key not in result.stdout


def test_helper_rejects_a_nul_byte_before_starting_the_command(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_bytes(b"OPENAI_API_KEY=key-before\x00key-after\n")
    dev_environment.chmod(0o600)
    invoked = tmp_path / "command-invoked"
    child = tmp_path / "must-not-run"
    _write_executable(child, f"#!/bin/sh\ntouch '{invoked}'\n")

    result = _run(helper, child)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "OPENAI_API_KEY in dev.env must not contain whitespace or control characters.\n"
    )
    assert "key-before" not in result.stderr
    assert "key-after" not in result.stderr
    assert not invoked.exists()


def test_helper_rejects_an_ambient_key_before_reading_dev_environment(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_text(f"OPENAI_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    dev_environment.chmod(0o600)
    invoked = tmp_path / "command-invoked"
    child = tmp_path / "must-not-run"
    _write_executable(child, f"#!/bin/sh\ntouch '{invoked}'\n")

    result = _run(helper, child, environment=_environment(OPENAI_API_KEY="ambient-key"))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "OPENAI_API_KEY is already set" in result.stderr
    assert "ambient-key" not in result.stderr
    assert FAKE_API_KEY not in result.stderr
    assert not invoked.exists()


def test_helper_rejects_missing_symlinked_and_permissive_dev_environment_files(
    tmp_path: Path,
) -> None:
    repository, helper = _prepare_helper(tmp_path)
    child = tmp_path / "must-not-run"
    invoked = tmp_path / "command-invoked"
    _write_executable(child, f"#!/bin/sh\ntouch '{invoked}'\n")

    missing = _run(helper, child)
    target = tmp_path / "credential-target"
    target.write_text(f"OPENAI_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    target.chmod(0o600)
    dev_environment = repository / "dev.env"
    dev_environment.symlink_to(target)
    symlinked = _run(helper, child)
    dev_environment.unlink()
    dev_environment.write_text(f"OPENAI_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    dev_environment.chmod(0o644)
    permissive = _run(helper, child)

    assert missing.returncode == 1
    assert symlinked.returncode == 1
    assert permissive.returncode == 1
    assert "readable, regular, non-symlink" in missing.stderr
    assert "readable, regular, non-symlink" in symlinked.stderr
    assert "mode 0600" in permissive.stderr
    assert FAKE_API_KEY not in missing.stderr + symlinked.stderr + permissive.stderr
    assert not invoked.exists()


def test_helper_rejects_a_fifo_without_waiting_for_a_writer(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    os.mkfifo(dev_environment, mode=0o600)
    invoked = tmp_path / "command-invoked"
    child = tmp_path / "must-not-run"
    _write_executable(child, f"#!/bin/sh\ntouch '{invoked}'\n")

    result = subprocess.run(
        [str(helper), str(child)],
        capture_output=True,
        check=False,
        env=_environment(),
        text=True,
        timeout=2,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "readable, regular, non-symlink" in result.stderr
    assert not invoked.exists()


def test_helper_ignores_ambient_python_import_configuration(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_text(f"OPENAI_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    dev_environment.chmod(0o600)
    shadow_directory = tmp_path / "shadow"
    shadow_directory.mkdir()
    imported = tmp_path / "ambient-module-imported"
    (shadow_directory / "pathlib.py").write_text(
        f"open({str(imported)!r}, 'w', encoding='utf-8').close()\n",
        encoding="utf-8",
    )
    child = tmp_path / "success"
    _write_executable(child, "#!/bin/sh\nprintf 'child=started\\n'\n")

    result = _run(
        helper,
        child,
        environment=_environment(PYTHONPATH=str(shadow_directory)),
    )

    assert result.returncode == 0
    assert result.stdout == "child=started\n"
    assert result.stderr == ""
    assert not imported.exists()


def test_helper_requires_an_explicit_command(tmp_path: Path) -> None:
    repository, helper = _prepare_helper(tmp_path)
    dev_environment = repository / "dev.env"
    dev_environment.write_text(f"OPENAI_API_KEY={FAKE_API_KEY}\n", encoding="utf-8")
    dev_environment.chmod(0o600)

    result = subprocess.run(
        [str(helper)],
        capture_output=True,
        check=False,
        env=_environment(),
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Usage: ./scripts/with-openai-dev-key COMMAND [ARGUMENT ...]\n"


def test_helper_rejects_an_empty_command_before_reading_the_key(tmp_path: Path) -> None:
    _repository, helper = _prepare_helper(tmp_path)

    result = subprocess.run(
        [str(helper), ""],
        capture_output=True,
        check=False,
        env=_environment(),
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Usage: ./scripts/with-openai-dev-key COMMAND [ARGUMENT ...]\n"
