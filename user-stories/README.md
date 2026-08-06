# User stories

This directory is the implementation backlog for Code Assist Harness. The backlog keeps the
learning-first delivery sequence explicit while preserving the long-term goal of a reusable Python
harness library.

## How to use this backlog

- Start with the dependency-ordered story list below; do not select a story whose dependencies are
  incomplete.
- Treat acceptance criteria as the behavioral contract and the validation section as the minimum
  evidence required for completion.
- Use [story-template.md](story-template.md) when refining a new unit. Map acceptance criteria to
  deterministic tests and carry an explicit story-specific definition of done.
- Read the linked lesson before implementation and update it with concrete paths, tests, and
  observed trade-offs before marking the story done.
- Prioritize review of core learning units about context selection, the explicit agent loop, LLM
  response handling, tool contracts and dispatch, future MCP extension boundaries, safety, and
  evaluation.
  Supporting units remain independently tested but keep their lessons tighter.
- Target roughly 600 or fewer changed production lines per story, counting additions plus deletions
  under `src/code_assist_harness/` and `tui/src/`. Exclude tests, documentation, fixtures,
  lockfiles, and generated artifacts; split a unit that gains another responsibility instead of
  treating the target as a quota.
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

CAH-001, CAH-008, CAH-002, CAH-003, CAH-004, CAH-005, CAH-006, CAH-009, CAH-007, CAH-010,
CAH-011, CAH-020, CAH-021, CAH-022, and CAH-023 are
**Done**: the architecture baseline, documentation standard, Ink shell, supervised Python process,
protocol version 1 boundary, deterministic mocked-session slice, authoritative cancellation
lifecycle, fixture-backed walking-skeleton guide, offline repository/CI gate, and equivalent
cross-language session reducers are implemented and validated. The Python runtime now also writes
private, redacted, replayable session transcripts and honest summaries unless explicitly disabled.
CAH-020 exposes provider-neutral request and stream contracts plus a strict programmable fake.
CAH-021 adds the first injected fake-backed turn, strict stream grammar, terminal and cleanup
serialization, and bounded usage evidence. CAH-022 adds four validated hard limits, fresh per-session
tracking, deterministic deadline and cleanup supervision, and transcript-v3 loop evidence with
v1/v2/v3 replay. CAH-023 adds the strict OpenAI Responses adapter plus explicit cross-language
provider/model configuration while preserving the mock default. M0 and M1 are complete. The 16
implementation-ready M2 units, CAH-024 through CAH-039 in the dependency order below, all remain
**Planned**. CAH-024 is the next dependency checkpoint; the sequence then adds shared read policy,
scoped instructions and handlers, attributable context, a typed registry, bounded provider
definitions, provider-neutral tool exchange, atomic response and argument admission, complete
result-path instruction coverage through one explicit round trip, the bounded agent loop, strict
OpenAI tool mapping, and deterministic vertical-slice evaluation.

## Dependency-ordered implementation sequence

