# Code Assist Harness architecture

**Status:** Accepted target architecture; implementation is incremental.

Code Assist Harness is a local, keyboard-first coding agent for Ubuntu under WSL. It is a
personal learning project first, but its Python core is deliberately separated from the user
interface, model provider, and execution environment so it can later become a reusable library.

This document describes the agreed destination. It does not claim that every component exists
yet. The architectural decision records in `docs/adr/` explain why the main choices were made,
and `docs/glossary.md` defines the domain language used here and in the code.

## Status of the repository

The repository began as a small Python 3.12 source-layout scaffold with one package-import test,
pytest, Ruff, `uv`, and LangChain dependencies. It did not contain an agent, model call, TUI,
protocol, tool, or executor implementation.

CAH-001 superseded the scaffold's description of LangChain as the project's foundation. CAH-002
added the npm-managed Ink shell, WSL-aware launcher, Node pin, and TypeScript checks. CAH-003 added
the minimal Python entry point, canonical single-workspace selection, and Node child-process
supervision. CAH-004 gave those pipes a strict protocol version 1 contract, cross-language fixtures,
bounded readers, ordered event writes, and a validated readiness handshake. CAH-005 now connects
editable Ink input to a deterministic Python session: three delayed deltas are reduced and rendered
before exact assistant and session completion, and a second session runs with a new ID and sequence
reset. CAH-006 adds Escape-driven cooperative cancellation: the TUI sends one addressable request,
Python serializes cancellation against assistant and terminal writes, and exactly one cancelled or
completed outcome wins. CAH-009 records that implemented path in a fixture-backed
[walking-skeleton guide](walking-skeleton.md), without adding runtime behavior. CAH-007 adds the
offline `./scripts/check` gate and lockfile-driven Linux workflow that run the complete M0 evidence
through one developer/CI entry point. CAH-010 begins M1 with equivalent pure Python and TypeScript
session-lifecycle reducers, shared transition and replay fixtures, structured invariant failures,
and integration through the mock runtime and TUI projection. CAH-011 adds private XDG transcript
storage, privacy-aware typed sanitization, honest terminal summaries, strict side-effect-free replay,
local opt-out, and recoverable persistence warnings. CAH-020 adds immutable provider-neutral request
and stream values, an explicit asynchronous operation port, and a strict deterministic fake without
changing the launched `MockSession` runtime or TUI. CAH-021 adds `ProviderSession`, one strict
fake-backed turn, an injected-provider runtime seam, and bounded usage evidence. CAH-022 adds four
validated hard limits, per-session accounting, deterministic deadline and cleanup supervision, and
transcript-v3 loop-limit evidence with v1/v2/v3 replay. CAH-023 adds SDK-free provider configuration,
an exact-model foreground OpenAI Responses adapter, explicit TUI/Python composition, deterministic
SDK-fake coverage, and an opt-in live smoke. The launch still defaults to the deterministic mock and
protocol v1 is unchanged. CAH-024 is implementation-ready but still planned; it will add the first
M2 primitive, an immutable Python workspace boundary, without file reads or protocol changes. Tool
execution, workspace discovery and reads, policy, and broader agent behavior remain target
architecture.

## Product boundary

The MVP will let a user:

- inspect, search, and read files in one repository automatically;
- ask repository questions and receive grounded explanations;
- review an implementation plan;
- review a generated diff before approving a batch of structured file changes;
- approve each validation command individually;
- cancel active work cleanly; and
- inspect a human-readable, append-only session record.

The MVP will not modify Git state, operate without approvals, expose network tools, orchestrate
multiple agents, use embeddings, resume interrupted sessions, run tools in a container, support
native Windows or macOS, or implement more than one real model-provider adapter. It also will not
use LangChain to orchestrate the agent loop.

## Process boundary

