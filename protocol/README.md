# Protocol fixtures

This directory is the language-neutral source of examples for protocol version 1. Python and
TypeScript maintain their validators by hand; neither implementation generates these files or acts
as the source of truth for the other. Both contract suites consume
[`fixtures/v1/manifest.json`](fixtures/v1/manifest.json) and must agree with every expected result.

## Process and stream ownership

The Ink/TypeScript parent writes commands to Python stdin. The Python runtime writes events to
stdout. Each message is UTF-8 and occupies exactly one physical line: one JSON object followed by
one line-feed byte (`\n`). Writers emit compact JSON, while readers also accept legal single-line
whitespace. Pretty-printed multi-line JSON, multiple objects on one line, blank lines, carriage
returns, and unterminated final objects are not valid protocol messages.

Python stdout is a machine-only event stream. Human diagnostics, tracebacks, and logs belong on
Python stderr and must never be inserted into a protocol event stream. A safe protocol error does
not quote an offending line because untrusted input can contain credentials or unbounded data.

## Version 1 envelopes

All objects use `protocol_version: 1`, a namespaced `type`, an exact UTC timestamp in
`YYYY-MM-DDTHH:mm:ss.SSSZ` form, and a type-specific `payload`. Objects are strict: fields not
declared by the selected envelope or payload schema are rejected rather than silently discarded.

Commands additionally carry a unique `command_id` beginning with `cmd_`. Events caused directly by
a command may carry its ID as `correlation_id`. Session events carry a `session_id` beginning with
`ses_` and a positive, strictly increasing `sequence`. Sequence establishes authoritative session
order; timestamps are descriptive and never repair, replace, or reorder sequence numbers.

The command catalog is:

| Type | Payload |
| --- | --- |
| `runtime.initialize` | `workspace: string` |
| `session.start` | `task: string` |
| `session.cancel` | `session_id: string` |
| `runtime.shutdown` | Empty object |

The event catalog is:

| Type | Session event | Payload |
| --- | --- | --- |
| `runtime.ready` | No | `workspace: string` |
| `session.started` | Yes | Empty object |
| `assistant.delta` | Yes | `text: string` |
| `assistant.completed` | Yes | `text: string` |
| `session.completed` | Yes | Empty object |
| `session.cancelled` | Yes | Empty object |
| `session.failed` | Yes | bounded machine `code`, safe single-line `message` |
| `runtime.error` | No | bounded machine `code`, safe single-line `message`, `recoverable: boolean` |

The fixture values are deliberately fake and bounded. Paths are illustrative Linux paths, not
locations that a test should create or access.

## Compatibility and error containment

Readers parse JSON, inspect the integer version before version 1-specific fields, validate the
common version 1 envelope, and only then dispatch to a known payload schema. The failure classes in
the manifest remain distinct so callers can tell malformed JSON from an unsupported version,
invalid envelope, unknown type, or invalid known payload. An unsupported version is not interpreted
as version 1, and an unknown type is never guessed or admitted to trusted state.

A failure is contained to the physical line that caused it. Where the owning runtime can safely
continue, it reports a bounded structured error and processes the next line. The fixture
classification describes the boundary failure; it does not authorize echoing the fixture bytes in
a user-visible error.

Version 1 uses a strict compatibility policy. Adding an optional field therefore requires an
intentional validator and fixture change in both languages. Changing a required field, field type
or meaning, identifier rule, or sequencing rule requires a new protocol version.

## Consuming the manifest

Each manifest entry identifies a fixture relative to `fixtures/v1/`, its direction, and its
expected result. `ndjson_line` files contain one candidate physical line including its terminating
newline. `ndjson_stream` files deliberately exercise framing across the complete byte stream.

For a valid entry, a contract test must verify framing, parse the JSON, validate the declared
direction, and confirm the resulting discriminator. For an invalid entry, it must verify the named
classification rather than accepting failure for an earlier, unrelated reason. The
`invalid_framing` fixture terminates one otherwise-valid command with `\r\n` instead of `\n`.
Readers reject that byte-level violation before JSON parsing. Two concatenated objects on an
LF-terminated line remain `malformed_json`; readers do not need a custom structural JSON scanner.
