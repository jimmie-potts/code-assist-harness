# CAH-010 lesson: Session state reducer

- **Unit:** CAH-010
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; equivalent Python and TypeScript reducers share one fixture suite
- **Story:** [CAH-010](../../user-stories/cah-010-session-state-reducer.md)
- **Visual lesson:** [Every event needs the right track](assets/cah-010-session-state-reducer.pptx)
- **Related architecture:** [Agent loop](../agent-loop.md), [protocol](../protocol.md),
  [architecture](../architecture.md), and [evaluation](../evaluation.md)

## Quick summary

CAH-010 implements one-session lifecycle reducers in Python and TypeScript. Both consume the same
trusted domain facts and validated protocol events, apply the same 16 legal transitions, and return
the same normalized state or payload-free invariant failure for 50 shared fixture cases. Replaying
an ordered input tape is deterministic, while `completed`, `cancelled`, and `failed` remain
absorbing.

## Learning objectives

After completing this unit, you should be able to:

- distinguish domain facts, wire events, derived state, effects, and rendering;
- explain why a one-session reducer and a multi-turn conversation projection are separate layers;
- trace correlation, identity, sequence, and assistant-completion guards in their evaluation order;
- prove cross-language equivalence with shared transition, failure, and replay fixtures; and
- recognize when statecharts or durable workflow infrastructure justify their operational cost.

## Why this unit matters

Before CAH-010, the TUI had a useful local reducer, but Python's mock lifecycle, future transcript
replay, and the UI could still assign different meanings to “running” or “terminal.” The shared
contract now makes those meanings inspectable and executable in both languages. A future transcript
can record validated inputs without becoming a second source of lifecycle truth.

## Key concepts

**State:** the immutable one-session snapshot needed to validate the next input: status, command and
session identities, last sequence, accumulated assistant text, completion confirmation, and a safe
terminal failure.

**Domain fact:** a trusted, application-owned input such as `task.submitted`, `cancel.requested`,
`approval.requested`, or `approval.resolved`. These facts drive lifecycle state without pretending
to be protocol-v1 messages.

**Wire event:** a complete protocol-v1 session envelope validated by Pydantic or Zod before it
reaches a reducer.

**Pure reducer:** a function of prior state and one trusted input. It performs no I/O, clock access,
randomness, mutation, logging, provider work, policy decision, or protocol parsing.

**Replay:** folding the same ordered inputs over the same initial state to reproduce an equivalent
result. Replay derives state; it does not restart work or repeat side effects.

**Absorbing terminal:** a completed, cancelled, or failed session rejects every later input and
returns the exact prior state.

## Architecture and invariants

The one-session cores live in
[`session_state.py`](../../src/code_assist_harness/session_state.py) and
[`session-lifecycle.ts`](../../tui/src/session-lifecycle.ts). The TUI keeps multi-turn history in
[`session-state.ts`](../../tui/src/session-state.ts), outside the absorbing core. A later task starts
a fresh lifecycle and appends a new conversation turn; it never revives the old session.

### Canonical transition table

| Prior state | Trusted input | Next state | Guard or meaning |
| --- | --- | --- | --- |
| `idle` | `task.submitted` | `starting` | Record start command and task. |
| `starting` | `session.started` | `running` | Start correlation and sequence 1. |
| `running` | `assistant.delta` | `running` | Append the next fragment. |
| `cancelling` | `assistant.delta` | `cancelling` | An already in-flight fragment may win. |
| `running` | `assistant.completed` | `running` | Text exactly confirms accumulated deltas. |
| `cancelling` | `assistant.completed` | `cancelling` | Completion may still win the race. |
| `running` | `approval.requested` | `awaiting_approval` | Domain-only wait fact. |
| `awaiting_approval` | `approval.resolved` | `running` | Domain-only resume fact. |
| `running` | `cancel.requested` | `cancelling` | Target the active session. |
| `awaiting_approval` | `cancel.requested` | `cancelling` | Waiting work remains cancellable. |
| `running` | `session.completed` | `completed` | Assistant completion was confirmed. |
| `cancelling` | `session.completed` | `completed` | Normal completion won the terminal race. |
| `cancelling` | `session.cancelled` | `cancelled` | Correlate to the accepted cancel command. |
| `running` | `session.failed` | `failed` | Preserve only validated safe failure data. |
| `awaiting_approval` | `session.failed` | `failed` | Failure may end a wait. |
| `cancelling` | `session.failed` | `failed` | Failure may win while cancellation is pending. |

