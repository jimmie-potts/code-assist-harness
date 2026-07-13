# CAH-009 - Document the first end-to-end execution

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-006

## User story

> As a learner, I want the mocked walking skeleton explained from user input through Python events
> and back to rendering so that I can trace the complete architecture before model behavior is added.

## Scope

- Trace the implemented `session.start` path across the Ink and Python processes.
- Explain message ownership, channel separation, streaming, reduction, cancellation, and terminal
  state using examples taken from the automated integration scenario.
- Identify intentional model-free and persistence-free simplifications.

## Acceptance criteria

1. The guide traces one `session.start` command from a user key action through stdin, Python mock
   orchestration, ordered events on stdout, TUI validation/reduction, and rendering.
2. It identifies which process owns terminal input, display, child supervision, orchestration,
   trusted session state, and future policy decisions.
3. It includes one valid NDJSON command and the corresponding `session.started`, multiple
   `assistant.delta`, `assistant.completed`, and `session.completed` events.
4. The examples follow the actual protocol version, IDs, correlations, sequences, timestamps, and
   payloads used by an automated integration fixture.
5. It explains why stdin carries commands, stdout carries only protocol events, and stderr carries
   human diagnostics.
6. It explains why raw logging on Python stdout would corrupt the protocol.
7. It traces cancellation from keypress through `session.cancel` to exactly one terminal
   `session.cancelled` event, including the completion-race rule.
8. The documented sequence matches an automated Node-Python integration test.
9. Intentional simplifications are named, including fake output, no provider, no tools, no approvals,
   and no durable transcript.
10. The guide links to the relevant protocol, agent-loop, safety, and glossary concepts without
    claiming unimplemented behavior exists.

## Validation

- Run the exact integration fixture referenced by the guide and compare its normalized event stream
  with every documented example.
- Validate every NDJSON example with both the Python and TypeScript protocol parsers.
- Review the guide beside the implementation to verify process and decision ownership.
- Run a documentation link check when one is available; until CAH-007 adds it, inspect local links
  manually and run `git diff --check`.

## Documentation impact

Creates the walking-skeleton execution guide, expected under `docs/agent-loop.md` or a clearly linked
dedicated document, and updates protocol and architecture cross-links. This is the learning record
for the first working vertical slice.

## Out of scope

- Explaining hypothetical provider, tool, edit, approval, or transcript paths as if implemented.
- Adding runtime behavior to make the guide easier to write.