```text
┌──────────────────────────────────────────────┐
│ Ink TUI — TypeScript / Node                  │
│                                              │
│ Conversation · plan · tool calls · diffs     │
│ Input · approvals · cancellation · status    │
└──────────────────────┬───────────────────────┘
                       │ versioned NDJSON
             commands  │ stdin
               events  │ stdout
          diagnostics  │ stderr
                       ▼
┌──────────────────────────────────────────────┐
│ Python harness runtime                       │
│                                              │
│ Session · agent loop · context · tools       │
│ Policy · providers · transcripts             │
└───────────────┬──────────────────┬───────────┘
                │                  │
                ▼                  ▼
       Model provider       Workspace executor
```

Both processes run inside Ubuntu under WSL and use Linux paths. The Ink process owns the terminal
and starts Python through a resolved, prevalidated Linux `uv` executable. The current directory is
the default workspace; `--workspace PATH` selects a different single workspace for the process.
Multi-root workspaces are out of scope.

CAH-003 implements that launch as one shell-free argument array:

```text
PREVALIDATED_LINUX_UV run --project REPOSITORY_ROOT --frozen
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  --python VENV_PYTHON
  -- python -E -m code_assist_harness.runtime --provider PROVIDER [--model EXACT_SNAPSHOT]
     --workspace CANONICAL_WORKSPACE
```

The line breaks above are explanatory only; Node passes each token as a separate argument with
`shell: false`. Before spawning, the supervisor resolves `uv` from a filtered `PATH`, follows its
real path, and rejects a path under `/mnt` or a name ending in `.exe`. It also requires both
`REPOSITORY_ROOT/.venv/pyvenv.cfg` and an executable `VENV_PYTHON` at `.venv/bin/python`. A failed
preflight does not invoke `uv`, create `.venv`, or otherwise mutate the repository. The harness
repository is `uv`'s project and child working directory, while the target repository is a distinct,
canonical `--workspace` value. `PROVIDER` defaults to `mock`; `openai` requires the exact
`gpt-5.6-luna` model. TypeScript validates the pair before child construction, and
Python validates it again before SDK import. These launch values are configuration arguments, not
NDJSON fields.

The explicit interpreter and launch flags keep the prepared environment fixed: `--frozen`
prevents lockfile updates, `--no-sync` avoids synchronizing the existing environment, and the
remaining flags prevent project `.env` loading, network access, progress output, and Python
downloads. The child receives a filtered copy of the parent environment that removes `PYTHONPATH`,
`PYTHONHOME`, `VIRTUAL_ENV`, and every `UV_*` variable without claiming a generally reduced
environment. The supported project, environment, and interpreter choices are supplied explicitly
in the argument array instead. Developers create or refresh the locked environment with
`uv sync --dev`; the preflight proves only that the required environment structure exists, not that
it is current with `uv.lock`.

The operating-system spawn event now establishes only the physical process. Node writes a validated
`runtime.initialize` command and remains `starting` until a strictly parsed, correctly correlated
`runtime.ready` confirms the same canonical workspace. Both byte readers impose a 64-KiB line
bound, require LF framing, decode UTF-8 strictly, and can resynchronize at the LF after one bad
physical line. Python uses that recovery capability for command stdin. The TUI deliberately stops
after the first bad or unexpected stdout event: it enters a visible `protocol-failed` state and
closes command input rather than trusting any later event. Encoders enforce the same byte bound so
local writers cannot produce a line the peer must reject.

stderr alone feeds a bounded, sanitized failure summary. If the byte-tail bound begins inside a
physical line, sanitization drops that leading partial line before inspecting the remainder.
Recognized separator-delimited and common camel-case or concatenated credential names consume their
complete physical-line values, so multi-part authorization, cookie, and common API-key values
cannot remain visible.

After Ink reports exit and restores the terminal, the application lifecycle queues a validated
`runtime.shutdown` command and closes stdin without waiting indefinitely for a write callback. If
the child does not close during the grace period,
Node sends `SIGTERM` and then `SIGKILL` to the detached uv/Python process group. Cleanup resolves
only after the child `close` event, which proves the wrapper and its pipes were reaped. Any close
before requested shutdown, including exit code zero, becomes a visible failure; the supervisor does
not restart the runtime. Parent `SIGHUP` and `SIGTERM` handlers unmount Ink and route through the
same asynchronous cleanup while preserving conventional signal exit codes.

