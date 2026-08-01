# CAH-006 lesson: Session cancellation

- **Unit:** CAH-006
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; Python, supervisor, reducer, rendering, and real-boundary tests
  exercise cooperative mock cancellation
- **Story:** [CAH-006](../../user-stories/cah-006-cancel-active-session.md)
- **Visual companion:** [Session cancellation presentation](assets/cah-006-session-cancellation.pptx)
- **Related architecture:** [Agent loop](../agent-loop.md), [protocol](../protocol.md),
  [architecture](../architecture.md), and
  [ADR 0002](../adr/0002-ink-python-process-boundary.md)

> Verified implementation: Escape requests cancellation, Python chooses the authoritative terminal
> outcome, and deterministic tests prove cancellation before output, between deltas, and while
> completion is already being written. Provider, tool, and subprocess cancellation remain later
> work.

## Quick summary

CAH-006 turns cancellation into a protocol-visible lifecycle rather than a local keypress or leaked
task exception. The TUI requests cancellation and projects `cancelling`; Python stops the active mock
and emits `session.cancelled` only when cancellation wins. If normal completion already owns the
terminal transition, `session.completed` remains authoritative. Exactly one terminal event survives.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a cancellation request from an acknowledged cancelled outcome;
- explain cooperative cancellation and why a delta may arrive before Python accepts the request;
- design idempotent handling for repeated, wrong-session, and late cancellation commands;
- serialize completion and cancellation so only one terminal event wins;
- test cancellation races with controlled scheduling rather than wall-clock luck; and
- compare one-process cancellation with distributed workflow cancellation.

## Why this unit matters

An agent may stream indefinitely, wait on a provider, or supervise a long-running tool. If Escape
only changes the TUI, Python can continue consuming resources and later emit contradictory events.
CAH-006 establishes user control, runtime ownership, and terminal-state discipline before expensive
provider or tool operations are introduced.

## Junior engineer foundation

An asynchronous task can pause at `await` while another task runs. That makes a cancellation race
possible: the user can request cancellation while a response task is between checkpoints or while
an event sink is writing. `asyncio.Event` is a one-way signal for that intent, while `asyncio.Lock`
creates a critical section in which only one task can inspect and update the outcome at a time.

```python
stop_requested = asyncio.Event()

async def do_work() -> None:
    if stop_requested.is_set():
        return
    await one_bounded_step()
```

`set()` wakes tasks waiting on the event; it does not forcibly interrupt arbitrary code or prove
cleanup finished. A common beginner misconception is that calling `Task.cancel()` or setting an
event means the session is already cancelled. In this design the request is only intent. The
Python-owned `session.cancelled` event is the acknowledgement that cancellation won the serialized
terminal race.

## Key concepts

**Cancellation request:** `session.cancel` expresses intent for one Python-owned session ID. It is
not proof that work stopped.

**Cancellation acknowledgement:** `session.cancelled` is Python's authoritative terminal event. It
correlates to the cancel command that won, while prior start and delta events remain correlated to
the original `session.start`.

**Cooperative cancellation:** `MockSession` owns an `asyncio.Event`. A request sets that signal, and
the running mock exits at its current scheduling checkpoint after required cleanup.

**Idempotency:** a second request for the same active or most recently terminal session creates no
new event and cannot duplicate the terminal outcome.

**Serialized race:** delta writes, normal completion, and cancellation acceptance share one state
lock. Whichever valid terminal selection obtains it first determines the only outcome.

## Architecture and invariants

```text
Escape
  -> App.onCancelSession
  -> PythonRuntimeSupervisor.cancelSession
       publishes cancel.requested, then writes session.cancel(session_id)
  -> run_runtime validates and routes by active session identity
  -> MockSession.request_cancellation sets the cooperative signal under its state lock
  -> MockSession.run emits session.cancelled or preserves an already-winning completion
  -> supervisor validates correlation, identity, and sequence
  -> reduceSessionState projects the authoritative terminal result
```

| Concern | Implemented owner | Verified invariant |
| --- | --- | --- |
| Key binding and hint | `tui/src/app.tsx` | Escape is advertised only for an addressable running session; Ctrl+C exits the application. |
| Request construction | `tui/src/runtime-supervisor.ts` | At most one validated cancel command is written for the active session ID. |
| Pending projection | `tui/src/session-state.ts` | Local `cancel.requested` enters `cancelling`, not terminal `cancelled`. |
| Active work and signal | `MockSession` | Python owns work, checkpoint interruption, and cleanup. |
| Terminal selection | `MockSession` state lock | Cancellation and completion cannot both emit terminal events. |
| Sequence and writes | `OrderedEventWriter` | The shortened cancelled tape remains monotonic and valid NDJSON. |
| Application exit | Node supervisor plus Python runtime | Shutdown drains the bounded mock; process-group fallbacks still reap an unresponsive child. |

