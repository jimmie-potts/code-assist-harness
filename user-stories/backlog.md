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
keeping the mock as the default. M1 is complete. CAH-025 is a completed E7 presentation unit: it
applies the responsive Magical Mission view to current conversation/runtime/session
truth without adding an agent capability. CAH-024 remains the first
implementation-ready E3 story: it plans an immutable Python workspace boundary while leaving
repository discovery and reads to later single-responsibility units.

## Epic backlog

The epics below intentionally remain outcome-level. Later implementation stories should receive
IDs only when they are refined with dependencies, acceptance criteria, and validation evidence.

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

Implementation-ready stories in this epic: CAH-020, CAH-021, CAH-022, and CAH-023. All four are
complete. The harness now owns one bounded provider turn with deterministic fake and explicitly
configured OpenAI paths; the SDK remains isolated behind the provider port.

### E3 - Repository context and read-only tools

**Outcome:** The agent retrieves relevant repository information without loading the entire
workspace.

- Establish a reusable Python boundary around the single canonical workspace root.
- Discover repository instructions and bounded context sources.
- Implement native file listing, bounded reads, text search, and path metadata tools.
- Track source locations, inclusion reasons, and context budgets.
- Evaluate known-file retrieval using fixture workspaces.

[CAH-024](cah-024-establish-workspace-boundary.md) is the first implementation-ready story in this
epic. It will validate contained, workspace-relative path targets against the selected root and
return immutable harness-owned path values. It does not discover instructions, read file content,
register model tools, or claim protection against filesystem changes after validation.

### E4 - Tool registry and controlled execution

**Outcome:** Tools have validated inputs, explicit capabilities, bounded behavior, and enforceable
policy.

- Register tools by name and runtime-validated schema.
- Classify read, write, command, network, and privileged capabilities.
- Reject unknown tools and unsupported arguments before execution.
- Run approved argument-array subprocesses without shell interpolation.
- Remove secrets, bound time and output, support cancellation, and emit audit events.
- Define an executor interface suitable for a later container implementation.

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

[CAH-025](cah-025-apply-magical-mission-ink-presentation.md) is the first implementation-ready story
focused on this epic's presentation outcome. It is **Done**: `App` retains input and callback
ownership while the Magical Mission view chooses wide, stacked, compact, no-color, and
reduced-decoration rendering for existing projections. It does not implement the future plan, tool,
result, diff, or approval-interaction bullets above; those remain dependent on their owning behavior
stories.

### E8 - Evaluation and observability

**Outcome:** Repeatable scenarios measure harness behavior instead of relying only on manual demos.

- Define fixture workspaces, tasks, fake-provider scripts, approval decisions, and expectations.
- Assert event order, terminal state, file state, limits, policy, conflicts, and timeouts.
- Collect steps, tool calls, context size, approvals, duration, tokens, and outcome.
- Keep optional live-provider smoke evaluations outside normal unit tests.

Initial deterministic scenarios cover normal streaming, cancellation, provider failure, malformed
protocol, unknown tools, limit exhaustion, rejected approvals, workspace escape, stale edits, and
command timeouts.

### E9 - Persistence, packaging, and future isolation

**Outcome:** Completed sessions can be inspected and the reusable core can run outside its own
repository with replaceable providers and executors.

- Browse, replay, and export completed session records.
- Install and launch the tool from another WSL repository.
- Separate user-level harness configuration from workspace configuration.
- Add a container executor, another provider, and an optional LangChain adapter behind existing
  interfaces.
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