Every other edge is illegal. There is deliberately no `starting -> cancelling` transition. A direct
mock caller can request cancellation before `session.started`; `MockSession` defers that domain fact,
reduces the started event first, and then reduces the cancellation request.

### Guard order

For a wire event, the reducers apply guards in this order:

1. reject every input when the prior state is terminal;
2. check that the input type is legal from the prior status;
3. check command correlation;
4. check session identity;
5. require the next contiguous sequence; and
6. enforce assistant-text and terminal payload invariants.

The stable invariant codes are `illegal_transition`, `terminal_state_absorbing`,
`correlation_mismatch`, `session_mismatch`, `sequence_gap`, `sequence_regression`,
`assistant_after_completion`, `assistant_already_completed`,
`assistant_completion_mismatch`, and `session_completion_before_assistant`.

An invariant failure contains only its code, the prior status, and the rejected input type. It never
copies task text, assistant text, identifiers, payloads, or validator details. The returned state is
the same object supplied to the failed reduction.

### Domain facts are not new wire messages

CAH-010 does not change protocol version 1. `task.submitted` and `cancel.requested` describe accepted
local command intent. The approval facts let both reducers and shared fixtures exercise the promised
state before a later approval story defines approval IDs, actions, decisions, and protocol ownership.
Adding those fields prematurely would create an unstable wire contract for behavior the runtime does
not yet implement.

## Practical walkthrough

1. Start at `INITIAL_SESSION_STATE` or `INITIAL_SESSION_LIFECYCLE_STATE`.
2. Reduce `task.submitted`; the lifecycle enters `starting` with sequence zero.
3. Validate `session.started` at the process boundary, then reduce it to establish session identity
   and sequence one.
4. Reduce each validated delta in order. The prior state remains unchanged, so earlier snapshots are
   safe to retain in tests or projections.
5. Require `assistant.completed` to exactly confirm accumulated text before accepting
   `session.completed`.
6. For cancellation, record `cancel.requested` first. Accept in-flight start-correlated output while
   cancellation is pending; whichever valid terminal event arrives first wins.
7. For a later task, the conversation adapter preserves the old terminal turn and creates a fresh
   one-session core.
8. To replay, run the same ordered inputs through `replay_session_updates` or
   `replaySessionLifecycle`; both stop at the first failure.

The actual M0 mock path now records every successfully written session event through the Python
reducer. The TypeScript supervisor validates the active tape with the core reducer, then publishes
accepted updates to the multi-turn projection and Ink view. `session.failed` is a normal session
terminal rather than a runtime protocol failure, so the child remains ready for another task.

## Shared fixture laboratory

The language-neutral suite under
[`protocol/fixtures/session-lifecycle/v1`](../../protocol/fixtures/session-lifecycle/v1) contains:

- 16 legal transition cases;
- 7 complete replay scenarios;
- 27 invariant-failure cases; and
- 110 complete wire-event instances validated through both existing protocol boundaries.

Each of the 50 cases starts from idle. Setup inputs construct the prior state rather than injecting
an arbitrary snapshot, and the expected result includes every normalized state or failure field.
Both language suites replay every case twice.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome | Evidence |
| --- | --- | --- | --- |
| Sequence 3 follows sequence 1 | One event is missing | `sequence_gap`; exact prior state | Shared invariant fixtures |
| Sequence 1 repeats | Duplicate or regression | `sequence_regression`; no text append | Reducer and fixture tests |
| A different session ID appears | Cross-session contamination attempt | `session_mismatch`; no mutation | Shared invariant fixtures |
| Completion text differs from deltas | Stream summary disagrees with history | `assistant_completion_mismatch` | Both core suites |
| Session completes before assistant confirmation | Terminal arrives too early | `session_completion_before_assistant` | Both core suites |
| A terminal event repeats | Second outcome is attempted | `terminal_state_absorbing` | All three terminal fixtures |
| A failure payload contains sensitive-looking text | Diagnostic could become an exfiltration path | Invariant failure omits payload and IDs | Failure-safety tests |
| Cancellation arrives before mock start is emitted | Direct-caller scheduling race | Defer request until after `session.started` | Python runtime integration test |

## Production expansion

### Example enterprise scenario

