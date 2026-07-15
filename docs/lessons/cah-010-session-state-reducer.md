# CAH-010 lesson: Session state reducer

- **Unit:** CAH-010
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; equivalent Python and TypeScript reducers do not exist yet
- **Story:** [CAH-010](../../user-stories/cah-010-session-state-reducer.md)
- **Related architecture:** [Agent loop](../agent-loop.md), [protocol](../protocol.md),
  [architecture](../architecture.md), and [evaluation](../evaluation.md)

> This lesson describes the planned state model. CAH-010 must still publish the actual transition
> specification and resolve how every listed state is represented by validated reducer input.

## Quick summary

CAH-010 will express session lifecycle as pure state reduction shared semantically by Python and
TypeScript. Given equivalent prior state and validated input, both sides must reach equivalent next
state, reject illegal ordering, and keep terminal states absorbing.

## Learning objectives

After completing this unit, you should be able to:

- distinguish events, state, effects, and rendering;
- write a pure reducer with explicit legal and illegal transitions;
- explain sequence, session-identity, duplicate, and terminal-event checks;
- prove cross-language equivalence using shared transition and replay fixtures; and
- identify when formal statechart or durable event-processing infrastructure is justified.

## Why this unit matters

Before a reducer, Python lifecycle logic, TUI status code, tests, and future replay can each invent a
slightly different meaning of “running” or “cancelled.” A published transition specification creates
one inspectable semantic contract while still allowing each language to use native types.

## Key concepts

**State:** the derived lifecycle snapshot, including status and safe identifiers needed to validate
the next input. It is not a hidden mutable flag owned independently by every component.

**Event:** a validated fact that has occurred. Reducers interpret facts; they do not perform I/O or
decide policy.

**Pure reducer:** a function of prior state and validated input only. It performs no clock access,
randomness, mutation, logging, provider call, or subprocess work.

**Transition specification:** the reviewed table of legal source, input, target, guards, and invariant
failures used by both implementations and shared fixtures.

**Replay:** folding the same ordered validated inputs over the same initial state to reproduce an
equivalent result. Replay in CAH-010 does not resume work or re-execute side effects.

**Absorbing terminal state:** `completed`, `cancelled`, or `failed` cannot return to active work.

## Architecture and design

Planned lifecycle states are `idle`, `starting`, `running`, `awaiting_approval`, `cancelling`,
`completed`, `cancelled`, and `failed`. A useful specification shape is:

| Prior state | Validated input | Next state | Important guard |
| --- | --- | --- | --- |
| `idle` | start accepted | `starting` or `running` | New session identity is valid. |
| `starting` | `session.started` | `running` | First sequence is valid. |
| `running` | assistant/session event | `running` or terminal | Session and sequence match. |
| `running` | cancellation accepted | `cancelling` | Request targets active session. |
| active state | terminal event | corresponding terminal state | No terminal outcome exists yet. |
| terminal state | later active event | invariant failure/no transition | Terminal states are absorbing. |

This table is illustrative, not the final CAH-010 contract. Protocol v1 currently names
`session.started`, the three terminal events, and assistant events, but does not yet name wire events
for every intermediate state. CAH-010 must deliberately decide whether command-originated facts or
new domain/protocol events drive `starting` and `cancelling`, and how the future
`awaiting_approval` state is represented. It must not let the TUI silently invent authoritative
transitions that Python cannot replay. Any new wire message requires protocol documentation and
cross-language fixtures.

| Layer | Responsibility |
| --- | --- |
| Boundary validators | Reject malformed or unsupported wire objects before reduction. |
| Sequence/session guard | Detect gaps, regressions, and cross-session events. |
| Reducer | Apply one legal transition without side effects. |
| Runtime effect layer | Start/cancel tasks and emit facts; never hide effects inside reducer. |
| TUI projection | Render reduced state without deciding lifecycle authority. |

## Practical walkthrough

1. Inventory every state promised by the story and every validated input capable of entering it.
2. Resolve missing transition inputs before coding; update the protocol if wire events are added.
3. Publish one transition table with source, input, target, guards, and duplicate policy.
4. Define immutable Python and TypeScript state shapes using only harness-owned data.
5. Keep session identity and last accepted sequence in state or in a clearly preceding validator.
6. Implement the smallest pure reducer in each language from the same specification.
7. Represent illegal transitions as bounded invariant failures without copying sensitive payloads.
8. Add shared fixtures for every legal edge, sequence gap, wrong session, duplicate, and late terminal.
9. Replay each fixture twice and compare normalized final state and failure identity across languages.
10. Route M0 completion and cancellation paths through the new reducers without moving effects into them.

