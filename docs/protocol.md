# Process Protocol

> Status: CAH-004 implements protocol version 1 schemas, bounded readers, ordered Python event
> writes, shared fixtures, and the `runtime.initialize` / `runtime.ready` readiness handshake.
> Session streaming remains CAH-005 work.

The Ink TUI and Python harness communicate through a small, versioned NDJSON protocol. The
protocol is deliberately simpler than a general RPC system: one local parent process owns the
terminal, one local child process owns the harness, and messages flow over standard streams.

## Process responsibilities

| Stream | Direction | Permitted content |
| --- | --- | --- |
| `stdin` | Ink to Python | Validated commands, one JSON object per LF-terminated line |
| `stdout` | Python to Ink | Validated events, one JSON object per LF-terminated line |
| `stderr` | Python to terminal diagnostics | Human-readable diagnostics and tracebacks |

Ink owns keyboard input, rendering, and child-process supervision. Python will own session
orchestration, policy, provider calls, tool execution, and the authoritative event stream. The TUI
will reduce validated events into visible state; it must not infer permission or agent-loop
decisions.

Protocol stdout is a machine interface. Debug prints, logging, progress bars, and tracebacks must
never be written there because a single non-JSON line can desynchronize the parent. Python uses a
single ordered event writer so concurrent tasks cannot interleave output.

## Implemented physical boundary

CAH-003 launches one child with this shell-free argument array:

```text
PREVALIDATED_LINUX_UV run --project REPOSITORY_ROOT --frozen
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  --python VENV_PYTHON
  -- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE
```

