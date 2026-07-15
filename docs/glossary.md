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

A requested, first-class lifecycle outcome that stops active work and prevents another costly
operation. Successful cancellation ends in the `cancelled` terminal state rather than `failed`.

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

## Harness core

The provider-neutral Python domain and orchestration logic: session state, agent loop, context,
tools, policy, and events. It excludes the Ink interface, provider SDK details, and concrete
execution environment.

## Human-readable summary

A compact session artifact containing the task, terminal outcome, changed files, and validation
results. It complements rather than replaces the append-only event transcript.

## Limit

A hard bound on work, such as model turns, tool calls, output size, tool duration, or total session
time. A limit is checked before beginning another costly operation and produces a distinct failure
code when exhausted.

## Lesson

The learning companion for one implementation-ready user story. It explains the unit's concepts,
architecture, practical exercises, failure modes, production alternatives, trade-offs, and local
glossary. A lesson is educational context, not evidence that planned behavior has shipped.

## Model turn

One provider request and its complete streamed response. A model turn may produce assistant text,
one or more tool-call requests, usage information, a provider failure, or cancellation.

## NDJSON

Newline-delimited JSON: exactly one complete JSON object followed by a newline for each protocol
message. The TUI writes protocol commands to child stdin, and Python writes events to child
stdout.

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
Provider SDK objects and raw responses remain inside the adapter. The deterministic fake is a
provider; OpenAI will be the first real provider adapter.

## Reducer

A pure function that derives the next state from the current state and an event. Replaying the same
ordered event list through a reducer must produce the same result.

## Runtime

The Python process entry point that reads protocol commands, supervises sessions and active work,
writes ordered events, and coordinates shutdown. It hosts the harness core but is not itself the
terminal interface.

## Sequence number

A monotonically increasing integer on session events. It establishes event order independently of
timestamps and correlation IDs.

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

An append-only JSONL record of validated session events stored under the WSL XDG state directory
unless disabled. It contains redacted domain data, not raw provider payloads or environment values.

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
