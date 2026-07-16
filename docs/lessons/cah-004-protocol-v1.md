# CAH-004 lesson: Protocol version 1

- **Unit:** CAH-004
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Implemented and validated across the real Node–uv–Python boundary
- **Story:** [CAH-004](../../user-stories/cah-004-define-protocol-v1.md)
- **Related architecture:** [ADR 0003](../adr/0003-ndjson-protocol.md) and
  [protocol design](../protocol.md)

> This lesson is verified against the implemented protocol schemas, byte readers, ordered writer,
> shared fixtures, runtime readiness handshake, and failure tests. Mock streaming begins in CAH-005.

## Quick summary

This unit converts the child pipes into a small, versioned command-and-event protocol. Every line is
framed before it is parsed, every message is runtime-validated before it becomes trusted, and the
parent enters `running` only after a correlated readiness event confirms the canonical workspace.
The result teaches framing, validation, causality, ordering, compatibility, and error containment
without introducing agent intelligence.

## Learning objectives

After completing this unit, you should be able to:

- explain why newline framing works only when stdout discipline is absolute;
- distinguish wire validation from Python or TypeScript static types;
- use command IDs, correlation IDs, session IDs, sequence numbers, and timestamps correctly;
- explain the chosen fail-closed policy for untrusted stdout; and
- prove Python and TypeScript agree through shared valid and invalid fixtures.

## Why this unit matters

Raw console text cannot reliably express a streamed delta, terminal outcome, or structured failure.
A versioned contract lets the two languages evolve independently while making incompatibility and
bad input observable instead of accidental.

## Key concepts

### NDJSON provides framing, not validation

Each physical line contains one UTF-8 JSON object followed by `\n`. The newline tells a reader where
one message ends. It does not prove that the JSON has a known version, discriminator, or payload.

### The envelope routes before the payload is trusted

`protocol_version` selects compatibility and `type` selects a message schema. A boundary validator
must validate the envelope and then the declared payload before converting it to trusted domain or
UI state.

### Identifiers answer different questions

- `command_id`: which TUI request is this?
- `correlation_id`: which command caused this event?
- `session_id`: which task lifecycle owns this event?
- `sequence`: where does this session event occur in authoritative order?
- `timestamp`: when was it observed, useful for people but not ordering?

### Static types disappear at the pipe

TypeScript annotations cannot validate bytes from Python, and Python annotations cannot validate
stdin. Pydantic v2 and Zod now validate those bytes; only successful results can become local types
with narrower responsibilities.

## Architecture and design

```text
Ink command object --Zod--> LF reader --stdin--> Pydantic command --Python runtime
Ink lifecycle     <--Zod--- LF reader <--stdout-- Pydantic event  <--ordered writer

Python stderr: diagnostics only; never part of the event stream
```

Initial commands are `runtime.initialize`, `session.start`, `session.cancel`, and
`runtime.shutdown`. Initial events are `runtime.ready`, `session.started`, `assistant.delta`,
`assistant.completed`, `session.completed`, `session.cancelled`, `session.failed`, and
`runtime.error`.

The implemented invariants are:

- every wire message is exactly one JSON object terminated by one newline;
- every message declares protocol version and type, and every command has a command ID;
- session events carry a session ID and strictly increasing sequence number;
- sequence, never timestamp, determines session order;
- one ordered writer owns sequence allocation and prevents concurrent event bytes from interleaving;
- unsupported versions, malformed JSON, invalid known payloads, and unknown types remain distinct;
- a recoverable bad line does not prevent a later valid line from being processed; and
- diagnostics and raw exceptions never corrupt protocol stdout.

The two directions deliberately choose different recovery policies. Python reports a safe,
recoverable `runtime.error` for a malformed command line and resumes at the next LF. The TUI fails
closed on an unknown or malformed event because stdout is the authoritative state stream: it enters
`protocol-failed`, closes command input, and never guesses event meaning.

| Implemented seam | Responsibility |
| --- | --- |
| `protocol/fixtures/v1/manifest.json` | Reviewed 12-valid / 12-invalid cross-language contract |
| `src/code_assist_harness/protocol/models.py` | Frozen, extra-forbid Pydantic v2 wire models |
| `src/code_assist_harness/protocol/codec.py` | JSON, version, envelope, type, and payload classification |
| `src/code_assist_harness/protocol/streams.py` | 64-KiB readers and cancellation-safe ordered event writer |
| `tui/src/protocol.ts` | Strict Zod schemas, parsers, wire types, and encoders |
| `tui/src/protocol-stream.ts` | Fatal UTF-8 decoding and LF-only byte framing |
| `runtime.py` / `runtime-supervisor.ts` | Correlated initialization, readiness, and orderly shutdown |

## Practical walkthrough

1. **Start with the reviewed fixtures.** `protocol/fixtures/v1/manifest.json` names every valid
   message family and each expected failure stage. Python and TypeScript load the same bytes.
2. **Establish envelope trust in layers.** Both codecs first require a JSON object and integer
   version, then validate common identifiers and the exact millisecond-UTC timestamp, dispatch a
   known type, and finally validate the strict selected model.
3. **Frame bytes before decoding.** Both 64-KiB readers wait for LF, reject CRLF, blank lines, invalid
   UTF-8, oversized lines, and incomplete EOF, and can resynchronize at the next physical line.
   Python continues after a bad command; the TUI deliberately fails closed after a bad event.
4. **Keep errors safe.** Parser results contain stable codes and input-independent messages—never
   the raw line, Pydantic errors, or Zod issues.
5. **Make ordering one operation.** `OrderedEventWriter` holds its lock across sequence selection,
   event validation, serialization, and sink completion. A failed sink does not advance sequence;
   cancellation cannot erase a successfully completed write.
