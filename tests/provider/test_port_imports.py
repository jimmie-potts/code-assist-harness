from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

from code_assist_harness.provider import FakeProvider, Provider

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_provider_package_imports_with_vendor_and_framework_modules_unavailable() -> None:
    environment = os.environ.copy()
    for name in (
        "OPENAI_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
    ):
        environment.pop(name, None)
    script = """
import sys
for name in ("openai", "langchain", "langchain_core", "anthropic"):
    sys.modules[name] = None
import code_assist_harness.provider
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_provider_port_is_structural_and_project_has_no_provider_sdk_dependency() -> None:
    fake = FakeProvider(())
    project = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    development_dependencies = project["dependency-groups"]["dev"]

    assert isinstance(fake, Provider)
    assert all("openai" not in dependency.lower() for dependency in dependencies)
    assert all("langchain" not in dependency.lower() for dependency in dependencies)
    assert all("openai" not in dependency.lower() for dependency in development_dependencies)
    assert all("langchain" not in dependency.lower() for dependency in development_dependencies)
