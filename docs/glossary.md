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
exist yet; it never turns missing evidence into empty success. The summary complements rather than
replaces the append-only lifecycle transcript.

## Invariant failure

A structured rejection from a pure reducer when an otherwise trusted input violates lifecycle
ordering, correlation, identity, sequence, assistant-completion, or terminal rules. It returns the
exact prior state and includes only a stable code, prior status, and input type; it excludes payloads,
identifiers, and user or assistant text.

## Limit

A hard bound on work, such as model turns, tool calls, output size, tool duration, or provider-work
time. Planned CAH-022 charges model-turn admission before provider start, checks an independent
monotonic provider-work deadline, reserves cumulative UTF-8 output before emission, and counts tool
request observations before handling them. The deadline starts supervised provider cancellation; a
conforming provider stops, while failed or timed-out cleanup remains explicitly unconfirmed. It does
not claim that a blocked local event or transcript sink has finished. The current runtime does not
yet enforce those limits.

## Lesson

The learning companion for one implementation-ready user story. It explains the unit's concepts,
architecture, practical exercises, failure modes, production alternatives, trade-offs, and local
glossary. A lesson is educational context, not evidence that planned behavior has shipped.

## Model turn

One provider request and its complete streamed response. A model turn may produce assistant text,
one or more tool-call requests, usage information, or a provider failure, and may end early through
operation cancellation. Cancellation closes the provider stream rather than appearing as a
provider stream event.

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
Provider SDK objects and raw responses remain inside the adapter. The implemented deterministic
fake uses the same port without an SDK or network access; planned CAH-023 will add the first real
adapter for one exact text-only foreground OpenAI Responses stream after hard limits exist. The
current M0 `MockSession` is a runtime fixture, not a provider consumer.

## Provider operation

One single-consumer asynchronous response stream returned by a provider. Its `cancel()` method is
idempotent and waits for cleanup, while `wait_closed()` observes cleanup without requesting it.
After either natural closure or awaited cancellation, no later provider event may be emitted.

## Provider request

The immutable harness-owned input for exactly one model turn. CAH-020 represents a non-empty ordered
conversation plus ordered caller-supplied repository instructions. The request deliberately excludes
provider credentials, SDK values, provider-specific response objects, instruction discovery, and
context-selection policy.

## Provider stream event

One harness-owned observation produced by an active provider operation. CAH-020 supports text
deltas, completed text, serialized tool-call requests, usage reports, normal completion, and
normalized failure. These are Python domain values, not protocol-v1 session events. Planned CAH-021
will translate accepted text and terminal observations into the existing lifecycle while reducing
optional bounded usage through a transcript-only `model.usage_observed` evidence record in transcript
version 2. That record does not change protocol v1 or the shared lifecycle reducers.

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
terminal interface.

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

An append-only JSONL record of trusted lifecycle inputs stored under the WSL XDG state directory
unless disabled. It preserves reducer order across application-owned domain facts and validated
session events after redaction and bounding; it never contains raw provider payloads or environment
values and does not replace authoritative in-memory state. A complete safe tape can be replayed;
an incomplete prefix is inspectable but not resumable.

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

## Workspace configuration

Repository-owned configuration that may narrow user or built-in command policy but may not silently
broaden it. This constraint prevents an untrusted repository from declaring arbitrary commands
safe.

## WSL

Windows Subsystem for Linux. The supported MVP environment is Ubuntu running under WSL, with both
Node and Python executing inside that Linux environment and exchanging Linux paths.
