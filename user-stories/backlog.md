# Product backlog

## Product statement

Code Assist Harness is a local, keyboard-first coding agent for Ubuntu under WSL. It can inspect
and explain a repository, form an implementation plan, propose controlled file changes, run
approved validation commands, display the resulting diff, and summarize the result.

The first release is a personal learning project. Its Python core must nevertheless remain
separate from the TUI, provider, and execution environment so it can later become a reusable
library.

## Milestone roadmap

| Milestone | Vertical slice | Result |
| --- | --- | --- |
| M0 - Walking skeleton | Mock agent through the real Python-Ink protocol | A task travels from the TUI to Python and streamed events return to the UI. |
| M1 - Conversational core | Explicit loop with fake and OpenAI providers | The harness completes one provider turn with cancellation and hard limits. |
| M2 - Read-only coding assistant | Repository context and native read tools | The agent can inspect, explain, and formulate a grounded plan. |
| M3 - Controlled coding agent | Approvals, edit proposals, commands, and diffs | The agent can modify and validate code without acting silently. |
| M4 - Reliability layer | Evaluation, transcripts, replay, and failure hardening | Loop, context, tool, and safety regressions are measurable. |
| M5 - Reusable harness | Packaging, extension APIs, and stronger isolation | Other interfaces, providers, and executors can reuse the core. |

Evaluation starts with deterministic M0 scenarios. M4 expands evaluation rather than introducing
it for the first time.

## Delivery timeline

**Last updated:** 2026-08-03 after PR #24 completed M1 and PR #28 review refined M2.

This is the authoritative delivery timeline. It tracks dependency and outcome checkpoints, not a
calendar forecast. Add target dates only when the remaining work in a milestone has been decomposed
enough to estimate; until then, `TBD` is more honest than extrapolating from differently sized
stories.

| Order | Milestone | Status | Actual or target | Implementation-ready coverage | Next checkpoint |
| ---: | --- | --- | --- | --- | --- |
| 1 | M0 - Walking skeleton | Done | Completed 2026-07-30 | 9 of 9 stories Done | Complete |
| 2 | M1 - Conversational core | Done | Completed 2026-08-03 | 6 of 6 stories Done | Complete |
| 3 | M2 - Read-only coding assistant | Current / Planned | TBD | 16 Planned stories, CAH-024 through CAH-039 in documented dependency order; see the [refined M2 plan](notes/2026-08-03-m2-read-only-assistant-planning.md) | Implement CAH-024 |
| 4 | M3 - Controlled coding agent | Not decomposed | TBD | No implementation-ready M3 story | Complete M2, then refine tool, approval, edit, and validation slices |
| 5 | M4 - Reliability layer | Not decomposed | TBD | No implementation-ready M4 story; deterministic evaluation and transcript foundations already exist | Complete the controlled workflow, then refine reliability expansion |
| 6 | M5 - Reusable harness | Not decomposed | TBD | No implementation-ready M5 story | Complete the reliability exit, then refine packaging and isolation |

### Progress and planning coverage

These ratios count checkpoints, not elapsed time, effort, or remaining complexity.

| Measure | Current state | Interpretation |
| --- | --- | --- |
| Full roadmap progress | 2 of 6 milestone outcomes complete (33%) | The project is entering M2, milestone 3 of 6. |
| MVP capability progress | 2 of 4 milestones through the M3 controlled-coding outcome complete (50%) | This is a capability-checkpoint count, not a release forecast. |
| Outcome-level planning | 6 of 6 milestones and 10 of 10 epics have defined outcomes | The product direction is mapped at a useful high level. |
| Story-level planning | 31 implementation-ready stories: 15 Done and 16 Planned | 48% of the currently refined inventory is Done; this is not a product-completion percentage. |
| Ready-story runway | The complete 16-story M2 sequence | CAH-024 is next; CAH-026 then supplies shared hard-deny policy before CAH-025, and the remaining M2 stories follow explicit dependencies. |

The M0/M1 work in E0 through E2 is decomposed and complete. The complete M2 vertical slice is now
refined across E2, E3, the read-only kernel of E4, and one E8 evaluation story. M3 through M5 remain
outcome-level, so there is no defensible product-completion percentage or calendar ETA beyond the
milestone checkpoint counts above. Update this section when a story changes status, a milestone
meets its exit outcome, or another milestone is refined; move completion dates from `TBD` only when
there is corresponding delivery evidence.

