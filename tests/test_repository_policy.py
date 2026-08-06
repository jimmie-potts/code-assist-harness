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


def _unclosed_markdown_fence(markdown: str) -> int | None:
    """Return the opening line of an unclosed Markdown code fence, if any."""
    active_character: str | None = None
    active_length = 0
    opening_line = 0
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        match = re.match(r"(`{3,}|~{3,})(.*)$", line.lstrip())
        if match is None:
            continue
        marker, remainder = match.groups()
        if active_character is None:
            active_character = marker[0]
            active_length = len(marker)
            opening_line = line_number
            continue
        if marker[0] == active_character and len(marker) >= active_length and not remainder.strip():
            active_character = None
            active_length = 0
            opening_line = 0
    return opening_line or None


def _pre_review_audit_rows(markdown: str) -> dict[str, str]:
    """Return the named evidence rows from one story's pre-review audit table."""
    marker = "## Pre-review adversarial audit"
    if marker not in markdown:
        return {}
    section = markdown.split(marker, maxsplit=1)[1]
    section = section.split("\n## ", maxsplit=1)[0]
    rows: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"Audit", "---"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


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


def test_markdown_code_fences_are_balanced() -> None:
    unclosed = {
        str(path.relative_to(REPOSITORY_ROOT)): opening_line
        for path in _repository_files(MARKDOWN_ROOTS, {".md"})
        if (opening_line := _unclosed_markdown_fence(path.read_text(encoding="utf-8"))) is not None
    }

    assert unclosed == {}


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


