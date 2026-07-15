# CAH-005 - Stream a mocked session end to end

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-002, CAH-003, CAH-004
- **Lesson:** [Mocked streaming session](../docs/lessons/cah-005-mocked-streaming-session.md)

## User story

> As a user, I want to submit a task and see a mocked agent response arrive incrementally so that the
> complete UI/runtime boundary is proven.

## Scope

- Connect the Ink input flow to the real child-process protocol using deterministic Python mock
  behavior.
- Stream assistant deltas and reduce them into visible conversation and status state.
- Complete one session and allow another without restarting the application.
- Add an integration test that exercises the real Node-Python boundary.

## Acceptance criteria

1. Submitting non-empty input sends one validated `session.start` command with a command ID.
2. Python emits `session.started` correlated to that command.
3. Python emits at least three ordered, deliberately delayed `assistant.delta` events.
4. The TUI renders each delta before the complete response arrives rather than buffering the whole
   message.
5. Python emits `assistant.completed` containing exactly the accumulated text.
6. Python then emits exactly one `session.completed` terminal event.
7. The status line visibly transitions through idle, running, and completed states.
8. After completion, a second non-empty task can run with a distinct session ID and sequence starting
   according to the documented session rules.
9. Empty or whitespace-only input does not start a session and yields understandable UI feedback.
10. No model, network, filesystem mutation, transcript persistence, tool, or subprocess execution
    occurs.
11. An integration test runs the real npm/Node to `uv`/Python boundary with deterministic mocked
    runtime behavior.
12. The visible streaming states have reducer and/or rendering coverage.

## Validation

- Run the Python protocol and mocked-runtime tests.
- Run the TypeScript reducer, rendering, and protocol tests.
- Run the Node-Python integration test and assert event ordering, intermediate renders, complete
  accumulated text, and two consecutive sessions.
- Run all static checks without an API key and with network access unavailable.
- Manually submit a sample task in WSL and observe incremental rendering as a supplemental check.

## Documentation impact

Update protocol examples with the exact command/event sequence and document the temporary mock
runtime mode. Add the end-to-end development command and describe visible status transitions.

## Out of scope

- Provider interfaces, prompts, tools, approvals, and workspace inspection.
- Cancellation, which is introduced by CAH-006.
- Durable transcripts or event replay.