| Order | Story | Lesson | Milestone | Status | Depends on |
| ---: | --- | --- | --- | --- | --- |
| 1 | [CAH-001: Record the architecture decisions](cah-001-record-architecture-decisions.md) | [Architecture decisions](../docs/lessons/cah-001-architecture-decisions.md) | M0 | Done | None |
| 2 | [CAH-008: Establish educational documentation standards](cah-008-establish-documentation-standards.md) | [Documentation standards](../docs/lessons/cah-008-documentation-standards.md) | M0 | Done | CAH-001 |
| 3 | [CAH-002: Bootstrap the Ink application](cah-002-bootstrap-ink-application.md) | [Ink application shell](../docs/lessons/cah-002-ink-application-shell.md) | M0 | Done | CAH-001, CAH-008 |
| 4 | [CAH-003: Start and supervise the Python runtime](cah-003-supervise-python-runtime.md) | [Python runtime supervision](../docs/lessons/cah-003-python-runtime-supervision.md) | M0 | Done | CAH-002 |
| 5 | [CAH-004: Define protocol version 1](cah-004-define-protocol-v1.md) | [Protocol version 1](../docs/lessons/cah-004-protocol-v1.md) | M0 | Done | CAH-003 |
| 6 | [CAH-005: Stream a mocked session end to end](cah-005-stream-mocked-session.md) | [Mocked streaming session](../docs/lessons/cah-005-mocked-streaming-session.md) | M0 | Done | CAH-002, CAH-003, CAH-004 |
| 7 | [CAH-006: Cancel an active session](cah-006-cancel-active-session.md) | [Session cancellation](../docs/lessons/cah-006-session-cancellation.md) | M0 | Done | CAH-005 |
| 8 | [CAH-009: Document the first end-to-end execution](cah-009-document-walking-skeleton.md) | [Walking-skeleton guide](../docs/lessons/cah-009-walking-skeleton-guide.md) | M0 | Done | CAH-006 |
| 9 | [CAH-007: Establish repository-wide checks](cah-007-establish-repository-checks.md) | [Repository-wide checks](../docs/lessons/cah-007-repository-checks.md) | M0 | Done | CAH-009 |
| 10 | [CAH-010: Implement session state as a reducer](cah-010-session-state-reducer.md) | [Session state reducer](../docs/lessons/cah-010-session-state-reducer.md) | M1 | Done | CAH-004, CAH-006, CAH-007 |
| 11 | [CAH-011: Write an append-only transcript](cah-011-append-only-transcript.md) | [Append-only transcript](../docs/lessons/cah-011-append-only-transcript.md) | M1 | Done | CAH-010 |
| 12 | [CAH-020: Define the provider interface and fake provider](cah-020-provider-interface-and-fake.md) | [Provider interface and fake](../docs/lessons/cah-020-provider-interface-and-fake.md) | M1 | Done | CAH-010, CAH-011 |
| 13 | [CAH-021: Run one provider-neutral turn](cah-021-complete-one-model-turn.md) | [One provider-neutral turn](../docs/lessons/cah-021-one-model-turn.md) | M1 | Done | CAH-020 |
| 14 | [CAH-022: Enforce loop limits](cah-022-enforce-loop-limits.md) | [Loop limits](../docs/lessons/cah-022-loop-limits.md) | M1 | Done | CAH-021 |
| 15 | [CAH-023: Add the OpenAI Responses adapter](cah-023-add-openai-responses-adapter.md) | [OpenAI Responses adapter](../docs/lessons/cah-023-openai-responses-adapter.md) | M1 | Done | CAH-022 |
| 16 | [CAH-024: Establish the workspace boundary](cah-024-establish-workspace-boundary.md) | [Workspace boundary](../docs/lessons/cah-024-workspace-boundary.md) | M2 | Planned | CAH-023 |
| 17 | [CAH-026: Define repository read contracts and policy](cah-026-define-repository-read-contracts.md) | [Repository read policy](../docs/lessons/cah-026-repository-read-policy.md) | M2 | Planned | CAH-024 |
| 18 | [CAH-025: Discover scoped repository instructions](cah-025-discover-repository-instructions.md) | [Scoped repository instructions](../docs/lessons/cah-025-repository-instructions.md) | M2 | Planned | CAH-024, CAH-026 |
| 19 | [CAH-027: List files and inspect path metadata](cah-027-list-files-and-stat-path.md) | [Repository listing and metadata](../docs/lessons/cah-027-list-files-and-stat-path.md) | M2 | Planned | CAH-026 |
| 20 | [CAH-028: Read one bounded text file](cah-028-read-bounded-text-file.md) | [Bounded repository reads](../docs/lessons/cah-028-bounded-text-file.md) | M2 | Planned | CAH-026 |
| 21 | [CAH-029: Search repository text literally](cah-029-search-repository-text.md) | [Literal repository search](../docs/lessons/cah-029-literal-text-search.md) | M2 | Planned | CAH-027, CAH-028 |
| 22 | [CAH-030: Build budgeted repository context](cah-030-build-budgeted-context.md) | [Budgeted repository context](../docs/lessons/cah-030-budgeted-context.md) | M2 | Planned | CAH-025, CAH-027, CAH-028, CAH-029 |
| 23 | [CAH-031: Register and dispatch read-only tools](cah-031-register-read-tools.md) | [Read-tool registry](../docs/lessons/cah-031-read-tool-registry.md) | M2 | Planned | CAH-027, CAH-028, CAH-029 |
| 24 | [CAH-038: Canonicalize provider tool definitions](cah-038-canonicalize-provider-tool-definitions.md) | [Bounded provider tool definitions](../docs/lessons/cah-038-bounded-provider-tool-definitions.md) | M2 | Planned | CAH-031 |
| 25 | [CAH-032: Define the provider-neutral tool contract](cah-032-define-provider-tool-contract.md) | [Provider-neutral tool contract](../docs/lessons/cah-032-provider-tool-contract.md) | M2 | Planned | CAH-030, CAH-031, CAH-038 |
| 26 | [CAH-033: Stage and validate one tool-aware response](cah-033-stage-and-validate-tool-aware-response.md) | [Tool-aware response admission](../docs/lessons/cah-033-tool-aware-response-admission.md) | M2 | Planned | CAH-032 |
| 27 | [CAH-039: Admit one provider tool argument object](cah-039-admit-provider-tool-arguments.md) | [Provider tool-argument admission](../docs/lessons/cah-039-provider-tool-argument-admission.md) | M2 | Planned | CAH-031, CAH-032, CAH-038 |
| 28 | [CAH-034: Run one read-tool round trip](cah-034-run-one-read-tool-round-trip.md) | [One read-tool round trip](../docs/lessons/cah-034-one-read-tool-round-trip.md) | M2 | Planned | CAH-030, CAH-031, CAH-032, CAH-033, CAH-039 |
| 29 | [CAH-035: Run the bounded agent loop](cah-035-run-bounded-agent-loop.md) | [Bounded agent loop](../docs/lessons/cah-035-bounded-agent-loop.md) | M2 | Planned | CAH-034 |
| 30 | [CAH-036: Map OpenAI Responses tool calls](cah-036-map-openai-tool-calls.md) | [OpenAI tool-call mapping](../docs/lessons/cah-036-openai-tool-calls.md) | M2 | Planned | CAH-035 |
| 31 | [CAH-037: Prove the read-only assistant](cah-037-prove-read-only-assistant.md) | [Read-only assistant evaluation](../docs/lessons/cah-037-read-only-assistant-evaluation.md) | M2 | Planned | CAH-024 through CAH-036, CAH-038, CAH-039 |

