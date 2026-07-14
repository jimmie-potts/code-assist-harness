# ADR 0003: Use a versioned NDJSON protocol

- **Status:** Accepted
- **Date:** 2026-07-13
- **Decision scope:** Communication between the Ink and Python processes

## Context

The TUI and runtime need to exchange streamed, ordered messages across standard pipes. The contract
must be easy to inspect while learning, deterministic in tests, resilient to incremental reads, and
explicit about compatibility. Introducing code generation or a transport service before the first
vertical slice would add machinery unrelated to the central agent-loop goals.

The transport also shares a process boundary with human-readable diagnostics. Any ambiguity about
which output is protocol data can corrupt a running session.

## Decision

Protocol version 1 uses newline-delimited JSON over the child process standard streams. Every wire
message is exactly one complete JSON object followed by one newline.

- The TUI sends commands on Python stdin.
- Python sends events on stdout.
- Python sends diagnostics on stderr.
- Raw logging, tracebacks, progress text, and debug printing are prohibited on protocol stdout.

An initial event envelope has this shape:

```json
{
  "protocol_version": 1,
  "type": "session.started",
  "session_id": "ses_123",
  "sequence": 1,
  "timestamp": "2026-07-13T14:00:00Z",
  "correlation_id": "cmd_123",
  "payload": {}
}
```

Commands have a unique command ID. Events caused by a command copy that value into
`correlation_id`. Session events have a session ID and a monotonically increasing sequence number;
timestamps are descriptive and do not determine event order.

The initial protocol surface is deliberately small:

- commands: `runtime.initialize`, `session.start`, `session.cancel`, and `runtime.shutdown`;
- events: `runtime.ready`, `session.started`, `assistant.delta`, `assistant.completed`,
  `session.completed`, `session.cancelled`, `session.failed`, and `runtime.error`.

Python and TypeScript maintain their protocol types explicitly. Pydantic v2 validates Python
commands and events; Zod validates messages at the TypeScript process boundary. Shared golden JSON
fixtures under `protocol/fixtures/` are parsed in contract tests in both languages. Schema-based
code generation is deferred until actual drift makes its benefit greater than its complexity.

## Compatibility and failure rules

- Both processes reject an unsupported `protocol_version` explicitly.
- Malformed JSON and an invalid known message become structured protocol errors rather than
  unhandled exceptions.
- An unknown event type does not crash the TUI; it is surfaced safely and handled according to the
  documented compatibility policy.
- A diagnostic may describe the offending input safely but must not echo credentials or unbounded
  content.
- Protocol parsing validates the envelope and the payload for the declared type.
- A writer serializes complete messages so output from concurrent runtime tasks cannot interleave.
- Session sequence numbers are assigned at the ordered event boundary.

Unknown fields and unknown message types need an explicit compatibility policy in the detailed
protocol specification before version 1 is considered stable. They must never be accepted merely
because a static type assertion says the value is valid.

## Consequences

### Benefits

- Messages are human-readable, recordable, and easy to construct as golden fixtures.
- Newline framing works naturally with streamed deltas and standard process pipes.
- The transport has no network listener, serialization service, or generated-code toolchain.
- Version, correlation, and sequence metadata make failures and replay diagnosable.

### Costs and risks

- Both languages must update their validators and shared fixtures when the contract changes.
- A stray print to stdout can corrupt the stream.
- JSON does not itself enforce schemas or encode every future data type conveniently.
- Very large payloads could block pipes or increase memory use unless message and output bounds are
  enforced.

These risks are controlled through boundary validation, stdout discipline, bounded payloads,
contract tests, and end-to-end process tests.

## Alternatives considered

### Unstructured console text

Rejected because it cannot reliably distinguish deltas, state transitions, errors, approvals, or
future compatibility.

### JSON-RPC

Deferred because request-response procedure semantics are more machinery than the initial
command-and-event stream requires. Correlation IDs provide the needed linkage without making
streamed domain events look like RPC responses.

### Protocol Buffers, MessagePack, or another binary protocol

Rejected for the first slices because code generation and binary inspection would hinder the
learning-first workflow without a demonstrated performance need.

### Generate Python and TypeScript from one schema immediately

Deferred because hand-maintained validators plus shared fixtures are simpler at this scale. The
choice can be revisited if contract drift becomes a recurring failure.

## Implementation status

This is an accepted target decision. At acceptance time, neither process protocol code nor shared
fixtures existed. CAH-004 defines version 1 in code and contract tests; CAH-005 exercises it across
the real Node–Python boundary.
