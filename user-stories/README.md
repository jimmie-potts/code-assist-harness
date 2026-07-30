# User stories

This directory is the implementation backlog for Code Assist Harness. The backlog keeps the
learning-first delivery sequence explicit while preserving the long-term goal of a reusable Python
harness library.

## How to use this backlog

- Start with the dependency-ordered story list below; do not select a story whose dependencies are
  incomplete.
- Treat acceptance criteria as the behavioral contract and the validation section as the minimum
  evidence required for completion.
- Read the linked lesson before implementation and update it with concrete paths, tests, and
  observed trade-offs before marking the story done.
- Update a story's documentation-impact section whenever its behavior changes.
- Keep provider-backed smoke tests outside default validation. Unit and contract tests must not use
  the network or a live model.
- Record newly locked decisions, material implementation discoveries, and unresolved issues in
  `notes/` so later stories can distinguish accepted constraints from assumptions.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| Planned | Scoped but not started. |
| In progress | Work is underway, but the story has not passed all acceptance criteria and review. |
| Blocked | Work cannot continue until a named dependency or external decision is resolved. |
| Done | Every acceptance criterion is met, validation passes, and required documentation is current. |

CAH-001, CAH-008, CAH-002, CAH-003, and CAH-004 are **Done**: the architecture baseline,
documentation standard, Ink shell, supervised Python process, and protocol version 1 boundary are
implemented and validated. CAH-005 is the next dependency-ready unit. Readiness works, but task
submission, mocked streaming, provider, workspace read, tool, policy, transcript, and agent behavior
remain unimplemented.

## Dependency-ordered implementation sequence

| Order | Story | Lesson | Milestone | Status | Depends on |
| ---: | --- | --- | --- | --- | --- |
| 1 | [CAH-001: Record the architecture decisions](cah-001-record-architecture-decisions.md) | [Architecture decisions](../docs/lessons/cah-001-architecture-decisions.md) | M0 | Done | None |
| 2 | [CAH-008: Establish educational documentation standards](cah-008-establish-documentation-standards.md) | [Documentation standards](../docs/lessons/cah-008-documentation-standards.md) | M0 | Done | CAH-001 |
| 3 | [CAH-002: Bootstrap the Ink application](cah-002-bootstrap-ink-application.md) | [Ink application shell](../docs/lessons/cah-002-ink-application-shell.md) | M0 | Done | CAH-001, CAH-008 |
| 4 | [CAH-003: Start and supervise the Python runtime](cah-003-supervise-python-runtime.md) | [Python runtime supervision](../docs/lessons/cah-003-python-runtime-supervision.md) | M0 | Done | CAH-002 |
| 5 | [CAH-004: Define protocol version 1](cah-004-define-protocol-v1.md) | [Protocol version 1](../docs/lessons/cah-004-protocol-v1.md) | M0 | Done | CAH-003 |
| 6 | [CAH-005: Stream a mocked session end to end](cah-005-stream-mocked-session.md) | [Mocked streaming session](../docs/lessons/cah-005-mocked-streaming-session.md) | M0 | Planned | CAH-002, CAH-003, CAH-004 |
| 7 | [CAH-006: Cancel an active session](cah-006-cancel-active-session.md) | [Session cancellation](../docs/lessons/cah-006-session-cancellation.md) | M0 | Planned | CAH-005 |
| 8 | [CAH-009: Document the first end-to-end execution](cah-009-document-walking-skeleton.md) | [Walking-skeleton guide](../docs/lessons/cah-009-walking-skeleton-guide.md) | M0 | Planned | CAH-006 |
| 9 | [CAH-007: Establish repository-wide checks](cah-007-establish-repository-checks.md) | [Repository-wide checks](../docs/lessons/cah-007-repository-checks.md) | M0 | Planned | CAH-009 |
| 10 | [CAH-010: Implement session state as a reducer](cah-010-session-state-reducer.md) | [Session state reducer](../docs/lessons/cah-010-session-state-reducer.md) | M1 | Planned | CAH-004, CAH-006, CAH-007 |
| 11 | [CAH-011: Write an append-only transcript](cah-011-append-only-transcript.md) | [Append-only transcript](../docs/lessons/cah-011-append-only-transcript.md) | M1 | Planned | CAH-010 |
| 12 | [CAH-020: Define the provider interface and fake provider](cah-020-provider-interface-and-fake.md) | [Provider interface and fake](../docs/lessons/cah-020-provider-interface-and-fake.md) | M1 | Planned | CAH-010, CAH-011 |
| 13 | [CAH-021: Complete one model turn](cah-021-complete-one-model-turn.md) | [One model turn](../docs/lessons/cah-021-one-model-turn.md) | M1 | Planned | CAH-020 |
| 14 | [CAH-022: Enforce loop limits](cah-022-enforce-loop-limits.md) | [Loop limits](../docs/lessons/cah-022-loop-limits.md) | M1 | Planned | CAH-021 |

See [backlog.md](backlog.md) for the milestone roadmap and the outcome-level E0-E9 backlog.

## Planning notes

- [2026-07-13 documentation baseline](notes/2026-07-13-documentation-baseline.md) records the
  decisions locked before implementation and the gaps observed in the initial scaffold.
- [2026-07-14 unit lesson standard](notes/2026-07-14-unit-lesson-standard.md) records the one-to-one
  story-to-lesson mapping, production-comparison rubric, and maintenance rule.
- [2026-07-14 CAH-001 dependency cleanup](notes/2026-07-14-cah-001-dependency-cleanup.md) records
  the final dependency decision, validation evidence, and environment issues encountered while
  completing the architecture story.
- [2026-07-15 CAH-008 documentation enforcement](notes/2026-07-15-cah-008-documentation-enforcement.md)
  records the Ruff policy, exemption boundary, negative probe, documentation audit, and validation
  evidence that completed the educational-documentation unit.
- [2026-07-15 CAH-002 Ink shell](notes/2026-07-15-cah-002-ink-shell.md) records the Node and npm
  contract, static shell boundaries, WSL launcher and temporary-directory discovery, test evidence,
  and manual terminal validation.
- [2026-07-15 CAH-003 Python runtime supervision](notes/2026-07-15-cah-003-python-runtime-supervision.md)
  records the exact `uv` launch request, workspace and stream contracts, bounded diagnostics,
  process-group cleanup discovery, and real Node-to-Python boundary evidence.
- [2026-07-16 CAH-004 protocol version 1](notes/2026-07-16-cah-004-protocol-v1.md) records the
  strict wire contract, failure taxonomy, readiness policy, fixture parity, and ordered-writer
  evidence.
