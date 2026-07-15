# Repository Guidelines

## Product and Architecture Boundaries

Code Assist Harness is a learning-first coding agent for Ubuntu under WSL. The target application
has an Ink/TypeScript process that owns the terminal and launches a Python harness child. They
communicate using versioned NDJSON: commands go to Python stdin, validated events come from Python
stdout, and Python stderr is reserved for diagnostics.

The Python harness owns orchestration, session lifecycle, context construction, tool policy,
approvals, and transcripts. The TUI reduces events into visible state; it must not decide whether a
tool is safe or whether an agent turn is complete. The project owns its explicit agent loop. Keep
OpenAI and any future LangChain adapter behind provider boundaries so framework SDK types never
enter core domain APIs.

## Project Structure and Module Organization

Python application code belongs in `src/code_assist_harness/`. Keep modules focused and expose only
intentional package APIs from `__init__.py`. Python tests live in `tests/` and mirror the source area
they cover.

The planned TypeScript application belongs in `tui/`, with source in `tui/src/` and tests in
`tui/test/`. Shared cross-language fixtures belong in `protocol/fixtures/`; do not make either
language's generated output the unreviewed source of truth during the first implementation.
Evaluation scenarios belong in `evals/`. Architecture guidance belongs in `docs/`, accepted
decisions in `docs/adr/`, unit learning companions in `docs/lessons/`, and dependency-ordered
delivery work in `user-stories/`.

Do not add empty planned directories. Introduce a path with the story that first uses it. Project
metadata, Python dependencies, and tool settings are defined in `pyproject.toml`; commit `uv.lock`
whenever Python dependency resolution changes. The TUI uses npm and must commit `package-lock.json`
whenever JavaScript dependency resolution changes. Pin the supported Node version in a repository
version file when the TUI is introduced.

## Build, Test, and Development Commands

The current Python scaffold supports:

- `uv sync --dev` to create the Python 3.12 environment and install locked dependencies.
- `uv run pytest` to run the Python test suite.
- `uv run ruff check .` to check lint rules and import ordering.
- `uv run ruff format --check .` to verify formatting; use `uv run ruff format .` to apply it.
- `uv build` to create ignored distributions under `dist/`.

When `tui/` is added, expose npm scripts for type checking, linting, and tests. CAH-007 must provide
one documented repository-wide command that runs all non-live Python, TypeScript, protocol, and
integration checks. Default checks must not require OpenAI credentials or network access.

## Python Style and Documentation

Use four-space indentation, type hints for public functions, and a maximum line length of 100
characters. Follow `snake_case` for modules, functions, and variables; `PascalCase` for classes; and
`UPPER_CASE` for constants. Keep imports sorted and prefer small, explicit functions over hidden
global state. Ruff is the style authority.

Production modules and public APIs use Google-style docstrings. Document responsibility, important
inputs and outputs, exceptions, side effects, cancellation, security assumptions, and invariants
when relevant. Add a concise example for a non-obvious abstraction. Tests and trivial private
helpers are exempt from mechanical docstrings, but private code still needs explanation when it
encodes a protocol invariant, security boundary, concurrency rule, context-selection decision, or
deliberate tradeoff. Comments explain why a choice exists rather than restating code.

Ruff `D` rules with the Google convention enforce this policy. Keep test exemptions narrow and do
not silence missing documentation broadly across production code.

## TypeScript and TUI Conventions

Use TypeScript for all TUI production code. Exported protocol types, reducers, hooks, components,
and other meaningful contracts use TSDoc. State whether a type is a wire shape or local UI state,
document legal states and transition invariants for state machines, and state whether reducers must
remain pure, how duplicate or unknown events behave, and what happens after the child process exits
when those concerns apply.

The TUI must preserve pending user input while background events arrive, expose keyboard
cancellation, and remain understandable in narrow or resized terminals. Keep orchestration and
policy decisions out of React components. Test reducers independently and use
`ink-testing-library` for user-visible screen states.

## Protocol and Runtime Conventions

Treat every process-boundary value as untrusted. Use Pydantic v2 to validate Python commands and
events and Zod at the TypeScript boundary. Validate the common envelope before dispatching by type
so malformed input becomes a structured protocol error and unknown event types cannot crash the
TUI. Every wire message is exactly one JSON object followed by a newline.

Session events carry a session ID and monotonic sequence. Commands carry an ID that resulting
events reference as a correlation ID. Use shared golden JSON fixtures in both languages whenever
the protocol changes. Protocol-message documentation identifies process ownership, correlation,
ordering, sequencing, and expected failure behavior. Never write logs, tracebacks, or diagnostics
to Python protocol stdout.

Use one explicit `asyncio` event loop in the Python runtime. Preserve ordered event writes, model
active work as cancellable tasks, and check cancellation and limits before starting another costly
operation. Move blocking work to a worker thread only when it cannot remain small and bounded.

