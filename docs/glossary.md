# Glossary

This glossary defines the domain language used by Code Assist Harness. Prefer these terms in code,
protocol messages, user stories, tests, and documentation. Where ordinary programming language is
ambiguous, the definition below is authoritative within this project.

## Agent loop

The project-owned, bounded orchestration cycle that builds model input, calls a provider,
interprets output, validates and executes tools, records results, and decides whether the session
continues. It is independent of provider SDKs and agent frameworks.

## Approval

A decision by the user about one fully described side effect. One approval may cover a complete,
unchanged edit batch. Every subprocess invocation requires a separate approval. Approval never
overrides a policy denial and cannot authorize an action that changed after it was displayed.

## Assistant delta

An ordered fragment of assistant text emitted while a provider response is streaming. Deltas are
presentation events; the completed assistant message is recorded separately.

## Cancellation

A first-class lifecycle operation that begins with a request and, when it wins the terminal race,
ends with an authoritative acknowledgement. The request alone does not prove work stopped.
Successful cancellation prevents later session output and ends in `cancelled` rather than `failed`.
At the lower provider boundary, awaiting `ProviderOperation.cancel()` is the cleanup barrier; it
closes that operation's stream but does not itself select or emit the session terminal event.

## Cleanup grace

The fixed local time allowed for one provider `cancel()` or `wait_closed()` awaitable to settle.
CAH-022 supervises the one shared cleanup task per provider session with a non-configurable
five-second monotonic grace. A cleanup task already complete when the grace wakes wins the tie;
otherwise its local barrier awaitable is cancelled and reaped and the required
`force_cancel_cleanup()` hook cancels and awaits all provider-owned local tasks without shielding.
Cleanup remains explicitly unconfirmed: local force-reaping is not proof of remote resource release
and requires cancellation-responsive provider code.

## Cancellation acknowledgement

The authoritative `session.cancelled` event emitted after Python accepts cancellation and prevents
later session output. It is correlated to the winning cancel command and is distinct from the
TUI's local `cancelling` projection.

## Cancellation request

A `session.cancel` command expressing the intent to stop one named active session. It may lose to
completion, and repeating it must not create another terminal event.

## Capability

A security-relevant class of tool behavior: read, write, command, network, or privileged. Policy
uses capabilities in addition to tool-specific rules. Network and privileged capabilities are not
available in the MVP.

## Command

The term has two qualified meanings:

- A **protocol command** is a request sent by the TUI to the Python runtime, such as
  `session.start`.
- A **subprocess command** is an executable plus an argument array proposed for host execution.

Use the qualified term when both meanings could be confused. A subprocess command is never a
shell string in the MVP.

## Context item

A bounded piece of information selected for a provider request. It includes content, source
provenance such as a path and line range, an inclusion reason, and a contribution to the context
budget.

## Correlation ID

The protocol command ID copied onto events caused by that command. It connects a request with its
results without replacing the event sequence number.

## Diff

A harness-generated unified representation of proposed or applied file changes. The model
proposes structured edit operations; it does not supply the authoritative review diff.

## Domain fact

A trusted application-owned lifecycle input that does not necessarily cross the process protocol.
`task.submitted`, `cancel.requested`, `approval.requested`, and `approval.resolved` are CAH-010
domain facts. They share reducer semantics with validated wire events without becoming protocol-v1
message types.

## Edit batch

One immutable proposal containing one or more exact replacement, create, or delete operations.
The entire batch is reviewed in one approval and applied only while its path and file-hash
preconditions remain valid.

## Event

A validated fact emitted by the Python runtime, reduced by the TUI into visible state, and eligible
for transcript persistence. Events are ordered within a session and are not requests for the TUI
to make orchestration or policy decisions.

## Executor

The interface responsible for running an already validated and approved subprocess with workspace,
environment, timeout, output, and cancellation controls. The MVP implementation runs restricted
host processes; a future implementation may use a container behind the same interface.

## Fake provider

The CAH-020 deterministic implementation of the provider port. It matches an ordered script of
exact harness-owned requests and explicit emit, logical-delay, or cancellation-checkpoint steps.
It is strict rather than permissive: omitted requests, unexpected requests, unfinished operations,
and unconsumed steps fail the test without exposing request contents in the diagnostic.

## Harness core

The provider-neutral Python domain and orchestration logic: session state, agent loop, context,
tools, policy, and events. It excludes the Ink interface, provider SDK details, and concrete
execution environment.

## Human-readable summary

A compact session artifact containing the task, terminal outcome, changed files, and validation
results. CAH-011 reports changed files and validation as unavailable because their producers do not
exist yet; it never turns missing evidence into empty success. A completed provider-backed turn also
reports bounded provider-supplied input and output token counts when that optional evidence exists,
or says model usage is unavailable. For a provider-backed version-3 tape, it also reports the four
configured limits, harness-owned counters, and exhausted limit restored from loop-limit evidence.
The summary complements rather than replaces the append-only transcript.

