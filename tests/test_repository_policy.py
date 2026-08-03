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
    agents_compact = " ".join(agents.split())
    architecture_compact = " ".join(architecture.split())
    lesson_readme_compact = " ".join(lesson_readme.split())
    cah_024_story_compact = " ".join(cah_024_story.split())
    cah_024_lesson_compact = " ".join(cah_024_lesson.split())
    cah_024_note_compact = " ".join(cah_024_note.split())
    cah_023_lesson_compact = " ".join(cah_023_lesson.split())

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
    assert "No presentation is part of CAH-024" in cah_024_story_compact
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


def test_m2_plans_are_reviewable_learning_units() -> None:
    story_lessons = {
        "cah-024-establish-workspace-boundary.md": "cah-024-workspace-boundary.md",
        "cah-025-discover-repository-instructions.md": "cah-025-repository-instructions.md",
        "cah-026-define-repository-read-contracts.md": "cah-026-repository-read-policy.md",
        "cah-027-list-files-and-stat-path.md": "cah-027-list-files-and-stat-path.md",
        "cah-028-read-bounded-text-file.md": "cah-028-bounded-text-file.md",
        "cah-029-search-repository-text.md": "cah-029-literal-text-search.md",
        "cah-030-build-budgeted-context.md": "cah-030-budgeted-context.md",
        "cah-031-register-read-tools.md": "cah-031-read-tool-registry.md",
        "cah-032-define-provider-tool-contract.md": "cah-032-provider-tool-contract.md",
        "cah-033-stage-and-validate-tool-aware-response.md": (
            "cah-033-tool-aware-response-admission.md"
        ),
        "cah-034-run-one-read-tool-round-trip.md": "cah-034-one-read-tool-round-trip.md",
        "cah-035-run-bounded-agent-loop.md": "cah-035-bounded-agent-loop.md",
        "cah-036-map-openai-tool-calls.md": "cah-036-openai-tool-calls.md",
        "cah-037-prove-read-only-assistant.md": "cah-037-read-only-assistant-evaluation.md",
    }
    story_headings = (
        "## Single responsibility",
        "## Scope",
        "## Locked contract",
        "## Reviewability budget",
        "## Acceptance criteria",
        "## Acceptance-to-test matrix",
        "## Validation",
        "## Documentation impact",
        "## Exclusions",
        "## Definition of done",
        "## Planned evidence",
        "## Deferred work",
    )
    lesson_headings = (
        "## Quick summary",
        "## Learning objectives",
        "## Why this unit matters",
        "## Junior engineer foundation",
        "## Key concepts",
        "## Architecture and design",
        "## Practical walkthrough",
        "## Implementation code samples",
        "## Failure scenarios to study",
        "## Production expansion",
        "### Local design versus production design",
        "### Trade-offs and graduation signals",
        "## Practical exercises",
        "## Key takeaways",
        "## Glossary",
        "## Further reading",
    )

    for story_name, lesson_name in story_lessons.items():
        story = (REPOSITORY_ROOT / "user-stories" / story_name).read_text(encoding="utf-8")
        lesson = (REPOSITORY_ROOT / "docs" / "lessons" / lesson_name).read_text(encoding="utf-8")

        story_status_match = re.search(r"^- \*\*Status:\*\* (.+)$", story, re.MULTILINE)
        lesson_status_match = re.search(r"^- \*\*Lesson status:\*\* (.+)$", lesson, re.MULTILINE)
        implementation_status_match = re.search(
            r"^- \*\*Implementation status:\*\* (.+)$", lesson, re.MULTILINE
        )
        assert story_status_match is not None
        assert lesson_status_match is not None
        assert implementation_status_match is not None

        story_status = story_status_match.group(1)
        lesson_status = lesson_status_match.group(1)
        implementation_status = implementation_status_match.group(1)
        expected_statuses = {
            "Planned": ("Planned", ("Planned",)),
            "In progress": ("Implementation companion", ("In progress", "Partially implemented")),
            "Blocked": ("Implementation companion - blocked", ("Blocked", "In progress")),
            "Done": ("Verified against implementation", ("Done", "Implemented")),
        }
        assert story_status in expected_statuses
        expected_lesson_status, implementation_prefixes = expected_statuses[story_status]
        assert lesson_status == expected_lesson_status
        assert implementation_status.startswith(implementation_prefixes)

        assert "**Learning emphasis:**" in story
        assert "**Review focus:**" in story
        assert "**Estimated production-code churn:**" in story
        assert "**Delivered production-code churn:**" in story
        assert "600" in story
        assert all(heading in story for heading in story_headings)

        assert "**Learning emphasis:**" in lesson
        assert "**Review focus:**" in lesson
        assert "**Visual companion:** None" in lesson
        assert "```text" in lesson
        assert all(heading in lesson for heading in lesson_headings)

    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template = (REPOSITORY_ROOT / "user-stories" / "story-template.md").read_text(encoding="utf-8")
    agents_compact = " ".join(agents.split())
    assert "core learning units" in agents_compact
    assert "roughly 600 or fewer changed production lines per story" in agents_compact
    assert "## Acceptance-to-test matrix" in template
    assert "## Definition of done" in template