## Tool and Safety Conventions

Implement safe repository reads as native Python tools, not subprocess wrappers. Validate tool
input before policy evaluation. Proposed edits are structured exact-replacement, create, or delete
operations; validate them, generate a unified diff, receive one approval for the exact batch,
re-check file hashes, and only then apply them.

Represent subprocesses as argument arrays and never use `shell=True`. Built-in policy supplies the
initial candidates, user configuration may broaden or narrow them, and workspace configuration may
only narrow them. Every allowed subprocess still requires its own approval. Approval never makes a
denied command safe. Enforce workspace boundaries after resolving symlinks, strip secrets from tool
environments, and apply time and output limits.

Every tool documents its purpose, input and output schemas, capability classification, approval
requirement, filesystem access, subprocess or network behavior, timeout and output limits,
cancellation, expected failures, and security considerations.

## Testing and Definition of Done

Use pytest for Python and the TUI's chosen test runner for TypeScript. Name Python test files
`test_*.py` and test functions `test_*`. Add focused regression coverage for every behavior change,
including at least one meaningful failure path. Unit tests replace model and network interactions
with deterministic fakes. When a test's setup and intent are not self-evident, document the modeled
scenario and why it matters; trivial tests do not need explanatory comments.

Every implementation-ready story, including documentation-only work, must keep its linked lesson
consistent with the story status and delivered evidence. The additional behavioral checks below
apply when the story changes executable behavior.

A behavioral story is complete only when:

1. Its happy path and a meaningful failure path are tested.
2. Public Python APIs are typed and documented, and meaningful exported TypeScript APIs use TSDoc.
3. Protocol changes have documentation and cross-language fixtures.
4. Side effects and user-visible failures are represented in validated events and transcripts.
5. Secrets do not enter events, logs, fixtures, snapshots, examples, or transcripts.
6. Python linting, formatting, docstring checks, and tests pass.
7. TypeScript type checking, linting, and tests pass when the TUI is in scope.
8. Visible TUI changes include a reducer or rendering test.
9. The unit lesson is updated with the implemented path, observed trade-offs, and test evidence.
10. Relevant conceptual documentation and user-story notes are updated.

## Unit Lesson Conventions

Every implementation-ready user story has one learning companion under `docs/lessons/`. The story
defines what must be delivered; the lesson explains what the unit teaches, why its architecture
exists, how to study its failure paths, and how a production organization might expand the design.

Follow `docs/lessons/lesson-template.md`. Each lesson includes status metadata, a quick summary,
learning objectives, why the unit matters, key concepts, architecture and invariants, a practical
walkthrough, failure scenarios, a production expansion, a direct local-versus-production
comparison, trade-offs and graduation signals, exercises, key takeaways, a local glossary, and
further reading.

Production-tool examples are illustrative rather than approved dependencies. Include three to five
representative tools with official references, describe the capability being compared, and discuss
operational cost as well as benefit. Keep lesson status honest: planned stories use `Planned`, work
in progress uses `Implementation companion`, blocked work states its blocker, and completed stories
use `Verified against implementation`. After a story ships, replace hypothetical paths with
concrete modules, events, tests, and observations.

## User Stories and Planning Notes

Use the story identifiers and dependency order in `user-stories/`. A story states its outcome,
dependencies, scope, acceptance criteria, validation, documentation impact, and exclusions, and
links to its lesson. Keep status accurate: documentation of a future capability is not evidence
that the capability works.

Record durable implementation discoveries under `user-stories/notes/`. Capture decisions,
unexpected constraints, failure causes, validation evidence, and follow-up work without turning the
notes into a second backlog. Update an ADR when a new decision supersedes an accepted architectural
choice.

## Commit and Pull Request Guidelines

Use short, imperative commit subjects consistent with history, such as `Document harness
architecture`. Keep each commit to one logical change and, where practical, one user story. Branch
names should be descriptive, such as `agent/add-tool-registry`. Pull requests explain what changed,
why it changed, and developer impact; list validation commands and link relevant stories or issues.
Include screenshots only for visible UI changes.

When a unit reaches **Done** and its required validation passes, complete the publish workflow in the
same unit: create or switch to a descriptive branch, commit only the intended changes, push the
branch, open a pull request, and mark it ready for review. Use a draft pull request while work is
incomplete, but do not leave a completed unit only in the local worktree or in draft state unless the
user explicitly requests that outcome.

## Security and Configuration

Never commit API keys or `.env`. Copy `.env.example` locally and provide `OPENAI_API_KEY` through
the environment only when an explicitly live-provider workflow requires it. Keep sample values
blank or unmistakably fake. Do not log credentials, environment values, raw provider responses, or
unbounded tool output.

Store validated, redacted transcripts under the WSL XDG state directory with restrictive local
permissions. Do not add harness state to target repositories. Support `--no-transcript` before the
first real-provider release.