After readiness, the implemented M0 session path is:

```text
Ink input -> PythonRuntimeSupervisor.submitTask -> session.start NDJSON
  -> runtime.run_runtime -> MockSessionRunner creates MockSession
  -> OrderedEventWriter returns each validated event -> Python lifecycle reducer
  -> completed six-event tape or shortened cancelled tape -> supervisor lifecycle reducer
  -> multi-turn conversation adapter -> App conversation and status rendering

Escape while running -> PythonRuntimeSupervisor.cancelSession -> session.cancel NDJSON
  -> MockSession.request_cancellation -> cooperative checkpoint wake-up
  -> session.cancelled if cancellation wins, or session.completed if completion already won
```

The supervisor publishes the local submission before writing the command, so even an immediate
`session.started` cannot arrive before the projection knows its correlation ID. Python owns the
active-session decision and authoritative event tape. The TUI also blocks whitespace and overlap
for immediate feedback, but the runtime independently rejects them as `invalid_task` and
`session_active`. After `session.started` exposes a session ID, the supervisor can publish one local
`cancel.requested` update and send one validated `session.cancel`. That local update projects
`cancelling`; only a terminal Python event projects `cancelled` or `completed`. Normal shutdown
still drains the bounded mock, while user-requested cancellation wakes its current checkpoint.
The [walking-skeleton guide](walking-skeleton.md) follows these exact functions and both terminal
paths using normalized protocol examples checked by the Python and TypeScript test suites.

An explicit OpenAI launch, or a deterministic test injecting a `Provider`, instead selects:

```text
validated session.start -> ProviderSessionRunner creates ProviderSession + fresh limit tracker
  -> capture provider-work deadline -> admit one ProviderRequest -> one ProviderOperation
  -> strict provider observation grammar + four hard-limit checks
  -> ordered, non-interleaved publication transaction: wire + reducer + transcript observer
  -> one completed, failed, or cancelled terminal after supervised provider cleanup
```

Default tests exercise this path network-free with `FakeProvider`; explicit OpenAI selection routes
the launcher and `main()` through the concrete adapter. Runtime shutdown, stdin EOF, and outer-task
cancellation tear down active provider work without fabricating a user-cancellation terminal when
teardown wins.

CAH-010 keeps one-session lifecycle meaning separate from process effects and conversation history.
`task.submitted`, `cancel.requested`, `approval.requested`, and `approval.resolved` are trusted domain
facts; the latter two do not expand protocol v1. Wire events reach the cores only after Pydantic or
Zod validation. The cores enforce correlation, identity, contiguous sequence, assistant completion,
and absorbing terminal states. A new conversation turn starts a fresh core instead of transitioning
an old terminal session back to active work.

The implemented Node project uses npm, commits `package-lock.json`, pins Node 22.22.1, and enforces
the Ink-compatible range `>=22.13.0 <23`. Python remains at version 3.12 and is managed with `uv`;
dependency-resolution changes commit `uv.lock`.

## Ownership

| Concern | Owner | Notes |
| --- | --- | --- |
| Terminal input, layout, and keybindings | Ink TUI | The TUI renders state; it does not make policy decisions. |
| Child-process startup and display of child failures | Ink TUI | A prevalidated Linux `uv` starts the prepared Python environment, which is terminated when the TUI exits. |
| Session lifecycle and terminal outcome | Python runtime | A session emits exactly one terminal event. |
| Agent turns, stopping, and limits | Python agent loop | The project owns the loop rather than delegating it to a framework. |
| Workspace path containment | Python workspace boundary | Planned in CAH-024: one immutable canonical root resolves contained, workspace-relative targets; later tools recheck at access time. |
| Context selection | Python context subsystem | Context items retain their source path, line range, and inclusion reason. |
| Tool validation and execution policy | Python tool and safety subsystems | The model and TUI cannot authorize a tool. |
| Provider translation | Provider adapter | Provider SDK objects do not cross this boundary. |
| Durable audit record | Python persistence subsystem | Redacted trusted lifecycle inputs and explicitly typed non-lifecycle evidence are persisted after admission. |
| Visible conversation, plan, tools, errors, and diffs | Ink TUI | Visible state is reduced from runtime events. |

