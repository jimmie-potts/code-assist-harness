# CAH-004 - Define protocol version 1

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-003
- **Lesson:** [Protocol version 1](../docs/lessons/cah-004-protocol-v1.md)

## User story

> As a harness developer, I want a small versioned protocol so that Python and TypeScript can evolve
> without relying on unstructured console text.

## Scope

- Define protocol version 1 envelopes and the initial commands and events.
- Validate Python boundary data with Pydantic v2 and TypeScript boundary data with Zod.
- Add line-oriented readers and ordered writers that preserve stdout exclusively for valid NDJSON.
- Add hand-maintained cross-language types plus shared golden fixtures.
- Define recoverable malformed-line and unknown-type behavior.

## Initial messages

Commands: `runtime.initialize`, `session.start`, `session.cancel`, and `runtime.shutdown`.

Events: `runtime.ready`, `session.started`, `assistant.delta`, `assistant.completed`,
`session.completed`, `session.cancelled`, `session.failed`, and `runtime.error`.

## Acceptance criteria

1. Every wire message is exactly one JSON object followed by one newline.
2. Every command has a protocol version, type, and command ID.
3. Every event has a protocol version and type; session events also have a session ID and monotonic
   sequence number.
4. Events caused by a command can reference its ID as a correlation ID.
5. Timestamps use one documented UTC representation and are not used as ordering substitutes for
   sequence numbers.
6. Both languages reject unsupported protocol versions with a structured protocol error.
7. Malformed JSON is contained to its input line and reported as a structured protocol error rather
   than crashing the runtime or TUI.
8. Unknown event types do not crash the TUI and remain distinguishable from malformed known events.
9. Pydantic v2 validates Python boundary objects and Zod validates TUI boundary objects before they
   enter trusted state.
10. Shared golden JSON fixtures are accepted by Python and TypeScript contract tests; invalid
    fixtures demonstrate version, envelope, and payload failures.
11. Protocol diagnostics are sent through structured events or stderr and never corrupt stdout.
12. Wire types are clearly distinguished from local domain and UI-state types in code documentation.

## Validation

- Run Python protocol unit and fixture tests with pytest.
- Run TypeScript parser, fixture, and unknown-event tests.
- Pipe multiple valid and invalid lines through the real runtime boundary and assert later valid lines
  are still processed after a recoverable malformed line.
- Assert emitted stdout can be parsed line by line as protocol version 1 objects.
- Run all Python and TUI static checks without network access.

## Documentation impact

Create or update `docs/protocol.md` and `protocol/README.md` with the envelope, ownership, sequencing,
correlation, compatibility, error-handling, stdin/stdout/stderr rules, and example messages. Record
intentional hand-maintained cross-language types as an M0 simplification.

## Out of scope

- Schema/code generation between languages.
- Tool-call, plan, approval, diff, transcript, or usage event families.
- Session lifecycle reduction beyond the minimum needed to parse and render initial events.