See [backlog.md](backlog.md) for the milestone roadmap and the outcome-level E0-E9 backlog.

## M2 learning emphasis

CAH-024 through CAH-026, CAH-030 through CAH-037, and CAH-039 are core learning units. Give the
closest review attention to the registry-to-evaluation sequence—CAH-031, CAH-038, CAH-032, CAH-033,
CAH-039, then CAH-034 through CAH-037. It exposes the registry boundary, provider-neutral LLM/tool
grammar, atomic response and argument admission, one complete function-calling exchange, the
bounded harness-owned loop, scoped context evolution, and strict OpenAI response mapping. CAH-037
then tests whether those parts produce grounded behavior rather than merely type-checking in
isolation.

CAH-027 through CAH-029 and CAH-038 are supporting implementation units. Their correctness and
failure tests are still required, but their lessons stay shorter because they implement filesystem
primitives or bounded definition plumbing consumed by the higher-value agentic design units. MCP
remains a later transport/discovery adapter to the registry; M2 teaches the seam and trust boundary
without adding a remote server or network path.

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
- [2026-07-30 CAH-005 mocked streaming session](notes/2026-07-30-cah-005-mocked-streaming-session.md)
  records the fixed event tape, reducer boundary, scheduling seam, real-process evidence, and work
  deliberately left to cancellation.