This boundary allows a future CLI, web UI, test harness, or library caller to use the same Python
core without reproducing orchestration and safety behavior.

## Runtime composition

The implemented Python boundary is separated from later domain subsystems:

```text
src/code_assist_harness/
├── runtime.py          Command loop, active-session routing, cancellation, and shutdown
├── mock_session.py     Fixed response, cooperative checkpoints, reducer integration, and terminals
├── loop_limits.py      Immutable hard limits, per-session counters, and bounded observations
├── model_evidence.py   Bounded transcript-only provider usage evidence
├── provider_session.py One strict provider turn, outcome selection, and cleanup
├── session_state.py    Pure one-session lifecycle reducer and replay
├── persistence/
│   └── transcript.py   Private JSONL append, sanitization, summary, and strict replay
├── provider/
│   ├── models.py       Immutable provider-neutral requests, events, usage, and failures
│   ├── port.py         Single-consumer async operation and cleanup protocols
│   ├── fake.py         Ordered request scripts, logical gates, and cancellation checkpoints
│   ├── openai_config.py SDK-free provider, model, environment, and credential validation
│   └── openai_responses.py Strict SDK translation, event automaton, and resource cleanup
├── protocol/
│   ├── models.py       Strict Pydantic v2 wire models
│   ├── codec.py        Two-stage parsing and safe serialization
│   └── streams.py      Bounded readers and ordered event writer
└── __init__.py         Intentional package surface
```

The provider package remains independent of orchestration. `provider_session.py` consumes its port
through harness-owned values. `runtime.py` keeps the mock default, but an explicit validated OpenAI
selection lazily imports the concrete adapter and supplies the CAH-022 safety budget to
`ProviderSessionRunner`. Future `core/`, `context/`, `tools/`, and `safety/` paths remain conceptual
and will be introduced only by their owning stories.

CAH-024 plans one sibling module; it is not part of the implemented tree above:

```text
src/code_assist_harness/
└── workspace.py        Planned immutable root, contained target resolution, and relative labels
```

The implemented TypeScript parent keeps protocol validation separate from React components:

```text
tui/
├── src/
│   ├── cli.ts
│   ├── bootstrap.ts
│   ├── check-node-version.ts
│   ├── node-version.ts
│   ├── provider-configuration.ts
│   ├── workspace.ts
│   ├── protocol.ts
│   ├── protocol-stream.ts
│   ├── runtime-diagnostics.ts
│   ├── runtime-supervisor.ts
│   ├── session-lifecycle.ts
│   ├── session-state.ts
│   ├── run-application.tsx
│   └── app.tsx
└── test/              Render, reducer, protocol, launcher, runtime, and lifecycle tests
```

`scripts/run-tui` resolves and validates both the Node and npm executable paths, rejecting Windows
paths even when a Linux-looking symlink hides them, then rejects unsupported Node versions before
npm and its TypeScript loader run. It preserves the caller's canonical launch directory and
forwards launch options as separate arguments. `cli.ts` repeats Node validation, resolves one
workspace, validates the provider/model pair, and creates `PythonRuntimeSupervisor`. The supervisor
always forwards `--provider`; `--model` is forwarded only for OpenAI. The canonical repository gate
invokes
`check-node-version.ts` before every npm-backed policy or TUI stage, reusing the same supported-range
assertion.
`run-application.tsx` projects supervisor state into `app.tsx`, routes `SIGHUP` and `SIGTERM` through
Ink unmount, and guarantees cleanup after every exit path. `protocol.ts` validates hand-maintained
Zod wire shapes and `protocol-stream.ts` owns byte framing. `session-lifecycle.ts` is the pure
absorbing one-session core; `session-state.ts` adapts accepted inputs into persistent multi-turn
conversation history. `runtime-supervisor.ts` validates each active tape with the core, writes at
most one cancellation command, and publishes accepted updates, while `app.tsx` owns only the draft,
Escape binding, and visible feedback.