The central invariant is that an accepted cancellation produces no later assistant output. A local
keypress is earlier than acceptance, so an event already in flight may still arrive while the TUI
shows `cancelling`. The reducer permits start-correlated deltas or normal completion during that
pending interval. Only Python's first valid terminal event makes the outcome final.

The successful tape remains `session.started`, three `assistant.delta` events,
`assistant.completed`, then `session.completed`. Cancellation before the first delta shortens it to
`session.started` and `session.cancelled`. Cancellation after one delta preserves that delta and
emits `session.cancelled` at the next sequence. The terminal cancellation alone uses the cancel
command correlation ID.

CAH-006 exercises the deterministic mock only. CAH-020 defines the provider-operation cancellation
contract, and CAH-021 now integrates it with this lifecycle through an injected provider session;
the launched path remains mocked, and later tool stories must add subprocess-tree propagation and
cleanup.

## Practical walkthrough

1. `App` handles Escape only when the runtime and session are both `running`. The status line shows
   `Esc to cancel` only after `session.started` has made the session addressable.
2. `PythonRuntimeSupervisor.cancelSession` obtains a fresh command ID, encodes the exact
   `session.cancel` line, and publishes `cancel.requested` before the asynchronous write. This keeps
   a fast `session.cancelled` from outrunning local correlation state.
3. The pure reducer stores the cancel command ID and enters `cancelling`. Repeated Escape presses
   now return `false` and write nothing.
4. `run_runtime` compares the requested session ID with its active `MockSession`. A mismatch emits
   recoverable `session_mismatch`; an unrelated inactive ID emits `session_not_active`.
5. `MockSession.request_cancellation` acquires the same state lock used by delta and completion
   writes. If completion already selected its outcome, the request returns `terminal`; otherwise it
   records the cancel command, selects `cancelled`, and sets the cooperative event.
6. `_wait_for_checkpoint` races the injected checkpoint with that event. When cancellation wins, it
   cancels and awaits the checkpoint task, then returns control to the session lifecycle.
7. `_emit_selected_cancellation` writes one `session.cancelled`. The session task finishes before
   the runtime clears active ownership, so another command cannot overlap cleanup.
8. The supervisor validates that `session.cancelled` matches the local cancel command and the next
   sequence. `reduceSessionState` then projects `cancelled · ready for another task`.
9. If `_emit_completion` obtained the state lock first, it selects `completed` before awaiting the
   terminal sink write. A concurrent cancel waits, observes the terminal outcome, and adds nothing.
10. Ctrl+C remains whole-application exit. `runApplication` enters its shared cleanup path,
    `runtime.shutdown` drains this bounded mock, and bounded process-group escalation remains the
    fallback for a child that does not close.

## Implementation code samples

### Sample 1: cancellation selects one terminal outcome under the session lock

From [`mock_session.py`](../../src/code_assist_harness/mock_session.py):

```python
async with self._state_lock:
    if self._cancel_command_id is not None:
        return "already_requested"
    if self._terminal_outcome is not None:
        return "terminal"

    cancellation = CancelRequested(command_id=command_id, session_id=self._session_id)
    if self._lifecycle_state.status == "starting":
        # A direct caller may cancel after allocation but before ``run`` publishes
        # session.started. Preserve the legal matrix by reducing this fact immediately
        # after the started event rather than inventing starting -> cancelling.
        self._deferred_cancellation = cancellation
    else:
        await self._reduce_lifecycle(cancellation)
    self._cancel_command_id = command_id
    self._terminal_outcome = "cancelled"
    self._cancellation_requested.set()
    return "accepted"
```

The lock makes the checks and selection indivisible relative to delta and completion writes. The
first branch makes a repeated request idempotent. The second preserves an already-selected terminal
outcome. A request that arrives before `session.started` is remembered for the first legal reducer
transition; otherwise the reducer accepts it immediately. Only after those checks does the method
record the cancel command, select the outcome, and wake the checkpoint-blocked run task.

### Sample 2: a deterministic failure-path test blocks before output

From [`test_runtime.py`](../../tests/test_runtime.py):

