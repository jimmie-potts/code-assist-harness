# CAH-005 mocked streaming session implementation note

- **Date:** 2026-07-30
- **Story:** [CAH-005](../cah-005-stream-mocked-session.md)
- **Lesson:** [Mocked streaming session](../../docs/lessons/cah-005-mocked-streaming-session.md)

## Delivered path

CAH-005 connects the editable Ink task buffer to a real `session.start` command and carries one
deterministic response through the already supervised Node-to-`uv`-to-Python boundary. The response
is fixed so this slice proves transport, lifecycle, ordering, projection, and rendering without
introducing provider behavior:

```text
1  session.started
2  assistant.delta      "Mock response: "
3  assistant.delta      "the task crossed the process boundary "
4  assistant.delta      "and streamed back successfully."
5  assistant.completed  exact concatenation of sequences 2..4
6  session.completed
```

All six events use the start command ID as their correlation ID. `MockSessionRunner` assigns
`ses_mock_1`, `ses_mock_2`, and so on within one runtime; every session owns an independent sequence
starting at 1.

## Implementation decisions

- `src/code_assist_harness/mock_session.py` is a runtime fixture, not a fake provider. It prevents
  provider abstractions from entering M0 before CAH-020.
- `run_runtime` starts the mock in one `asyncio` task. The command reader therefore remains able to
  reject overlap and receive shutdown while the three deltas are delayed.
- The default checkpoint sleeps for 50 ms before each delta so streaming is visible by hand. Tests
  inject events that hold and release each checkpoint, avoiding timing-based unit assertions.
- `PythonRuntimeSupervisor.submitTask` publishes `task.submitted` synchronously before writing the
  command. This closes the race in which a fast child could send `session.started` before the local
  projection knew the command ID.
- `tui/src/session-state.ts` is a pure projection used both to validate the active supervisor tape
  and to build conversation history in `runApplication`. It fails closed on wrong correlation,
  identity, sequence, duplicate completion, or mismatched accumulated text.
- The Ink component owns only editable input and feedback. Whitespace and concurrent submission are
  blocked locally, while Python independently returns recoverable `invalid_task` and
  `session_active` for protocol callers that bypass the UI.
- Normal shutdown and stdin EOF drain an accepted bounded mock. This is not cancellation and must
  not be generalized to an unbounded provider call.

## Observed constraints and trade-offs

- The supervisor keeps only the active tape needed for validation; `runApplication` owns completed
  conversation history. Reusing one projection state for both responsibilities would make a second
  session appear to overlap the completed first.
- The first session event must be `session.started` at sequence 1. The successful CAH-005 reducer
  intentionally has no cancellation or failure terminal transition yet.
- Python is the session authority even though Ink duplicates two rejection checks for faster,
  clearer feedback. Approval, safety, or completion authority did not move into React.
- The real integration scenario confirms the selected target workspace remains empty. The mock does
  not inspect it, mutate it, persist a transcript, call a model, or access the network.

## Validation evidence

- `tests/test_runtime.py` covers controlled intermediate checkpoints, exact text and event order,
  distinct second-session identity, per-session sequence reset, overlap and whitespace rejection,
  shutdown draining, and interactive second-session acceptance.
- `tui/test/session-state.test.ts` covers successful projection plus correlation, identity,
  sequence, and completion failures.
- `tui/test/app.test.tsx` covers whitespace feedback, exact submission, intermediate rendering,
  status changes, and draft preservation during background events.
- `tui/test/runtime-supervisor.test.ts` covers command creation, publication order, two session
  tapes, invalid transitions, local rejection, and write failure.
- `tui/test/runtime-boundary.test.ts` launches the real process tree, observes all three partial
  accumulations, runs two sessions without restart, verifies no workspace file is created, and
  verifies both `uv` and Python are reaped.
- The unit is documented in the protocol and architecture references, and the lesson includes a
  [visual companion](../../docs/lessons/assets/cah-005-mocked-streaming-session.pptx).

## Follow-up boundary

CAH-006 is the next dependency-ready unit. It must add keyboard cancellation as a command and an
authoritative Python terminal outcome, including races with completion and repeated cancellation.
CAH-005 does not implement or simulate that behavior: Ctrl+C still exits the application, and the
runtime still reports `command_unavailable` for `session.cancel`.
