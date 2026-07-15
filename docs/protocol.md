# Process Protocol

> Status: CAH-003 implements the physical pipes and process supervision. Versioned messages,
> readiness, parsing, validation, and the catalogs below remain proposed for CAH-004.

The Ink TUI and Python harness will communicate through a small, versioned NDJSON protocol. The
protocol is deliberately simpler than a general RPC system: one local parent process owns the
terminal, one local child process owns the harness, and messages flow over standard streams.

## Process responsibilities

| Stream | Direction | Permitted content |
| --- | --- | --- |
| `stdin` | Ink to Python | Commands, one JSON object per line |
| `stdout` | Python to Ink | Events, one JSON object per line |
| `stderr` | Python to terminal diagnostics | Human-readable diagnostics and tracebacks |

Ink owns keyboard input, rendering, and child-process supervision. Python will own session
orchestration, policy, provider calls, tool execution, and the authoritative event stream. The TUI
will reduce validated events into visible state; it must not infer permission or agent-loop
decisions.

Protocol stdout is a machine interface. Debug prints, logging, progress bars, and tracebacks must
never be written there because a single non-JSON line can desynchronize the parent. Python should
use a single ordered event writer so concurrent tasks cannot interleave output.

## Implemented physical boundary

CAH-003 launches one child with this shell-free argument array:

```text
uv run --project REPOSITORY_ROOT --frozen
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  -- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE
```

Node supplies each displayed token separately with `shell: false` and configures stdin, stdout,
and stderr as pipes. `REPOSITORY_ROOT` identifies the harness project for `uv`; the separately
resolved `CANONICAL_WORKSPACE` identifies the one future target repository. The launch directory is
the default workspace, and `--workspace PATH` selects an override relative to that launch directory
before both Node and Python canonicalize and validate it.

No line has protocol meaning yet. `src/code_assist_harness/runtime.py` drains and discards stdin
until EOF and emits no stdout. `tui/src/runtime-supervisor.ts` drains and discards stdout rather
than displaying or parsing it. stderr is collected separately by
`tui/src/runtime-diagnostics.ts`, which retains a bounded byte tail, removes terminal controls,
redacts distinctive inherited environment values and credential-shaped assignments, and imposes a
second display bound before failure text enters TUI state.

The Node spawn event is CAH-003's temporary `running` transition; it is not a readiness handshake.
Any child close before requested shutdown, including exit code zero, is shown as an unexpected
runtime failure. During requested shutdown the parent closes stdin, allowing the minimal runtime to
exit on EOF, then escalates to `SIGTERM` and `SIGKILL` for the detached uv/Python process group only
when needed. Cleanup settles after the child `close` event. CAH-004 must replace the temporary
spawn boundary with the validated `runtime.ready` contract and add the first meaningful stdin and
stdout lines. Parent `SIGHUP` and `SIGTERM` request Ink unmount so external terminal shutdown uses
the same child cleanup path instead of abandoning the detached process group.

## Framing and envelope

Messages use UTF-8. Each physical line contains exactly one complete JSON object followed by
`\n`. Pretty-printed or multi-line JSON is invalid.

An initial command will have this shape:

```json
{
  "protocol_version": 1,
  "type": "session.start",
  "command_id": "cmd_123",
  "timestamp": "2026-07-13T14:00:00Z",
  "payload": {
    "task": "Explain the configuration loader"
  }
}
```

A related event will have this shape:

```json
{
  "protocol_version": 1,
  "type": "session.started",
  "session_id": "ses_123",
  "sequence": 1,
  "timestamp": "2026-07-13T14:00:00Z",
  "correlation_id": "cmd_123",
  "payload": {}
}
```

Envelope fields have specific jobs:

- `protocol_version` selects the complete wire contract. Version 1 is the initial version.
- `type` is a namespaced discriminator, not display text.
- `command_id` uniquely identifies a command within the runtime process.
- `session_id` groups events for one task.
- `sequence` is a session-local, strictly increasing event number.
- `timestamp` is useful for people and diagnostics, but never establishes ordering.
- `correlation_id` links an event to the command that caused it when a direct relationship exists.
- `payload` contains only fields defined for that message type.

Session sequence numbers, rather than arrival timestamps, determine event order. The runtime must
not reuse a sequence number or emit a lower number. Protocol-level runtime events that do not
belong to a session need no session sequence.