```python
def test_mock_session_cancels_before_the_first_delta_and_repeats_idempotently() -> None:
    async def scenario() -> tuple[list[bytes], str, str, SessionState]:
        lines: list[bytes] = []
        checkpoint_reached = asyncio.Event()
        blocked_checkpoint = asyncio.Event()

        async def sink(line: bytes) -> None:
            lines.append(line)

        async def checkpoint(_index: int, _delta: str) -> None:
            checkpoint_reached.set()
            await blocked_checkpoint.wait()

        session = MockSessionRunner(OrderedEventWriter(sink), checkpoint).create(
            _session_start("cmd_session")
        )
        running = asyncio.create_task(session.run())
        await asyncio.wait_for(checkpoint_reached.wait(), timeout=1)
        first_result = await session.request_cancellation("cmd_cancel")
        repeated_result = await session.request_cancellation("cmd_cancel")
        await asyncio.wait_for(running, timeout=1)
        return lines, first_result, repeated_result, session.lifecycle_state

    lines, first_result, repeated_result, lifecycle = asyncio.run(scenario())
    events = _event_lines(b"".join(lines))

    assert first_result == "accepted"
    assert repeated_result == "already_requested"
    assert [event.type for event in events] == ["session.started", "session.cancelled"]
    assert [event.sequence for event in events] == [1, 2]
```

The injected checkpoint, rather than a short sleep, proves the exact scheduling state before the
request. The assertions then connect API outcomes to wire evidence: one accepted request, one
harmless repeat, no assistant output, and one contiguous terminal sequence.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Verified safe outcome |
| --- | --- | --- | --- |
| TUI cancels locally only | Spinner stops but Python emits later | Ownership boundary | The TUI stays `cancelling` until a Python terminal event. |
| Cancellation wins, then a delta arrives | Text changes after acknowledged terminal state | Python session lifecycle | Shared locking prevents post-acceptance assistant output. |
| Completion and cancellation both emit | Two terminal events close one session | Terminal selection | The state lock lets only the first valid outcome emit. |
| Escape repeats | Duplicate commands or terminal events appear | TUI supervisor and Python idempotency | The TUI writes once; direct repeat requests are harmless. |
| Wrong session ID is accepted | Another task is interrupted | Runtime routing | Recoverable `session_mismatch`; active work is unchanged. |
| Old unrelated ID is cancelled | Historical state changes | Runtime routing | Recoverable `session_not_active`; recent-terminal repeats are silent. |
| Conflicting terminal reaches the TUI | Completed history becomes cancelled | Reducer boundary | A second terminal event fails the projection closed. |
| TUI exits during work | Orphan Python process remains | Child supervision | Shared cleanup drains or terminates and awaits child close. |

## Validation evidence

- `test_mock_session_cancels_before_the_first_delta_and_repeats_idempotently` proves the two-event
  cancelled tape, cancel-command correlation, and duplicate-request no-op.
- `test_mock_session_cancels_between_deltas_without_later_assistant_output` proves accepted prior
  output remains while later assistant output is absent.
- `test_mock_session_completion_write_wins_a_concurrent_cancellation_race` blocks the terminal sink
  and proves completion selection is authoritative even before its write returns.
- `test_runtime_routes_cancellation_and_rejects_a_wrong_active_session` proves process-level routing,
  safe mismatch handling, late idempotency, and one cancellation terminal.
- `tui/test/session-state.test.ts` proves `cancelling`, cancelled correlation, completion winning,
  and duplicate-terminal fail-closed behavior.
- `tui/test/runtime-supervisor.test.ts` proves one command write, repeated and late local no-ops, and
  both legal race outcomes.
- `tui/test/app.test.tsx` drives Escape, checks the contextual hint, renders pending and cancelled
  states, suppresses a repeated keypress, and preserves the editable draft.
- `tui/test/runtime-boundary.test.ts` cancels genuine Python sessions before the first delta and
  between later deltas across the Node-to-`uv` boundary, keeps observing beyond the remaining mock
  cadence to reject post-terminal output, and proves active shutdown reaps both `uv` and Python.

