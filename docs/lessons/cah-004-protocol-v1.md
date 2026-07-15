# CAH-004 lesson: Protocol version 1

- **Unit:** CAH-004
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; protocol models, readers, writers, and fixtures do not exist
- **Story:** [CAH-004](../../user-stories/cah-004-define-protocol-v1.md)
- **Related architecture:** [ADR 0003](../adr/0003-ndjson-protocol.md) and
  [protocol design](../protocol.md)

> This lesson describes the accepted NDJSON decision and planned CAH-004 contract. It does not
> claim that either process can exchange validated messages yet. Mock streaming begins in CAH-005.

## Quick summary

This unit converts the child pipes into a small, versioned command-and-event protocol. It teaches
message framing, runtime validation, ordering, correlation, compatibility, error containment, and
cross-language contract testing without introducing agent intelligence.

## Learning objectives

After completing this unit, you should be able to:

- explain why newline framing works only when stdout discipline is absolute;
- distinguish wire validation from Python or TypeScript static types;
- use command IDs, correlation IDs, session IDs, sequence numbers, and timestamps correctly;
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
stdin. Pydantic v2 and Zod are planned boundary validators; validated wire values are then converted
to local types with narrower responsibilities.

## Architecture and design

```text
Ink command object --Zod--> NDJSON line --stdin--> Pydantic command --Python runtime
Ink UI state      <--Zod--- NDJSON line <--stdout-- Pydantic event  <--ordered writer

Python stderr: diagnostics only; never part of the event stream
```

Initial commands are `runtime.initialize`, `session.start`, `session.cancel`, and
`runtime.shutdown`. Initial events are `runtime.ready`, `session.started`, `assistant.delta`,
`assistant.completed`, `session.completed`, `session.cancelled`, `session.failed`, and
`runtime.error`.

The planned invariants are:

- every wire message is exactly one JSON object terminated by one newline;
- every message declares protocol version and type, and every command has a command ID;
- session events carry a session ID and strictly increasing sequence number;
- sequence, never timestamp, determines session order;
- one ordered writer prevents concurrent event bytes from interleaving;
- unsupported versions, malformed JSON, invalid known payloads, and unknown types remain distinct;
- a recoverable bad line does not prevent a later valid line from being processed; and
- diagnostics and raw exceptions never corrupt protocol stdout.

One compatibility detail is intentionally unresolved before implementation: the TUI must not crash
on an unknown event, but CAH-004 must choose and test whether it continues or terminates after
surfacing that condition. That choice differs from the required recovery after a malformed line.

## Practical walkthrough

1. **Specify the envelope.** Document exact required fields, UTC timestamp representation, payload
   rules, and which runtime events do not carry session fields.
2. **Write shared fixtures first.** Include each initial message family plus unsupported-version,
   malformed-envelope, and invalid-payload examples. Keep all values fake and bounded.
3. **Implement Python models.** Use Pydantic discriminated models for inbound commands and outbound
   events. Convert validation failures into safe structured errors without echoing raw input.
4. **Implement TypeScript schemas.** Use Zod at both outgoing-command and incoming-event boundaries;
   distinguish inferred wire shapes from reducer state with names and TSDoc.
5. **Build line readers.** Buffer partial chunks until newline, decode UTF-8 deliberately, parse one
   line in isolation, and resume after a recoverable malformed line.
6. **Build an ordered writer.** Serialize one already validated message at a time and append exactly
   one newline. Assign session sequence numbers at this authoritative ordering boundary.
7. **Test both languages.** Parse the same golden fixtures and prove invalid fixtures fail for the
   intended reason rather than an incidental earlier error.
8. **Test the real pipes.** Send multiple valid and invalid lines through the runtime, assert later
   valid lines survive a recoverable failure, and parse every stdout line as protocol v1.

## Failure scenarios to study

### A plain log line reaches stdout

**Symptom:** the TUI receives text that is not JSON. **Boundary:** Python event writer and logging
configuration. **Safe outcome:** report a bounded protocol failure and route diagnostics to stderr.
**Evidence:** every emitted stdout line parses as a version 1 object.

### Two async producers interleave bytes

**Symptom:** fragments from valid events form one invalid line. **Boundary:** ordered writer.
**Safe outcome:** producers enqueue domain events; exactly one writer serializes them. **Evidence:** a
concurrency test emits many events with complete, monotonic lines.

### One bad line kills the runtime

**Symptom:** malformed JSON closes the child and discards a following valid command. **Boundary:**
line reader. **Safe outcome:** contain the failure to one line, emit a safe error when possible, and
continue with the next recoverable line. **Evidence:** the real-pipe validation sequence proves it.

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

## Practical exercises

1. Given three event timestamps and sequences, order them correctly and explain why.
2. Split one JSON message across arbitrary byte chunks and design the reader states before newline.
3. Create one invalid fixture for each layer: JSON syntax, envelope, version, and known payload.

## Key takeaways

- NDJSON frames messages; runtime schemas establish trust.
- Sequence numbers establish session order, while correlation IDs connect cause and effect.
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