CAH-005 completes the first task-to-response M0 slice: Ink sends a validated task through the real
Node-to-`uv`-to-Python boundary, Python emits a fixed three-delta response, and the TUI renders each
validated event while preserving correlation and session-local order. CAH-006 makes that same path
cancellable: Escape sends one addressable request, Python cooperatively selects either cancellation
or prior completion, and the TUI waits for the authoritative terminal event. CAH-009 turns that
verified walking skeleton into a fixture-backed learner guide without changing production behavior.
CAH-007 closes M0 with one offline `./scripts/check` gate and lockfile-driven Linux workflow for every
current Python, TypeScript, protocol, policy, documentation, and real-boundary layer. CAH-010 begins
M1 with pure Python and TypeScript lifecycle reducers, one reviewed transition matrix, shared replay
fixtures, and integration through the existing mock and TUI paths. CAH-011 now persists redacted,
bounded trusted lifecycle inputs and honest summaries under private XDG state, supports strict
side-effect-free replay and local opt-out, and reports persistence loss without becoming a second
source of truth. CAH-020 now supplies provider-neutral request and stream types plus a strict,
network-free programmable fake. CAH-021 now connects that port to one provider-neutral, fake-backed
turn through an injected runtime seam, with strict observation grammar and bounded usage evidence.
CAH-022 puts four validated hard limits, fresh per-session accounting, deterministic deadline and
cleanup supervision, and transcript-v3 loop evidence around that turn. CAH-023 now activates one
explicitly configured, text-only OpenAI Responses adapter behind that bounded provider port while
keeping the mock as the default. M1 is complete. CAH-024 is the next dependency-ready E3 story: it
plans an immutable Python workspace boundary while leaving repository discovery and reads to the
now-refined CAH-026, CAH-025, then CAH-027 through CAH-030 units. CAH-026 intentionally precedes
CAH-025 so instruction discovery reuses pure lexical/hard-deny admission without importing
ordinary-read limits, errors, or `.gitignore` behavior. CAH-031 through CAH-039, in documented
dependency order, complete the planned M2 registry, bounded definition bridge,
requested/result-path instruction propagation, LLM/tool exchange, atomic provider-response and
argument admission, explicit agent loop, OpenAI mapping, and evaluation sequence.

## Epic backlog

The epics below retain stable outcome-level ownership. M2 work across E2, E3, E4, and E8 is now
refined into CAH-024 through CAH-039 in documented dependency order; later milestone work should
receive IDs only when it has dependencies, acceptance criteria, review sizing, and validation
evidence.

### E0 - Architecture and WSL walking skeleton

**Outcome:** Ink and Python form one reliable WSL application before model or tool complexity is
introduced.

- Record the architecture and educational documentation standards.
- Add the TypeScript/Ink application and pin its Node runtime.
- Start and supervise Python as a child process through `uv`.
- Define a versioned NDJSON protocol with cross-language fixtures.
- Stream a deterministic mocked session and support clean cancellation.
- Establish one repository-wide, non-live validation workflow.

All implementation-ready M0 stories, CAH-001 through CAH-009, are complete.

### E1 - Session, state, and event model

**Outcome:** Every run has explicit lifecycle state, ordered events, structured failures, and a
replayable local record.

- Define commands, events, legal transitions, correlation IDs, and monotonic sequence numbers.
- Make cancellation a first-class terminal state.
- Write trusted domain facts and validated events to append-only, redacted transcripts.
- Reconstruct visible state by replaying ordered lifecycle inputs from `idle`.

CAH-010 and CAH-011 are complete. Their reducer and durable-evidence outcomes unlocked CAH-020 through
CAH-022. The transcript writer now emits version 3, replay accepts versions 1, 2, and 3, and optional
provider usage and provider-backed loop-limit observations remain a separate evidence projection
rather than lifecycle state. A version-3 mock tape may omit loop evidence.

### E2 - Provider interface and explicit agent loop

**Outcome:** The harness owns a bounded, testable model loop without framework orchestration.

- Define provider-neutral request and stream types.
- Build a programmable fake provider before the OpenAI adapter.
- Execute one provider-neutral turn and stream text before introducing a network adapter.
- Enforce model-turn admission, provider-work deadline, output, and observed tool-call limits.
- Add the OpenAI Responses adapter only after the provider-neutral turn and hard limits pass.
- Keep OpenAI SDK types and future LangChain adapters outside core domain types.

CAH-020 through CAH-023 are complete. The harness now owns one bounded provider turn with
deterministic fake and explicitly configured OpenAI paths; the SDK remains isolated behind the
provider port. Planned M2 stories CAH-038, CAH-032, CAH-033, CAH-039, and CAH-034 through CAH-036
extend that same seam with bounded provider definitions, positional opaque continuation, raw calls,
correlated results, atomic full-response and argument admission, one explicit round trip, bounded
sequential iteration, and strict OpenAI Responses tool-call translation. Parallel calls and
framework-owned orchestration remain excluded.

### E3 - Repository context and read-only tools

**Outcome:** The agent retrieves relevant repository information without loading the entire
workspace.

- Establish a reusable Python boundary around the single canonical workspace root.
- Discover repository instructions and bounded context sources.
- Implement native file listing, bounded reads, text search, and path metadata tools.
- Track source locations, inclusion reasons, and context budgets.
- Evaluate known-file retrieval using fixture workspaces.

