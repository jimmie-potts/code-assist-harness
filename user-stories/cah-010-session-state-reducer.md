# CAH-010 - Implement session state as a reducer

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E1 - Session, state, and event model
- **Dependencies:** CAH-004, CAH-006, CAH-007
- **Lesson:** [Session state reducer](../docs/lessons/cah-010-session-state-reducer.md)

## User story

> As a harness developer, I want session state to be derived from events so that UI state,
> transcripts, tests, and replay all share the same lifecycle semantics.

## Scope

- Define the initial lifecycle states: `idle`, `starting`, `running`, `awaiting_approval`,
  `cancelling`, `completed`, `cancelled`, and `failed`.
- Publish one documented transition specification used to keep pure Python and TypeScript reducers
  semantically equivalent.
- Represent illegal transitions as structured invariant failures.
- Add exhaustive transition and deterministic replay tests.

## Acceptance criteria

1. A pure reducer maps current state plus one validated event to the next state without I/O, clock,
   randomness, mutation of prior state, or provider-specific objects.
2. Every legal transition among the initial states is explicitly enumerated and tested.
3. An illegal transition produces a structured invariant failure containing the prior state and event
   type without leaking event payload secrets.
4. `completed`, `cancelled`, and `failed` are terminal and cannot transition back to an active state.
5. Duplicate or late terminal events cannot create a second terminal transition and follow one
   documented error/idempotency policy.
6. Replaying the same ordered validated event list produces equivalent state every time.
7. Event sequence gaps, regressions, and session-ID mismatches are detected before they silently
   alter state.
8. Python and TUI reducers pass the same shared transition and replay fixtures.
9. Tests cover normal completion, cancellation, runtime failure, approval waiting, cancellation
   races, and every legal terminal path.
10. Reducer APIs and the transition specification document purity, ordering, ownership, and terminal
    invariants.

## Validation

- Run shared fixture suites through both reducers and compare normalized final state and failures.
- Run focused Python and TypeScript reducer tests, including replaying every fixture twice.
- Run protocol integration tests to verify the reducer consumes only validated events.
- Run the repository-wide non-live checks.

## Documentation impact

Update the glossary and agent-loop/protocol documents with lifecycle states, the transition table,
sequence validation, replay semantics, and exactly-one-terminal-state behavior.

## Out of scope

- Durable transcript storage, introduced by CAH-011.
- Provider requests or tool execution.
- Resuming or mutating a completed session.
