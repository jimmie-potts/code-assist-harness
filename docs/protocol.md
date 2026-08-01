# Process Protocol

> Status: CAH-006 implements protocol version 1 readiness, deterministic mocked streaming, and
> cooperative session cancellation across the real Node-to-`uv`-to-Python boundary. CAH-009
> documents that execution with normalized message tapes. CAH-010 derives equivalent lifecycle
> state from validated v1 events. CAH-021 and CAH-022 reuse that wire contract for the separately
> injected provider turn and its hard-limit failures; the launched `main()` path remains `MockSession`.
> CAH-023 is the next unit and will add the first live adapter without changing that ownership split.

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

| Command | Payload | Implemented behavior through CAH-006 |
| --- | --- | --- |
| `runtime.initialize` | `workspace: non-empty string` | Compare with the supervised canonical workspace and emit readiness or a terminal initialization error. |
| `session.start` | `task: non-empty string` | After readiness, start the deterministic mock when trimmed task text is non-empty and no session is active. |
| `session.cancel` | `session_id: ses_…` | Request cooperative cancellation for the matching active mock; repeated or recent-terminal requests are harmless. |
| `runtime.shutdown` | Empty object | End cleanly; an accepted mock session is drained before exit. |

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

The schemas are maintained by hand. Both protocol contract suites consume the reviewed
`protocol/fixtures/v1/manifest.json`; neither implementation generates the other. The separate
`protocol/fixtures/session-lifecycle/v1/` suite combines complete validated envelopes with
domain-only lifecycle facts and expected reducer results. Schema generation is deferred until
contract drift becomes a demonstrated maintenance problem.

An unsupported version is rejected before interpreting its version-specific fields. Malformed JSON,
numeric overflow, an invalid envelope, an unknown command type, or an invalid known payload becomes
a safe `runtime.error`; the Python reader continues at the next physical line. The error never
copies the raw line or validator internals. After readiness, Python also returns recoverable
`invalid_task` for a whitespace-only task and recoverable `session_active` for an overlapping task,
both correlated to the rejected command. The Ink submission path blocks these two cases locally,
so those runtime errors protect direct or future protocol callers rather than define normal UI
flow. The supervisor also encodes and size-checks the complete `session.start` line before
publishing local submission state. An oversized task therefore remains editable, publishes no
phantom session, writes no bytes, and leaves the runtime available. The TUI uses a stricter authority
boundary: an unknown, malformed, or semantically invalid event becomes a visible, classified
protocol failure, closes command input, and never enters trusted state.

A validated post-readiness `runtime.error` with `recoverable: true` leaves the supervisor running
and becomes a sanitized visible warning. CAH-011 uses this existing envelope for
`transcript_persistence_failed`; the warning is not a session event, does not enter the lifecycle
transcript, and does not alter an active or terminal session outcome. A nonrecoverable runtime error,
malformed message, or invalid session tape still fails closed.

The injected provider path also uses that recoverable envelope for `provider_cleanup_failed` when a
cleanup barrier or subsequent local read reaping raises or exceeds its local grace. Provider cleanup
has one shared loop-owned task per session; a deadline watcher may start it in cancellation mode and
the finalizer joins that same task rather than invoking cleanup concurrently. Every `cancel()` or
`wait_closed()` await is supervised by a fixed five-second grace. Cleanup completion wins an exact
cleanup/grace tie; otherwise the local cleanup awaitable is cancelled and reaped. This requires the
provider to propagate task cancellation and does not claim remote cleanup succeeded.

The fixed, payload-free warning is correlated to the originating `session.start`, emitted at most
once after the cleanup attempt, and precedes any already-selected session terminal. If runtime
teardown won first, the warning may appear without a fabricated session terminal. It is not a session
event, lifecycle-reducer input, or transcript record, and it cannot replace the selected session
outcome. An iterator or cleanup awaitable that suppresses cancellation remains an in-process
containment limit rather than a protocol-visible outcome.

