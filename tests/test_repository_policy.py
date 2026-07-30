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
MARKDOWN_ROOTS = (REPOSITORY_ROOT,)
PRODUCTION_SOURCE_ROOTS = (
    REPOSITORY_ROOT / "src" / "code_assist_harness",
    REPOSITORY_ROOT / "tui" / "src",
)
PYTHON_NETWORK_GUARD = REPOSITORY_ROOT / "tests" / "network_guard"
NODE_NETWORK_GUARD = REPOSITORY_ROOT / "scripts" / "deny-network.mjs"
IGNORED_DIRECTORY_NAMES = frozenset({".git", ".venv", "coverage", "dist", "node_modules"})

MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*]\(([^)]+)\)|!\[[^]]*]\(([^)]+)\)")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
PYTHON_NETWORK_MODULES = frozenset(
    {
        "aiohttp",
        "http.client",
        "httpx",
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
TYPESCRIPT_NETWORK_CALLS = (
    ("fetch", re.compile(r"(?<![\w.])fetch\s*\(")),
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


def _files_under(roots: Iterable[Path], suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        candidates = (root,) if root.is_file() else root.rglob("*")
        files.extend(
            path
            for path in candidates
            if path.is_file()
            and path.suffix in suffixes
            and not IGNORED_DIRECTORY_NAMES.intersection(path.parts)
        )
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


def _python_network_violations(path: Path) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        imported_modules: list[str] = []
        if isinstance(node, ast.Import):
            imported_modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules = [node.module]
        for module in imported_modules:
            if _is_denied_python_module(module):
                violations.append(f"{path}:{node.lineno}: network module {module!r}")
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
        ):
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                module = node.args[0].value
                if _is_denied_python_module(module):
                    violations.append(f"{path}:{node.lineno}: dynamic network import {module!r}")
    return violations


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


def test_internal_markdown_links_resolve() -> None:
    broken = {
        str(path.relative_to(REPOSITORY_ROOT)): failures
        for path in _files_under(MARKDOWN_ROOTS, {".md"})
        if (failures := _broken_markdown_links(path))
    }

    assert broken == {}


def test_m0_has_static_and_runtime_network_guards() -> None:
    violations: list[str] = []
    for path in _files_under(PRODUCTION_SOURCE_ROOTS, {".py", ".ts", ".tsx"}):
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


def test_tui_lockfile_matches_direct_package_contract() -> None:
    package = json.loads((REPOSITORY_ROOT / "tui" / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((REPOSITORY_ROOT / "tui" / "package-lock.json").read_text(encoding="utf-8"))
    locked_package = lock["packages"][""]

    assert lock["lockfileVersion"] == 3
    for field in ("name", "version", "dependencies", "devDependencies", "engines"):
        assert locked_package[field] == package[field]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "import socket\nsocket.create_connection(('example.test', 443))\n",
            "network module 'socket'",
        ),
        ("client = __import__('httpx')\n", "dynamic network import 'httpx'"),
    ],
)
def test_python_network_policy_rejects_synthetic_source(
    tmp_path: Path, source: str, expected: str
) -> None:
    path = tmp_path / "network_client.py"
    path.write_text(source, encoding="utf-8")

    assert expected in _python_network_violations(path)[0]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import 'node:https';\n", "network module 'node:https'"),
        ("const response = await fetch('https://example.test');\n", "fetch"),
    ],
)
def test_typescript_network_policy_rejects_synthetic_source(
    tmp_path: Path, source: str, expected: str
) -> None:
    path = tmp_path / "network-client.ts"
    path.write_text(source, encoding="utf-8")

    assert expected in _typescript_network_violations(path)[0]


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
