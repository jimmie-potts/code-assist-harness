# Documentation baseline - 2026-07-13

## Purpose

This note records the implementation baseline used to create the first dependency-ordered backlog.
It distinguishes locked product decisions from scaffold gaps so future work does not accidentally
revive superseded assumptions.

This is a documentation-only pass. It does not implement runtime, TUI, protocol, provider, model,
tool, approval, editing, subprocess, transcript, or evaluation behavior.

## Locked decisions

- The product is learning-first now and should expose a reusable Python harness core later.
- Ubuntu under WSL is the only initial runtime environment. Node and Python both run inside WSL and
  use Linux paths.
- A TypeScript Ink process owns the terminal and launches the Python runtime as a child process.
- Commands travel over child stdin, events travel over child stdout, and diagnostics use child
  stderr. The wire format is versioned NDJSON.
- Python owns session orchestration, agent completion, context construction, tool policy, approvals,
  and safety. The TUI sends commands and projects events into visible state.
- The project owns an explicit `asyncio`-based agent loop. LangChain is not an MVP orchestrator and
  may only be introduced later as an adapter that does not change core domain types.
- OpenAI is the first provider, behind provider-neutral request and stream types. OpenAI SDK objects
  do not cross the provider boundary, and live-provider tests stay outside default validation.
- Pydantic v2 validates Python data crossing process or model boundaries. Zod validates TypeScript
  protocol data at the process boundary. Internal domain state may use simpler typed structures.
- Native, bounded repository reads and searches may run automatically. Applying a complete proposed
  edit batch requires one approval. Every subprocess command requires a separate approval.
- The model proposes structured exact-replacement, create, and delete operations. The harness
  validates them, computes the unified diff, verifies file preconditions, and applies only an
  approved, unchanged batch.
- Commands are argument arrays and never shell strings. Built-in and user configuration may broaden
  or narrow the allowlist; workspace configuration may narrow but cannot silently broaden it.
  Every permitted command still requires approval.
- The workspace is the launch directory by default with an optional `--workspace PATH`; one process
  serves one workspace.
- Append-only transcripts live under the WSL XDG state directory and contain the complete validated,
  redacted event stream with bounded tool results. Raw provider payloads and environment values are
  excluded. `--no-transcript` is required before a real provider ships.
- Python public production APIs use Google-style docstrings enforced with Ruff `D` rules. Exported
  TypeScript contracts use TSDoc. Tests and trivial private helpers do not require mechanical
  docstrings.
- JavaScript tooling uses npm, a committed `package-lock.json`, and a repository-pinned compatible
  Node version. No monorepo build tool is needed for the first slices.

## Scaffold gaps observed before implementation

The observations below describe the repository at the start of this documentation pass. They are
historical input to the stories, not a claim that every row remains current after this pass.

| Observation | Consequence | Owning stories |
| --- | --- | --- |
| The README and package description still present LangChain as the foundation. | The checked-in narrative conflicts with the explicit-loop decision. | CAH-001 |
| LangChain packages remain declared runtime dependencies. | Unused framework dependencies imply the superseded architecture and complicate the learning baseline. | CAH-001 |
| Documentation covers only the initial Python package and basic commands. | Process ownership, safety, protocol, terminology, and learning rationale are not yet recorded. | CAH-001, CAH-008 |
| `AGENTS.md` has no TUI, npm lockfile, TypeScript testing, protocol-fixture, or conceptual-documentation conventions. | Cross-language contributions have no repository-local standard yet. | CAH-001, CAH-008 |
| Ruff currently checks `E`, `F`, `I`, and `UP`, but not public docstrings with the Google convention. | The educational API-documentation standard is not mechanically enforced. | CAH-008 |
| There is no `tui/` project, pinned Node version, npm lockfile, or Ink rendering test. | The terminal shell and its toolchain do not exist. | CAH-002 |
| There is no Python runtime entry point or child-process supervisor. | The application cannot yet operate as one Node-Python tool. | CAH-003 |
| There are no protocol types, fixtures, readers, writers, or cross-language contract tests. | No safe process-boundary contract exists yet. | CAH-004 |
| There is no mock streaming integration or cancellation lifecycle. | The proposed architecture has not been exercised end to end. | CAH-005, CAH-006 |
| There is no unified Python-and-Node check command or Linux CI workflow. | Cross-language regressions cannot yet be caught as one change. | CAH-007 |
| There is no reducer, transcript writer, provider interface, fake provider, or agent loop. | M1 behavior remains entirely unimplemented. | CAH-010, CAH-011, CAH-020, CAH-021, CAH-022 |
| The existing tests only establish the minimal package scaffold. | Behavioral, failure-path, render, protocol, and integration coverage must be added with their stories. | CAH-002 onward |

## Planning consequences

- CAH-001 and CAH-008 are marked **In progress**, not complete: LangChain dependency removal and
  Ruff public-docstring enforcement remain outstanding acceptance criteria.
- CAH-002 through CAH-007 remain model-free so the process, protocol, cancellation, and validation
  boundaries are learned and tested before prompts or providers are introduced.
- CAH-009 follows the working cancellation slice because its sequence must match a real automated
  integration test rather than describe a hypothetical flow.
- CAH-010 through CAH-022 depend on the completed walking skeleton and repository-wide checks.
- No later epic receives speculative implementation IDs until it is refined into independently
  testable stories.

## Issues encountered in this pass

- The repository did not yet contain a `user-stories/` directory, so the backlog, index, story
  records, and notes structure were established from the locked product definition.
- The initial scaffold and the newly selected architecture disagree about LangChain. The backlog
  records this as an explicit removal and documentation task rather than silently accepting drift.
- The desired layout includes many future directories that do not yet exist. Documentation must
  distinguish a target layout from current repository contents until each owning story creates it.
- The available execution environment did not expose `uv` on `PATH`, so the documented `uv` lock,
  test, lint, format, and build commands could not be invoked directly during this pass. The
  existing `.venv` still provided Python 3.12.13, pytest 9.1.1, and Ruff 0.15.21, which allowed the
  current package test and Python static checks to run. A direct Hatchling build was unavailable
  because Hatchling was not installed in that environment.

## Open design questions preserved for implementation

These questions do not block the documentation baseline. Their owning stories must choose and test
one explicit contract rather than letting incidental implementation behavior decide it.

- Define whether a multi-file edit batch is applied transactionally or how rollback and partial
  failure are represented. No implementation may report full success after a partial application.
- Finalize how the TUI recovers or terminates after a structurally valid envelope contains an
  unknown event type, and how that differs from malformed JSON or an invalid known payload.
- Select the evaluation-scenario serialization format when the runner is implemented; optimize for
  readable diffs, deterministic bytes, and fixture isolation rather than framework adoption.
- Document the residual time-of-check/time-of-use risk for host filesystem operations and prefer
  descriptor-relative or atomic operations where practical. The restricted host executor is not an
  operating-system sandbox.

## Validation evidence for this pass

- `git diff --check` passed for tracked changes, and an explicit trailing-whitespace scan passed for
  the new untracked Markdown files.
- `.venv/bin/pytest` passed the existing package test: 1 test passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/ruff format --check .` passed for the two current Python files.
- `uv lock --check` and `uv build` remain unverified because `uv` was not available on `PATH`; a
  direct `.venv/bin/python -m hatchling build` attempt confirmed that the build backend was not
  installed in the existing environment.
