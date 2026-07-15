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

CAH-003 completes the physical M0 process boundary: Ink now starts one workspace-bound Python
runtime through `uv`, reports failures, and reaps the detached process group. CAH-004 is the next
dependency-ready unit and will give the reserved stdin/stdout pipes their first validated,
versioned NDJSON messages and readiness semantics.

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

Implementation-ready stories: CAH-001 through CAH-009.

### E1 - Session, state, and event model

**Outcome:** Every run has explicit lifecycle state, ordered events, structured failures, and a
replayable local record.

- Define commands, events, legal transitions, correlation IDs, and monotonic sequence numbers.
- Make cancellation a first-class terminal state.
- Write validated events to append-only, redacted transcripts.
- Reconstruct visible state by replaying events.

Implementation-ready stories at the start of this epic: CAH-010 and CAH-011.

### E2 - Provider interface and explicit agent loop

**Outcome:** The harness owns a bounded, testable model loop without framework orchestration.

- Define provider-neutral request and stream types.
- Build a programmable fake provider before the OpenAI adapter.
- Execute one turn, stream text, and later interpret tool calls across multiple turns.
- Enforce step, time, output, and tool-call limits.
- Keep OpenAI SDK types and future LangChain adapters outside core domain types.

Implementation-ready stories at the start of this epic: CAH-020, CAH-021, and CAH-022.

### E3 - Repository context and read-only tools

**Outcome:** The agent retrieves relevant repository information without loading the entire
workspace.

- Establish a single validated workspace root.
- Discover repository instructions and bounded context sources.
- Implement native file listing, bounded reads, text search, and path metadata tools.
- Track source locations, inclusion reasons, and context budgets.
- Evaluate known-file retrieval using fixture workspaces.

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