CAH-024 through CAH-030 are the implementation-ready E3 sequence. They separate the canonical
workspace boundary, common hard-deny/read policy, scoped repository instructions, listing and metadata,
bounded text reads, literal search, and attributable context selection. CAH-024 is first and does
not discover instructions, read file content, register model tools, or claim protection against
filesystem changes after validation. CAH-037 later proves these pieces through the composed M2
vertical slice.

### E4 - Tool registry and controlled execution

**Outcome:** Tools have validated inputs, explicit capabilities, bounded behavior, and enforceable
policy.

- Register tools by name and runtime-validated schema.
- Classify read, write, command, network, and privileged capabilities.
- Reject unknown tools and unsupported arguments before execution.
- Run approved argument-array subprocesses without shell interpolation.
- Remove secrets, bound time and output, support cancellation, and emit audit events.
- Define an executor interface suitable for a later container implementation.

CAH-031 is the implementation-ready M2 registry kernel. It owns typed registration, dispatch, and
harness-only ordered instruction-scope extraction for execution-time canonical request and
model-visible result paths from the already-defined native read handlers. CAH-038 atomically turns
those descriptors into bounded provider definitions. CAH-039's registry-only factory invokes that
bridge internally, atomically binds its definitions to the exact CAH-031 registry identity,
re-exposes `catalog.definitions` to every request, and admits raw provider
arguments into a same-entry prepared call. CAH-034/035 dispatch only through that same catalog; those
loop units use result metadata without
re-resolving a request alias, require each discovered bundle to retain the captured canonical scope,
and add every applicable instruction before result replay or another provider turn. M3 retains write
and command capabilities, layered policy, approvals, subprocess execution, network behavior, and
executor isolation.

### E5 - Safety and human approval

**Outcome:** Side effects occur only after a clear, current, and informed approval.

- Approve one validated edit batch and each subprocess command individually.
- Display exact operations, command arguments, working directory, and risk classification.
- Prevent stale approvals from authorizing changed actions.
- Enforce workspace and symlink boundaries.
- Deny prohibited command families even when a user could otherwise approve them.
- Record both the decision and exact authorized action.

### E6 - Coding workflow and validation

**Outcome:** The agent completes the MVP workflow from explicit plan through an applied and tested
diff.

- Represent plan changes as session state, separate from conversational prose.
- Propose structured multi-file edit batches and generate unified diffs in the harness.
- Apply approved edits only when file-hash preconditions still hold.
- Suggest checks, run each approved command, and feed bounded failures back into the loop.
- Produce a grounded final summary of changed files and validation results.

### E7 - Ink TUI experience

**Outcome:** The user can understand and control the agent without reading raw protocol or logs.

- Render streamed conversation and persistent lifecycle status.
- Expand and collapse plans, tool calls, results, errors, and multi-file diffs.
- Present focused approval interactions while preserving pending input.
- Support cancellation, narrow terminals, resize, and child/protocol failures.
- Test reducers separately and important screens with `ink-testing-library`.

### E8 - Evaluation and observability

**Outcome:** Repeatable scenarios measure harness behavior instead of relying only on manual demos.

- Define fixture workspaces, tasks, fake-provider scripts, approval decisions, and expectations.
- Assert event order, terminal state, file state, limits, policy, conflicts, and timeouts.
- Collect steps, tool calls, context size, approvals, duration, tokens, and outcome.
- Keep optional live-provider smoke evaluations outside normal unit tests.

Initial deterministic scenarios cover normal streaming, cancellation, provider failure, malformed
protocol, unknown tools, limit exhaustion, rejected approvals, workspace escape, stale edits, and
command timeouts.

CAH-037 is the implementation-ready M2 evaluation slice. It composes a fixture workspace, strict
fake-provider script, context selection, read registry, and bounded loop to prove grounded read-only
behavior. The general scenario format and the broader safety/reliability matrix remain M4 work.

### E9 - Persistence, packaging, and future isolation

**Outcome:** Completed sessions can be inspected and the reusable core can run outside its own
repository with replaceable providers and executors.

- Browse, replay, and export completed session records.
- Install and launch the tool from another WSL repository.
- Separate user-level harness configuration from workspace configuration.
- Add a container executor, another provider, and an optional LangChain adapter behind existing
  interfaces.
- Consider a trusted MCP client adapter behind the stable tool registry only after remote trust,
  authentication, network policy, catalog-change, and cancellation semantics are designed.
- Consider resumable sessions only after deterministic event replay is stable.

## MVP boundary

The MVP automatically performs bounded native repository reads and searches. It explains code,
maintains a visible plan, proposes structured edits, asks before applying an edit batch, asks before
every allowlisted subprocess, shows diffs, runs approved validation, cancels cleanly, and writes a
human-readable local session record.

The MVP does not modify Git state, run autonomously, expose network tools, use multiple agents,
orchestrate through LangChain, use embeddings, resume sessions, execute in containers, support
native Windows or macOS, or implement more than the provider interface plus its first OpenAI
adapter.