Shared golden JSON fixtures live under `protocol/fixtures/`. Python and TypeScript protocol types
are intentionally hand-maintained at first. The CAH-010 lifecycle fixtures contain domain facts and
complete validated wire envelopes without making the fixture schema part of protocol v1. The
separate runtime-configuration fixture keeps provider names and the OpenAI model aligned across
languages; it is not a wire-message definition. Schema generation is deferred until contract drift
demonstrates that its additional machinery is worthwhile.

## Agent loop

The explicit loop performs these bounded steps:

1. Build a provider-neutral model request from session state, instructions, and selected context.
2. Ask the configured provider for a streaming response.
3. Convert provider output into harness events before exposing it to other components.
4. Validate requested tool names and inputs.
5. Evaluate capability and policy, requesting approval for a side effect when required.
6. Execute the approved tool and append its bounded result to session state.
7. Continue only if the session remains active and all turn, tool, output, and deadline limits
   permit another costly operation.
8. Emit exactly one completed, cancelled, or failed terminal event.

At most one provider operation is active for a session. CAH-020 implements the structural
`Provider` and `ProviderOperation` protocols: one harness-owned request starts a single-consumer
stream with explicit awaited cancellation and cleanup. Its immutable event union covers text
deltas, completed text, serialized tool requests, usage, normal completion, and normalized failure.
Cancellation closes iteration instead of fabricating a failure event.

The first implementation is a strict deterministic fake. It matches ordered requests, emits
scripted events, exposes named logical delay and cancellation checkpoints, and fails on mismatches,
omitted requests, or unconsumed steps. Diagnostics report only bounded differing field paths, not
request contents. `ProviderSession` builds one request from the accepted task and an ordered,
already-resolved instruction tuple, starts and claims at most one operation, and admits provider
observations through one decision lock. A valid success is one or more deltas, exactly matching
completed text, optional usage, and provider completion in that order. Candidate completion is
buffered until the full grammar selects completion and the cleanup barrier has been attempted. A
cleanup-contract failure adds a separate bounded diagnostic without rewriting that selection.
Invalid grammar becomes
`provider_invalid_response`; normalized provider failure remains bounded; a tool request becomes
`tool_unavailable` without parsing or execution. An empty completed-text candidate is retained only
so a following tool request reaches that classification; it cannot admit usage or complete
successfully.

CAH-022 wraps that turn in an immutable `LoopLimits` value and gives each allocated provider session
a fresh `LoopLimitTracker`. The four configured integers default to one model turn, 120 seconds of
provider work, 4,096 accepted assistant-output bytes, and one observed tool call. Model-turn admission
is charged before `Provider.start()`, UTF-8 output is reserved before publication, and tool requests
are counted before unavailable-tool handling. The rejecting tool observation remains counted; the
rejecting output delta is not admitted. The configurable output budget runs before the fixed
8,192-byte protocol-compatibility ceiling.

Each limit selects one bounded `session.failed` payload with a distinct stable code:
`model_turn_limit_exceeded`, `provider_work_deadline_exceeded`,
`assistant_output_limit_exceeded`, or `tool_call_limit_exceeded`. Provider-reported token usage is
observational evidence only and never replaces these harness-owned counters or authorizes more work.

The absolute provider-work deadline is captured when an accepted command allocates its provider
session, before transcript setup and observer attachment. An independent watcher races every stream
wait and rereads the monotonic clock afterward; at an exact event/deadline tie, expiry wins and the
observation is not admitted. The watcher can latch expiry and start provider cancellation while an
already-admitted publication is blocked. That ordered, non-interleaved publication transaction
completes its wire write, reducer acceptance, and transcript-observer attempt before the deadline
terminal is selected. An ordinary later sink failure does not roll back an earlier accepted view, and
the deadline does not bound local sink latency.