## Version 1 message set

Initial commands:

- `runtime.initialize`: provide the explicitly selected workspace and runtime options.
- `session.start`: begin one task after initialization.
- `session.cancel`: request cancellation of the named active session.
- `runtime.shutdown`: request an orderly child shutdown.

Initial events:

- `runtime.ready`: initialization succeeded and commands may be accepted.
- `session.started`: the runtime accepted a task and assigned its session ID.
- `assistant.delta`: append streamed text to the current assistant response.
- `assistant.completed`: publish the complete accumulated assistant response.
- `session.completed`: end a session successfully.
- `session.cancelled`: end a session because cancellation won the race.
- `session.failed`: end a session with a structured, actionable failure.
- `runtime.error`: report a protocol or runtime problem not represented by a normal session event.

Later stories may add plan, tool, approval, diff, transcript, and usage events. They must be
documented here and added to cross-language fixtures before either process relies on them.

## Runtime validation

Static types do not validate untrusted bytes. Both sides therefore validate at the process
boundary:

- Python uses Pydantic v2 models for incoming commands and outgoing events.
- TypeScript uses Zod schemas for outgoing commands and incoming events.
- Validated wire objects are converted into local domain or UI types before business logic uses
  them.
- Provider SDK objects and component-local state never become wire types accidentally.

The schemas will initially be maintained in both languages. Shared golden JSON fixtures prove that
both implementations agree. Schema generation is intentionally deferred until contract drift
becomes a demonstrated maintenance problem.

An unsupported version is rejected before interpreting its payload. Malformed JSON, an invalid
envelope, or an invalid payload becomes a structured protocol error when a valid event can still be
sent. The offending raw line must not be copied into user-visible output because it could contain a
secret. If the TUI cannot validate an event, it surfaces a child-protocol failure and continues to
supervise or terminate the child predictably; it does not attempt to render the object as trusted
state. An unknown event type must not crash the TUI.

## Lifecycle and cancellation

The target MVP supports one workspace per runtime process and at most one active session. After
CAH-004 and CAH-005, a normal mocked session is expected to follow this order:

```text
Ink                      Python
 | runtime.initialize ---> |
 | <----- runtime.ready     |
 | session.start ---------> |
 | <----- session.started   |
 | <----- assistant.delta   |
 | <----- assistant.delta   |
 | <----- assistant.completed
 | <----- session.completed |
```

Cancellation is a request, not an immediate state rewrite in the TUI. Ink sends `session.cancel`,
Python cancels active work, and Python emits exactly one terminal session event. If completion won
the race before cancellation was processed, the existing completion remains authoritative.
Repeated cancellation must be harmless.

When `runtime.shutdown` is implemented, Python will stop accepting new work, cancel or finish active
work according to the shutdown contract, flush validated events and transcripts, and exit. Today,
CAH-003 shutdown closes stdin and the minimal runtime exits on EOF. If the child exits unexpectedly,
Ink already enters a visible failed state instead of treating end-of-file as successful completion.

## Compatibility rules

- Additive optional payload fields may be introduced only when older readers can safely ignore
  them.
- Changing required fields, meanings, or ordering semantics requires a protocol-version change.
- Unknown message types are diagnostic conditions, never permission to guess behavior.
- Event names and failure codes are stable machine values; user-facing wording may evolve.
- Golden fixtures are examples of the contract, but boundary validators remain the authority.

## Implementation stories

### CAH-004 — Define protocol version 1

> As a harness developer, I want a small versioned protocol so that Python and TypeScript can evolve
> without relying on unstructured console text.

Complete this story when both boundaries validate the envelope, shared fixtures pass in both
languages, sequence and correlation behavior is tested, unsupported versions fail clearly, and
diagnostics cannot contaminate stdout.

### CAH-006 — Cancel an active session

> As a user, I want to cancel a running session so that I retain control over long or incorrect
> operations.

Complete this story when cancellation before, during, and after streaming has deterministic tests
and exactly one terminal event is emitted.

### CAH-009 — Document the first end-to-end execution

> As a learner, I want the implemented walking skeleton traced across both processes so that I can
> connect the protocol design to observable behavior.

This page describes the target contract. CAH-009 must update it with the exact implemented sequence
and link that sequence to the real Node–Python integration test.