## Invariant failure

A structured rejection from a pure reducer when an otherwise trusted input violates lifecycle
ordering, correlation, identity, sequence, assistant-completion, or terminal rules. It returns the
exact prior state and includes only a stable code, prior status, and input type; it excludes payloads,
identifiers, and user or assistant text.

## Limit

A hard bound on work, such as model turns, tool calls, output size, tool duration, or provider-work
time. CAH-022 charges model-turn admission before provider start, checks an independent monotonic
provider-work deadline, reserves cumulative UTF-8 output before emission, and counts tool-request
observations before handling them. Each allocated provider session has a fresh tracker. At an exact
event/deadline tie the deadline wins; its watcher can start supervised cancellation while an admitted
publication is blocked, but it does not bound local event or transcript sink latency. The publication
finishes as an ordered, non-interleaved wire/reducer/observer transaction; an ordinary later failure
does not roll back an earlier accepted view. CAH-021's fixed 8,192-byte assistant ceiling remains a
protocol-compatibility backstop after CAH-022's configurable output budget. The four stable terminal
codes are
`model_turn_limit_exceeded`, `provider_work_deadline_exceeded`,
`assistant_output_limit_exceeded`, and `tool_call_limit_exceeded`.

## Lesson

The learning companion for one implementation-ready user story. It explains the unit's concepts,
architecture, practical exercises, failure modes, production alternatives, trade-offs, and local
glossary. A lesson is educational context, not evidence that planned behavior has shipped.

## Model turn

One provider request and its complete streamed response. A model turn may produce assistant text,
one or more tool-call requests, usage information, or a provider failure, and may end early through
operation cancellation. Cancellation closes the provider stream rather than appearing as a
provider stream event. CAH-021 implements exactly one provider-neutral turn, and CAH-023 runs that
same turn when the user explicitly selects OpenAI and the exact supported model; the default remains
mock. Another turn, tool continuation, and automatic multi-turn behavior remain planned.

## NDJSON

Newline-delimited JSON: exactly one complete JSON object followed by a newline for each protocol
message. The TUI writes protocol commands to child stdin, and Python writes events to child
stdout.

## Normalized provider failure

A harness-owned safe representation of a provider error: one stable failure code, one bounded
single-line message, and a retryable observation. It excludes the SDK exception, raw response,
request, headers, environment, and credentials. A provider adapter must normalize at its boundary;
the loop decides whether and how a session fails or retries.

## Plan

Structured session state describing intended implementation work. It is displayed and updated
separately from ordinary assistant prose so the user can see the current course of action.

## Policy engine

The Python component that decides whether a validated action is prohibited, may run automatically,
or requires approval. The TUI presents decisions but does not make them; the model cannot bypass
them.

## Protocol version

The integer identifying the wire contract understood by both processes. Unsupported versions are
rejected explicitly instead of being interpreted optimistically.

## Provider

An adapter that accepts harness-level model requests and emits provider-neutral stream events.
Provider SDK objects and raw responses remain inside the adapter. The deterministic fake uses the
same port without an SDK or network access. The implemented OpenAI adapter accepts one exact
text-only foreground Responses stream after hard limits; it is selected only by `--provider openai`
plus the allowlisted model. The default `MockSession` is a runtime fixture, not a provider consumer.

## Provider operation

One single-consumer asynchronous response stream returned by a provider. Its `cancel()` method is
idempotent and waits for cleanup, while `wait_closed()` observes cleanup without requesting it.
After either natural closure or awaited cancellation, no later provider event may be emitted. The
OpenAI operation lazily owns one SDK client and stream and routes natural termination and cancellation
through one shielded adapter cleanup task. The required session-only `force_cancel_cleanup()` method
bypasses that shield after cleanup grace expires, cancels and reaps all operation-owned local tasks,
and closes the stream logically without claiming remote resources were released.

## Provider request

The immutable harness-owned input for exactly one model turn. CAH-020 represents a non-empty ordered
conversation plus ordered caller-supplied repository instructions. The request deliberately excludes
provider credentials, SDK values, provider-specific response objects, instruction discovery, and
context-selection policy.

## Provider stream event

One harness-owned observation produced by an active provider operation. CAH-020 supports text
deltas, completed text, serialized tool-call requests, usage reports, normal completion, and
normalized failure. These are Python domain values, not protocol-v1 session events. CAH-021
translates accepted text and terminal observations into the existing lifecycle and stores optional
bounded usage through a transcript-only `model.usage_observed` evidence record. CAH-022 may add one
`loop.limits_observed` record to a provider-backed version-3 tape. Neither record changes protocol v1
or the shared lifecycle reducers.