CAH-023 implements the first real adapter against foreground OpenAI Responses streaming. It maps one
provider-neutral text request to `background=false` and `store=false`, accepts only the reviewed event
automaton, rejects terminal state-changing C0/C1 text controls while preserving TAB/LF layout, and
normalizes SDK failures to fixed provider failures. Python and TypeScript wire schemas mirror the text
invariant before terminal state changes. Every operation lazily owns one SDK client and stream plus one
shielded resource-cleanup task. Provider-specific configuration is confined to the SDK-free
validation, composition, and adapter modules; SDK objects, raw responses, and cleanup state remain
inside the adapter itself. The default `MockSession` is still a separate runtime fixture rather than a
provider consumer, and default validation never makes a live model or network request.

## Concurrency and cancellation

The Python runtime creates one `asyncio` event loop and arms its stdin file-descriptor reader for one
bounded chunk at a time. `CommandLineReader` validates each completed line independently, while
`OrderedEventWriter` holds one lock across sequence allocation, validation, serialization, and sink
completion. The accepted mock runs in one child task so the command reader remains available for an
overlapping `session.start`, `session.cancel`, or `runtime.shutdown`. Shutdown waits for the bounded
three-delta task. For an injected provider, `ProviderSession` shields each ordered, non-interleaved
publication transaction from interruption and selects completion, failure, cancellation, deadline
expiry, or teardown through one guard and shared finalizer. The transaction contains the wire write,
reducer acceptance, and observer attempt; an ordinary later failure does not roll back an earlier
accepted view. Cancellation calls and awaits operation cleanup. Teardown from shutdown, EOF, or outer
cancellation emits no fabricated session terminal when it wins.

Provider cleanup has exactly one loop-owned task per session. A deadline watcher may create it in
cancellation mode without waiting for the publication lock; the finalizer joins that same task and
never invokes the provider cleanup API concurrently. Each `cancel()` or `wait_closed()` await is
raced against one fixed five-second local grace through the injected monotonic waiter. Cleanup
completion wins an exact tie; otherwise grace expiry cancels and reaps the local cleanup awaitable
and emits at most one payload-free `provider_cleanup_failed` runtime error without rewriting the
selected outcome. The loop also cancels and joins any pending local provider read. These in-process
joins require the provider awaitables to propagate task cancellation; stronger process isolation is
required for an implementation that suppresses it. The OpenAI adapter supplies its own single-owner
stream/client cleanup beneath this loop-owned grace; failure remains bounded and cannot rewrite the
selected session outcome. Later units add tool supervision to the same loop. Small, bounded filesystem
operations may run directly; blocking work moves to a worker thread when needed.

CAH-006 implements mock cancellation as a lifecycle operation rather than an exception leaked to the
TUI. Each `MockSession` owns an `asyncio.Event` and a state lock. A matching request selects
`cancelled` while holding that lock and wakes any blocked checkpoint. Delta writes, assistant
completion, and terminal selection use the same lock, so a request cannot become accepted in the
middle of a write: no assistant event follows accepted cancellation. Conversely, completion marks
its outcome before its terminal write finishes, so a waiting cancellation observes that completion
already won and cannot add a second terminal event.

The first accepted cancel command correlates `session.cancelled`; normal stream and completion
events remain correlated to `session.start`. Repeated requests for the active session and late
requests for its most recent terminal ID are harmless no-ops. A wrong active ID produces recoverable
`session_mismatch`; an unrelated inactive ID produces recoverable `session_not_active`. Provider
cancellation is implemented for the injected one-turn path; tool and subprocess cancellation remain
future work. An ordered writer preserves monotonic session sequence numbers even when internal tasks
finish concurrently.

## Protocol boundary

Commands travel from Node to Python on child stdin. Events travel from Python to Node on child
stdout. Human-readable diagnostics travel on child stderr, where the parent bounds and sanitizes
failure context. Every complete stdout line must therefore be a validated protocol event; raw logs
and tracebacks are prohibited there.

Protocol version 1 uses one UTF-8 JSON object followed by one LF per message. Commands carry an ID;
related events may carry it as a correlation ID. Session events carry a session ID and a positive,
JavaScript-safe sequence number assigned by the ordered Python writer. Timestamps always use
millisecond UTC with a literal `Z` and never establish order. Unsupported versions and malformed
input become safe structured errors. Unknown or malformed events never enter trusted TUI state.

