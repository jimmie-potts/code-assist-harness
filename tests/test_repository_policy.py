import ast
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from collections.abc import Iterable
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TUI_ROOT = REPOSITORY_ROOT / "tui"
MARKDOWN_ROOTS = (REPOSITORY_ROOT,)
PRODUCTION_SOURCE_ROOTS = (
    REPOSITORY_ROOT / "src" / "code_assist_harness",
    REPOSITORY_ROOT / "tui" / "src",
)
PYTHON_NETWORK_GUARD = REPOSITORY_ROOT / "tests" / "network_guard"
NODE_NETWORK_GUARD = REPOSITORY_ROOT / "scripts" / "deny-network.mjs"
OPENAI_ADAPTER_SOURCE = (
    REPOSITORY_ROOT / "src" / "code_assist_harness" / "provider" / "openai_responses.py"
)

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)|!\[[^]]*]\(([^)]+)\)")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
PYTHON_NETWORK_MODULES = frozenset(
    {
        "aiohttp",
        "http.client",
        "httpx",
        "openai",
        "requests",
        "socket",
        "urllib",
        "urllib3",
        "websockets",
    }
)
TYPESCRIPT_NETWORK_MODULES = frozenset(
    {
        "axios",
        "dgram",
        "dns",
        "dns/promises",
        "http",
        "http2",
        "https",
        "net",
        "node:dgram",
        "node:dns",
        "node:dns/promises",
        "node:http",
        "node:http2",
        "node:https",
        "node:net",
        "node:tls",
        "tls",
        "undici",
        "ws",
    }
)
TYPESCRIPT_IMPORT = re.compile(
    r"(?:\bfrom\s*|\bimport\s*(?:\(\s*)?|\brequire\s*\(\s*)['\"]([^'\"]+)['\"]"
)
TYPESCRIPT_FETCH_CALL = re.compile(
    r"(?<![\w.$])(?:fetch|(?:globalThis|window)\s*"
    r"(?:\??\.\s*fetch|(?:\?\.\s*)?\[\s*(?:\"fetch\"|'fetch'|`fetch`)\s*\]))"
    r"\s*(?:\?\.\s*)?\("
)
TYPESCRIPT_NETWORK_CALLS = (
    ("fetch", TYPESCRIPT_FETCH_CALL),
    ("WebSocket", re.compile(r"\bnew\s+WebSocket\s*\(")),
    ("network request", re.compile(r"\b(?:http|https)\.(?:get|request)\s*\(")),
    ("network connection", re.compile(r"\b(?:net|tls)\.(?:connect|createConnection)\s*\(")),
)


def _is_denied_python_module(module: str) -> bool:
    return any(
        module == denied or module.startswith(f"{denied}.") for denied in PYTHON_NETWORK_MODULES
    )


def _is_denied_typescript_module(module: str) -> bool:
    return any(
        module == denied or module.startswith(f"{denied}/") for denied in TYPESCRIPT_NETWORK_MODULES
    )


