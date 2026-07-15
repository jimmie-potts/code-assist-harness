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
added the npm-managed Ink shell, WSL-aware launcher, Node pin, and TypeScript checks. CAH-003 now
adds the minimal Python entry point, canonical single-workspace selection, and Node child-process
supervision. The physical stdin/stdout/stderr boundary exists, but protocol parsing, readiness,
provider, tool, workspace-read, policy, transcript, and agent behavior remain target architecture.

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
and starts Python through `uv`. The current directory is the default workspace; `--workspace PATH`
selects a different single workspace for the process. Multi-root workspaces are out of scope.

CAH-003 implements that launch as one shell-free argument array:

```text
uv run --project REPOSITORY_ROOT
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  -- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE
```

The line breaks above are explanatory only; Node passes each token as a separate argument with
`shell: false`. The harness repository is `uv`'s project and child working directory, while the
target repository is a distinct, canonical `--workspace` value. Launch therefore cannot resolve
dependencies, read a project `.env`, download Python, or silently change the selected workspace.
Developers prepare the locked environment explicitly with `uv sync --dev`.

The supervisor treats the operating-system spawn event as `running` only for this physical
boundary. Protocol readiness is not inferred; CAH-004 will replace that temporary boundary with a
validated readiness event. Node drains and discards stdout without interpreting or displaying it,
Python drains and discards stdin until EOF, and stderr alone feeds a bounded, sanitized failure
summary. These are transport reservations, not an implemented message protocol.

After Ink reports exit and restores the terminal, the application lifecycle closes stdin so the
minimal Python loop can end normally. If the child does not close during the grace period, Node
sends `SIGTERM` and then `SIGKILL` to the detached uv/Python process group. Cleanup resolves only
after the child `close` event, which proves the wrapper and its pipes were reaped. Any close before
requested shutdown, including exit code zero, becomes a visible failure; CAH-003 does not restart
the runtime. Parent `SIGHUP` and `SIGTERM` handlers unmount Ink and route through the same
asynchronous cleanup while preserving conventional signal exit codes.

The implemented Node project uses npm, commits `package-lock.json`, pins Node 22.22.1, and enforces
the Ink-compatible range `>=22.13.0 <23`. Python remains at version 3.12 and is managed with `uv`;
dependency-resolution changes commit `uv.lock`.

## Ownership

| Concern | Owner | Notes |
| --- | --- | --- |
| Terminal input, layout, and keybindings | Ink TUI | The TUI renders state; it does not make policy decisions. |
| Child-process startup and display of child failures | Ink TUI | Python is started through `uv` and terminated when the TUI exits. |
| Session lifecycle and terminal outcome | Python runtime | A session emits exactly one terminal event. |
| Agent turns, stopping, and limits | Python agent loop | The project owns the loop rather than delegating it to a framework. |
| Context selection | Python context subsystem | Context items retain their source path, line range, and inclusion reason. |
| Tool validation and execution policy | Python tool and safety subsystems | The model and TUI cannot authorize a tool. |
| Provider translation | Provider adapter | Provider SDK objects do not cross this boundary. |
| Durable audit record | Python persistence subsystem | Only validated, redacted domain events are persisted. |
| Visible conversation, plan, tools, errors, and diffs | Ink TUI | Visible state is reduced from runtime events. |

This boundary allows a future CLI, web UI, test harness, or library caller to use the same Python
core without reproducing orchestration and safety behavior.

## Runtime composition

The target Python package is divided by responsibility. Only `runtime.py` exists today:

```text
src/code_assist_harness/
├── runtime.py          Implemented child entry point and stdin-EOF lifetime
├── core/              Agent loop, session state, events, and limits
├── context/           Instructions, retrieval, provenance, and budgets
├── providers/         Provider-neutral port, deterministic fake, OpenAI adapter
├── tools/             Definitions, registry, filesystem, editing, subprocess
├── safety/            Policy, approvals, workspace and path enforcement
└── persistence/       Append-only transcripts and redaction
```

The implemented CAH-003 TypeScript parent is deliberately smaller than the target project:

```text
tui/
├── src/
│   ├── cli.ts
│   ├── bootstrap.ts
│   ├── node-version.ts
│   ├── workspace.ts
│   ├── runtime-diagnostics.ts
│   ├── runtime-supervisor.ts
│   ├── run-application.tsx
│   ├── app.tsx
│   └── (protocol and state modules arrive in later stories)
└── test/              Render, bootstrap, launcher, runtime, and lifecycle tests
```