The repeatable verification commands are `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and `npm --prefix tui run check`. None needs an API key or network
access.

## Production expansion

### Example enterprise scenario

Consider a multi-service code-analysis workflow that schedules builds, sandbox jobs, and provider
requests across regions. The initiator can disconnect, workers can be partitioned, and some actions
cannot be rolled back after they start. Cancellation needs authenticated propagation, deadlines,
durable intent, compensation policy, and telemetry showing which components actually stopped.

### Typical production capabilities and tools

These are representative capabilities, not required dependencies or endorsements:

- [Python asyncio synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
  provide the local `Event` and `Lock` used by this implementation. They keep ownership inspectable,
  but intent disappears on process exit and lock scope still requires careful review.
- [gRPC cancellation](https://grpc.io/docs/guides/cancellation/) illustrates propagation across RPC
  boundaries while handlers still own cleanup; teams must carry deadlines and idempotency through
  every service.
- [Temporal documentation](https://docs.temporal.io/) illustrates durable workflow state,
  cancellation, retries, and compensation while adding persistent history, workers, deterministic
  workflow constraints, and upgrade operations.
- [Kubernetes pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
  illustrates grace periods followed by forced termination, with operational burden in lifecycle
  hooks, process-tree cleanup, and cluster troubleshooting.
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) illustrate tracing
  cancellation latency across services, but require instrumentation, backend capacity, retention,
  cardinality controls, and privacy review.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One Python child and one active mock session | Distributed workers and nested operations |
| Intent storage | In-memory command and `asyncio.Event` | Durable authenticated cancellation record |
| Propagation | Direct event to one owned task | RPC or workflow propagation with deadlines |
| Race control | One in-process state lock | Durable compare-and-set, idempotency keys, or workflow history |
| Cleanup | Await checkpoint task and reap child | Grace periods, compensation, and forced termination |
| Evidence | Deterministic event assertions | Traces, metrics, audit records, and alerts |
| Failure model | Process-local ordering race | Partitions, retries, duplicate delivery, and abandoned work |

### Trade-offs and graduation signals

The implementation deliberately uses cooperative signaling rather than injecting `Task.cancel()` as
the user-facing outcome. That keeps cleanup and terminal semantics explicit and avoids a cancellation
exception interrupting the ordered writer's shielded commit. Holding one state lock across writes
makes the completion race deterministic, but a slow sink can delay when cancellation becomes
accepted. The TUI therefore needs an honest pending state.

The 500 ms production checkpoint delay makes Escape practical to test by hand; injected checkpoints
keep Python unit tests fast and deterministic. Remembering only the most recent terminal session is
enough to absorb a normal pipe race, but it is not durable deduplication. Draining the bounded mock on
application exit is acceptable because its maximum work is known; a provider or subprocess will need
deadlines, propagation, and forced-cleanup policy.

Graduate to durable workflow machinery when sessions outlive one process, side effects span
services, requests can be retried after reconnect, or measured cancellation-loss and cleanup-latency
objectives cannot be met by direct task ownership.

## Practical exercises

1. Draw both legal outcomes when cancel and completion become ready together, including correlation
   IDs.
2. Hold checkpoint one and prove cancellation produces no assistant text.
3. Release one delta, cancel at checkpoint two, and predict the terminal sequence number.
4. Delay the terminal sink and explain why completion can be selected before its write returns.
5. Send a wrong session ID, a repeated active ID, and a recent-terminal ID; compare their wire
   effects.
6. Explain why process-group termination is a shutdown fallback, not a substitute for
   `session.cancel`.

## Key takeaways

- Ink requests cancellation; Python owns active work and the terminal result.
- `cancelling` is honest pending UI state, while `session.cancelled` is the acknowledgement.
- Exactly one terminal event is the central race invariant.
- A shared lock makes acceptance relative to writes explicit: no output follows accepted
  cancellation, though an already in-flight event can follow the keypress.
- Repeated and late requests must be harmless at both convenience and authority boundaries.
- Distributed cancellation is justified when work or intent outlives the local process boundary.

## Glossary

- **Cancellation acknowledgement:** authoritative evidence that cancellation won the session race.
- **Cancellation checkpoint:** a place where active work observes and responds to a request.
- **Cooperative cancellation:** cleanup-aware stopping performed by the active operation.
- **Idempotent request:** a repeated request whose additional application changes nothing.
- **Serialized terminal selection:** one critical section that permits a single final outcome.
- **Forced termination:** stopping a process after cooperative cleanup does not finish in time.

See the shared [project glossary](../glossary.md) for cancellation request, session, terminal event,
and runtime.

## Further reading

- [CAH-006 user story](../../user-stories/cah-006-cancel-active-session.md)
- [Visual lesson presentation](assets/cah-006-session-cancellation.pptx)
- [Agent-loop cancellation model](../agent-loop.md)
- [Protocol lifecycle](../protocol.md)
- [Process-boundary decision](../adr/0002-ink-python-process-boundary.md)
- [Evaluation strategy](../evaluation.md)
- [Python asyncio synchronization primitives](https://docs.python.org/3/library/asyncio-sync.html)
- [gRPC cancellation](https://grpc.io/docs/guides/cancellation/)
- [Temporal documentation](https://docs.temporal.io/)
- [Kubernetes pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)