Node supplies each displayed token separately with `shell: false` and configures stdin, stdout, and
stderr as pipes. Before spawn, the supervisor resolves `uv` from filtered `PATH`, realpaths it, and
rejects a path under `/mnt` or a name ending in `.exe`. It also requires
`REPOSITORY_ROOT/.venv/pyvenv.cfg` plus executable `VENV_PYTHON` at `.venv/bin/python`; failure stops
before `uv` can create or change the project environment. `REPOSITORY_ROOT` identifies the harness
project for `uv`, while `--python VENV_PYTHON` fixes its prepared interpreter. The separately
resolved `CANONICAL_WORKSPACE` identifies the one future target repository. The launch directory is
the default workspace, and `--workspace PATH` selects an override relative to that launch directory
before both Node and Python canonicalize and validate it. The child environment removes
`PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, and every `UV_*` variable so ambient selectors cannot
bypass the preflight or redirect the requested harness module.

`src/code_assist_harness/runtime.py` feeds stdin bytes to `CommandLineReader`, validates commands,
and emits only models serialized by `OrderedEventWriter`. `tui/src/runtime-supervisor.ts` feeds
stdout bytes through `NdjsonLineReader` and the Zod-backed event parser before any event can affect
local state. Each reader retains at most 64 KiB for the active physical line, requires LF rather
than CRLF, decodes UTF-8 strictly, reports one bounded failure for an oversized or incomplete line,
and resumes at the next LF.

After OS spawn, Node sends `runtime.initialize` with the canonical workspace. Spawn alone leaves the
state at `starting`; only a `runtime.ready` with the matching correlation ID and workspace moves it
to `running`. Unknown, malformed, unexpected, mismatched, or late readiness data fails closed into
`protocol-failed` and closes command input. During requested shutdown the parent sends a validated
`runtime.shutdown`, closes stdin, and retains the CAH-003 `SIGTERM` / `SIGKILL` process-group
fallback. Parent `SIGHUP` and `SIGTERM` still request Ink unmount and the same cleanup path.

stderr remains separate. `tui/src/runtime-diagnostics.ts` retains a bounded byte tail, drops a
leading partial physical line when necessary, removes terminal controls, redacts recognized
credential assignments and inherited secret values, and imposes a display bound before failure
text enters TUI state.

## Framing and envelope

Messages use UTF-8. Each physical line contains exactly one complete JSON object followed by the LF
byte `\n`. CRLF, blank lines, pretty-printed JSON, multiple objects on one line, and an unterminated
final object are invalid.

An initial command has this shape:

```json
{
  "protocol_version": 1,
  "type": "session.start",
  "command_id": "cmd_123",
  "timestamp": "2026-07-13T14:00:00.000Z",
  "payload": {
    "task": "Explain the configuration loader"
  }
}
```

A related event has this shape:

```json
{
  "protocol_version": 1,
  "type": "session.started",
  "session_id": "ses_123",
  "sequence": 1,
  "timestamp": "2026-07-13T14:00:00.000Z",
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
- `timestamp` uses exact `YYYY-MM-DDTHH:mm:ss.SSSZ` UTC form and is useful for people and
  diagnostics, but never establishes ordering.
- `correlation_id` links an event to the command that caused it when a direct relationship exists.
- `payload` contains only fields defined for that message type.

Session sequence numbers, rather than arrival timestamps, determine event order. The runtime must
not reuse a sequence number or emit a lower number. Protocol-level runtime events that do not
belong to a session need no session sequence.

Command and correlation IDs match `cmd_[A-Za-z0-9_-]{1,64}`. Session IDs match
`ses_[A-Za-z0-9_-]{1,64}`. Sequence values start at 1 and cannot exceed JavaScript's largest safe
integer, `9007199254740991`, so Python and TypeScript preserve the same value. Error codes use
`[a-z][a-z0-9_.-]{0,63}`; visible error messages are 1–1024 characters and reject C0/C1 terminal
controls. Encoders and readers enforce a 64-KiB JSON-object limit, excluding the terminating LF.

## Version 1 message set

All objects are strict: undeclared envelope or payload fields are invalid.

| Command | Payload | Implemented behavior in CAH-004 |
| --- | --- | --- |
| `runtime.initialize` | `workspace: non-empty string` | Compare with the supervised canonical workspace and emit readiness or a terminal initialization error. |
| `session.start` | `task: non-empty string` | Validate, then report `command_unavailable` until CAH-005. |
| `session.cancel` | `session_id: ses_…` | Validate, then report `command_unavailable` until CAH-006. |
| `runtime.shutdown` | Empty object | End the runtime cleanly, even before initialization. |

| Event | Scope | Payload |
| --- | --- | --- |
| `runtime.ready` | Runtime | `workspace: non-empty string` |
| `runtime.error` | Runtime | `code`, `message`, and `recoverable` |
| `session.started` | Session | Empty object |
| `assistant.delta` | Session | `text: non-empty string` |
| `assistant.completed` | Session | `text: non-empty string` |
| `session.completed` | Session | Empty object |
| `session.cancelled` | Session | Empty object |
| `session.failed` | Session | `code` and `message` |

Later stories may add plan, tool, approval, diff, transcript, and usage events. They must be
documented here and added to cross-language fixtures before either process relies on them.

## Runtime validation

Static types do not validate untrusted bytes. Both sides therefore validate at the process
boundary:

- Python uses strict Pydantic v2 models for incoming commands and outgoing events.
- TypeScript uses strict Zod schemas for outgoing commands and incoming events.
- Validated wire objects are converted into local domain or UI types before business logic uses
  them.
- Provider SDK objects and component-local state never become wire types accidentally.

The schemas are maintained by hand. Both contract suites consume the reviewed
`protocol/fixtures/v1/manifest.json`; neither implementation generates the other. Schema generation
is deferred until contract drift becomes a demonstrated maintenance problem.

An unsupported version is rejected before interpreting its version-specific fields. Malformed JSON,
numeric overflow, an invalid envelope, an unknown command type, or an invalid known payload becomes
a safe `runtime.error`; the Python reader continues at the next physical line. The error never
copies the raw line or validator internals. The TUI uses a stricter authority boundary: an unknown
or malformed event becomes a visible, classified protocol failure, closes command input, and never
enters trusted state.

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

`runtime.shutdown` is implemented for the idle CAH-004 runtime. Python stops reading commands and
exits after prior ordered writes have completed. Later session work will define how active work is
cancelled or flushed. EOF remains a cleanup fallback, and an unrequested child exit remains visible.

## Compatibility rules

- Version 1 readers reject unknown fields. Additions require coordinated validators, fixtures, and
  writers in both languages before use.
- Changing required fields, meanings, or ordering semantics requires a protocol-version change.
- Unknown message types are diagnostic conditions, never permission to guess behavior.
- Event names and failure codes are stable machine values; user-facing wording may evolve.
- Golden fixtures are examples of the contract, but boundary validators remain the authority.

## Implementation stories

### CAH-004 — Define protocol version 1

> As a harness developer, I want a small versioned protocol so that Python and TypeScript can evolve
> without relying on unstructured console text.

This story is complete: both boundaries validate the envelope and selected payload, shared fixtures
pass in both languages, the ordered writer owns sequence assignment, unsupported versions and bad
lines fail safely, and the real supervisor reaches `running` only through correlated readiness.

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