`scripts/run-tui` resolves and validates both the Node and npm executable paths, rejecting Windows
paths even when a Linux-looking symlink hides them, then rejects unsupported Node versions before
npm and its TypeScript loader run. It preserves the caller's canonical launch directory and
forwards `--workspace` as separate arguments. `cli.ts` repeats Node validation, resolves one
workspace, and creates `PythonRuntimeSupervisor`. `run-application.tsx` projects supervisor state
into `app.tsx`, routes `SIGHUP` and `SIGTERM` through Ink unmount, and guarantees cleanup after every
exit path. Later TypeScript stories add protocol validation and session-state reduction separately
from components; empty planned directories are not created early.

Shared golden JSON fixtures live under `protocol/fixtures/`. Python and TypeScript protocol types
are intentionally hand-maintained at first. Schema generation is deferred until contract drift
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

At most one provider operation is active for a session. OpenAI will be the first real adapter and
will target the Responses API, but OpenAI SDK objects remain inside that adapter. A deterministic
fake provider drives unit tests and the first model-free vertical slice. Default validation never
makes a live model or network request.

## Concurrency and cancellation

The Python runtime now creates one `asyncio` event loop and uses its stdin file-descriptor reader to
drain bytes until EOF. CAH-004 will replace that discard behavior with command validation and
ordered event writing; later units add provider operations, tool supervision, cancellation, and
deadlines to the same loop. Small, bounded filesystem operations may run directly; blocking work
moves to a worker thread when needed.

Cancellation is a lifecycle operation rather than an exception leaked to the TUI. It is checked
before each costly operation, propagates to the active provider or tool, stops further deltas, and
ends the session with one `session.cancelled` event. Repeated cancellation is harmless. An ordered
writer preserves monotonic session sequence numbers even when internal tasks finish concurrently.

## Protocol boundary

Commands will travel from Node to Python on child stdin. Events will travel from Python to Node on
child stdout. CAH-003 has created both pipes and reserves them by discarding bytes rather than
assigning premature meaning. Human-readable diagnostics already travel on child stderr, where the
parent bounds and sanitizes failure context. Nothing may log to stdout because CAH-004 will make
every complete line a validated protocol message.

Protocol version 1 uses one JSON object followed by one newline per message. Commands carry an ID;
related events carry it as a correlation ID. Session events carry a session ID and a monotonically
increasing sequence number. Unsupported versions and malformed input become structured protocol
errors. An unknown event must not crash the TUI.

Pydantic v2 validates Python commands, events, tool inputs, and tool results at untrusted
boundaries. Zod validates protocol input at the TypeScript process boundary. Internal code may use
dataclasses or ordinary TypeScript types where runtime validation adds no value.

See ADR 0003 for the protocol decision. Detailed message catalogs and examples belong in
`docs/protocol.md` as the protocol is implemented.

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

Evaluation scenarios will check whether known relevant files were selected, how much context was
used, and whether unnecessary reads occurred. These mechanisms are target behavior for the
read-only assistant milestone, not part of the initial scaffold.

## Persistence and privacy

Validated session events are appended as JSONL beneath the WSL XDG state directory, normally
`~/.local/state/code-assist-harness/`. A stable workspace identifier groups sessions without
placing harness files into repositories or exposing personal paths in filenames.

The default transcript contains user tasks, assistant output, tool metadata, approval decisions,
and bounded tool results. It excludes raw provider payloads and environment values. Sensitive
configured values are redacted, files use restrictive local permissions, and write failures are
visible without silently changing session semantics. A documented `--no-transcript` mode must
exist before a real provider release.

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
or reducer test. No default test or evaluation makes a network request.

## Delivery sequence

The architecture is delivered as vertical slices rather than as disconnected subsystems:

| Milestone | Slice | Observable result |
| --- | --- | --- |
| M0 | Mock runtime through the real Node–Python boundary | Tasks and streamed fake events cross the protocol. |
| M1 | Explicit loop with fake and OpenAI providers | One bounded model conversation can complete or cancel. |
| M2 | Repository context and native read tools | The agent can inspect, explain, and form grounded plans. |
| M3 | Approval, edit, subprocess, and diff workflow | Approved changes and validation are controlled and auditable. |
| M4 | Evaluation, replay, and failure hardening | Behavioral regressions are measurable and reproducible. |
| M5 | Packaging and executor/provider extension points | The core can support other interfaces and isolation models. |

Evaluation begins in M0 with deterministic scenarios. M4 makes it comprehensive; it is not the
first point at which behavior is tested.
