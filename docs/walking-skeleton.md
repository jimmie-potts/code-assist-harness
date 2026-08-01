# Walking-skeleton execution guide

- **Unit:** [CAH-009](../user-stories/cah-009-document-walking-skeleton.md)
- **Status:** Verified against the CAH-005, CAH-006, and CAH-010 lifecycle paths
- **Protocol:** Version 1 NDJSON
- **Automated boundary:** [Node-to-Python integration test](../tui/test/runtime-boundary.test.ts)

> This guide follows the deterministic M0 mock that exists today. It does not describe a model,
> repository context, tools, approvals, or edits. CAH-011 now records the same lifecycle, but the M0
> trace below intentionally stays on the protocol path rather than following that persistence side
> channel record by record. CAH-020 adds the provider port and fake, and CAH-021 adds a separately
> tested injected-provider session. Neither changes the launched `MockSession` trace below.

## What this slice proves

One task crosses the real Ink-to-Python process boundary and returns as incrementally rendered
assistant text. A second controlled path proves that Escape can request cancellation while Python
still owns the terminal outcome. Together they exercise terminal input, child supervision, strict
wire validation, equivalent pure lifecycle reduction in both languages, rendering, and cleanup
without a provider or network call.

The runtime-readiness handshake has already completed before either trace begins:
`PythonRuntimeSupervisor.start` has sent `runtime.initialize`, and Python has returned the correlated
`runtime.ready`. The session trace starts when a user presses Enter.

```text
keypress
  -> useInput handler in App / submitDraft              Ink input owner
  -> runApplication task callback
  -> PythonRuntimeSupervisor.submitTask
  -> session.start + LF                                child stdin
  -> CommandLineReader / parse_command_line
  -> run_runtime -> MockSessionRunner -> MockSession    Python lifecycle owner
  -> OrderedEventWriter                                child stdout
  -> NdjsonLineReader / parseEventLine
  -> reduceSessionState                                trusted TUI projection
  -> App rerender                                      visible terminal frame
```

## Ownership at every boundary

| Decision or resource | Owner | Concrete implementation |
| --- | --- | --- |
| Editable task, Enter, Escape, and terminal layout | Ink/TypeScript | [`App`](../tui/src/app.tsx) |
| Mounting, rerendering, and whole-app cleanup | Ink lifecycle wrapper | [`runApplication`](../tui/src/run-application.tsx) |
| Child process, command encoding, stdout containment, and local update publication | TypeScript supervisor | [`PythonRuntimeSupervisor`](../tui/src/runtime-supervisor.ts) |
| Incoming command validity | Python protocol boundary | [`CommandLineReader` and `parse_command_line`](../src/code_assist_harness/protocol/) |
| Active session, cancellation routing, and terminal outcome | Python runtime and session | [`run_runtime`](../src/code_assist_harness/runtime.py) and [`MockSession`](../src/code_assist_harness/mock_session.py) |
| Sequence allocation and complete event writes | Python ordered writer | [`OrderedEventWriter`](../src/code_assist_harness/protocol/streams.py) |
| Incoming event validity | TypeScript protocol boundary | [`NdjsonLineReader` and `parseEventLine`](../tui/src/) |
| Visible conversation state | Pure TypeScript projection | [`reduceSessionState`](../tui/src/session-state.ts) |

Ink may reject an obviously unavailable submission for immediate feedback, but it does not accept a
session, assign a session ID, or select a terminal state. Python does not read terminal keys or
render the display. Future tool-policy decisions also belong to Python, although no tools or policy
engine exist in this slice.

## Reading the protocol identities

Each wire message is one UTF-8 JSON object followed by LF. The four identifiers below have different
jobs:

- `command_id` identifies one request created by TypeScript.
- `correlation_id` points an event back to the command responsible for it.
- `session_id` is allocated by Python and identifies one accepted lifecycle.
- `sequence` is allocated by Python and establishes session-local order.

Timestamps use millisecond UTC with a literal `Z`, but they do not establish event order. The fixed
timestamps in the scenario fixtures are representative teaching values. The real-boundary
comparison normalizes timestamp values only; both the Python and TypeScript parsers still validate
the exact timestamp syntax in every fixture line.