CAH-022's four hard-limit failures use the existing `session.failed` envelope and therefore do not
change protocol version 1. Their stable payload codes are `model_turn_limit_exceeded`,
`provider_work_deadline_exceeded`, `assistant_output_limit_exceeded`, and
`tool_call_limit_exceeded`. The bounded messages contain neither configured values nor provider
content. The provider-work deadline is not a protocol-sink timeout: its watcher may start cancellation
while an already-admitted publication is blocked, but that ordered, non-interleaved publication
transaction completes its wire/reducer/observer work before the latched deadline selects the
terminal. An ordinary later failure does not roll back an earlier accepted view. At an exact provider
event/deadline tie, the deadline wins and the observation is not published.

Transcript compatibility is a separate local-storage contract, not an NDJSON protocol revision. The
writer now emits transcript version 3, replay accepts internally consistent versions 1, 2, and 3, and
provider-backed version-3 tapes may contain one `loop.limits_observed` evidence record immediately
before the terminal session event. Its exhausted-limit value and that terminal must agree exactly:
each exhausted class maps to its stable `session.failed` code, while null exhaustion forbids those
codes. Version 3 also rejects a reserved limit-failure code without the preceding record. A
mock-session version-3 tape may omit the record because the launched mock does not enter the
provider-backed path. The evidence consumes no protocol sequence number and is never sent to the TUI.

A cancel command for the wrong currently active session produces recoverable `session_mismatch`.
When no session is active, a command naming neither the most recent terminal session nor an active
session produces recoverable `session_not_active`. A repeated request for the active session and a
late request for the most recent terminal session deliberately emit no response: they are
idempotent no-ops, not new lifecycle facts. The TUI prevents those normal repeat and late cases
locally by writing at most one cancellation command while a session is addressable.

## Lifecycle reduction above the wire

Protocol validation establishes that one object is a safe version-1 message. CAH-010 then applies
semantic lifecycle guards: the event must be legal from the prior status, carry the expected command
correlation and session identity, and use exactly the next session sequence. Assistant completion
must confirm the accumulated deltas before `session.completed` is legal. A violation returns the
exact prior state plus a bounded code, prior status, and input type; event payloads and identifiers
are not copied into the invariant diagnostic.

The reducers also consume application-owned facts:

- `task.submitted` records that a validated `session.start` command was accepted for sending;
- `cancel.requested` records that a validated `session.cancel` command targeted the active session;
- `approval.requested` enters `awaiting_approval`; and
- `approval.resolved` returns that session to `running`.

These are domain discriminators, not NDJSON message types. In particular, CAH-010 does not add
approval messages to protocol v1. A later story must define approval request and decision identities,
action binding, ownership, and failure behavior before either process relies on a wire shape.

`completed`, `cancelled`, and `failed` are absorbing for one session. Every duplicate or late input,
including a repeated terminal event, produces `terminal_state_absorbing` and cannot create another
terminal transition. A later user task creates a fresh one-session reducer state; the TUI's separate
conversation projection retains the old terminal turn.

## Lifecycle and cancellation

The target MVP supports one workspace per runtime process and at most one active session. The
successful mocked session tape is:

```text
Ink                      Python
 | runtime.initialize ---> |
 | <----- runtime.ready     |
 | session.start ---------> |
 | <----- session.started   | sequence 1
 | <----- assistant.delta   | sequence 2: "Mock response: "
 | <----- assistant.delta   | sequence 3: "the task crossed the process boundary "
 | <----- assistant.delta   | sequence 4: "and streamed back successfully."
 | <----- assistant.completed | sequence 5: exact accumulated text
 | <----- session.completed | sequence 6
```

`session.started` has sequence 1. Every event in the six-event tape carries the `session.start`
command ID as `correlation_id` and the same Python-owned session ID. The complete text is exactly
`Mock response: the task crossed the process boundary and streamed back successfully.` A later
accepted task receives a distinct session ID, while its independent session-local sequence starts
again at 1 and ends at 6. The three deltas are separated by 500 ms scheduling checkpoints so the TUI
can render the accumulations and a user can request cancellation before completion.

Cancellation is a request, not an immediate state rewrite. Escape is enabled only after
`session.started` has supplied the Python-owned session ID. The supervisor publishes a local
`cancel.requested` update before writing one validated `session.cancel`; the TUI shows `cancelling`
but waits for Python's terminal fact. Normal deltas and completion remain correlated to
`session.start`. If cancellation wins, `session.cancelled` is instead correlated to the winning
cancel command:

```text
Ink                          Python
 | session.start ------------> |
 | <------- session.started    | sequence 1, correlation: start command
 | session.cancel -----------> |
 | <------ session.cancelled   | sequence 2, correlation: cancel command
```

If one delta was already accepted before the request, it remains in the tape and
`session.cancelled` receives the next sequence. A delta whose write was already in flight may also
arrive while the local TUI shows `cancelling`; the acknowledgement, rather than the keypress, marks
when cancellation became authoritative. Once Python accepts cancellation, it prevents later
assistant output and emits exactly one terminal event.

Completion and cancellation share one serialized terminal-selection boundary in `MockSession`.
If cancellation obtains that boundary first, the shortened tape ends in `session.cancelled`. If
assistant completion has obtained it first, Python finishes the normal six-event tape and the
waiting or late cancellation has no effect. The first valid terminal outcome therefore wins and a
session never emits both `session.completed` and `session.cancelled`.

The existing `session.failed` event is now part of the same lifecycle core. A valid failure from
`running`, `awaiting_approval`, or `cancelling` ends that session as `failed`, displays its validated
safe code and message, and leaves the runtime ready for a later task. It is distinct from a malformed
or semantically invalid tape, which still fails the supervising runtime closed as `protocol-failed`.

Ctrl+C exits the application; it does not invoke `session.cancel`. `runtime.shutdown` and
command-pipe EOF stop new command processing but drain an already accepted bounded mock before
Python exits. The Node supervisor retains bounded `SIGTERM`/`SIGKILL` process-group fallbacks and
waits for child close, so exit during work cannot leave the supervised process tree running. An
unrequested child exit remains visible.

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

### CAH-005 — Stream a mocked session end to end

> As a user, I want to submit a task and see a mocked agent response arrive incrementally so that
> the complete UI/runtime boundary is proven.

This story is complete: the TUI submits and projects a deterministic session, Python emits the
documented six-event tape, and the real-boundary test observes three intermediate accumulations and
two consecutive sessions. Beyond the supervised Node-to-Python runtime child, the mock performs no
provider, network, workspace, tool, agent subprocess, or transcript operation.

### CAH-006 — Cancel an active session

> As a user, I want to cancel a running session so that I retain control over long or incorrect
> operations.

This story is complete: Python tests control checkpoints before and between deltas and serialize a
cancel request against a blocked completion write; reducer, supervisor, rendering, and real-boundary
tests cover pending cancellation, authoritative cancellation, completion winning, idempotent
requests, and process cleanup. Exactly one Python terminal event remains authoritative.

### CAH-009 — Document the first end-to-end execution

> As a learner, I want the implemented walking skeleton traced across both processes so that I can
> connect the protocol design to observable behavior.

CAH-009 is complete. The [walking-skeleton guide](walking-skeleton.md) traces the successful and
cancelled mock tapes through concrete functions, ownership boundaries, validation, reduction,
rendering, and automated evidence. It deliberately adds no provider, tool, approval, transcript, or
other runtime behavior.

### CAH-010 — Implement session state as a reducer

> As a harness developer, I want session state derived from trusted facts so that Python, the TUI,
> tests, and replay share lifecycle semantics.

This story is complete without a protocol-version change. Both reducers consume the existing
validated session event union plus four explicitly domain-only facts. Fifty shared cases verify every
legal edge, replay, invariant failure, and absorbing terminal path. `session.failed` now enters the
session lifecycle, while malformed or semantically invalid event tapes still fail the supervisor
closed.

### CAH-011 — Write an append-only transcript

> As a user, I want each session recorded so that I can inspect what happened after the application
> exits.

This story is complete without adding a protocol message. Python observes reducer-accepted domain
facts and validated session events, sanitizes them, and appends a separate transcript-v1 JSONL
record with contiguous `record_order`. Protocol event `sequence` remains authoritative within the
session event tape. Persistence failure reuses recoverable `runtime.error`; transcript contents and
summary paths never cross stdout.