Pydantic v2 validates incoming commands and outgoing events in Python. Zod validates outgoing
commands and incoming events in TypeScript. Both implementations first establish JSON, version, and
common-envelope trust, then select a known strict payload schema. Internal code may use dataclasses
or ordinary TypeScript types where runtime validation adds no value.

See ADR 0003 for the protocol decision and `docs/protocol.md` for the implemented catalog,
compatibility policy, examples, and failure behavior.

## Tools and safety

Filesystem reads are native Python operations, not subprocess commands. Bounded `list_files`,
`read_file`, `search_text`, and `stat_path` operations may run automatically after path and policy
validation.

Edits use a staged workflow:

1. The model proposes a batch of exact replacement, create, or delete operations.
2. The harness validates workspace paths and file preconditions.
3. The harness generates a unified diff.
4. The TUI displays the complete batch for one approval decision.
5. Immediately before any write, the harness verifies that all file preconditions still match.
6. The harness follows the documented multi-file failure contract or reports a conflict without
   overwriting newer content.

Subprocess commands use argument arrays and never shell strings or `shell=True`. A command must
first satisfy the effective allowlist and then receive its own approval. Built-in policy supplies
the initial safe candidates; user configuration may broaden or narrow them; workspace
configuration may narrow but never silently broaden them. Approval is not a substitute for
policy, and a changed action cannot reuse a stale approval.

The host executor enforces a workspace, a reduced environment, time and output limits, and
cancellation. Network and privileged capabilities are unavailable in the MVP. Git-state-changing
operations are prohibited. The executor interface is kept independent so a future container
implementation can replace the restricted host implementation without changing the agent loop.

## Context engineering

The context subsystem retrieves bounded repository information instead of loading the entire
workspace. It discovers repository instructions such as `AGENTS.md` and relevant project
documentation, respects ignored paths and size limits, and preserves provenance for every context
item. The context builder must be able to explain why an item was included and enforce a total
budget before calling a provider.

CAH-024 is the planned foundation for that subsystem. The Python harness will own an immutable
boundary around the canonical launch root and return only contained targets with workspace-relative
labels. Instruction discovery, content reads, ignored-path policy, context budgeting, and
execution-time race protection remain outside that unit.

Evaluation scenarios will check whether known relevant files were selected, how much context was
used, and whether unnecessary reads occurred. These mechanisms are target behavior for the
read-only assistant milestone, not part of the initial scaffold.

## Persistence and privacy

Trusted lifecycle inputs—application-owned domain facts and validated session events—and explicitly
typed non-lifecycle evidence are redacted, bounded, and appended as JSONL beneath the WSL XDG state
directory, normally
`~/.local/state/code-assist-harness/transcripts/`. Their contiguous `record_order` supports reducer
replay from `idle`, while session events retain their authoritative sequence. A stable `ws1_` hash
and random transcript ID prevent repeating mock session IDs from colliding without placing harness
files into repositories or exposing personal paths in filenames. Record timestamps are descriptive;
neither they nor event timestamps replace the two explicit order fields.

The writer now emits transcript version 3 for every session. Replay accepts internally consistent
version-1, version-2, and version-3 tapes and rejects a mixed-version tape. Lifecycle records still
contain the current user task, assistant output, cancellation intent, minimal approval facts when a
producer exists, and terminal failures. A provider-backed tape may contain one bounded
`model.usage_observed` record after `ProviderSession` has reconciled and buffered the provider's
`ProviderTextCompleted` observation but before the `assistant.completed` and session-terminal
records. The buffered provider observation is not itself a transcript record, so replay validates
the observable window instead: one session-bound usage record while the session is running, after
non-empty assistant text, and before assistant completion.