## Successful execution

### 1. Enter becomes one validated command

The `useInput` handler inside `App` accumulates the draft and routes Return to `submitDraft`. The
component checks the visible runtime and session state, then calls the callback supplied by
`runApplication`. The callback delegates to `PythonRuntimeSupervisor.submitTask`.

The supervisor creates the command, validates its complete wire shape, publishes a local
`task.submitted` update, and only then schedules the stdin write. Publishing first prevents a fast
`session.started` event from arriving before the projection knows its command correlation. The
teaching scenario supplies the stable ID and timestamp shown here:

<!-- fixture: scenarios/walking-skeleton-success.commands.ndjson -->
```ndjson
{"protocol_version":1,"type":"session.start","command_id":"cmd_walk_success_001","timestamp":"2026-07-30T14:00:00.000Z","payload":{"task":"Explain the rendered boundary."}}
```

### 2. Python accepts and streams the mock

`CommandLineReader` frames stdin by LF and `parse_command_line` validates the common envelope before
selecting the strict `session.start` model. `run_runtime` independently rejects whitespace-only or
overlapping work. For this valid command, `MockSessionRunner.create` allocates `ses_mock_1`, and the
runtime starts `MockSession.run` as a child task so command reading remains responsive.

`MockSession` emits `session.started`, waits at three 500 ms cooperative checkpoints, and emits the
three fragments in `MOCK_RESPONSE_DELTAS`. It then emits `assistant.completed` with text exactly equal
to the concatenated deltas and selects `session.completed`. `OrderedEventWriter` validates each
event, allocates the next sequence while holding its write lock, and writes one complete line.

<!-- fixture: scenarios/walking-skeleton-success.events.ndjson -->
```ndjson
{"protocol_version":1,"type":"session.started","session_id":"ses_mock_1","sequence":1,"timestamp":"2026-07-30T14:00:00.100Z","correlation_id":"cmd_walk_success_001","payload":{}}
{"protocol_version":1,"type":"assistant.delta","session_id":"ses_mock_1","sequence":2,"timestamp":"2026-07-30T14:00:00.600Z","correlation_id":"cmd_walk_success_001","payload":{"text":"Mock response: "}}
{"protocol_version":1,"type":"assistant.delta","session_id":"ses_mock_1","sequence":3,"timestamp":"2026-07-30T14:00:01.100Z","correlation_id":"cmd_walk_success_001","payload":{"text":"the task crossed the process boundary "}}
{"protocol_version":1,"type":"assistant.delta","session_id":"ses_mock_1","sequence":4,"timestamp":"2026-07-30T14:00:01.600Z","correlation_id":"cmd_walk_success_001","payload":{"text":"and streamed back successfully."}}
{"protocol_version":1,"type":"assistant.completed","session_id":"ses_mock_1","sequence":5,"timestamp":"2026-07-30T14:00:01.601Z","correlation_id":"cmd_walk_success_001","payload":{"text":"Mock response: the task crossed the process boundary and streamed back successfully."}}
{"protocol_version":1,"type":"session.completed","session_id":"ses_mock_1","sequence":6,"timestamp":"2026-07-30T14:00:01.602Z","correlation_id":"cmd_walk_success_001","payload":{}}
```

### 3. Validation, reduction, and rendering happen per event

The supervisor's bounded line reader yields one physical stdout line. `parseEventLine` establishes
JSON, version, envelope, known type, and payload trust in stages. Only a successful parse reaches
`PythonRuntimeSupervisor.#acceptSessionEvent`, which asks `reduceSessionLifecycle` whether the edge,
correlation, session identity, sequence, and payload-specific transition are legal.

`runApplication` subscribes to each accepted update, passes it through the multi-turn conversation
adapter outside React, and rerenders `App`. The visible progression is therefore causal rather than
timer-driven:

| Event | Trusted state change | Visible result |
| --- | --- | --- |
| `session.started`, sequence 1 | `starting` to `running`; store `ses_mock_1` | Running status and `Esc to cancel` |
| First delta, sequence 2 | Append `Mock response: ` | First partial assistant frame |
| Second delta, sequence 3 | Append the boundary phrase | Longer partial frame |
| Third delta, sequence 4 | Append the final fragment | Complete text while still running |
| `assistant.completed`, sequence 5 | Confirm exact accumulated text | Assistant message is internally complete |
| `session.completed`, sequence 6 | `running` to `completed` | Completed status; another task is allowed |

The lifecycle core returns a payload-free invariant failure if a sequence skips, a correlation or
session ID changes, a delta follows assistant completion, or completed text differs from accumulated
deltas. The supervisor then fails the untrusted tape closed; React never sees an unvalidated or
semantically rejected wire value.

## Cancellation execution

After `session.started` makes the Python-owned ID addressable, Escape calls
`PythonRuntimeSupervisor.cancelSession`. The supervisor validates a single `session.cancel`,
publishes `cancel.requested` before its asynchronous write, and locally projects `cancelling`.
That projection is pending intent, not a terminal fact.

The command fixture contains both commands in their TypeScript-to-Python order. In the live exchange,
`session.started` arrives between them and supplies `ses_mock_1` before the cancel command is built.

<!-- fixture: scenarios/walking-skeleton-cancel.commands.ndjson -->
```ndjson
{"protocol_version":1,"type":"session.start","command_id":"cmd_walk_cancel_start_001","timestamp":"2026-07-30T14:01:00.000Z","payload":{"task":"Cancel before output."}}
{"protocol_version":1,"type":"session.cancel","command_id":"cmd_walk_cancel_001","timestamp":"2026-07-30T14:01:00.200Z","payload":{"session_id":"ses_mock_1"}}
```

`run_runtime` checks that the requested ID names the active session, then awaits
`MockSession.request_cancellation`. If cancellation obtains the session state lock before the first
checkpoint completes, it selects `cancelled`, wakes the checkpoint, and emits the terminal event
correlated to the cancel command—not the start command.

<!-- fixture: scenarios/walking-skeleton-cancel.events.ndjson -->
```ndjson
{"protocol_version":1,"type":"session.started","session_id":"ses_mock_1","sequence":1,"timestamp":"2026-07-30T14:01:00.100Z","correlation_id":"cmd_walk_cancel_start_001","payload":{}}
{"protocol_version":1,"type":"session.cancelled","session_id":"ses_mock_1","sequence":2,"timestamp":"2026-07-30T14:01:00.300Z","correlation_id":"cmd_walk_cancel_001","payload":{}}
```

The TUI accepts `session.cancelled` only while the newest turn is `cancelling`, with the next
sequence, matching session ID, and matching cancel-command correlation. It then renders
`cancelled · ready for another task`. No assistant event may follow that accepted terminal event.
Before it arrives, a delta or completion write that already owns Python's state lock may still
arrive while the local projection says `cancelling`.

### The completion race

Cancellation and assistant writes use the same `MockSession` state lock. The first terminal
selection at that serialized boundary wins:

- If cancellation selects `cancelled` first, the session emits one `session.cancelled` and stops.
- If assistant completion selects `completed` first, Python finishes the normal six-event tape and
  the waiting or late cancellation has no effect.
- Repeated cancellation for an active or most recently terminal session is an idempotent no-op.

The keypress cannot force a result. Python's terminal event is authoritative, and one session never
emits both `session.completed` and `session.cancelled`.

## Why the three process channels stay separate

| Channel | Direction | Allowed content | Why |
| --- | --- | --- | --- |
| stdin | TypeScript to Python | Validated commands only | Gives Python one bounded command stream. |
| stdout | Python to TypeScript | Validated protocol events only | Lets every complete line enter strict event parsing. |
| stderr | Python to TypeScript | Human diagnostics | Keeps non-protocol text out of the event stream; the supervisor bounds and sanitizes it. |

A Python `print("debug")` on stdout is not harmless logging. The line reader hands `debug` to
`parseEventLine`; JSON parsing fails, the supervisor enters visible `protocol-failed`, closes command
input, and requests child shutdown. Printing inside a JSON line is worse: it corrupts that event's
framing. Diagnostics therefore go to stderr, while stdout is treated as a protocol transport rather
than a console.