- [2026-07-30 CAH-006 session cancellation](notes/2026-07-30-cah-006-session-cancellation.md)
  records cooperative cancellation ownership, terminal-race serialization, idempotent request
  handling, visible TUI states, and deterministic evidence across the real process boundary.
- [2026-07-30 CAH-009 walking-skeleton guide](notes/2026-07-30-cah-009-walking-skeleton-guide.md)
  records the normalized teaching tapes, documentation-to-fixture checks, ownership trace, and work
  deliberately left to later runtime stories.
- [2026-07-30 CAH-007 repository checks](notes/2026-07-30-cah-007-repository-checks.md) records the
  canonical offline gate, Linux workflow, policy guards, failure probes, visual lesson evidence, and
  M0-to-M1 handoff.
- [2026-07-30 CAH-010 session reducer](notes/2026-07-30-cah-010-session-state-reducer.md) records the
  domain-versus-wire input boundary, canonical transitions, strict terminal policy, shared fixture
  evidence, runtime integration, and visual lesson validation.
- [2026-07-30 CAH-011 append-only transcript](notes/2026-07-30-cah-011-append-only-transcript.md)
  records the transcript schema, privacy and filesystem boundaries, replay behavior, recoverable
  warning integration, interruption evidence, and visual lesson validation.
- [2026-07-30 CAH-020 provider interface and fake provider](notes/2026-07-30-cah-020-provider-interface-and-fake.md)
  records the provider-neutral port, strict fake script, logical checkpoint and cancellation
  behavior, content-safe mismatch diagnostics, test evidence, and handoff to CAH-021.
- [2026-07-31 CAH-021 story split](notes/2026-07-31-cah-021-story-split.md) records why the
  provider-neutral turn, hard limits, and OpenAI adapter are three dependency-ordered units and
  locks their planned-versus-implemented boundary.
- [2026-07-31 CAH-021 one provider-neutral turn](notes/2026-07-31-cah-021-one-model-turn.md) records
  the strict stream grammar, transaction and cleanup boundaries, transcript-v2 usage evidence,
  deterministic validation, and handoff to CAH-022.
- [2026-07-31 CAH-022 loop limits](notes/2026-07-31-cah-022-loop-limits.md) records the four-field
  budget, deadline and cleanup race semantics, stable failure codes, transcript-v3 evidence,
  deterministic validation, and handoff to CAH-023. The linked
  [visual lesson](../docs/lessons/assets/cah-022-loop-limits.pptx) accompanies the written lesson.
- [2026-08-01 CAH-023 OpenAI Responses adapter](notes/2026-08-01-cah-023-openai-responses-adapter.md)
  records the configuration gate, strict event automaton, cleanup ownership, deterministic and
  optional-live validation boundary, and Markdown learning evidence.
- [2026-08-02 CAH-023 adversarial-review hardening](notes/2026-08-02-cah-023-adversarial-review-hardening.md)
  records the credential, environment, stream-validation, and cleanup fixes plus the deliberately
  unchanged model and refusal boundaries.
- [2026-08-02 CAH-024 workspace-boundary planning](notes/2026-08-02-cah-024-workspace-boundary-planning.md)
  records the E3 story split, the decisions already fixed by the architecture, and the boundary
  between planned path containment and later filesystem access.
- [2026-08-03 M2 read-only assistant planning](notes/2026-08-03-m2-read-only-assistant-planning.md)
  records the 16-story vertical slice, learning priorities, exact loop and tool-exchange defaults,
  review-size policy, and the distinction between local function calling and a future MCP adapter.
- [2026-08-03 PR 28 review churn learnings](notes/2026-08-03-pr-28-review-learnings.md) records the
  complete finding taxonomy, contract-neighborhood audit, single-responsibility splits, and
  pre-review evidence adopted to prevent repeated review rounds.