def test_m2_search_and_scoped_instruction_contracts_stay_coherent() -> None:
    story_names = (
        "cah-025-discover-repository-instructions.md",
        "cah-026-define-repository-read-contracts.md",
        "cah-029-search-repository-text.md",
        "cah-030-build-budgeted-context.md",
        "cah-031-register-read-tools.md",
        "cah-032-define-provider-tool-contract.md",
        "cah-033-stage-and-validate-tool-aware-response.md",
        "cah-034-run-one-read-tool-round-trip.md",
        "cah-035-run-bounded-agent-loop.md",
        "cah-036-map-openai-tool-calls.md",
        "cah-037-prove-read-only-assistant.md",
    )
    stories = {
        name: " ".join(
            (REPOSITORY_ROOT / "user-stories" / name).read_text(encoding="utf-8").split()
        )
        for name in story_names
    }
    lesson_names = (
        "cah-026-repository-read-policy.md",
        "cah-030-budgeted-context.md",
        "cah-031-read-tool-registry.md",
        "cah-032-provider-tool-contract.md",
        "cah-033-tool-aware-response-admission.md",
        "cah-034-one-read-tool-round-trip.md",
        "cah-035-bounded-agent-loop.md",
        "cah-036-openai-tool-calls.md",
        "cah-037-read-only-assistant-evaluation.md",
    )
    lessons = {
        name: " ".join(
            (REPOSITORY_ROOT / "docs" / "lessons" / name).read_text(encoding="utf-8").split()
        )
        for name in lesson_names
    }
    conceptual_names = (
        "agent-loop.md",
        "architecture.md",
        "context-engineering.md",
        "evaluation.md",
        "safety-model.md",
        "tool-system.md",
    )
    conceptual = {
        name: " ".join((REPOSITORY_ROOT / "docs" / name).read_text(encoding="utf-8").split())
        for name in conceptual_names
    }

    instruction = stories["cah-025-discover-repository-instructions.md"]
    assert "**Dependencies:** CAH-024 and CAH-026" in instruction
    assert "pure lexical path admission and non-overridable hard-deny classifier" in instruction
    assert "deliberately skipping GitIgnoreSpec" in instruction
    assert "canonical candidate-owner directory as `applies_to`" in instruction
    assert '`source="shared/rules.md"`, `applies_to="pkg"`' in instruction
    assert "same canonical target referenced by different owners produces distinct" in instruction
    assert (
        "reruns containment plus CAH-026 hard denial immediately before each bounded read"
        in instruction
    )
    assert "Before any `WorkspaceBoundary` or filesystem call" in instruction
    assert (
        "rejects non-string values, lone surrogates, NUL, empty/absolute paths, and every "
        "`..` component" in instruction
    )
    assert "never loads an ancestor `.gitignore` as policy input" in instruction
    assert "bytes are read only as instruction content" in instruction
    assert "binding or byte limit" in instruction
    assert "catch only its fixed `RepositoryPathSyntaxError`" in instruction
    assert "map that rejection to `invalid_instruction_scope`" in instruction
    assert "a parity corpus matches CAH-024's established string grammar" in instruction

    read_policy = stories["cah-026-define-repository-read-contracts.md"]
    assert "`normalize_repository_path_components(value: str) -> tuple[str, ...]`" in read_policy
    assert "`is_hard_denied_path(components)`" in read_policy
    assert "single implementation of this table" in read_policy
    assert "classifier neither resolves paths nor reveals which entry matched" in read_policy
    assert "CAH-025 instruction discovery both call these pure primitives" in read_policy
    assert "`RepositoryPathSyntaxError` is the helper's only failure" in read_policy
    assert "exact fixed message `Repository path syntax is invalid.`" in read_policy
    assert "maps it to `invalid_repository_path`" in read_policy
    assert "CAH-025 catches the same value" in read_policy
    assert "without Unicode normalization" in read_policy
    assert "CAH-024 lexical parity" in read_policy
    assert "the full read policy consumes both primitives" in read_policy
    assert "CAH-025 owns the later control-plane consumer evidence" in read_policy
    assert "CAH-025/read-policy integration tests" not in read_policy

    policy_lesson = lessons["cah-026-repository-read-policy.md"]
    policy_concept = conceptual["safety-model.md"]
    runtime_rules = " ".join((REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    for document in (read_policy, policy_lesson, policy_concept):
        assert ".gitignore" in document
        assert "canonical source" in document
        assert "candidate owner" in document or "candidate-owner" in document
        assert "repository_policy_invalid" in document
        assert "internal symlink" in document
    assert "`WorkspaceBoundary.resolve_existing` before content I/O" in read_policy
    assert "canonical hard denial" in read_policy
    assert "rechecks regular-file type and size" in read_policy
    assert "never enter the cache or consume count or byte budget" in read_policy
    assert "pre-read size failures perform no policy-source content read" in read_policy
    assert "one bounded, uncommitted policy candidate" in read_policy
    assert "actually absent directory entry is normal" in read_policy
    assert "Pre-read-rejected sources are not opened, cached, or charged" in policy_lesson
    assert "budget commit occur atomically only after text validation" in policy_lesson
    assert "no policy failure is followed by requested-content I/O" in policy_lesson
    assert "WorkspaceBoundary" in policy_concept
    assert "canonical hard denial" in policy_concept
    assert "re-resolve" in policy_concept and "before" in policy_concept
    assert "not opened, cached, or charged" in policy_concept
    assert "without reading requested content" in policy_concept

    instruction_lesson = (
        REPOSITORY_ROOT / "docs" / "lessons" / "cah-025-repository-instructions.md"
    ).read_text(encoding="utf-8")
    read_policy_lesson = (
        REPOSITORY_ROOT / "docs" / "lessons" / "cah-026-repository-read-policy.md"
    ).read_text(encoding="utf-8")
    assert ".relative_path.parts" in instruction_lesson
    assert ".relative_path.parts" in read_policy_lesson
    assert ".components" not in instruction_lesson
    assert ".components" not in read_policy_lesson

    story_index = " ".join(
        (REPOSITORY_ROOT / "user-stories" / "README.md").read_text(encoding="utf-8").split()
    )
    assert story_index.index("CAH-026: Define repository read contracts") < story_index.index(
        "CAH-025: Discover scoped repository instructions"
    )
    lesson_index = " ".join(
        (REPOSITORY_ROOT / "docs" / "lessons" / "README.md").read_text(encoding="utf-8").split()
    )
    assert lesson_index.index("CAH-026") < lesson_index.index("CAH-025")

    planning_note = " ".join(
        (
            REPOSITORY_ROOT
            / "user-stories"
            / "notes"
            / "2026-08-03-m2-read-only-assistant-planning.md"
        )
        .read_text(encoding="utf-8")
        .split()
    )
    assert (
        "CAH-030 - Build budgeted repository context | E3 | Core | Selection priority, "
        "provenance, and omission evidence | 475-600" in planning_note
    )
    assert "present `.gitignore`" in planning_note
    assert "candidate-owner" in planning_note and "canonical source" in planning_note
    assert "repository_policy_invalid" in planning_note
    assert "Pre-read-rejected policy sources" in planning_note
    assert "are not opened, cached, or charged" in planning_note
    assert "bounded uncommitted candidate" in planning_note
    assert "never exposed, cached, or charged" in planning_note
    assert "pair-preserving" in planning_note
    assert "unknown-tool lookup" in planning_note
    assert "duplicate" in planning_note and "invalid_read_tool_input" in planning_note
    assert "instruction_scopes" in planning_note
    assert "first-occurrence search-match owner" in planning_note
    assert "never becomes a search root" in planning_note
    assert "before replay" in planning_note

    assert "use one `cooperate_then_guard` seam" in runtime_rules
    assert "`await asyncio.sleep(0)` outside every lock" in runtime_rules
    assert (
        "before dispatch, after dispatch, after instruction discovery, after context merge"
        in runtime_rules
    )
    assert (
        "Keep results, context, history, and the bounded request as local candidates"
        in runtime_rules
    )
    assert "with no observer/gate installed, queue cancellation on the same loop" in runtime_rules
    assert "awaited `asyncio.Event` hook" in runtime_rules

    search = stories["cah-029-search-repository-text.md"]
    assert "`candidate_files`" not in search
    assert "one bounded listing" in search
    assert "499/500/501 admitted listing entries" in search
    assert "`listing` or `candidate_bytes` reasons" in search
    search_lesson = " ".join(
        (REPOSITORY_ROOT / "docs" / "lessons" / "cah-029-literal-text-search.md")
        .read_text(encoding="utf-8")
        .split()
    )
    assert "if listing.truncated:" in search_lesson
    assert 'limit_reasons.add("listing")' in search_lesson
    assert "for entry in listing.entries:" in search_lesson
    assert 'if entry.kind != "file":' in search_lesson

    context = stories["cah-030-build-budgeted-context.md"]
    assert "**Estimated production-code churn:** 475-600 changed lines." in context
    assert "pure, atomic merge" in context
    assert "without evicting or rewriting prior context" in context
    assert "canonical `applies_to` directory" in context
    assert "16 distinct instruction bindings, 24 total items, and 96 KiB" in context
    assert "topology-correct positions inside the instruction block" in context
    assert "an ancestor created after its descendant was admitted" in context
    assert "bundle for `request.scope` first" in context
    assert "bundle for every distinct canonical focus path" in context
    assert (
        "`SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)`"
        in context
    )
    assert "search-result paths never become search roots" in context
    assert "every first-occurrence canonical owner directory of a search match" in context
    assert "complete scope-plus-focus-plus-search-owner instruction union" in context
    assert (
        "no search excerpt becomes visible before its owner's applicable instruction chain"
        in context
    )
    assert "Search-owner discovery never launches another search" in context
    assert "It never derives applicability from the source path" in context
    assert "same source under a different `applies_to` is an unseen valid binding" in context

    context_lesson = lessons["cah-030-budgeted-context.md"]
    assert "Every search keeps the supplied scope as its root" in context_lesson
    assert "focus or match cannot silently widen search" in context_lesson
    assert "A match owner does trigger instruction discovery" in context_lesson
    assert "search-match owner" in context_lesson
    assert "instruction union" in context_lesson
    assert "before any focus item or search excerpt" in context_lesson

    registry = stories["cah-031-register-read-tools.md"]
    assert "`instruction_scopes(validated_input, validated_result)` extractor" in registry
    assert "A known native or registry failure carries no instruction scopes" in registry
    assert "validated `request.path` byte-for-byte" in registry
    assert "`list_files`: for each returned entry" in registry
    assert "`stat_path`: append the canonical result path" in registry
    assert "`read_file`: append the canonical result file's parent directory" in registry
    assert "`search_text`: append each canonical match file's parent directory" in registry
    assert "at most 501 pre-deduplication candidates for `list_files`" in registry
    assert "201 for `search_text`" in registry
    assert (
        "parsing, walking, or otherwise deriving authority from `output_json` is prohibited"
        in registry
    )

    registry_lesson = lessons["cah-031-read-tool-registry.md"]
    assert "ordered `instruction_scopes`" in registry_lesson
    assert "requested path first" in registry_lesson
    assert "directory entry itself or file entry parent" in registry_lesson
    assert "append every match file parent" in registry_lesson
    assert "501 candidates for listing, 201 for search" in registry_lesson
    assert "no partial tuple" in registry_lesson

    provider = stories["cah-032-define-provider-tool-contract.md"]
    assert "Every `ProviderRequest` is an immutable snapshot" in provider
    assert "successive request from CAH-030's atomically enriched package" in provider
    assert "local `ReadToolSuccess.instruction_scopes` never enter" in provider
    assert "target_scope" not in provider
    assert "canonical candidate-owner `applies_to`" in provider
    assert "never derived from a possibly symlink-resolved source" in provider
    assert "already JSON-decoded, duplicate-free object" in provider
    assert "CAH-034's pair-preserving decoder" in provider
    assert "unparsed JSON argument string" in provider

    provider_lesson = lessons["cah-032-provider-tool-contract.md"]
    assert "raw arguments" in provider_lesson
    assert "pair preservation" in provider_lesson
    assert "normal dictionary has already forgotten earlier duplicate values" in provider_lesson
    assert "local `instruction_scopes`" in provider_lesson
    assert "target_scope" not in provider_lesson

    staged_turn = stories["cah-033-stage-and-validate-tool-aware-response.md"]
    assert (
        "preserves CAH-032's bounded `arguments_json` byte-for-byte and does not parse it"
        in staged_turn
    )
    assert "CAH-034 is the sole owner of pair-preserving decode" in staged_turn
    assert "before its exact-key gate, Pydantic validation, or dispatch" in staged_turn
    staged_turn_lesson = lessons["cah-033-tool-aware-response-admission.md"]
    assert (
        "argument string byte-for-byte without parsing or duplicate detection" in staged_turn_lesson
    )
    assert "deferred to CAH-034" in staged_turn_lesson

    round_trip = stories["cah-034-run-one-read-tool-round-trip.md"]
    assert "post-dispatch" in round_trip and "deadline check" in round_trip
    assert "seam runs after every scope's discovery and merge" in round_trip
    assert "pre-start guard runs immediately before the follow-up" in round_trip
    assert "CAH-025" in round_trip and "CAH-030" in round_trip
    assert "exact registry lookup, duplicate-aware JSON-object decoding" in round_trip
    assert "consumes preserved object pairs" in round_trip
    assert "repeated decoded member name at any nesting depth" in round_trip
    assert "Equality is exact after JSON escape decoding" in round_trip
    assert "no case folding or Unicode normalization" in round_trip
    assert "unknown lookup wins before decoding" in round_trip
    assert "same-value/conflicting/reversed duplicate names" in round_trip
    assert "escape-equivalent `path` names" in round_trip
    assert "nested duplicates" in round_trip
    assert "maps to `invalid_read_tool_input`" in round_trip
    assert "duplicate arguments run no key gate, Pydantic validation, dispatch" in round_trip
    assert "charged call and fixed error must replay" in round_trip
    assert "one charged observation, unchanged context, exact call/error history" in round_trip
    admitted_call = round_trip.index("CAH-033 atomically returns the first accepted call")
    charged_call = round_trip.index("charge the one observed tool call")
    assert admitted_call < charged_call
    assert round_trip.index("charge the one observed tool call") < round_trip.index(
        "exact registry lookup, duplicate-aware JSON-object decoding"
    )
    assert round_trip.index(
        "exact registry lookup, duplicate-aware JSON-object decoding"
    ) < round_trip.index("CAH-032's exact model-facing required-key gate")
    assert round_trip.index("CAH-032's exact model-facing required-key gate") < round_trip.index(
        "native Pydantic input validation"
    )
    assert round_trip.index("native Pydantic input validation") < round_trip.index(
        "synchronous dispatch"
    )
    assert "ordered, exact-deduplicated local `instruction_scopes` tuple" in round_trip
    assert "owner directory for every model-visible returned path" in round_trip
    assert "process each scope in order" in round_trip
    assert "`await asyncio.sleep(0)` outside every lock" in round_trip
    for checkpoint in (
        '"before_dispatch"',
        '"after_dispatch"',
        '"after_discovery"',
        '"after_merge"',
        '"before_provider_start"',
    ):
        assert checkpoint in round_trip
    assert "remain local candidates" in round_trip
    assert "production-mode seam test installs no observer/gate" in round_trip
    assert "deleting the unconditional outside-lock `asyncio.sleep(0)` must fail" in round_trip

    round_trip_lesson = lessons["cah-034-one-read-tool-round-trip.md"]
    assert "lookup name -> pair-preserving recursive decode" in round_trip_lesson
    assert "repeated decoded name at any depth" in round_trip_lesson
    assert "without normalization or case folding" in round_trip_lesson
    assert "unknown-tool lookup still wins first" in round_trip_lesson
    assert "For each scope in order" in round_trip_lesson
    assert (
        "All scope candidates, the result, and the complete context remain local"
        in round_trip_lesson
    )

    agent_loop = stories["cah-035-run-bounded-agent-loop.md"]
    assert "accumulate instruction items" in agent_loop
    assert "every model-visible returned-path owner before each result replay" in agent_loop
    assert "duplicate-aware JSON-object decode" in agent_loop
    assert "later loop iterations reuse this decoder" in agent_loop
    assert "validated request path first" in agent_loop
    assert "every exact-deduplicated owner of a model-visible returned path" in agent_loop
    assert "guards run after every discovery, after every merge" in agent_loop
    assert (
        "reuses—not wraps or reimplements—CAH-034's `cooperate_then_guard(checkpoint)`"
        in agent_loop
    )
    assert "unconditionally yields with `await asyncio.sleep(0)` outside locks" in agent_loop
    assert "same source under another owner remains a distinct charged binding" in agent_loop

    agent_loop_lesson = lessons["cah-035-bounded-agent-loop.md"]
    assert (
        "Every iteration calls CAH-034's one pair-preserving recursive decoder" in agent_loop_lesson
    )
    assert (
        "requested path first, then every exact-deduplicated returned-path owner"
        in agent_loop_lesson
    )
    assert "discover and merge all scopes before replay" in agent_loop_lesson
    assert "YIELD/GUARD -> for each instruction_scope" in agent_loop_lesson

    adapter = stories["cah-036-map-openai-tool-calls.md"]
    assert "exactly `source`, `applies_to`, and `content`" in adapter
    assert "one sibling never overrides another" in adapter
    assert "canonical candidate-owner directory" in adapter
    assert "copied without derivation" in adapter
    assert "preserved byte-for-byte" in adapter
    assert "completed argument object with repeated member names" in adapter
    assert "must not decode it into a last-value-wins dictionary" in adapter
    assert "CAH-034's pair-preserving decoder owns duplicate rejection" in adapter

    adapter_lesson = lessons["cah-036-openai-tool-calls.md"]
    assert "byte-exact function-call text forwarded without parsing" in adapter_lesson
    assert "duplicate-member collapse" in adapter_lesson
    assert "never calls a JSON decoder on function-call arguments" in adapter_lesson

    evaluation = stories["cah-037-prove-read-only-assistant.md"]
    assert '`read_file` with `path="pkg/file.py"`' in evaluation
    assert 'next request containing the binding `source="shared/rules.md"`' in evaluation
    assert '`applies_to="pkg"`' in evaluation
    assert "broad `list_files` or `search_text` result is not replayed until" in evaluation
    assert "every owner bundle is discovered, folded, budgeted, and guarded" in evaluation
    assert "complete result/context transaction fails" in evaluation
    assert "duplicate-aware decoder as `invalid_read_tool_input`" in evaluation
    assert "conflicting and escape-equivalent `path` names" in evaluation
    assert "zero key-gate, Pydantic, native read" in evaluation
    assert "one charged observation" in evaluation
    assert "exact call/error replay in a follow-up against unchanged context" in evaluation
    assert (
        '`SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`'
        in evaluation
    )
    assert '`source="shared/rules.md"` with `applies_to="pkg"`' in evaluation
    assert "hard-denied instruction target" in evaluation
    assert "denied target is never read and yields no partial package" in evaluation
    assert "Named `asyncio.Event` gates" in evaluation
    assert "`before_dispatch`" in evaluation
    assert "zero dispatch at the first gate" in evaluation
    assert "next provider-start count remains zero" in evaluation

    evaluation_lesson = lessons["cah-037-read-only-assistant-evaluation.md"]
    evaluation_lesson_lower = evaluation_lesson.lower()
    assert "broad list/search" in evaluation_lesson_lower
    assert "instruction" in evaluation_lesson_lower and "before replay" in evaluation_lesson_lower
    assert "duplicate" in evaluation_lesson_lower and "zero dispatch" in evaluation_lesson_lower

    agent_loop_doc = conceptual["agent-loop.md"]
    agent_loop_doc_lower = agent_loop_doc.lower()
    assert "pair-preserving" in agent_loop_doc_lower
    assert "unknown-tool lookup" in agent_loop_doc_lower
    assert "instruction_scopes" in agent_loop_doc_lower
    assert "after every discovery" in agent_loop_doc_lower
    assert "after every merge" in agent_loop_doc_lower

    architecture = conceptual["architecture.md"]
    assert "duplicate-aware" in architecture
    assert "instruction_scopes" in architecture
    assert "every model-visible returned path" in architecture

    context_engineering = conceptual["context-engineering.md"]
    assert "first-occurrence search-match owner" in context_engineering
    assert "never become inferred search roots" in context_engineering
    assert "before result replay" in context_engineering

    tool_system = conceptual["tool-system.md"]
    assert "instruction_scopes" in tool_system
    assert "501" in tool_system and "201" in tool_system
    assert "pair-preserving" in tool_system
    assert "unknown-tool lookup" in tool_system

    evaluation_doc = conceptual["evaluation.md"].lower()
    assert "broad list/search" in evaluation_doc
    assert "duplicate-member" in evaluation_doc
    assert "zero dispatch" in evaluation_doc


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