A healthy, terminal provider-backed version-3 tape also contains exactly one
`loop.limits_observed` record immediately before its terminal session event. It records the four
configured limits, admitted model turns and assistant bytes, observed tool calls, and an optional
exhausted-limit enum; it contains no monotonic timestamp or raw provider value. Replay validates its
session, position, cardinality, ranges, counters, and agreement with the adjacent terminal: an
exhausted budget requires its exact stable failure code, while no exhaustion forbids those codes.
In version 3, a reserved limit-failure code also requires this preceding record. Replay restores the
record beside usage in the separate evidence projection used by the summary. A
mock-session version-3 tape may omit that record because
`MockSession` does not enter the provider-backed loop. Neither evidence kind is a protocol-v1 event,
reducer input, sequence consumer, billing proof, or authority to admit more work.

Later tool stories may add bounded tool metadata and results through the same typed boundary. Raw
provider payloads and environment mappings are excluded. Recognized environment values are used only
as in-memory redaction candidates; configured secrets and credential-shaped text are replaced before
persistence. Application directories use `0700`, files use `0600`, and each record is flushed and
fsynced. A first storage failure disables later writes, emits one recoverable TUI warning, and never
rolls back the already accepted lifecycle state.

`--no-transcript` short-circuits state-location and secret discovery and creates neither JSONL nor
summary. It controls local harness files only. Local permissions are not encryption or protection
from another process running as the same WSL user, the workspace hash is pseudonymous rather than
anonymous, and automatic retention remains out of scope.

## Documentation and testing

Architecture is part of the product. Public Python production APIs use type annotations and
Google-style docstrings; exported TypeScript contracts use TSDoc. State machines, protocol
semantics, tools, cancellation, and safety boundaries document their invariants and expected
failures. Comments explain rationale rather than paraphrasing code.

Each implementation-ready story also has a lesson under `docs/lessons/`. Lessons connect the small
repository design to practical exercises and production alternatives, including the extra
reliability, security, observability, governance, and operating cost those alternatives introduce.
Before implementation, a lesson describes planned behavior; story completion replaces that plan
with concrete implementation and validation evidence.

Tests mirror source responsibilities and use fake providers, temporary workspaces, shared protocol
fixtures, and fake approval decisions. Behavioral work includes a happy path and a meaningful
failure path. Python checks include pytest, Ruff linting, formatting, and public-docstring rules.
TypeScript checks include type checking, linting, and tests; visible Ink changes include a render
or reducer test. `./scripts/check` is the canonical fail-fast gate for those layers, protocol
fixtures, local documentation links and anchors, top-level Python/Node process-network guards,
the source policy that isolates SDK/network imports to the concrete adapter, and the genuine
Node-to-Python boundary. The real Python child
retains its runtime-selector sanitization and therefore relies on the source policy rather than the
ambient `PYTHONPATH` guard. CI installs from both committed locks and invokes the same command. No
default test or evaluation makes a network request; the optional `live_provider` smoke requires
explicit flags, the exact model, and a credential. The guards are defense in depth rather than an
operating-system sandbox for native subprocesses.

Retained presentation files through CAH-022 are frozen historical artifacts under
`docs/lessons/assets/`. They may diverge from later design corrections and are not authoritative.
Starting with CAH-023, the Markdown lesson and its compact architecture diagram are the only lesson
artifacts. No presentation is added or revised unless the user explicitly reverses this freeze.

## Delivery sequence

The architecture is delivered as vertical slices rather than as disconnected subsystems:

| Milestone | Slice | Observable result |
| --- | --- | --- |
| M0 | Mock runtime through the real Node–Python boundary | Tasks stream, cancel, and terminate authoritatively across the protocol. |
| M1 | Explicit loop with fake and OpenAI providers | One bounded model conversation can complete or cancel. |
| M2 | Repository context and native read tools | CAH-024 is planned as the first boundary unit; the completed milestone lets the agent inspect, explain, and form grounded plans. |
| M3 | Approval, edit, subprocess, and diff workflow | Approved changes and validation are controlled and auditable. |
| M4 | Evaluation, replay, and failure hardening | Behavioral regressions are measurable and reproducible. |
| M5 | Packaging and executor/provider extension points | The core can support other interfaces and isolation models. |

Evaluation begins in M0 with deterministic scenarios. M4 makes it comprehensive; it is not the
first point at which behavior is tested.