A distributed workflow platform runs millions of long-lived executions, deploys schema changes while
old histories remain active, and reconstructs state after worker loss. It may need durable event
logs, snapshots, migrations, formal state models, property-based sequence generation, poison-event
quarantine, and transition telemetry.

### Representative capabilities and tools

These are illustrative capabilities, not approved dependencies for this repository:

- [Redux Toolkit](https://redux.js.org/redux-toolkit/overview/) standardizes complex UI reducer and
  immutable-update patterns, with dependency, convention, and migration costs.
- [XState](https://stately.ai/docs/xstate) provides executable statecharts, guards, visualization,
  and model-based structure, but adds a modeling language and machine-version governance.
- [Temporal](https://docs.temporal.io/workflow-execution) provides durable workflow history and
  replay across worker failures, while requiring persistent services, workers, retention, and
  compatibility operations.
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html) generates
  action sequences and shrinks failures, but teams must maintain strategies and a faithful model.
- [OpenTelemetry](https://opentelemetry.io/docs/) observes transition latency and failures outside
  reducers, with instrumentation, storage, privacy, cardinality, and on-call ownership costs.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| State lifetime | One in-memory local session | Durable, long-lived distributed workflow |
| Specification | Reviewed table plus shared JSON | Versioned statecharts and migration policy |
| Storage | In memory; transcript is next | Event log, snapshots, retention, replication |
| Verification | Exhaustive small matrix and replay | Property, model, and compatibility suites |
| Failure handling | Safe structured rejection | Quarantine, repair, replay, incident tooling |
| Operations | Local deterministic checks | Lag, poison-event, and transition telemetry |

### Trade-offs and graduation signals

Two hand-written reducers duplicate a small amount of implementation code, but keep the learning
surface direct and force the semantic contract into reviewed fixtures. The observed cost is adapter
code between camelCase and snake_case plus careful handling of one-session versus multi-turn state.
The benefit is that framework types, protocol parsing, effects, and rendering stay outside the core.

Graduate when the graph becomes difficult to review, histories must survive process loss, schema
migrations must replay old sessions, or recurring state bugs exceed what the shared matrix can
control. Until then, a durable workflow service would add more operational responsibility than
learning value.

## Practical exercises

1. Remove sequence 2 from a replay and predict the exact state and failure fields.
2. Send `session.cancelled` with the start command's correlation ID and explain why it fails before
   changing state.
3. Add a late delta after each terminal status and compare the three normalized results.
4. Sketch the future approval protocol fields without adding them to protocol v1.
5. Change one fixture expectation and observe both language suites reject the same drift.

## Key takeaways

- Effects create facts; reducers derive state; renderers display projections.
- Command-originated facts and wire events can share lifecycle semantics without sharing a wire shape.
- Correlation, identity, sequence, and completion checks are part of state correctness.
- Terminal states stay absorbing even when duplicate or late input is diagnostically useful.
- One shared fixture suite makes equivalent behavior reviewable across two native implementations.

## Glossary

- **Absorbing state:** a terminal state from which no legal input returns to active work.
- **Domain fact:** a trusted application-owned lifecycle input that is not necessarily a wire event.
- **Guard:** a condition that must hold before a transition is accepted.
- **Invariant failure:** a stable, payload-free report that history violates the lifecycle contract.
- **Pure reducer:** a deterministic, side-effect-free state transition function.
- **Replay equivalence:** matching normalized results after processing the same ordered inputs.
- **Transition specification:** the canonical legal edges, guards, and duplicate policy.

See the shared [project glossary](../glossary.md) for the project-wide definitions.

## Further reading

- [CAH-010 user story](../../user-stories/cah-010-session-state-reducer.md)
- [Visual lesson](assets/cah-010-session-state-reducer.pptx)
- [State-switchyard cover illustration](assets/cah-010-state-switchyard.png)
- [Shared lifecycle fixture manifest](../../protocol/fixtures/session-lifecycle/v1/manifest.json)
- [Agent-loop state and terminal outcomes](../agent-loop.md)
- [Process protocol](../protocol.md)
- [Evaluation assertion layers](../evaluation.md)
- [Redux Toolkit](https://redux.js.org/redux-toolkit/overview/)
- [XState](https://stately.ai/docs/xstate)
- [Temporal workflow execution](https://docs.temporal.io/workflow-execution)
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- [OpenTelemetry](https://opentelemetry.io/docs/)
