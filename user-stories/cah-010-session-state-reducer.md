# CAH-010 - Implement session state as a reducer

- **Status:** Done
- **Milestone / epic:** M1 - Conversational core / E1 - Session, state, and event model
- **Dependencies:** CAH-004, CAH-006, CAH-007
- **Lesson:** [Session state reducer](../docs/lessons/cah-010-session-state-reducer.md)
- **Visual lesson:**
  [Every event needs the right track](../docs/lessons/assets/cah-010-session-state-reducer.pptx)

## User story

> As a harness developer, I want session state to be derived from trusted lifecycle inputs so that
> UI state, transcripts, tests, and replay all share the same lifecycle semantics.

## Scope

- Define the initial lifecycle states: `idle`, `starting`, `running`, `awaiting_approval`,
  `cancelling`, `completed`, `cancelled`, and `failed`.
- Publish one documented transition specification used to keep pure Python and TypeScript reducers
  semantically equivalent.
- Represent illegal transitions as structured invariant failures.
- Add exhaustive transition and deterministic replay tests.

## Acceptance criteria

1. A pure reducer maps current state plus one trusted domain fact or validated session event to the
   next state without I/O, clock, randomness, mutation of prior state, or provider-specific objects.
2. Every legal transition among the initial states is explicitly enumerated and tested.
3. An illegal transition produces a structured invariant failure containing the prior state and input
   type without leaking input payload secrets.
4. `completed`, `cancelled`, and `failed` are terminal and cannot transition back to an active state.
5. Duplicate or late terminal events cannot create a second terminal transition and follow one
   documented error/idempotency policy.
6. Replaying the same ordered trusted lifecycle input list produces equivalent state every time.
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
- Run protocol integration tests to verify wire events are validated before reduction, while domain
  facts enter only through their trusted application owners.
- Run the repository-wide non-live checks.

## Documentation impact

Update the glossary and agent-loop/protocol documents with lifecycle states, the transition table,
sequence validation, replay semantics, and exactly-one-terminal-state behavior.

## Out of scope

- Durable transcript storage, introduced by CAH-011.
- Provider requests or tool execution.
- Resuming or mutating a completed session.

## Delivered evidence

- Pure immutable reducers live in `src/code_assist_harness/session_state.py` and
  `tui/src/session-lifecycle.ts`; the TUI conversation adapter remains a separate multi-turn
  projection.
- The canonical table has 16 legal transitions across all eight states. Structured failures use
  ten stable codes and return the exact prior state without copying payloads or identifiers.
- `protocol/fixtures/session-lifecycle/v1/` supplies 16 legal-transition cases, 7 replay scenarios,
  and 27 invariant failures. Both languages validate each wire envelope before reduction and replay
  all 50 cases twice.
- The Python mock records successfully written events through the reducer. The TypeScript
  supervisor validates its active tape through the core before publishing it to Ink.
- Focused core, fixture, runtime, supervisor, and render tests cover completion, cancellation,
  approval waiting, failure, races, sequence and identity violations, terminal absorption, and a
  later task after every terminal outcome.
- `./scripts/check` is the final local and CI validation entry point for this completed unit.
