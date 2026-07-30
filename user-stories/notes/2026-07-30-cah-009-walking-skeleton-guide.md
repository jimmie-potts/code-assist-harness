# CAH-009 walking-skeleton guide implementation note

- **Date:** 2026-07-30
- **Story:** [CAH-009](../cah-009-document-walking-skeleton.md)
- **Guide:** [First end-to-end execution](../../docs/walking-skeleton.md)
- **Lesson:** [Walking-skeleton guide](../../docs/lessons/cah-009-walking-skeleton-guide.md)

## Delivered learning path

CAH-009 turns the already implemented CAH-005 success path and CAH-006 cancellation path into one
causal, ownership-aware walkthrough. It begins with Ink's Enter or Escape handling, follows the
validated command written to Python stdin, names the runtime and mock-session functions that select
and emit lifecycle facts, and returns through TypeScript framing, validation, pure reduction, and
Ink rendering.

The guide keeps local projection updates distinct from wire messages. `task.submitted` prevents a
fast `session.started` event from outrunning its local cause, and `cancel.requested` renders pending
intent without claiming that cancellation already won. Python remains authoritative for session
identity, sequence assignment, and the sole terminal event.

## Executable teaching evidence

Four shared NDJSON tapes live under `protocol/fixtures/v1/scenarios/` and are listed in the version 1
fixture manifest:

- `walking-skeleton-success.commands.ndjson` contains the successful `session.start`;
- `walking-skeleton-success.events.ndjson` contains `session.started`, three
  `assistant.delta` events, exact `assistant.completed` text, and `session.completed`;
- `walking-skeleton-cancel.commands.ndjson` contains the cancellation scenario's `session.start`
  and addressable `session.cancel`; and
- `walking-skeleton-cancel.events.ndjson` contains `session.started` followed by the sole
  `session.cancelled` terminal event.

The Python and TypeScript protocol suites validate every physical line with their respective
boundary parsers and verify that the guide's four NDJSON blocks match these files exactly. The real
Node-to-`uv`-to-Python boundary comparison normalizes only event timestamps; it preserves message
types, command and session IDs, correlations, sequences, and payloads. Timestamps are descriptive,
while the unchanged sequence values remain the ordering authority.

The success and cancellation files stay separate by direction because stdin commands and stdout
events are not one multiplexed transcript. They are documentation fixtures, not the future `evals/`
scenario format and not a substitute for either language's validator.

## Scope boundary

CAH-009 changes documentation, shared fixture evidence, and tests only. It does not change the
runtime, supervisor, reducer, Ink component, protocol schema, or any user-visible execution
behavior. The deterministic response is still a mock runtime fixture. No provider call, workspace
read, tool dispatch, approval, file edit, transcript, or full agent loop exists yet.

The guide also preserves the cancellation race rather than presenting Escape as guaranteed
success. Cancellation may terminate at sequence 2 before output or at the next sequence after an
already accepted delta. If completion owns the serialized terminal boundary first, the ordinary
six-event completion tape remains authoritative and no `session.cancelled` event follows.

## Validation evidence

- The shared Python fixture suite frames and parses every teaching command and event.
- The shared TypeScript fixture suite frames and parses the same files and checks the guide blocks.
- The real process-boundary suite compares normalized success and cancellation tapes while retaining
  exact lifecycle fields other than timestamps.
- Existing Python checkpoint tests continue to cover cancellation before output, between deltas,
  and against the completion boundary without relying on the teaching timestamps.
- Local documentation links and whitespace are checked before publication; CAH-007 will make the
  complete non-live repository gate one canonical command.

All evidence remains model-free, credential-free, and network-free. The runtime resolves the
temporary workspace and the tests inspect its directory, but no target-workspace content is
discovered or read and no workspace mutation occurs.

## Next unit

CAH-007 is now dependency-ready. It should establish one documented repository command that runs
the required Python, TypeScript, protocol, integration, and documentation checks without credentials
or network access. It must reuse the existing suites rather than duplicate their command lists in
CI.