def _repository_files(
    roots: Iterable[Path],
    suffixes: set[str],
    *,
    repository_root: Path = REPOSITORY_ROOT,
) -> list[Path]:
    """Return tracked and nonignored untracked policy inputs from Git.

    Git remains the source of truth for ignored local environments and generated artifacts, while
    ``--others`` keeps new, unstaged source and documentation inside the pre-commit gate.
    """
    git = shutil.which("git")
    if git is None:
        raise AssertionError("git is required to discover repository policy inputs")

    resolved_repository_root = repository_root.resolve()
    pathspecs: list[str] = []
    for root in roots:
        try:
            relative_root = root.resolve().relative_to(resolved_repository_root)
        except ValueError as error:
            raise AssertionError(f"policy root escapes the repository: {root}") from error
        pathspecs.append(relative_root.as_posix())

    result = subprocess.run(
        [
            git,
            "-C",
            str(resolved_repository_root),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            *pathspecs,
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        diagnostic = os.fsdecode(result.stderr).strip() or "unknown Git error"
        raise AssertionError(f"git could not discover repository policy inputs: {diagnostic}")

    files: list[Path] = []
    for encoded_path in result.stdout.split(b"\0"):
        if not encoded_path:
            continue
        path = resolved_repository_root / os.fsdecode(encoded_path)
        if not path.is_file() or path.suffix not in suffixes:
            continue
        try:
            path.resolve().relative_to(resolved_repository_root)
        except ValueError as error:
            raise AssertionError(f"policy input escapes the repository: {path}") from error
        files.append(path)
    return sorted(files)


def _outside_fenced_blocks(markdown: str) -> str:
    visible_lines: list[str] = []
    active_fence: str | None = None
    for line in markdown.splitlines():
        stripped = line.lstrip()
        fence_match = re.match(r"(`{3,}|~{3,})", stripped)
        if fence_match:
            fence = fence_match.group(1)
            if active_fence is None:
                active_fence = fence[0]
            elif fence.startswith(active_fence):
                active_fence = None
            continue
        if active_fence is None:
            visible_lines.append(line)
    return "\n".join(visible_lines)


def _markdown_destinations(markdown: str) -> Iterable[str]:
    for match in MARKDOWN_LINK.finditer(_outside_fenced_blocks(markdown)):
        destination = next(group for group in match.groups() if group is not None).strip()
        if destination.startswith("<") and ">" in destination:
            destination = destination[1 : destination.index(">")]
        else:
            destination = destination.split(maxsplit=1)[0]
        yield destination


def _heading_anchors(markdown_path: Path) -> set[str]:
    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    markdown = _outside_fenced_blocks(markdown_path.read_text(encoding="utf-8"))
    for line in markdown.splitlines():
        match = MARKDOWN_HEADING.match(line)
        if match is None:
            continue
        heading = re.sub(r"<[^>]+>", "", match.group(1))
        heading = re.sub(r"[`*_~]", "", heading).strip().lower()
        slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        slug = re.sub(r"\s+", "-", slug)
        duplicate_number = occurrences.get(slug, 0)
        occurrences[slug] = duplicate_number + 1
        anchors.add(slug if duplicate_number == 0 else f"{slug}-{duplicate_number}")
    return anchors


def _broken_markdown_links(
    markdown_path: Path, *, repository_root: Path = REPOSITORY_ROOT
) -> list[str]:
    broken: list[str] = []
    markdown = markdown_path.read_text(encoding="utf-8")
    for destination in _markdown_destinations(markdown):
        parsed = urllib.parse.urlsplit(destination)
        if parsed.scheme or parsed.netloc:
            continue
        target = markdown_path if not parsed.path else markdown_path.parent / parsed.path
        target = Path(urllib.parse.unquote(str(target))).resolve()
        try:
            target.relative_to(repository_root)
        except ValueError:
            broken.append(f"{destination} escapes the repository")
            continue
        if not target.exists():
            broken.append(f"{destination} targets a missing path")
            continue
        if parsed.fragment and target.suffix.lower() == ".md":
            fragment = urllib.parse.unquote(parsed.fragment).lower()
            if fragment not in _heading_anchors(target):
                broken.append(f"{destination} targets a missing heading")
    return broken


def _python_network_violations(
    path: Path,
    *,
    openai_adapter_source: Path = OPENAI_ADAPTER_SOURCE,
) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        imported_modules: list[str] = []
        if isinstance(node, ast.Import):
            imported_modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules = [node.module]
        for module in imported_modules:
            if _is_denied_python_module(module) and not _is_allowed_openai_adapter_import(
                path,
                module,
                openai_adapter_source,
            ):
                violations.append(f"{path}:{node.lineno}: network module {module!r}")
        if isinstance(node, ast.Call) and _is_dynamic_import_call(node.func):
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                module = node.args[0].value
                if _is_denied_python_module(module) and not _is_allowed_openai_adapter_import(
                    path,
                    module,
                    openai_adapter_source,
                ):
                    violations.append(f"{path}:{node.lineno}: dynamic network import {module!r}")
    return violations


def _is_dynamic_import_call(function: ast.expr) -> bool:
    """Recognize literal dynamic imports without evaluating repository source."""
    if isinstance(function, ast.Name):
        return function.id in {"__import__", "import_module"}
    return (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "importlib"
        and function.attr == "import_module"
    )


def _is_allowed_openai_adapter_import(
    path: Path,
    module: str,
    openai_adapter_source: Path,
) -> bool:
    """Allow the OpenAI SDK namespace only in the one concrete adapter module."""
    return (
        module == "openai" or module.startswith("openai.")
    ) and path.resolve() == openai_adapter_source.resolve()


def _typescript_network_violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    violations: list[str] = []
    for match in TYPESCRIPT_IMPORT.finditer(source):
        module = match.group(1)
        if _is_denied_typescript_module(module):
            line = source.count("\n", 0, match.start()) + 1
            violations.append(f"{path}:{line}: network module {module!r}")
    for description, pattern in TYPESCRIPT_NETWORK_CALLS:
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            violations.append(f"{path}:{line}: {description}")
    return violations


def _run_npm_lock_graph_check(directory: Path) -> subprocess.CompletedProcess[str]:
    """Validate an npm package-lock graph without installing or updating dependencies."""
    npm = shutil.which("npm")
    if npm is None:
        raise AssertionError("npm is required to validate tui/package-lock.json")

    environment = os.environ.copy()
    environment.update(
        {
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_OFFLINE": "true",
            "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        }
    )
    return subprocess.run(
        [npm, "ls", "--all", "--package-lock-only", "--offline", "--ignore-scripts", "--json"],
        capture_output=True,
        check=False,
        cwd=directory,
        env=environment,
        text=True,
    )


def test_internal_markdown_links_resolve() -> None:
    broken = {
        str(path.relative_to(REPOSITORY_ROOT)): failures
        for path in _repository_files(MARKDOWN_ROOTS, {".md"})
        if (failures := _broken_markdown_links(path))
    }

    assert broken == {}


def test_presentations_are_frozen_and_markdown_is_authoritative() -> None:
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    architecture = (REPOSITORY_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    lesson_readme = (REPOSITORY_ROOT / "docs" / "lessons" / "README.md").read_text(encoding="utf-8")
    template = (REPOSITORY_ROOT / "docs" / "lessons" / "lesson-template.md").read_text(
        encoding="utf-8"
    )
    cah_024_story = (
        REPOSITORY_ROOT / "user-stories" / "cah-024-establish-workspace-boundary.md"
    ).read_text(encoding="utf-8")
    cah_024_lesson = (
        REPOSITORY_ROOT / "docs" / "lessons" / "cah-024-workspace-boundary.md"
    ).read_text(encoding="utf-8")
    cah_024_note = (
        REPOSITORY_ROOT
        / "user-stories"
        / "notes"
        / "2026-08-02-cah-024-workspace-boundary-planning.md"
    ).read_text(encoding="utf-8")
    cah_023_lesson = (
        REPOSITORY_ROOT / "docs" / "lessons" / "cah-023-openai-responses-adapter.md"
    ).read_text(encoding="utf-8")
    cah_025_story = (
        REPOSITORY_ROOT / "user-stories" / "cah-025-apply-magical-mission-ink-presentation.md"
    ).read_text(encoding="utf-8")
    cah_025_lesson = (
        REPOSITORY_ROOT / "docs" / "lessons" / "cah-025-magical-mission-ink-presentation.md"
    ).read_text(encoding="utf-8")
    agents_compact = " ".join(agents.split())
    architecture_compact = " ".join(architecture.split())
    lesson_readme_compact = " ".join(lesson_readme.split())
    cah_024_story_compact = " ".join(cah_024_story.split())
    cah_024_lesson_compact = " ".join(cah_024_lesson.split())
    cah_024_note_compact = " ".join(cah_024_note.split())
    cah_023_lesson_compact = " ".join(cah_023_lesson.split())
    cah_025_story_compact = " ".join(cah_025_story.split())
    cah_025_lesson_compact = " ".join(cah_025_lesson.split())

    assert "Markdown lessons are authoritative" in agents_compact
    assert "Retained presentation files are frozen historical artifacts" in agents_compact
    assert "Do not add or revise presentation files" in agents_compact
    assert "Every new written lesson includes a compact architecture" in agents_compact
    assert "Retained presentation files through CAH-022" in architecture_compact
    assert "Starting with CAH-023" in architecture_compact
    assert "No presentation is added or revised" in architecture_compact
    assert "Retained visual PowerPoint companions through CAH-022" in lesson_readme_compact
    assert "Starting with CAH-023" in lesson_readme_compact
    assert "Do not add or revise presentations" in lesson_readme_compact
    assert "do not add or revise presentation files while the freeze is active" in template
    assert "**Visual companion:** None" in cah_023_lesson_compact
    assert "**Visual companion:** None" in cah_024_lesson_compact
    assert "**Visual companion:** None" in cah_025_lesson_compact
    assert "No presentation is part of CAH-024" in cah_024_story_compact
    assert "no presentation is part of CAH-025" in cah_025_story_compact
    assert "one `WorkspaceBoundaryError`" in cah_024_lesson_compact
    assert "`ResolvedWorkspacePath`" in cah_024_lesson_compact
    assert "five stable error codes" in cah_024_lesson_compact
    assert "No presentation is planned evidence for CAH-024" in cah_024_note_compact

    lesson_decks = (REPOSITORY_ROOT / "docs" / "lessons" / "assets").glob("cah-*.pptx")
    deck_units = {int(path.name.split("-", maxsplit=2)[1]) for path in lesson_decks}
    assert all(unit < 23 for unit in deck_units)


def test_review_follow_up_requires_thread_resolution() -> None:
    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    agents_compact = " ".join(agents.split())

    assert (
        "Whenever a review comment is addressed, mark its inline review thread as resolved."
        in agents_compact
    )
    assert "verify that no unresolved actionable review thread remains" in agents_compact


def test_network_access_is_isolated_to_openai_adapter_and_runtime_guards() -> None:
    violations: list[str] = []
    for path in _repository_files(PRODUCTION_SOURCE_ROOTS, {".py", ".ts", ".tsx"}):
        if path.suffix == ".py":
            violations.extend(_python_network_violations(path))
        else:
            violations.extend(_typescript_network_violations(path))

    assert violations == []

    python_environment = os.environ.copy()
    python_environment["PYTHONPATH"] = str(PYTHON_NETWORK_GUARD)
    python_environment["PYTHONDONTWRITEBYTECODE"] = "1"
    python_probes = (
        "import socket; socket.create_connection(('127.0.0.1', 9), timeout=0.01)",
        "import socket; socket.socket.sendto(None, b'x', ('127.0.0.1', 9))",
        "import socket; socket.gethostbyname('localhost')",
    )
    for probe in python_probes:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            check=False,
            env=python_environment,
            text=True,
        )
        assert result.returncode != 0
        assert "Network access is disabled by ./scripts/check" in result.stderr

    node = shutil.which("node")
    assert node is not None
    node_environment = os.environ.copy()
    node_environment["NODE_OPTIONS"] = f'--import="{NODE_NETWORK_GUARD}"'
    node_probes = (
        "await fetch('http://127.0.0.1:9')",
        "import {lookup} from 'node:dns'; lookup('example.test', () => {})",
        "import {lookup} from 'node:dns/promises'; await lookup('example.test')",
    )
    for probe in node_probes:
        result = subprocess.run(
            [node, "--input-type=module", "--eval", probe],
            capture_output=True,
            check=False,
            env=node_environment,
            text=True,
        )
        assert result.returncode != 0
        assert "Network access is disabled by ./scripts/check" in result.stderr

    local_lookup = subprocess.run(
        [
            node,
            "--input-type=module",
            "--eval",
            "import {lookup} from 'node:dns/promises'; "
            "const result = await lookup('localhost'); console.log(result.address)",
        ],
        capture_output=True,
        check=False,
        env=node_environment,
        text=True,
    )
    assert local_lookup.returncode == 0
    assert local_lookup.stdout.strip() == "127.0.0.1"


def test_tui_lockfile_matches_package_contract_and_complete_graph(tmp_path: Path) -> None:
    package_path = TUI_ROOT / "package.json"
    lock_path = TUI_ROOT / "package-lock.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    locked_package = lock["packages"][""]

    assert lock["lockfileVersion"] == 3
    for field in ("name", "version", "dependencies", "devDependencies", "engines"):
        assert locked_package[field] == package[field]

    valid_directory = tmp_path / "valid"
    valid_directory.mkdir()
    shutil.copy2(package_path, valid_directory / package_path.name)
    shutil.copy2(lock_path, valid_directory / lock_path.name)
    result = _run_npm_lock_graph_check(valid_directory)

    assert result.returncode == 0, result.stderr
    assert (valid_directory / package_path.name).read_bytes() == package_path.read_bytes()
    assert (valid_directory / lock_path.name).read_bytes() == lock_path.read_bytes()
    assert not (valid_directory / "node_modules").exists()

    broken_directory = tmp_path / "missing-transitive"
    broken_directory.mkdir()
    shutil.copy2(package_path, broken_directory / package_path.name)
    broken_lock = json.loads(lock_path.read_text(encoding="utf-8"))
    removed = broken_lock["packages"].pop("node_modules/@alcalzone/ansi-tokenize")
    assert removed["version"] == "0.3.0"
    (broken_directory / lock_path.name).write_text(
        f"{json.dumps(broken_lock, indent=2)}\n", encoding="utf-8"
    )

    broken_result = _run_npm_lock_graph_check(broken_directory)
    broken_report = json.loads(broken_result.stdout)
    assert broken_result.returncode != 0
    assert any("@alcalzone/ansi-tokenize" in problem for problem in broken_report["problems"])
    assert not (broken_directory / "node_modules").exists()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "import socket\nsocket.create_connection(('example.test', 443))\n",
            "network module 'socket'",
        ),
        ("client = __import__('httpx')\n", "dynamic network import 'httpx'"),
        ("import openai\n", "network module 'openai'"),
        (
            "import importlib\nclient = importlib.import_module('openai')\n",
            "dynamic network import 'openai'",
        ),
    ],
)
def test_python_network_policy_rejects_synthetic_source(
    tmp_path: Path, source: str, expected: str
) -> None:
    path = tmp_path / "network_client.py"
    path.write_text(source, encoding="utf-8")

    assert expected in _python_network_violations(path)[0]