6. **Handshake through the real pipes.** The supervisor encodes `runtime.initialize`; Python compares
   its workspace with the CLI-owned canonical workspace and emits a correlated `runtime.ready`.
7. **Shut down as protocol first, signals second.** Normal cleanup writes `runtime.shutdown` before
   closing stdin; the existing process-group escalation remains the bounded fallback.
8. **Prove recovery and failure closure.** The Python subprocess test sends invalid–valid input and
   still reaches readiness. TUI tests distinguish `unknown_type` from `invalid_payload`, reject a
   mismatched ready event, and verify the real child is reaped.

## Failure scenarios to study

### A plain log line reaches stdout

**Symptom:** the TUI receives text that is not JSON. **Boundary:** Python event writer and logging
configuration. **Safe outcome:** enter a classified `protocol-failed` state and route human
diagnostics to stderr. **Evidence:** runtime and real-boundary tests parse every emitted stdout line
as a version 1 event.

### Two async producers interleave bytes

**Symptom:** fragments from valid events form one invalid line. **Boundary:** ordered writer.
**Safe outcome:** producers call one writer; its lock covers sequence allocation through sink
completion. **Evidence:** concurrency, sink-failure, and cancellation tests preserve complete,
monotonic lines without advancing sequence for an unwritten event.

### One bad line kills the runtime

**Symptom:** malformed JSON closes the child and discards a following valid command. **Boundary:**
line reader. **Safe outcome:** contain the failure to one line, emit a safe error, and continue with
the next recoverable line. **Evidence:** the subprocess sequence emits `malformed_json`,
`unsupported_version`, `unknown_type`, and `invalid_payload`, then still emits `runtime.ready`.

### An unknown event arrives on authoritative stdout

**Symptom:** a newer or corrupted child emits a discriminator the TUI does not understand.
**Boundary:** TypeScript event parser and runtime supervisor. **Safe outcome:** distinguish
`unknown_type` from a malformed known payload, enter `protocol-failed`, and close stdin without
guessing. **Evidence:** supervisor tests assert both categories remain visible and distinct.

## Production expansion

### Example enterprise scenario

Suppose independently deployed desktop clients and remote runtimes must remain compatible across
several release trains. Messages cross networks, teams publish new fields concurrently, and a bad
schema change can interrupt thousands of active sessions. Formal schemas, generated bindings, and
breaking-change gates may then outweigh hand-maintained simplicity.

### Typical production capabilities and tools

- [JSON Schema](https://json-schema.org/learn/getting-started-step-by-step) represents portable JSON
  structure and constraint definitions, while schema versioning, validator parity, and optional code
  generation add maintenance work.
- [Protocol Buffers](https://protobuf.dev/overview/) represents compact schemas and generated
  cross-language types, at the cost of compiler plugins, generated artifacts, and migration-aware
  build pipelines.
- [Buf breaking-change detection](https://buf.build/docs/breaking/) represents automated
  compatibility checks for schema evolution, while baselines, CI integration, and policy exceptions
  require ongoing governance.

These are examples of production capabilities, not replacements selected for this local protocol.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Transport | Local child pipes | Authenticated network or broker transport |
| Schema source | Hand-maintained Pydantic and Zod | Central schema with generated bindings |
| Compatibility | Integer version and golden fixtures | Multi-version policy and breaking-change gates |
| Cost | Inspectable JSON and little tooling | Registry, generators, migration policy, and operations |

### Trade-offs and graduation signals

Generated schemas reduce repetitive drift and can improve compatibility governance, but introduce a
toolchain, generated artifacts, migration rules, and less direct debugging. Graduate when clients
deploy independently, fixture drift recurs, message volume matters, or compatibility incidents are
measurable. Local pipes and a small contributor group do not justify a distributed protocol
platform.

The implementation exposed two concrete trade-offs. Closed schemas make compatibility mistakes
obvious, but even an optional field needs coordinated Pydantic, Zod, fixture, and writer changes.
Failing closed on bad stdout sacrifices in-process recovery to protect authoritative UI state, while
recovering from bad stdin preserves availability because Python can safely describe that command
failure. The cost remains justified at this scale: 120 Python tests and 119 TUI tests verify the
contract without a schema generator, service, model, credentials, or network.

## Practical exercises

1. Given three event timestamps and sequences, order them correctly and explain why.
2. Split one fixture across arbitrary byte and multibyte UTF-8 boundaries, then predict each reader
   result before running the test.
3. Create one invalid fixture for each layer: JSON syntax, envelope, version, type, and known payload.
4. Change `runtime.ready` to use a different correlation ID and explain why valid JSON is still not
   valid readiness.

## Key takeaways

- NDJSON frames messages; runtime schemas establish trust.
- Sequence numbers establish session order, while correlation IDs connect cause and effect.
- Recover malformed commands when the line boundary remains trustworthy; fail closed on untrusted
  authoritative events.
- stdout is a machine contract and stderr is the diagnostic escape path.

## Glossary

- **Envelope:** Common routing and compatibility fields surrounding a message payload.
- **Framing:** The rule that separates one byte-level message from the next.
- **Wire type:** A validated process-boundary shape, distinct from local domain or UI state.

See the shared [project glossary](../glossary.md) for event, command, correlation ID, and sequence.

## Further reading

- [CAH-004 delivery contract](../../user-stories/cah-004-define-protocol-v1.md)
- [ADR 0003: Use a versioned NDJSON protocol](../adr/0003-ndjson-protocol.md)
- [JSON Schema introduction](https://json-schema.org/learn/getting-started-step-by-step)
- [Protocol Buffers overview](https://protobuf.dev/overview/)
- [Buf breaking-change detection](https://buf.build/docs/breaking/)
