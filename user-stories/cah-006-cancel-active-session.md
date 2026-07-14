# CAH-006 - Cancel an active session

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-005
- **Lesson:** [Session cancellation](../docs/lessons/cah-006-session-cancellation.md)

## User story

> As a user, I want to cancel a running session so that I retain control when an operation is taking
> too long or heading in the wrong direction.

## Scope

- Add a visible keyboard action that sends `session.cancel` for the active session.
- Make mock streaming cancellable and define idempotent race behavior around completion.
- Preserve the exactly-one-terminal-event invariant.
- Ensure application exit during active work terminates and reaps the Python child.

## Acceptance criteria

1. The TUI displays a clear key hint whenever an active session can be cancelled.
2. Invoking the action sends a validated `session.cancel` command for the active session.
3. Python stops producing assistant deltas after it accepts cancellation.
4. A cancelled session emits exactly one `session.cancelled` terminal event and no later completed or
   failed terminal event.
5. The UI clearly distinguishes cancellation from failure and returns to a state from which another
   task can be started.
6. Repeated cancellation requests are harmless and do not produce duplicate terminal events.
7. A cancel request racing with normal completion produces one documented terminal result based on
   which terminal transition wins.
8. Exiting while a session is active terminates and reaps the Python child without leaving terminal
   artifacts.
9. Automated tests cover cancellation before the first delta, between deltas, repeated requests,
   the completion race, and a request after completion.
10. Cancellation code documents task ownership, cleanup, and exactly-one-terminal-event invariants.

## Validation

- Run deterministic Python lifecycle tests with controlled scheduling points.
- Run TypeScript reducer and rendering tests for cancelling, cancelled, and failed distinctions.
- Run Node-Python integration tests that cancel before the first delta and between deltas and assert
  the child emits no post-terminal assistant events.
- Launch the TUI, cancel an active mocked session, start another, and exit during active work as
  supplemental WSL checks.
- Run all Python and TUI static checks without network access.

## Documentation impact

Update the protocol and architecture documents with cancellation ownership, the completion race,
idempotency, cleanup, and terminal-event invariant. Document the key binding and user-visible states.

## Out of scope

- Provider-operation cancellation; CAH-020 and CAH-021 apply the established lifecycle to providers.
- Tool or subprocess cancellation.
- Persisted cancellation records before CAH-011.