## Provider session

The harness-owned orchestrator for one provider-neutral turn. `ProviderSession` builds one
request, owns one fresh CAH-022 limit tracker, starts and claims at most one operation, validates its
strict stream grammar, and admits each lifecycle publication as an ordered, non-interleaved,
cancellation-shielded wire/reducer/observer transaction. It selects one outcome and joins the
session's one supervised cleanup task. This protects admission against competing cancellation,
deadline, or terminal selection; an ordinary later sink or observer failure does not roll back an
earlier accepted view. The
session is distinct from the default `MockSession`, provider adapter, multi-turn loop, and TUI
projection.

## Reducer

A pure function that derives the next state from the current state and one trusted domain fact or
validated event. It performs no I/O, clock access, randomness, mutation, parsing, or policy work.
Replaying the same ordered inputs through a reducer must produce the same result.

## Replay

Deterministically folding trusted ordered lifecycle inputs over an initial state. Replay derives
state and stops at the first invariant failure; it does not resume work or repeat provider, tool,
filesystem, or subprocess effects.

## Runtime

The Python process entry point that reads protocol commands, supervises sessions and active work,
writes ordered events, and coordinates shutdown. It hosts the harness core but is not itself the
terminal interface. `run_runtime` supports provider composition and accepts the immutable limits
configuration plus injectable monotonic clock pair. `main()` defaults to `MockSession`; explicit
OpenAI/model selection validates configuration before lazily composing the concrete adapter and
supplying default limits.

## Sequence number

A positive, contiguous integer on session events. It establishes event order independently of
timestamps and correlation IDs; a gap, duplicate, or regression is a lifecycle invariant failure.

## Session

One user task and the complete bounded lifecycle used to handle it. A session has an ID, ordered
events, derived state, configured limits, and exactly one terminal outcome.

## Side effect

An operation that changes workspace files or starts a subprocess. Side effects require informed
approval and appear in the transcript. Native bounded file reads are not side effects under the
MVP approval model.

## Step

One meaningful loop action, such as a provider request, policy evaluation, approval wait, or tool
execution. A step is broader than a tool call and smaller than a complete session. Metrics may
count steps even when no model turn occurs.

## Terminal event

The single event that closes a session: `session.completed`, `session.cancelled`, or
`session.failed`. No later event may return that session to running work.

## Terminal state

One of `completed`, `cancelled`, or `failed`. Terminal states are absorbing: the session cannot
transition from them back to `running`.

## Tool

A named, schema-validated operation exposed to the model through a registry. A tool definition
documents its purpose, inputs, outputs, capability, approval needs, resource access, limits,
cancellation, expected failures, and security assumptions.

## Tool call

A provider-requested invocation of a named tool with structured arguments. It is validated before
policy evaluation and may be rejected, require approval, or execute automatically according to
its capability and effective policy.

## Transcript

An append-only JSONL record stored under the WSL XDG state directory unless disabled. The current
writer emits version 3; replay accepts an internally consistent version-1, version-2, or version-3
tape and rejects mixed versions. It preserves reducer order across application-owned domain facts and
validated session events after redaction and bounding. Separate replay evidence may contain bounded
model usage and, for a provider-backed version-3 tape, one `loop.limits_observed` record immediately
before its terminal session event. A mock-session version-3 tape may omit loop evidence. A transcript
never contains raw provider payloads or environment values and does not replace authoritative
in-memory state. A complete safe tape can be replayed; an incomplete prefix is inspectable but not
resumable.

## TUI

The TypeScript/Node terminal user interface rendered with Ink. It owns keyboard input, rendering,
approval presentation, and Python child supervision. It projects runtime state but does not own the
agent loop or safety policy.

## Validation command

A subprocess command proposed to check work, such as an approved pytest or Ruff invocation. It
must satisfy the command allowlist and receive individual approval even when the project normally
uses it.

## Workspace

The single canonical directory tree the session may inspect or modify. It defaults to the launch
directory and can be set with `--workspace PATH`. Path validation, including symlink resolution,
must prevent escape from this boundary.

## Workspace boundary

The planned CAH-024 immutable Python value that owns one canonical workspace root and resolves
model-facing relative targets into contained paths with workspace-relative labels. It describes a
validated filesystem snapshot; later read, edit, or command code must recheck containment when it
performs access because validation alone does not prevent filesystem replacement races.

## Workspace configuration

Repository-owned configuration that may narrow user or built-in command policy but may not silently
broaden it. This constraint prevents an untrusted repository from declaring arbitrary commands
safe.

## WSL

Windows Subsystem for Linux. The supported MVP environment is Ubuntu running under WSL, with both
Node and Python executing inside that Linux environment and exchanging Linux paths.
