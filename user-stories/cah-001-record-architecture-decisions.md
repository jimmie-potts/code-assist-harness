# CAH-001 - Record the architecture decisions

- **Status:** In progress
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** None
- **Lesson:** [Architecture decisions](../docs/lessons/cah-001-architecture-decisions.md)

## User story

> As a contributor, I want the agreed architecture documented so that implementation does not
> drift back toward implicit framework orchestration or native-Windows assumptions.

## Scope

- Correct the product description and remove the superseded LangChain-foundation narrative.
- Record the supported environment, process boundary, orchestration ownership, wire protocol,
  approval model, edit representation, command policy, transcript location, and provider boundary.
- Add the initial architecture overview, glossary, and ADRs.
- Extend repository guidance for the future `tui/`, npm lockfile, TypeScript tests, protocol
  fixtures, and conceptual documentation.
- Remove unused LangChain dependencies and refresh `uv.lock`; do not add a provider SDK yet.

## Acceptance criteria

1. An ADR states that the MVP runs entirely within Ubuntu under WSL using Linux paths.
2. An ADR states that the Ink/Node process owns the terminal and launches Python through `uv`.
3. An ADR states that commands use stdin, versioned NDJSON events use stdout, and diagnostics use
   stderr.
4. An ADR states that the project owns the explicit agent loop and that LangChain is only a possible
   future adapter.
5. An ADR records why native reads, edit batches, and subprocess commands have different approval
   behavior.
6. An ADR records restricted host execution first and a replaceable executor boundary later.
7. The README and Python package metadata no longer describe LangChain as the architectural
   foundation.
8. Unused LangChain packages are removed from project dependencies and `uv.lock` is updated.
9. `AGENTS.md` defines conventions for `tui/`, npm and its lockfile, TypeScript tests, protocol
   fixtures, and documentation maintenance.
10. The glossary defines at least session, turn, step, tool call, event, command, provider, context
    item, approval, and terminal state.
11. Architecture documentation clearly distinguishes the current scaffold from the target project
    layout.
12. No agent, model, protocol-runtime, tool, subprocess, or TUI behavior is added.

## Validation

- Run `uv lock --check` after dependency removal.
- Run `uv run pytest`.
- Run `uv run ruff check .` and `uv run ruff format --check .` using the rules available at this
  point in the sequence.
- Run `git diff --check`.
- Search tracked project documentation and metadata for active claims that LangChain owns the MVP
  architecture; references describing it only as an explicitly future adapter are allowed.
- Review every ADR against the baseline decisions in
  `notes/2026-07-13-documentation-baseline.md`.

## Documentation impact

Updates the README, `AGENTS.md`, architecture overview, glossary, and ADR set. These records become
the decision source for all subsequent stories.

## Out of scope

- Creating the Ink application or protocol implementation.
- Adding Pydantic, Zod, Ink, OpenAI, or another runtime dependency not needed for this documentation
  and cleanup change.
- Implementing a LangChain adapter.