Do not test only named states. Prove edges, including the boundary between the last active state and
each terminal state. Inject events in the wrong order and assert that state does not advance. A
duplicate policy may be idempotent or diagnostic for a particular event, but it must be explicit and
must never create a second terminal transition.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe outcome |
| --- | --- | --- | --- |
| Reducer reads clock | Replay differs later | Reducer design | Time arrives as validated data, if needed. |
| TUI invents `cancelling` | Python and UI disagree | Transition/input contract | Both consume equivalent authoritative facts. |
| Sequence gap is ignored | Missing event silently changes state | Sequence guard | Structured invariant failure, no advance. |
| Wrong session event arrives | State is contaminated | Identity guard | Event is rejected before mutation. |
| Terminal event repeats | Two outcomes appear | Duplicate/terminal policy | Terminal state remains absorbing. |
| Payload is copied into error | Secret reaches diagnostics | Failure normalization | Only safe state and event type are reported. |

## Production expansion

### Example enterprise scenario

A distributed workflow platform maintains millions of long-lived executions, supports rolling
schema upgrades, and must reconstruct state after crashes while auditors inspect transition history.
It may need durable event logs, snapshots, migration policy, formal state models, property-based
testing, partition ownership, and observability around poison events and replay lag.

### Typical production capabilities and tools

These references illustrate optional capabilities, not recommendations for this MVP:

- [Redux Toolkit](https://redux.js.org/redux-toolkit/overview/) illustrates standardized reducer and
  immutable-update patterns for complex UI state, while introducing framework conventions,
  dependency upgrades, integration code, and migration work when state contracts change.
- [XState](https://stately.ai/docs/xstate) illustrates executable statecharts, guards, visualization,
  and model-based state-machine structure, but teams must absorb its modeling vocabulary, maintain
  generated or visual artifacts, and govern version and machine migrations.
- [Temporal](https://docs.temporal.io/workflow-execution) illustrates durable workflow event history
  and replay across worker failures while adding persistent services, deterministic workflow rules,
  worker operations, retention, and compatibility management.
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html) illustrates
  generation of action sequences to discover unexpected state-machine paths, at the cost of strategy
  design, runtime, shrinking diagnosis, and maintenance of a faithful behavioral model.
- [OpenTelemetry](https://opentelemetry.io/docs/) illustrates observing transition latency and
  failures without putting telemetry side effects inside reducers, but requires instrumentation,
  cardinality controls, storage, dashboards, privacy policy, and an owning operations path.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| State lifetime | One local runtime/session | Durable, long-lived distributed workflows |
| Specification | Reviewed table plus fixtures | Versioned statecharts/schemas and migration policy |
| Storage | In memory; transcript later | Event log, snapshots, retention, replication |
| Verification | Exhaustive small table and replay tests | Property/model checking and compatibility suites |
| Failure handling | Structured invariant failure | Quarantine, repair, replay tooling, incident workflows |
| Operations | Local diagnostics | Lag, transition, poison-event metrics and runbooks |

### Trade-offs and graduation signals

Two small hand-written reducers keep the lifecycle visible and teach the core semantics. A statechart
library reduces boilerplate for hierarchy and concurrency; durable workflow systems add recovery and
coordination. Both introduce abstractions, upgrade constraints, and operational ownership. Graduate
when the transition graph becomes hard to review, histories must survive process loss, or recurring
cross-version and concurrency bugs exceed what shared fixtures can control.

## Practical exercises

1. Enumerate which currently named protocol events can and cannot enter each planned state.
2. Write one illegal transition fixture for every terminal state.
3. Remove a sequence number from a replay and predict the exact invariant failure.
4. Add the same event twice and compare an idempotent policy with a strict diagnostic policy.
5. Sketch a property: “after a terminal event, no generated event sequence returns to active state.”

## Key takeaways

- Reducers derive state; runtime code performs effects and emits authoritative facts.
- Purity and explicit transitions make cross-language replay testable.
- Sequence, session identity, duplicates, and terminal absorption are part of lifecycle correctness.
- More formal or durable machinery is justified by graph complexity and recovery needs.

## Glossary

- **Absorbing state:** a state from which no legal transition returns to active work.
- **Guard:** a condition that must hold before a transition is legal.
- **Invariant failure:** a structured report that the event history violates a lifecycle rule.
- **Pure reducer:** a deterministic, side-effect-free state transition function.
- **Replay equivalence:** matching defined state semantics after processing the same ordered inputs.
- **Transition specification:** the canonical legal-edge and guard definition.

See the shared [project glossary](../glossary.md) for reducer, event, session, terminal state, and sequence.

## Further reading

- [CAH-010 user story](../../user-stories/cah-010-session-state-reducer.md)
- [Agent-loop state and terminal outcomes](../agent-loop.md)
- [Process protocol](../protocol.md)
- [Evaluation assertion layers](../evaluation.md)
- [Project glossary](../glossary.md)
- [Redux Toolkit](https://redux.js.org/redux-toolkit/overview/)
- [XState](https://stately.ai/docs/xstate)
- [Temporal workflow execution](https://docs.temporal.io/workflow-execution)
- [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- [OpenTelemetry](https://opentelemetry.io/docs/)