def test_pre_review_adversarial_audit_prompts_remain_durable() -> None:
    agents = " ".join((REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8").split())
    story_template = " ".join(
        (REPOSITORY_ROOT / "user-stories" / "story-template.md").read_text(encoding="utf-8").split()
    )
    lesson_template = " ".join(
        (REPOSITORY_ROOT / "docs" / "lessons" / "lesson-template.md")
        .read_text(encoding="utf-8")
        .split()
    )
    review_record = " ".join(
        (REPOSITORY_ROOT / "user-stories" / "notes" / "2026-08-03-pr-28-review-learnings.md")
        .read_text(encoding="utf-8")
        .split()
    )

    assert "close each affected contract neighborhood" in agents
    assert "upstream producers through every carrier and consumer" in agents
    assert "composition roots, evaluation wiring, control-plane inputs" in agents
    assert "empty/error/cancellation paths" in agents
    assert "Run three independent review lenses" in agents
    assert "Trace concrete factory inputs, carrier fields, return types" in agents
    assert "implementable without a reverse dependency" in agents
    assert "advertised tuple, validation catalog, and guarded executor entry" in agents
    assert "one captured identity" in agents
    assert "framework- or SDK-generated snapshots" in agents
    assert "per value, per request snapshot, per session, or cumulative" in agents
    assert "Trace every byte/item bound back to the first producer" in agents
    assert "mapped-empty observations use an iterative pump" in agents
    assert (
        "every async checkpoint/transition an exact continue/stop return or private sentinel"
        in (agents)
    )
    assert "immutable installed-state carrier construction, final clock read" in agents
    assert "one non-failing pointer commit" in agents
    assert "uninstalled/intermediate/terminal cleanup" in agents
    assert "exact service/catalog/handler identities and explicit runtime profiles" in agents
    assert "default runtime path or opaque identifier changes" in agents
    assert "render the changed Markdown neighborhood" in agents
    assert "repeat the neighborhood audit" in agents
    assert "land a skeleton milestone map separately" in agents

    assert "**Planning PR scope:**" in story_template
    assert "## Pre-review adversarial audit" in story_template
    for audit_prompt in (
        "Identity ledger",
        "End-to-end contract",
        "Failure and atomicity",
        "Reachable boundaries",
        "Closed grammar and cardinality",
        "Real producer and repeated snapshots",
        "Failure vocabulary and precedence",
        "Accounting scope and adoption",
        "Lazy async lifecycle",
        "Composition identity",
        "Publication and evidence completeness",
        "Runtime migration surface",
        "Mechanical artifact integrity",
        "Artifact parity",
        "Independent lenses",
    ):
        assert f"| {audit_prompt} |" in story_template
    assert "request alias, execution-time canonical target, semantic owner" in story_template
    assert "producer -> carrier -> consumer -> observable side effect" in story_template
    assert "exact factory/method signatures, return variants, carrier field names" in story_template
    assert "without an invented wrapper or reverse dependency" in story_template
    assert "empty, no-match, partial, error, cancellation, deadline, and rollback" in story_template
    assert "below, at, and above each limit" in story_template
    assert "parser or runtime limit failures" in story_template
    assert "Trace each bound to the first producer" in story_template
    assert "exact continue/stop return or private sentinel" in story_template
    assert "mapped-empty observations pump iteratively" in story_template
    assert "immutable installed-state carrier" in story_template
    assert "same named stage order and failure precedence" in story_template

    assert "Use the same named stage order and failure precedence" in lesson_template
    assert "story's exact carrier fields and callable signatures" in lesson_template
    assert "do not reorder the pipeline merely for exposition" in lesson_template
    assert "render the changed Markdown neighborhood" in lesson_template
    assert "validated observations end and harness-owned atomic admission begins" in lesson_template
    assert "Trace each bound to the first producer" in lesson_template
    assert "iterative/terminal-to-EOF transport behavior" in lesson_template
    assert "consume every async transition's continue/stop result or private sentinel" in (
        lesson_template
    )
    assert "replayable model content, a session terminal, or a diagnostic" in lesson_template

    assert "21 substantive inline findings: 13 P1 and 8 P2" in review_record
    assert "about 9,000 lines across more than 40 files" in review_record
    for root_cause in (
        "Filesystem identity, indirection, and TOCTOU",
        "Cross-story carriers and downstream consumers",
        "Provider and serialization boundaries",
        "Producer and scheduler realism",
        "Story and lesson pipeline drift",
    ):
        assert root_cause in review_record
    assert "## Additional gaps found before handoff" in review_record
    assert "signed 64-bit JSON integer tokens" in review_record
    assert "min(remaining, per-file cap) + 1" in review_record
    assert "Split CAH-038 as the sole bounded definition bridge" in review_record
    assert "CAH-039 as the sole raw-argument admission path" in review_record
    assert "inherited impossible tests from an earlier ownership boundary" in review_record
    assert "exact built-in schema containers/scalars" in review_record
    assert "same-shaped but different tool catalogs" in review_record
    assert "one registry-only factory that invokes CAH-038 internally" in review_record
    assert "Trace concrete callable signatures and return types" in review_record
    assert "counts below describe that fixed snapshot" in review_record
    assert "`JSONEncoder` to materialize a huge direct provider string first" in review_record
    assert "hostile SDK `id` or `encrypted_content`" in review_record
    assert "generic cleanup walk could consume unmetered work" in review_record
    assert "pseudocode consumed an invented wrapper" in review_record
    assert "duplicated a reverse-dependency sentence" in review_record
    assert "## Seventh handoff audit round" in review_record
    assert "one exact `RepositoryTextReader.read_text_candidate` producer" in review_record
    assert "one guard-owned outcome-adoption transaction" in review_record
    assert "Separate continuation cleanup from terminal cleanup" in review_record
    assert (
        "Adapter transport validation was incorrectly described as turn atomicity" in review_record
    )
    assert "replay a call as exactly `type`, `call_id`, `name`, and `arguments`" in review_record
    assert "a result as exactly `type`, `call_id`, and `output`" in review_record
    assert "pseudocode continued after a losing transition" in review_record
    assert "Trace each bound to the first producer and every carrier" in review_record
    assert "Pump mapped-empty SDK events iteratively" in review_record
    assert "rejects story audit evidence copied verbatim from the generic template" in review_record
    assert "split service composition or operation-generation work" in review_record
    assert "After any review fix, repeat the full contract-neighborhood audit" in review_record


def test_m2_plans_are_reviewable_learning_units() -> None:
    story_lessons = {
        "cah-024-establish-workspace-boundary.md": "cah-024-workspace-boundary.md",
        "cah-026-define-repository-read-contracts.md": "cah-026-repository-read-policy.md",
        "cah-025-discover-repository-instructions.md": "cah-025-repository-instructions.md",
        "cah-027-list-files-and-stat-path.md": "cah-027-list-files-and-stat-path.md",
        "cah-028-read-bounded-text-file.md": "cah-028-bounded-text-file.md",
        "cah-029-search-repository-text.md": "cah-029-literal-text-search.md",
        "cah-030-build-budgeted-context.md": "cah-030-budgeted-context.md",
        "cah-031-register-read-tools.md": "cah-031-read-tool-registry.md",
        "cah-038-canonicalize-provider-tool-definitions.md": (
            "cah-038-bounded-provider-tool-definitions.md"
        ),
        "cah-032-define-provider-tool-contract.md": "cah-032-provider-tool-contract.md",
        "cah-033-stage-and-validate-tool-aware-response.md": (
            "cah-033-tool-aware-response-admission.md"
        ),
        "cah-039-admit-provider-tool-arguments.md": ("cah-039-provider-tool-argument-admission.md"),
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
        "## Pre-review adversarial audit",
        "## Definition of done",
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
    expected_m2_ids = tuple(
        re.match(r"cah-(\d{3})-", story_name).group(1) for story_name in story_lessons
    )
    assert expected_m2_ids == (
        "024",
        "026",
        "025",
        "027",
        "028",
        "029",
        "030",
        "031",
        "038",
        "032",
        "033",
        "039",
        "034",
        "035",
        "036",
        "037",
    )
    story_index = (REPOSITORY_ROOT / "user-stories" / "README.md").read_text(encoding="utf-8")
    indexed_m2_rows = re.findall(
        r"^\| \d+ \| \[CAH-(\d{3}):[^\n]+?\| M2 \| ([^|]+?) \|",
        story_index,
        re.MULTILINE,
    )
    assert tuple(story_id for story_id, _ in indexed_m2_rows) == expected_m2_ids
    all_indexed_story_ids = tuple(
        re.findall(r"^\| \d+ \| \[CAH-(\d{3}):", story_index, re.MULTILINE)
    )
    lesson_index = (REPOSITORY_ROOT / "docs" / "lessons" / "README.md").read_text(encoding="utf-8")
    indexed_lesson_rows = re.findall(
        r"^\| (\d+) \| CAH-(\d{3}) \| [^\n]+?\| ([^|]+?) \|$",
        lesson_index,
        re.MULTILINE,
    )
    indexed_m2_lesson_rows = indexed_lesson_rows[-len(expected_m2_ids) :]
    assert tuple(int(order) for order, _, _ in indexed_m2_lesson_rows) == tuple(range(16, 32))
    indexed_m2_lessons = tuple((story_id, status) for _, story_id, status in indexed_m2_lesson_rows)
    assert tuple(story_id for story_id, _ in indexed_m2_lessons) == expected_m2_ids
    assert "31 implementation-ready stories" in lesson_index
    backlog = _compact_repository_document("user-stories/backlog.md")
    planning_path = (
        REPOSITORY_ROOT / "user-stories" / "notes" / "2026-08-03-m2-read-only-assistant-planning.md"
    )
    planning_source = planning_path.read_text(encoding="utf-8")
    planning = " ".join(planning_source.split())
    planned_churn_by_story = dict(
        re.findall(
            r"^\| \d+ \| CAH-(\d{3}) - [^\n]+?\| ([\d]+-[\d]+) \|$",
            planning_source,
            re.MULTILINE,
        )
    )
    assert tuple(planned_churn_by_story) == expected_m2_ids
    all_indexed_statuses = re.findall(
        r"^\| \d+ \| \[CAH-\d{3}:[^\n]+?\| M\d \| ([^|]+?) \|",
        story_index,
        re.MULTILINE,
    )
    assert len(all_indexed_statuses) == 31
    for status in ("Done", "In progress", "Planned"):
        count = sum(indexed_status.strip() == status for indexed_status in all_indexed_statuses)
        if count:
            assert f"{count} {status}" in backlog
    assert "CAH-024" in backlog
    assert "CAH-039" in backlog
    assert "The complete 16-story M2 sequence" in backlog
    story_template_source = (REPOSITORY_ROOT / "user-stories" / "story-template.md").read_text(
        encoding="utf-8"
    )
    generic_audit_prompts = _pre_review_audit_rows(story_template_source)
    for planned_unit in (
        "CAH-038 - Canonicalize provider tool definitions | E2 | Supporting",
        "CAH-032 - Define the provider-neutral tool contract | E2 | Core",
        "CAH-039 - Admit one provider tool argument object | E4 | Core",
        "CAH-034 - Run one read-tool round trip | E2 | Core",
    ):
        assert planned_unit in planning
    for planned_range in ("275-425", "425-575", "300-450", "350-500", "420-570"):
        assert planned_range in planning

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
        story_id = re.match(r"cah-(\d{3})-", story_name).group(1)
        indexed_status = dict(indexed_m2_rows)[story_id].strip()
        assert indexed_status == story_status
        indexed_lesson_status = dict(indexed_m2_lessons)[story_id].strip()
        assert indexed_lesson_status == lesson_status

        assert "**Learning emphasis:**" in story
        assert "**Review focus:**" in story
        assert "**Estimated production-code churn:**" in story
        assert "**Delivered production-code churn:**" in story
        assert "**Planning PR scope:**" in story
        assert "600" in story
        assert all(heading in story for heading in story_headings)
        evidence_heading = (
            "## Planned evidence" if story_status == "Planned" else "## Implementation evidence"
        )
        assert evidence_heading in story
        for audit_lens in (
            "Identity ledger",
            "End-to-end contract",
            "Failure and atomicity",
            "Reachable boundaries",
            "Closed grammar and cardinality",
            "Artifact parity",
            "Independent lenses",
        ):
            assert f"| {audit_lens} |" in story
        story_audit_rows = _pre_review_audit_rows(story)
        for audit_lens, evidence in story_audit_rows.items():
            if audit_lens in generic_audit_prompts:
                assert evidence != generic_audit_prompts[audit_lens]
        assert not story_audit_rows["Independent lenses"].startswith("Record ")
        story_churn = re.search(r"\*\*Estimated production-code churn:\*\* ([\d]+-[\d]+)", story)
        assert story_churn is not None
        assert planned_churn_by_story[story_id] == story_churn.group(1)
        metadata = story.split("## User story", maxsplit=1)[0]
        dependency_block = metadata.split("**Dependencies:**", 1)[1].split("- **Lesson:**", 1)[0]
        dependency_ids = re.findall(r"CAH-(\d{3})", dependency_block)
        story_index_position = all_indexed_story_ids.index(story_id)
        assert all(dependency_id in all_indexed_story_ids for dependency_id in dependency_ids)
        assert all(
            all_indexed_story_ids.index(dependency_id) < story_index_position
            for dependency_id in dependency_ids
        )

        assert "**Learning emphasis:**" in lesson
        assert "**Review focus:**" in lesson
        assert "**Visual companion:** None" in lesson
        assert "```text" in lesson
        assert all(heading in lesson for heading in lesson_headings)

    agents = (REPOSITORY_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template = story_template_source
    agents_compact = " ".join(agents.split())
    assert "core learning units" in agents_compact
    assert "roughly 600 or fewer changed production lines per story" in agents_compact
    assert "## Acceptance-to-test matrix" in template
    assert "## Pre-review adversarial audit" in template
    assert "**Planning PR scope:**" in template
    assert "## Definition of done" in template


def _compact_repository_document(relative_path: str) -> str:
    return " ".join((REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8").split())


def _m2_story_and_lesson(story_name: str, lesson_name: str) -> tuple[str, str]:
    return (
        _compact_repository_document(f"user-stories/{story_name}"),
        _compact_repository_document(f"docs/lessons/{lesson_name}"),
    )


def test_m2_workspace_path_budget_has_one_owner_and_reaches_every_carrier() -> None:
    workspace, workspace_lesson = _m2_story_and_lesson(
        "cah-024-establish-workspace-boundary.md",
        "cah-024-workspace-boundary.md",
    )
    policy, policy_lesson = _m2_story_and_lesson(
        "cah-026-define-repository-read-contracts.md",
        "cah-026-repository-read-policy.md",
    )
    assert "one pure `normalize_workspace_relative_path(value: str)`" in workspace
    assert "4,095-byte, 256-component, 255-byte-per-component" in workspace
    assert "4,094/4,095/4,096" in workspace
    assert "254/255/256" in workspace
    assert "255/256/257" in workspace
    assert "not portability claims" in workspace
    assert "Windows-backed DrvFS" in workspace_lesson
    assert "delegates to CAH-024's sole" in policy
    assert "does not duplicate CAH-024's" in policy
    assert "adapter preserves exact endpoint tuples" in policy_lesson

    downstream_pairs = (
        (
            "cah-025-discover-repository-instructions.md",
            "cah-025-repository-instructions.md",
        ),
        ("cah-027-list-files-and-stat-path.md", "cah-027-list-files-and-stat-path.md"),
        ("cah-028-read-bounded-text-file.md", "cah-028-bounded-text-file.md"),
        ("cah-029-search-repository-text.md", "cah-029-literal-text-search.md"),
        ("cah-030-build-budgeted-context.md", "cah-030-budgeted-context.md"),
    )
    for story_name, lesson_name in downstream_pairs:
        story, lesson = _m2_story_and_lesson(story_name, lesson_name)
        assert "4,095" in story
        assert "256" in story
        assert "255" in story
        assert "4,095" in lesson
        assert "256" in lesson
        assert "255" in lesson

    registry, registry_lesson = _m2_story_and_lesson(
        "cah-031-register-read-tools.md",
        "cah-031-read-tool-registry.md",
    )
    assert "does not implement a second path parser" in registry
    assert "No duplicate path parser" in registry_lesson

    definitions, definitions_lesson = _m2_story_and_lesson(
        "cah-038-canonicalize-provider-tool-definitions.md",
        "cah-038-bounded-provider-tool-definitions.md",
    )
    assert "count string characters, not strict-UTF-8 bytes" in definitions
    assert "only as a coarse necessary character cap" in definitions
    assert "maxLength` counts characters, not UTF-8 bytes" in definitions_lesson

    admission, admission_lesson = _m2_story_and_lesson(
        "cah-039-admit-provider-tool-arguments.md",
        "cah-039-provider-tool-argument-admission.md",
    )
    assert "check occurs only at the existing strict-Pydantic stage" in admission
    assert "Unknown-tool plus over-bound path still stops at lookup" in admission
    assert "Path limits do not move earlier" in admission_lesson

    for path in (
        "AGENTS.md",
        "docs/architecture.md",
        "docs/context-engineering.md",
        "docs/safety-model.md",
        "docs/tool-system.md",
        "docs/glossary.md",
        "user-stories/notes/2026-08-03-m2-read-only-assistant-planning.md",
        "user-stories/notes/2026-08-03-pr-28-review-learnings.md",
    ):
        document = _compact_repository_document(path)
        assert "4,095" in document
        assert "256" in document
        assert "255" in document


def test_m2_filesystem_identity_and_provenance_contracts_stay_coherent() -> None:
    instruction, instruction_lesson = _m2_story_and_lesson(
        "cah-025-discover-repository-instructions.md",
        "cah-025-repository-instructions.md",
    )
    assert "Probe each exact `AGENTS.md` directory entry without following it" in instruction
    assert (
        "Only the exact leaf proved absent beneath a still-admitted owner is normal" in instruction
    )
    assert "present dangling or looping symlink" in instruction
    assert "entry that disappears after the probe" in instruction
    assert "Immediately before the non-following leaf probe" in instruction
    assert "allowed-to-allowed retarget already present at either deterministic checked seam" in (
        instruction
    )
    assert "cannot preserve `applies_to=A` while selecting `B/AGENTS.md`" in instruction
    assert "does not claim descriptor-relative race protection" in instruction
    assert "fails with `instruction_source_unavailable`" in instruction
    assert "precedence rank is the depth of its canonical `applies_to` owner" in instruction
    assert "The rank is not the binding's tuple index" in instruction
    assert "Missing ancestor candidates therefore leave legal gaps" in instruction
    assert "Equal-depth owners in sibling subtrees have equal ranks" in instruction
    assert "validates `precedence == canonical_depth(applies_to)`" in instruction
    assert "`RepositoryInstructions` is created only through one result factory" in instruction
    assert "complete root-to-nearest topology without filesystem I/O" in instruction
    assert "canonical workspace-relative `source` and `applies_to` labels" in instruction
    assert "construction share one pure canonical-label validator" in instruction
    assert "requires the rendered canonical label to equal the supplied text exactly" in instruction
    assert "absolute, escaping, repeated-separator, redundant-dot, NUL" in instruction
    assert "probe_exact_entry_without_following(candidate)" in instruction_lesson
    assert "precedence=canonical_depth(owner)" in instruction_lesson
    assert "Only true leaf absence" in instruction_lesson
    assert "dangling/looping links and post-probe disappearance" in instruction_lesson
    assert "require_exact_directory(re_admit(owner), expected=owner)" in instruction_lesson
    assert "One result factory" in instruction_lesson
    assert "Canonical label gate" in instruction_lesson
    assert "Source, owner, and scope strings must exactly match" in instruction_lesson
    assert "same string corpus must agree with CAH-024's existing lexical grammar" in (
        instruction_lesson
    )
    assert "a pathname mutation after the final check can still race" in instruction_lesson

    read_policy, policy_lesson = _m2_story_and_lesson(
        "cah-026-define-repository-read-contracts.md",
        "cah-026-repository-read-policy.md",
    )
    safety_model = _compact_repository_document("docs/safety-model.md")
    for document in (read_policy, policy_lesson, safety_model):
        assert ".gitignore" in document
        assert "canonical source" in document
        assert "candidate owner" in document or "candidate-owner" in document
        assert "repository_policy_invalid" in document
    assert "Pre-read-rejected sources are not opened, cached, or charged" in policy_lesson
    assert "capture that owner's canonical directory when the view admits it" in read_policy
    assert "same directory immediately before the non-following leaf probe" in read_policy
    assert "again before a cache-miss read" in read_policy
    assert "persistent `owner A -> allowed B` replacement" in read_policy
    assert "before `B/.gitignore` is resolved or read" in read_policy
    assert "re-resolves `pkg-link` before the non-following leaf probe" in policy_lesson
    assert "repeats that owner check before a cache-miss read" in policy_lesson
    assert "A-to-B change fails before B's leaf is resolved or read" in policy_lesson
    assert "requires the owner label to resolve identically before probing" in safety_model
    assert "does not eliminate mutation after the final check" in safety_model

    listing, listing_lesson = _m2_story_and_lesson(
        "cah-027-list-files-and-stat-path.md",
        "cah-027-list-files-and-stat-path.md",
    )
    assert "content-suppressed `canonical_request_scope`" in listing
    assert "final access-time admission for this listing, including an empty listing" in listing
    assert "final boundary/policy admission immediately before metadata inspection" in listing
    assert "Immediately before directory enumeration or direct metadata inspection" in listing
    assert "`canonical_request_scope` remains `A`" in listing
    assert "even an empty list records the canonical directory actually" in listing_lesson
    assert "admitted_root = final_admit(request.path)" in listing_lesson

    read_file, read_file_lesson = _m2_story_and_lesson(
        "cah-028-read-bounded-text-file.md",
        "cah-028-bounded-text-file.md",
    )
    assert "copied from the final pre-open boundary/policy admission" in read_file
    assert "including empty and beyond-EOF successes" in read_file
    assert "allowed-to-allowed alias retarget therefore reports the target actually admitted" in (
        read_file
    )
    assert "allowed replacement reads/reports final canonical `B`" in read_file
    assert "result contains the final pre-open canonical path" in read_file_lesson
    assert "path=candidate.path" in read_file_lesson
    assert "read_text_candidate(path: str, max_source_bytes: int)" in read_file
    assert "TextSourceCandidate" in read_file_lesson

    search, search_lesson = _m2_story_and_lesson(
        "cah-029-search-repository-text.md",
        "cah-029-literal-text-search.md",
    )
    assert "one bounded listing" in search
    assert "499/500/501 admitted listing entries" in search
    assert "read_text_candidate(path, max_source_bytes=min(remaining, 262_144))" in search
    assert "Search charges exactly `candidate.source_bytes_examined`" in search
    assert "one-byte overflow sentinel" in search
    assert "At most one sentinel byte per attempted candidate" in search
    assert "source_bytes_examined` never exceeds 2,097,152" in search
    assert "at most `source_bytes_examined + files_examined`" in search
    assert "only the first additional occurrence proves match truncation" in search
    assert "immediately break both" in search
    assert "exact canonical order `matches`, `candidate_bytes`, `listing`" in search
    assert "`truncated` is exactly `bool(limit_reasons)`" in search
    assert "remaining = 2_MiB - source_bytes_examined" in search_lesson
    assert "active_cap = min(remaining, 256_KiB)" in search_lesson
    assert "source = text_reader.read_text_candidate(candidate, active_cap)" in search_lesson
    assert "source_bytes_examined += source.source_bytes_examined" in search_lesson
    assert "physical_bytes_read += source.source_bytes_examined + int(source.overflowed)" in (
        search_lesson
    )
    assert "physical_bytes_read <= source_bytes_examined + files_examined" in search_lesson
    assert "first extra occurrence is evidence only" in search_lesson
    assert "stop_candidates = True" in search_lesson
    assert 'observed["candidate_bytes"] = True' in search_lesson
    assert 'reason for reason in ("matches", "candidate_bytes", "listing")' in search_lesson
    assert "truncated=bool(reasons)" in search_lesson


def test_m2_context_and_registry_handoff_contracts_stay_coherent() -> None:
    context, context_lesson = _m2_story_and_lesson(
        "cah-030-build-budgeted-context.md",
        "cah-030-budgeted-context.md",
    )
    assert "before invoking any CAH-025/028/029 filesystem operation" in context
    assert "first CAH-025 `discover_for_path` call" in context
    assert "Complete every required focus read, discovery, fold, and budget check" in context
    assert "before inspecting its matches or starting the next search" in context
    assert "without admitting match content, running a later search" in context
    assert "require its `canonical_scope` to equal that focus result's captured `path`" in context
    assert "returned bundle's `canonical_scope` to equal the captured owner" in context
    assert "one `expected_canonical_scope` captured by the successful native operation" in context
    assert "exact equality with `bundle.canonical_scope`" in context
    assert "Copy each CAH-025 canonical-owner-depth precedence rank unchanged" in context
    assert "legal gaps remain gaps" in context
    assert "compare each result scope immediately before next search" in context_lesson
    assert "require_exact_scope(bundle, focus.path)" in context_lesson
    assert "search_results.append(result) # checked before another search may start" in (
        context_lesson
    )
    assert "require_exact_scope(bundle, owner)" in context_lesson
    assert "def merge_atomically(package, expected_canonical_scope, discovered_instructions)" in (
        context_lesson
    )
    assert "Canonical depth ranks are copied unchanged" in context_lesson

    registry, registry_lesson = _m2_story_and_lesson(
        "cah-031-register-read-tools.md",
        "cah-031-read-tool-registry.md",
    )
    assert "pure `instruction_scopes(validated_result)` extractor" in registry
    assert "four production extractors are trusted, closed harness code" in registry
    assert "Import/static policy and interaction tests enforce their intended purity" in registry
    assert "cannot detect or roll back an arbitrary side effect" in registry
    assert (
        "execution-time canonical request scope captured by the validated native result" in registry
    )
    assert "never reads or re-resolves the original `request.path`" in registry
    assert "CAH-030 requires each discovered bundle's `canonical_scope`" in registry
    for extractor_contract in (
        "`list_files`: for each returned entry",
        "`stat_path`: append the canonical result path",
        "`read_file`: append the canonical result file's parent directory",
        "`search_text`: append each canonical match file's parent directory",
    ):
        assert extractor_contract in registry
    assert "inclusive signed 64-bit range" in registry
    assert 'complete wrapped `{"result":<projected>}` envelope' in registry
    assert "outer envelope object is depth 1" in registry
    assert "one 65,536-unit work budget" in registry
    assert "defensive serializer `RecursionError` or `ValueError` maps to" in registry
    assert "`invalid_read_tool_result` without error text" in registry
    assert "`read_tool_output_too_large`" in registry
    assert "copies CAH-029's already-validated `limit_reasons` tuple without reordering" in registry
    assert "dispatch_bound(read_tool, validated_input)" in registry
    assert "`name`, `description`, `input_model`, `result_type`, and `capability`" in registry
    assert "`entries: tuple[ReadTool, ...]`" in registry
    assert "verifies by object identity" in registry
    assert "same-shaped entry from a second registry" in registry
    assert "neither method imports CAH-039 or provider-domain values" in registry
    assert "canonical request scope captured by the native operation's final access-time" in (
        registry_lesson
    )
    assert "four closed harness implementations" in registry_lesson
    assert "Count the outer object as depth 1" in registry_lesson
    assert "one 65,536-unit work budget" in registry_lesson
    assert "separate from the final 65,536-byte envelope limit" in registry_lesson
    assert "exhaustion is `read_tool_output_too_large`" in registry_lesson
    assert "serializer `RecursionError` or `ValueError`" in registry_lesson
    assert "registry-owned `ReadTool` object" in registry_lesson
    assert "accepts no CAH-039 or provider type" in registry_lesson
    assert "registry.dispatch_bound(read_file_entry, request)" in registry_lesson
    assert "CAH-032 carrier" in registry_lesson
    assert "CAH-039 catalog-bound preparation" in registry_lesson


def test_m2_provider_exchange_and_result_bounds_stay_coherent() -> None:
    provider, provider_lesson = _m2_story_and_lesson(
        "cah-032-define-provider-tool-contract.md",
        "cah-032-provider-tool-contract.md",
    )
    assert "provider's unparsed JSON argument string" in provider
    assert "argument bytes 16,383/16,384/16,385" in provider
    assert "does not parse JSON, inspect or compare keys" in provider
    assert "CAH-039 owns pair-preserving argument admission" in provider
    assert "complete envelope" in provider
    assert "outer object is structural depth 1" in provider
    assert "One 65,536-byte/work budget covers the whole envelope" in provider
    assert "before Python decimal conversion" in provider
    assert "Decoder `RecursionError` or `ValueError`" in provider
    assert "Serializer `RecursionError` or `ValueError`" in provider
    assert "owner-depth precedence including legal gaps" in provider
    assert "Projection neither re-resolves, selects, deduplicates, reorders, renumbers" in provider
    assert "CAH-031's local `instruction_scopes` never enter" in provider
    assert "CAH-039 owns that non-executing preparation boundary" in provider
    assert "CAH-034 alone guards and dispatches" in provider
    assert "Every CAH-032-owned or directly projected string must be an exact built-in `str`" in (
        provider
    )
    assert (
        "`conversation`, `repository_instructions`, `repository_context`, and `tools` must all"
        in (provider)
    )
    assert "1-16 conversation items, 0-16 legacy instructions, 0-24 context items" in provider
    assert "an encoder cannot first materialize an unbounded escaped string" in provider
    assert "encoding/iteration hooks; install projection and JSON-encoder spies" in provider
    assert "numeric precedence is likewise copied exactly from CAH-030" in provider_lesson
    assert "not recomputed from tuple position" in provider_lesson
    assert "counts the outer object as depth 1" in provider_lesson
    assert "one 65,536-byte/work budget" in provider_lesson
    assert "CAH-032 consumes CAH-038 definitions unchanged" in provider_lesson
    assert "later CAH-039 parse/key gate -> prepared request" in provider_lesson
    assert "later CAH-034 guard/CAH-031 dispatch" in provider_lesson
    assert "one chunk may already contain a whole escaped string" in provider_lesson
    assert "Exact conversation, legacy-instruction" in provider_lesson
    assert "repository-context, and tools tuple cardinalities" in provider_lesson
    assert "No generic JSON encoder receives an unbounded caller string" in provider_lesson
    assert "CAH-039 validates and prepares admitted arguments without executing them" in (
        provider_lesson
    )


def test_m2_provider_definition_bounds_stay_coherent() -> None:
    definitions, definitions_lesson = _m2_story_and_lesson(
        "cah-038-canonicalize-provider-tool-definitions.md",
        "cah-038-bounded-provider-tool-definitions.md",
    )
    assert "Every schema integer is a non-boolean value" in definitions
    assert "signed-64-bit endpoints/overflow" in definitions
    assert "shape-directed copier" in definitions
    assert "never calls `deepcopy`" in definitions
    assert "enum has at most 256 values" in definitions
    assert "one non-resetting 16,384-unit work budget" in definitions
    assert "stop before retaining the 16,385th byte" in definitions
    assert "Defensive serializer `RecursionError` or `ValueError`" in definitions
    assert "publishes all definitions or none" in definitions
    assert "pre-Pydantic exact-key gate" in definitions
    assert "belongs to CAH-039" in definitions
    assert "exact built-in `dict`, `list`, `str`, `int`, and `bool`" in definitions
    assert "rejected before calling their hooks" in definitions
    assert "only trusted schema-generation calls are the exact" in definitions
    assert "never runs a generic recursive strip/filter pre-pass" in definitions
    assert "tool_definitions.py" in definitions
    assert "-> tuple[ProviderToolDefinition, ...]" in definitions
    assert "read_tool.descriptor.input_model" in definitions
    assert "`parameters_json`, and `required_keys`" in definitions
    assert "materialize_parameters() -> dict[str, object]" in definitions
    assert "sole stored schema representation" in definitions
    assert "distinct equal tree" in definitions
    assert "immutable tuple[ProviderToolDefinition, ...]" in definitions_lesson
    assert "require_bounded_name_and_description" in definitions_lesson
    assert "A huge ignored annotation fails its O(1) length/work gate" in definitions
    assert "swapped/foreign/subclassed model before its generation hook" in definitions
    assert "Shape-directed copy" in definitions_lesson
    assert "never `deepcopy`" in definitions_lesson
    assert "at most 256 enum values" in definitions_lesson
    assert "one shared 16,384-unit visit/scalar" in definitions_lesson
    assert "stop before retaining byte 16,385" in definitions_lesson
    assert "publishes the tuple only after all four succeed" in definitions_lesson
    assert "runtime argument-key enforcement remains CAH-039's" in definitions_lesson
    assert "never by a generic recursive cleanup" in definitions_lesson
    assert "exact four-model generator set" in definitions_lesson
    assert "huge, subclassed, nested, or misplaced root/property annotation" in definitions_lesson
    assert "root `title`/`description`, property `title`, and property `default`" in (
        definitions_lesson
    )


def test_m2_tool_response_and_argument_admission_stay_coherent() -> None:
    staged_turn, staged_turn_lesson = _m2_story_and_lesson(
        "cah-033-stage-and-validate-tool-aware-response.md",
        "cah-033-tool-aware-response-admission.md",
    )
    assert "preserves CAH-032's bounded `arguments_json` byte-for-byte" in staged_turn
    assert "CAH-039 is the sole owner of pair-preserving decode" in staged_turn
    assert "argument string byte-for-byte without parsing or duplicate detection" in (
        staged_turn_lesson
    )
    assert "MAX_PROVIDER_TEXT_BYTES = 8192" in staged_turn
    assert "ProviderTextOverflowObserved(required_bytes=8193)" in staged_turn
    assert "exact kind `text.overflow`" in staged_turn
    assert "must be exact built-in `str`, pass an O(1)" in staged_turn
    assert "text.delta* -> text.overflow" in staged_turn
    assert "missing/misplaced marker is invalid response" in staged_turn
    assert "first provider-specific producer" in staged_turn_lesson
    assert "content-free overflow marker" in staged_turn_lesson

    argument_admission, argument_admission_lesson = _m2_story_and_lesson(
        "cah-039-admit-provider-tool-arguments.md",
        "cah-039-provider-tool-argument-admission.md",
    )
    stage_order = (
        "lookup -> structural + numeric preflight",
        "constant-rejecting pair decode",
        "iterative duplicate walk",
        "dictionary construction",
        "exact-key gate",
        "strict Pydantic validation",
        "prepared call",
    )
    assert [argument_admission.index(stage) for stage in stage_order] == sorted(
        argument_admission.index(stage) for stage in stage_order
    )
    assert "before scanning or decoding `arguments_json`" in argument_admission
    assert "malformed names fail at the CAH-032 carrier boundary" in argument_admission
    assert "root must be one JSON object at structural depth 1" in argument_admission
    assert "Objects and arrays may nest through depth 64" in argument_admission
    assert "fit the inclusive signed 64-bit range before Python conversion" in argument_admission
    assert "rejecting `parse_constant` callback" in argument_admission
    assert "object_pairs_hook" in argument_admission
    assert "before any dictionary exists" in argument_admission
    assert "decoder or conversion `RecursionError`/`ValueError`" in argument_admission
    assert "equal the CAH-038 definition's canonical required names exactly" in argument_admission
    assert "does not authorize execution" in argument_admission
    assert "do not construct an impossible `ProviderToolCall`" in argument_admission
    assert "admits complete argument values at 16,383/16,384 bytes and rejects 16,385" in (
        argument_admission
    )
    assert "public path scans both reachable endpoints" in argument_admission
    assert "focused scanner test retains the defensive over-bound rejection" in argument_admission
    assert "build_read_tool_catalog(registry)" in argument_admission
    assert "callers cannot supply a second definition tuple" in argument_admission
    assert "Catalog identity uses exact object identity (`is`)" in argument_admission
    assert "same-shaped second registry" in argument_admission
    assert "`ReadToolCatalogEntry` contains exactly `read_tool: ReadTool`" in argument_admission
    assert "lookup_exact(name) -> ReadToolCatalogEntry | None" in argument_admission
    assert "entry.required_keys is entry.definition.required_keys" in argument_admission
    assert "both fail by `is` identity with that same exact error before handler I/O" in (
        argument_admission
    )
    assert "-> PreparedReadToolCall | ProviderToolResult" in argument_admission
    assert "contains exactly `call_id`, `catalog_identity`, `read_tool`, and `request`" in (
        argument_admission
    )
    assert "there is no third wrapper type" in argument_admission
    lesson_walkthrough = argument_admission_lesson.split("## Practical walkthrough", maxsplit=1)[1]
    lesson_stage_order = (
        "Look up the exact CAH-032-admitted lowercase ASCII name",
        "Scan the already bounded 16-KiB value once",
        "Pair-decode with non-finite constants rejected",
        "Construct dictionaries only after uniqueness is proven",
        "Require exactly the advertised CAH-038 keys",
        "Return `PreparedReadToolCall | ProviderToolResult` directly",
    )
    assert [lesson_walkthrough.index(stage) for stage in lesson_stage_order] == sorted(
        lesson_walkthrough.index(stage) for stage in lesson_stage_order
    )
    assert "no execution authority" in argument_admission_lesson
    assert "exact catalog/entry identity; zero dispatch or I/O" in argument_admission_lesson
    assert "re-exposes those definitions for requests" in argument_admission_lesson
    assert "require_exact_keys(arguments, entry.required_keys)" in argument_admission_lesson
    assert "entry.read_tool.descriptor.input_model.model_validate(arguments)" in (
        argument_admission_lesson
    )
    assert "tool_admission.py" in argument_admission
    assert "provider SDK/adapter/port/operation/start" in argument_admission
    assert "call.call_id" in argument_admission_lesson
    assert "call.id" not in argument_admission_lesson
    assert "call_id=call.call_id" in argument_admission_lesson
    assert "read_tool=entry.read_tool" in argument_admission_lesson

    for conceptual_path in (
        "docs/architecture.md",
        "docs/context-engineering.md",
        "docs/safety-model.md",
        "docs/tool-system.md",
        "docs/glossary.md",
        "user-stories/backlog.md",
        "user-stories/notes/2026-08-03-m2-read-only-assistant-planning.md",
    ):
        conceptual = _compact_repository_document(conceptual_path)
        assert "exact CAH-031 registry identity" in conceptual
        assert "CAH-038" in conceptual
        assert "definition" in conceptual
        assert "factory" in conceptual


def test_m2_round_trip_handoff_stays_coherent() -> None:
    round_trip, round_trip_lesson = _m2_story_and_lesson(
        "cah-034-run-one-read-tool-round-trip.md",
        "cah-034-one-read-tool-round-trip.md",
    )
    assert "call CAH-039's sole synchronous admission path" in round_trip
    assert "must not wrap, copy, or partially reimplement those stages" in round_trip
    assert "rejected value causes zero dispatch" in round_trip
    assert "prepared value reaches same-catalog, same-entry dispatch" in round_trip
    assert "exposes the one retained `catalog.definitions`" in round_trip
    assert "prepared.catalog_identity is catalog.identity" in round_trip
    assert "exact non-replayable `ReadToolCatalogError`" in round_trip
    assert "one guard-owned outcome-adoption transaction" in round_trip
    assert "LoopLimitTracker.observe_tool_call()" in round_trip
    assert "dispatch_bound(prepared.read_tool, prepared.request)" in round_trip
    assert "constructs the correlated CAH-032 `ProviderToolResult`" in round_trip
    assert "dispatch_one(catalog: ReadToolCatalog, prepared: PreparedReadToolCall)" in round_trip
    assert "`provider_result: ProviderToolResult`" in round_trip
    assert 'cooperate_then_guard("before_dispatch")' in round_trip
    assert 'cooperate_then_guard("after_dispatch")' in round_trip
    assert "require `bundle.canonical_scope == scope`" in round_trip
    assert "never re-resolves or falls back to the original request alias" in round_trip
    assert "`read_tool_output_too_large`" in round_trip
    assert "produces a local safe-result candidate" in round_trip
    assert "retains the initial context candidate" in round_trip
    assert "replay against unchanged context" in round_trip
    assert "Callable[[], Awaitable[None]] | None" in round_trip
    assert "_SessionLifecycleStop" in round_trip
    assert "async def _start_claim_and_commit_turn_atomically" in round_trip
    assert "one non-failing pointer assignment" in round_trip
    assert "deadline becoming due only after the single" in round_trip
    assert "terminal finalizer joins that same task" in round_trip
    assert "_settle_and_clear_current_generation_for_continuation() -> bool" in round_trip
    lesson_walkthrough = round_trip_lesson.split("## Practical walkthrough", maxsplit=1)[1]
    lesson_stage_order = (
        "Call the sole boundary-only services factory once",
        "Require the exact continuation cleanup helper",
        "Then call CAH-039 exactly once",
        "run the cooperative pre-dispatch checkpoint",
        "take CAH-031's local `instruction_scopes`",
        "Stage the selected context",
        "In the final outcome-adoption guard",
    )
    assert [lesson_walkthrough.index(stage) for stage in lesson_stage_order] == sorted(
        lesson_walkthrough.index(stage) for stage in lesson_stage_order
    )
    assert "isinstance(admission, ProviderToolResult)" in round_trip_lesson
    assert "dispatch_one(catalog, admission)" in round_trip_lesson
    assert "admission.is_error" not in round_trip_lesson
    assert "admission.provider_result" not in round_trip_lesson
    assert "catalog.registry.dispatch_bound(prepared.read_tool, prepared.request)" in (
        round_trip_lesson
    )
    assert "ProviderToolResult(" in round_trip_lesson
    assert "tools=catalog.definitions" in round_trip_lesson
    assert 'await cooperate_then_guard("after_dispatch")' in round_trip_lesson
    assert round_trip_lesson.count('await cooperate_then_guard("after_dispatch")') == 1
    assert "CAH-039 owns every raw-JSON/key/type detail" in round_trip_lesson
    assert "one error crosses the outcome-adoption test gate with zero dispatch/context growth" in (
        round_trip_lesson
    )
    assert "prepared value crosses the pre-dispatch checkpoint unchanged" in round_trip_lesson
    assert "require `bundle.canonical_scope == scope`" in round_trip_lesson
    assert "known, replayable tool error with no instruction scopes" in round_trip_lesson
    assert "Static imports prevent orchestration from growing" in round_trip_lesson
    assert "dispatch_candidate, dispatch_error = capture_sync" in round_trip_lesson
    assert "request_candidate, request_error = capture_sync" in round_trip_lesson
    assert "await start_claim_and_commit_turn_atomically" in round_trip_lesson
    assert "if installed is None" in round_trip_lesson
    assert "adopt_turn_outcome_under_guard(final_turn, all_turn_usage)" in round_trip_lesson
    assert "require_type(adopted, AcceptedFinalText)" in round_trip_lesson
    for checkpoint in (
        '"before_dispatch"',
        '"after_dispatch"',
        '"after_discovery"',
        '"after_merge"',
        '"before_provider_start"',
    ):
        assert checkpoint in round_trip


def test_m2_iterative_loop_and_adapter_mapping_stay_coherent() -> None:

    agent_loop, agent_loop_lesson = _m2_story_and_lesson(
        "cah-035-run-bounded-agent-loop.md",
        "cah-035-bounded-agent-loop.md",
    )
    assert "reuse this complete admission path" in agent_loop
    assert "Each accepted call first follows CAH-039's exact lookup" in agent_loop
    assert "one-value 16-KiB work bound and 64-level object/array ceiling" in agent_loop
    assert "signed-64-bit JSON integer tokens" in agent_loop
    assert "defensive decoder `RecursionError`/`ValueError`" in agent_loop
    assert "execution-time canonical request scope first" in agent_loop
    assert "never re-resolves or falls back to the original request alias" in agent_loop
    assert "requires `bundle.canonical_scope == scope`" in agent_loop
    assert "after every discovery, after every merge" in agent_loop
    assert "reuses—not wraps or reimplements—CAH-034's" in agent_loop
    assert "`read_tool_output_too_large`" in agent_loop
    assert "stages its safe result against the current context" in agent_loop
    assert "next iteration derives both `context` and `history` from that installed carrier" in (
        agent_loop
    )
    assert "before CAH-039 argument admission" in agent_loop
    assert "_SessionLifecycleStop" in agent_loop
    assert "CAH-039's lookup-first, bounded structural and signed-64-bit numeric" in (
        agent_loop_lesson
    )
    assert "isinstance(admission, ProviderToolResult)" in agent_loop_lesson
    assert "dispatch_one(catalog, admission)" in agent_loop_lesson
    assert "admission.is_error" not in agent_loop_lesson
    assert "adopt_turn_outcome_under_guard(outcome, all_turn_usage)" in agent_loop_lesson
    assert "case ProviderFailure(code=code, message=message, retryable=retryable)" in (
        agent_loop_lesson
    )
    assert "select_normalized_provider_failure" in agent_loop_lesson
    assert "isinstance(adopted, AcceptedFinalText)" in agent_loop_lesson
    assert "require_type(adopted, AcceptedToolCall)" in agent_loop_lesson
    assert "tools=catalog.definitions" in agent_loop_lesson
    assert "require its `canonical_scope` to equal the captured scope" in agent_loop_lesson
    assert "all covered before replay or whole transaction discarded" in agent_loop_lesson
    assert "same known-error path after dispatch" in agent_loop_lesson
    assert "no scopes, exposes no oversized content" in agent_loop_lesson
    assert "if not await settle_and_clear_current_generation_for_continuation()" in (
        agent_loop_lesson
    )
    assert "context_candidate = installed.context" in agent_loop_lesson
    assert "append_turn(installed.history" in agent_loop_lesson
    assert "request_candidate, request_error = capture_sync" in agent_loop_lesson
    assert "await start_claim_and_commit_turn_atomically" in agent_loop_lesson

    adapter, adapter_lesson = _m2_story_and_lesson(
        "cah-036-map-openai-tool-calls.md",
        "cah-036-openai-tool-calls.md",
    )
    assert "preserved byte-for-byte" in adapter
    assert "must not decode it into a last-value-wins dictionary" in adapter
    assert "CAH-039's pair-preserving admission owns duplicate rejection" in adapter
    assert "exactly `source`, `applies_to`, `precedence`, and `content`" in adapter
    assert "never derives it from array index" in adapter
    assert "Both direct SDK strings must be exact built-in `str` values" in adapter
    assert "Before scalar inspection, equality, UTF-8 encoding" in adapter
    assert "no `json.dumps`, `JSONEncoder.encode`" in adapter
    assert "scalar/UTF-8/equality/retention/canonicalizer/JSON-serializer spies" in adapter
    assert "provider-neutral semantic classification" in adapter
    assert "required it to agree with the compact success/error shape" in adapter
    assert "never calls a JSON decoder on function-call arguments" in adapter_lesson
    assert "request.repository_context" in adapter_lesson
    assert "request.context" not in adapter_lesson
    assert "materialize_parameters()" in adapter
    assert "never sends `parameters_json` as a string" in adapter
    assert "`source`, `applies_to`, `precedence`, then `content`" in adapter_lesson
    assert "whole escaped string as one chunk" in adapter_lesson
    assert "serializer spy must remain untouched" in adapter_lesson
    assert "ProviderTextOverflowObserved(required_bytes=8193)" in adapter
    assert "iterative raw-observation pump" in adapter
    assert "drains the raw SDK iterator to EOF" in adapter
    assert "raw iterator exception before EOF discards that tuple" in adapter
    assert "16,384 legal one-byte argument deltas" in adapter
    assert "first-producer text saturation" in adapter_lesson
    assert "no recursive" in adapter_lesson
    assert "require_raw_eof" in adapter_lesson
    saturation = adapter_lesson.split(
        "### Planned pseudocode: first-producer text saturation", maxsplit=1
    )[1].split("### Planned pseudocode: iterative SDK pump", maxsplit=1)[0]
    saturation_steps = (
        "text_bytes = 0",
        "overflowed = False",
        "require_exact_builtin_str(delta)",
        "if overflowed:",
        "scan_at_most_remaining_plus_one",
        "text_bytes += accepted_bytes",
    )
    assert [saturation.index(step) for step in saturation_steps] == sorted(
        saturation.index(step) for step in saturation_steps
    )


def test_m2_evaluation_and_scheduler_composition_stays_coherent() -> None:
    evaluation, evaluation_lesson = _m2_story_and_lesson(
        "cah-037-prove-read-only-assistant.md",
        "cah-037-read-only-assistant-evaluation.md",
    )
    assert "every focus read/discovery/fold finishes before search" in evaluation
    assert "first-result scope mismatch causes zero second-search calls" in evaluation
    assert "owner bundle is discovered, its `canonical_scope` exactly matches" in evaluation
    assert "original request alias and a retargeted canonical label" in evaluation
    assert "Carrier cases cover 16,383/16,384/16,385 argument bytes" in evaluation
    assert "reachable at-or-below-limit arguments" in evaluation
    assert "object/array depth 63, 64, and 65" in evaluation
    assert "signed-64-bit endpoints/overflow, fractions/exponents" in evaluation
    assert "defensive `ValueError`" in evaluation
    assert "unknown-tool control still wins before structural work" in evaluation
    assert "fixed `read_tool_output_too_large` known error" in evaluation
    assert "zero discovery/context growth rather than a session terminal" in evaluation
    assert "8,191/8,192/8,193 ASCII and multibyte bytes" in evaluation
    assert "maximum-fragment function-call stream" in evaluation
    assert "raw EOF precedes neutral release" in evaluation
    assert "zero later searches" in evaluation_lesson
    assert "exact bundle-scope check" in evaluation_lesson
    assert "16-KiB/ 64-level structural plus signed-64-bit numeric preflight" in evaluation_lesson
    assert "16,383/16,384/16,385-byte argument carriers through CAH-032/036" in evaluation_lesson
    assert "rejected carriers never invoke CAH-033 or CAH-039" in evaluation_lesson
    assert "use only admitted, at-or-below-limit carriers for CAH-039" in evaluation_lesson
    assert "before_dispatch -> CAH-034 identity guard" in evaluation_lesson
    assert "dispatch_bound(entry, request) -> after_dispatch" in evaluation_lesson
    assert "replay against unchanged context rather than terminating the session" in (
        evaluation_lesson
    )
    assert "Drive 8,191/8,192/8,193-byte ASCII/multibyte text" in evaluation_lesson
    assert "constant stack depth" in evaluation_lesson
    assert "raw terminal releases no neutral tuple before EOF" in evaluation_lesson

    runtime_rules = _compact_repository_document("AGENTS.md")
    assert "use one `cooperate_then_guard` seam" in runtime_rules
    assert "`await asyncio.sleep(0)` outside every lock" in runtime_rules
    assert "with no observer/gate installed, queue cancellation on the same loop" in runtime_rules
    assert "complete 16-KiB argument payload" in runtime_rules
    assert "signed 64-bit JSON integers" in runtime_rules
    assert "exactly equal the captured scope" in runtime_rules
    assert "complete wrapped envelope" in runtime_rules
    assert "outer `result` object at depth 1" in runtime_rules
    assert "65,536-unit work budget" in runtime_rules
    assert "shape-directed, incrementally byte-charged copier" in runtime_rules
    assert "private session stop sentinel" in runtime_rules
    assert "immutable installed-turn carrier construction" in runtime_rules
    assert "Join valid uninstalled-operation cleanup before terminal publication" in runtime_rules
    assert "Provider text is bounded at its first producer" in runtime_rules
    assert "iterative mapped-empty observation pump" in runtime_rules

    tool_system = _compact_repository_document("docs/tool-system.md")
    assert "table is not the exact CAH-031 descriptor shape" in tool_system
    assert "CAH-031 intentionally encodes only" in tool_system
    assert "without running a handler" in tool_system
    assert "dispatch_bound(entry, validated_input)` exactly once" in tool_system
    assert "there is no earlier or second execution" in tool_system

    conceptual_names = (
        "agent-loop.md",
        "architecture.md",
        "context-engineering.md",
        "evaluation.md",
        "safety-model.md",
        "tool-system.md",
    )
    conceptual = {name: _compact_repository_document(f"docs/{name}") for name in conceptual_names}
    for document in conceptual.values():
        assert "instruction" in document.lower()
    assert (
        "owns unknown-name lookup followed by the complete 16-KiB/64-level"
        in conceptual["agent-loop.md"]
    )
    assert "execution-time canonical" in conceptual["architecture.md"]
    assert "never become inferred search roots" in conceptual["context-engineering.md"]
    assert "canonical-result mismatch and no package" in conceptual["evaluation.md"]
    assert "reuse it immediately before access" in conceptual["safety-model.md"]
    assert "signed 64-bit" in conceptual["tool-system.md"]
    assert "complete wrapped envelope" in conceptual["tool-system.md"]
    assert "one 65,536-unit work budget" in conceptual["tool-system.md"]
    assert "separately capped at 65,536 UTF-8 bytes inclusive" in conceptual["tool-system.md"]


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