def test_python_network_policy_allows_only_openai_sdk_in_concrete_adapter(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / "openai_responses.py"
    adapter.write_text(
        "from openai import AsyncOpenAI, DefaultAsyncHttpxClient\n",
        encoding="utf-8",
    )
    provider_neutral = tmp_path / "provider_session.py"
    provider_neutral.write_text("from openai import AsyncOpenAI\n", encoding="utf-8")

    assert _python_network_violations(adapter, openai_adapter_source=adapter) == []
    assert (
        "network module 'openai'"
        in _python_network_violations(
            provider_neutral,
            openai_adapter_source=adapter,
        )[0]
    )


def test_python_network_policy_keeps_direct_network_modules_out_of_openai_adapter(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / "openai_responses.py"
    adapter.write_text("import httpx\n", encoding="utf-8")

    assert (
        "network module 'httpx'"
        in _python_network_violations(
            adapter,
            openai_adapter_source=adapter,
        )[0]
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import 'node:https';\n", "network module 'node:https'"),
        ("const response = await fetch('https://example.test');\n", "fetch"),
        ("const response = await globalThis.fetch('https://example.test');\n", "fetch"),
        ("const response = await window.fetch('https://example.test');\n", "fetch"),
        ("const response = await globalThis?.fetch?.('https://example.test');\n", "fetch"),
        ("const response = await window?.['fetch']?.('https://example.test');\n", "fetch"),
    ],
)
def test_typescript_network_policy_rejects_synthetic_source(
    tmp_path: Path, source: str, expected: str
) -> None:
    path = tmp_path / "network-client.ts"
    path.write_text(source, encoding="utf-8")

    assert expected in _typescript_network_violations(path)[0]


@pytest.mark.parametrize(
    "source",
    [
        "const response = await client.fetch('/local-cache');\n",
        "const response = await client?.fetch?.('/local-cache');\n",
        "const response = await client['fetch']('/local-cache');\n",
    ],
)
def test_typescript_network_policy_does_not_treat_arbitrary_members_as_global_fetch(
    tmp_path: Path, source: str
) -> None:
    path = tmp_path / "local-client.ts"
    path.write_text(source, encoding="utf-8")

    assert _typescript_network_violations(path) == []


def test_repository_file_discovery_respects_git_ignore_rules(tmp_path: Path) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run([git, "init", "--quiet"], cwd=tmp_path, check=True)

    (tmp_path / ".gitignore").write_text("venv/\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("[New guide](docs/new.md)\n", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "new.md").write_text("# New guide\n", encoding="utf-8")
    ignored = tmp_path / "venv"
    ignored.mkdir()
    (ignored / "bad.md").write_text("[Broken](missing.md)\n", encoding="utf-8")
    subprocess.run([git, "add", ".gitignore", "README.md"], cwd=tmp_path, check=True)

    discovered = _repository_files((tmp_path,), {".md"}, repository_root=tmp_path)
    relative_paths = {path.relative_to(tmp_path).as_posix() for path in discovered}
    broken = {
        path.relative_to(tmp_path).as_posix(): failures
        for path in discovered
        if (failures := _broken_markdown_links(path, repository_root=tmp_path))
    }

    assert relative_paths == {"README.md", "docs/new.md"}
    assert broken == {}


def test_root_dev_environment_is_ignored_and_cannot_be_tracked() -> None:
    git = shutil.which("git")
    assert git is not None

    ignored = subprocess.run(
        [git, "check-ignore", "--quiet", "--no-index", "--", "dev.env"],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    tracked = subprocess.run(
        [git, "ls-files", "--error-unmatch", "--", "dev.env"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert ignored.returncode == 0
    assert tracked.returncode != 0


def test_markdown_policy_rejects_synthetic_missing_target_and_heading(tmp_path: Path) -> None:
    guide = tmp_path / "guide.md"
    guide.write_text(
        "# Guide\n\n"
        "[External links are intentionally offline](https://example.test)\n"
        "[Missing](absent.md)\n"
        "[Bad heading](#absent)\n",
        encoding="utf-8",
    )

    assert _broken_markdown_links(guide, repository_root=tmp_path) == [
        "absent.md targets a missing path",
        "#absent targets a missing heading",
    ]