EOF is also not a successful session event. An unrequested child close is a visible runtime failure;
normal completion is represented only by the validated terminal event selected by Python.

## Executable evidence

The four marked blocks above are copied exactly from the files under
[`protocol/fixtures/v1/scenarios`](../protocol/fixtures/v1/scenarios/). Their tests enforce three
properties:

1. The marked guide blocks and fixture files remain byte-for-byte synchronized.
2. Python and TypeScript accept every exact command and event line, including timestamp syntax.
3. The real Node-to-`uv`-to-Python scenarios match the stable fixture fields after normalizing only
   timestamps.

The real-boundary test also proves behavior that static fixtures cannot:

- `starts the genuine runtime with filtered overrides and reaps the process group` observes three
  intermediate text projections, six ordered events, a second independent session, an unchanged
  workspace, and no remaining child process;
- `cancels genuine sessions before the first delta and between later deltas` proves cancellation at
  sequences 2 and 3 and waits beyond the remaining mock cadence to reject late output;
- `renders every genuine mocked delta before completion and accepts a second task` drives the real
  Ink input path and asserts the partial frames appear in order; and
- `stops and reaps genuine uv and Python processes during active session work` proves direct
  supervisor shutdown is distinct from session cancellation and leaves no supervised process
  behind.

Run the focused evidence with:

```bash
TMPDIR=/tmp npm --prefix tui test -- test/protocol-fixtures.test.ts test/runtime-boundary.test.ts
TMPDIR=/tmp uv run pytest tests/protocol/test_fixtures.py tests/test_runtime.py
```

The commands use no API key, model, network call, or target-workspace write.

## Intentional M0 omissions

The response text is fixed. `MockSession` is a runtime fixture, not a provider adapter or an agent
loop. The CAH-020 provider package and CAH-021 `ProviderSession` exist beside this launched path but
do not replace its response source. This walking-skeleton path does not yet:

- call OpenAI or any other provider;
- discover, search, or read workspace content;
- expose tools, evaluate policy, or request approval;
- propose or apply edits, run repository subprocesses, or show diffs;
- select the implemented provider-backed turn from `main()` or the TUI.

These omissions keep the first boundary deterministic. They must not be filled in by explanatory
prose before their owning stories implement and test them.

The transcript writer observes this unchanged mock tape after reducer acceptance and writes a
redacted local version-2 transcript plus terminal summary unless disabled. Replay accepts internally
consistent version-1 and version-2 tapes, but the walking skeleton still does not browse, export,
resume, or derive live authority from storage. Optional provider usage evidence exists only on the
separately injected path and never changes this protocol-v1 trace.

## What comes next

[CAH-007](../user-stories/cah-007-establish-repository-checks.md) now runs the separate Python,
TypeScript, protocol, integration, documentation, and network-policy checks through one offline
repository command and Linux CI workflow. It changed how this evidence is run, not the
walking-skeleton runtime semantics documented here.

[CAH-010](../user-stories/cah-010-session-state-reducer.md) now routes this tape through equivalent
pure Python and TypeScript lifecycle reducers while keeping multi-turn rendering as an adapter.
[CAH-011](../user-stories/cah-011-append-only-transcript.md) now persists validated, redacted
history without becoming the lifecycle source of truth.
[CAH-020](../user-stories/cah-020-provider-interface-and-fake.md) now defines and tests the
provider-neutral interface and deterministic fake independently of this M0 runtime.
[CAH-021](../user-stories/cah-021-complete-one-model-turn.md) now connects that boundary to one
injected provider-neutral turn while preserving the existing lifecycle invariants and visible mock.
[CAH-022](../user-stories/cah-022-enforce-loop-limits.md) is next and will add hard limits before
[CAH-023](../user-stories/cah-023-add-openai-responses-adapter.md) activates a real provider.

See the [architecture](architecture.md), [protocol](protocol.md), [agent-loop design](agent-loop.md),
[safety model](safety-model.md), and [glossary](glossary.md) for the broader design boundaries.
