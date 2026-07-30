# CAH-006 session cancellation implementation note

- **Date:** 2026-07-30
- **Story:** [CAH-006](../cah-006-cancel-active-session.md)
- **Lesson:** [Session cancellation](../../docs/lessons/cah-006-session-cancellation.md)

## Delivered path

CAH-006 makes the deterministic M0 stream cancellable without moving lifecycle authority into Ink:

```text
Escape
  -> cancel.requested local projection
  -> session.cancel(session_id, cancel command ID)
  -> Python MockSession cooperative signal
  -> session.cancelled if cancellation wins
     or session.completed if completion already won
```

The TUI shows `Esc to cancel` only after `session.started` makes the Python-owned session ID
addressable. The local state becomes `cancelling` after one command is prepared, but only a validated
Python terminal event changes the projection to `cancelled` or `completed`. Ctrl+C remains whole-app
exit and uses the existing child cleanup path.

No wire schema changed. CAH-004 already defined and cross-language-tested `session.cancel` and
`session.cancelled`; this unit supplies their runtime meaning.

## Terminal and correlation rules

- Start, delta, assistant-completion, and normal session-completion events correlate to the original
  `session.start` command.
- A winning `session.cancelled` correlates to the cancel command that selected that outcome.
- Cancellation before the first delta produces sequences `1: session.started` and
  `2: session.cancelled`.
- Cancellation after one accepted delta preserves that output and emits `session.cancelled` at
  sequence 3.
- Completion selected before a concurrent request remains the normal six-event tape.
- One session cannot emit both `session.completed` and `session.cancelled`.

## Implementation decisions

- `MockSessionRunner.create` allocates the session ID synchronously so `run_runtime` can retain an
  addressable lifecycle owner beside its task.
- `MockSession` uses an `asyncio.Event` for cooperative intent and an `asyncio.Lock` for state and
  writes. This avoids using `Task.cancel()` as the user-facing lifecycle mechanism.
- `_wait_for_checkpoint` races the injected delay against the cancellation event. It cancels and
  awaits only the checkpoint task when the request wins.
- `_emit_delta`, `_emit_completion`, and `request_cancellation` share the state lock. Cancellation
  therefore cannot be accepted in the middle of an assistant write. Completion records its outcome
  before awaiting the terminal sink, so a request blocked behind that write cannot add a second
  terminal event.
- The default checkpoint delay increased from 50 ms to 500 ms. This makes Escape practical during
  manual use, while injected checkpoints keep unit tests independent of elapsed time.
- `PythonRuntimeSupervisor.cancelSession` encodes the exact command and publishes
  `cancel.requested` before its asynchronous write. A fast Python acknowledgement therefore cannot
  outrun local cancel-command correlation.
- The TypeScript reducer permits start-correlated deltas and normal completion while locally
  `cancelling`. A keypress is a request; Python acceptance is the authority boundary.
- `runtime.shutdown` still drains the bounded mock. Session cancellation and application exit remain
  separate operations, and Node retains its bounded process-group signal fallback.

## Idempotency and rejection policy

| Request | Runtime result | Rationale |
| --- | --- | --- |
| First matching active ID | Select cancellation when completion has not won | Addressed active work may stop. |
| Repeated matching active ID | No event | A retry cannot create another outcome. |
| Most recent terminal ID | No event | A legitimate completion/cancellation pipe race is harmless. |
| Wrong ID while another session is active | Recoverable `session_mismatch` | Never interrupt different work. |
| Unrelated ID with no active session | Recoverable `session_not_active` | The caller named no addressable lifecycle. |

The TUI normally writes only the first matching-active case. Python still enforces the complete
policy because protocol callers must not depend on React guards.

## Observed constraints and trade-offs

- Holding the state lock across ordered writes makes terminal ownership explicit, but a slow sink
  delays cancellation acceptance. The `cancelling` projection communicates that pending interval.
- A delta already in flight can arrive after Escape but before Python accepts cancellation. No
  assistant output may arrive after the acknowledgement becomes authoritative.
- `run_runtime` remembers only the most recent terminal session ID for late-request absorption. That
  is enough for a local ordered pipe, not durable deduplication after reconnect or process restart.
- The cancelled conversation keeps already accepted assistant text. The TUI uses
  `Cancelled before a response.` only when the accumulated text is empty.
- Provider, tool, and subprocess operations do not yet receive the signal. Their owning stories must
  define cleanup, timeout, and forced-termination behavior without weakening the terminal rule.

## Validation evidence

- Python's focused cancellation tests cover before-output, between-delta, repeated-request,
  wrong-session, inactive-session, recent-terminal, post-cancellation reuse, and blocked-terminal
  completion races.
- The full Python suite passes 130 tests, and Ruff lint and format checks pass.
- TypeScript reducer, supervisor, rendering, and lifecycle tests cover pending cancellation,
  correlation, exactly-one terminal behavior, repeated Escape, completion winning, draft
  preservation, and cleanup.
- The full TUI check passes type checking, ESLint, and 153 tests.
- `tui/test/runtime-boundary.test.ts` cancels the genuine Python runtime before the first delta and
  between deltas, observes sequences 2 and 3 as the respective terminal positions, verifies the
  workspace remains unchanged, waits beyond the remaining mock cadence to reject delayed
  post-terminal output, and reaps both `uv` and Python when stopped during active work.
- The verified lesson includes a
  [visual companion](../../docs/lessons/assets/cah-006-session-cancellation.pptx).

All default evidence is model-free, credential-free, and network-free.

## Next unit

CAH-009 is now dependency-ready. It should trace the successful and cancelled walking-skeleton
paths from keypress and task input through the exact TypeScript and Python functions, protocol
messages, terminal race, tests, and manual observations. It is documentation work: it must not
claim that provider, workspace, tool, transcript, or full agent-loop behavior exists.
