# CAH-005 lesson: Mocked streaming session

- **Unit:** CAH-005
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; Python, Ink, reducer, and real-process tests exercise the mock
- **Story:** [CAH-005](../../user-stories/cah-005-stream-mocked-session.md)
- **Visual companion:** [Mocked streaming session presentation](assets/cah-005-mocked-streaming-session.pptx)
- **Related architecture:** [Architecture](../architecture.md), [protocol](../protocol.md),
  [ADR 0002](../adr/0002-ink-python-process-boundary.md), and
  [ADR 0003](../adr/0003-ndjson-protocol.md)

> Verified implementation: `MockSessionRunner` emits a fixed six-event tape, the supervisor and
> pure reducer reject invalid transitions, and the real boundary test observes each accumulation and
> a second session without a model or network.

## Quick summary

CAH-005 proves the first complete vertical path: Ink sends a task to the Python child, Python emits
three deliberately delayed mock deltas, and the TUI renders text before the response is complete.
The exact final response is `Mock response: the task crossed the process boundary and streamed back
successfully.` The lesson is streaming and process integration, not model intelligence.

## Learning objectives

After completing this unit, you should be able to:

- explain the difference between a streamed event and a buffered final response;
- trace a command and its correlated events across two processes;
- keep Python stdout valid as a machine-readable NDJSON channel;
- test intermediate rendering, ordering, completion, and a second session deterministically; and
- identify when a local pipe should graduate to durable messaging infrastructure.

## Why this unit matters

A static TUI and a child that merely starts do not prove that the application works as one tool.
Streaming introduces partial reads, scheduling, ordering, state projection, and cleanup at once.
Proving those concerns with fixed mock text removes provider latency and nondeterminism, giving later
model work a trustworthy transport and UI baseline.

## Key concepts

**Vertical slice:** one thin path through every real boundary. CAH-005 uses the real Ink process,
Python process, pipes, protocol validators, `reduceSessionState`, and renderer while replacing only
agent output.

**Delta:** an ordered fragment appended to the active assistant message. A delta is observable before
`assistant.completed`; otherwise the implementation is buffering, not streaming.

**Correlation:** all six session events copy the initiating `session.start` command ID. Correlation
answers “which request caused this?” while a session sequence answers “what happened next?”

**Deterministic mock:** `MOCK_RESPONSE_DELTAS` defines three fragments, and `MockSessionRunner`
invokes an injectable checkpoint before each one. Production uses a 50 ms scheduling delay; Python
tests replace it with events they can hold and release. This is not the M1 fake provider.

**Projection:** `PythonRuntimeSupervisor` validates the active event tape, then
`reduceSessionState` accumulates immutable visible state. Python remains the authority for session
lifecycle; React components do not decide completion.

## Architecture and design

```text
App editable draft
   -> submitTask encodes session.start, publishes task.submitted, then writes the exact line
   -> run_runtime validates task and starts one MockSessionRunner child task
   -> OrderedEventWriter emits started, 3 deltas, assistant completion, session completion
   -> supervisor validates correlation/identity/sequence before publishing each update
   -> reduceSessionState accumulates; runApplication rerenders App immediately
```

| Concern | Owner | Implemented invariant |
| --- | --- | --- |
| Terminal input and intermediate rendering | Ink/TypeScript | Draft text survives background rerenders and blocked overlap. |
| Mock scheduling and session outcome | Python runtime | One accepted session emits exactly one six-event tape. |
| Framing and validation | Both boundaries | One complete JSON object occupies each stdout line. |
| Event order | Python ordered writer | Each session uses sequence `1..6`; the next starts again at 1. |
| Visible accumulation | TUI reducer | `assistant.completed` must exactly equal accepted deltas. |

The M0 mock performs no model call, network request, workspace read or mutation, transcript write,
tool call, approval, or subprocess execution beyond the already required `uv` child launch. The
real-boundary test verifies the selected workspace remains empty. Delays exist only to expose
intermediate states. Backpressure and output bounds still matter at the seam, but CAH-005 does not
add a broker or production telemetry stack.

## Practical walkthrough

1. `App` keeps the draft in component state. Enter calls `submitDraft`, which rejects whitespace,
   waits for runtime readiness, preserves input during active work, and otherwise calls the
   supervisor.
2. `PythonRuntimeSupervisor.submitTask` creates a command ID and encodes the complete
   `session.start` line before changing projection state. Once the command fits the wire contract,
   it publishes `task.submitted` before any child response can race it and writes that exact line.
3. `run_runtime` independently strips the task for validity, rejects overlap, and starts one
   `MockSessionRunner` child task while continuing to read commands.
4. `MockSessionRunner` assigns `ses_mock_1`, emits `session.started` at sequence 1, then emits
   `MOCK_RESPONSE_DELTAS` at sequences 2, 3, and 4.
5. It emits exact `assistant.completed` at sequence 5 and one `session.completed` at sequence 6;
   every event carries the start command ID as its correlation ID.
6. The supervisor runs each parsed event through the same reducer invariants before publishing it.
   A mismatch fails the runtime boundary closed rather than entering the conversation projection.
7. `runApplication` reduces each published update and rerenders `App`. The app test observes all
   three partial strings and proves a draft typed mid-stream survives those rerenders.
8. Once complete, another task gets `ses_mock_2` and a fresh `1..6` sequence without restarting
   Node or Python.
9. On shutdown or stdin EOF, Python waits for an accepted bounded mock to finish. CAH-006—not
   Ctrl+C or local state—will define how active work is interrupted.

The strongest evidence observes more than the final screen. `tests/test_runtime.py` holds and
releases each injectable checkpoint. `tui/test/runtime-boundary.test.ts` launches the genuine
`uv`/Python process, captures each intermediate accumulation, runs a second session, confirms no
workspace file appeared, and verifies the process tree is reaped.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe evidence |
| --- | --- | --- | --- |
| Final response is buffered | No partial text appears | TUI read/reduce/render path | `app.test.tsx` and `runtime-boundary.test.ts` observe all three accumulations. |
| Delta is duplicated or reordered | Projection cannot trust accumulation | Ordered writer or reducer | `session-state.test.ts` fails closed on sequence or completion disagreement. |
| Whitespace starts work | Empty session appears | Ink and Python validation | App writes no command; runtime returns correlated `invalid_task` for a direct caller. |
| An oversized task is projected | A phantom starting turn replaces the editable draft | TypeScript command boundary | Supervisor rejects before publishing or writing; App preserves the draft and the runtime remains usable. |
| A task overlaps active work | Two lifecycles compete | Ink and Python ownership | Draft is preserved locally; runtime returns correlated `session_active`. |
| Second task reuses state | Old text or sequence leaks | Session initialization | Real-boundary test requires `ses_mock_2` and a fresh `1..6`. |
| Diagnostic reaches stdout | NDJSON parser fails | Python output discipline | Every captured stdout line parses. |
| Child exits mid-stream | UI hangs or reports success | Child supervisor | Visible failure and reaped child are asserted. |

## Validation evidence

- `test_mock_session_checkpoints_expose_each_intermediate_delta` proves the exact event types,
  `1..6` sequence, correlation, three fragments, and accumulated completion without wall-clock
  assumptions.
- `test_runtime_rejects_a_second_session_while_the_first_is_active` and
  `test_runtime_rejects_a_whitespace_only_task_without_starting_a_session` prove the recoverable
  Python-side defenses.
- `tui/test/session-state.test.ts` proves pure transition, identity, correlation, sequence, and
  exact-completion rules, including meaningful fail-closed paths.
- `tui/test/app.test.tsx` proves whitespace feedback, exact task submission, visible intermediate
  text, completed status, and preservation of a draft during background rerenders or synchronous
  submission rejection.
- `tui/test/runtime-supervisor.test.ts` proves one child can publish two complete event tapes and
  that local whitespace, overlap, and encoded-size checks write no command. The oversized-task
  regression also proves no update is published and a subsequent valid task still succeeds.
- `tui/test/runtime-boundary.test.ts` proves the real launch boundary, all three intermediate
  accumulations, two sessions, an unchanged workspace, and complete process cleanup.

The repeatable verification commands are `uv run pytest`, `uv run ruff check .`,
`uv run ruff format --check .`, and `npm --prefix tui run check`. None needs an API key or network
access.

## Production expansion

### Example enterprise scenario

Imagine hundreds of concurrent coding sessions served by separate UI gateways and worker pools.
Clients reconnect, workers restart, deltas cross regions, and operators need to diagnose latency and
dropped or duplicated events. Local pipes and process lifetime are no longer the whole reliability
boundary; durable delivery, flow control, tenancy, retention, and observability become explicit.

### Typical production capabilities and tools

These references illustrate capabilities, not vendor endorsements or project dependencies:

- [Apache Kafka](https://kafka.apache.org/documentation/) illustrates durable, partitioned event
  streaming for high throughput and replay, at the cost of broker capacity, partition and retention
  planning, schema governance, and on-call ownership.
- [NATS JetStream](https://docs.nats.io/nats-concepts/jetstream) illustrates persistence, consumer
  acknowledgements, retention, and replay with a messaging system, while cluster sizing, stream
  configuration, storage, and failure recovery require operations.
- [AsyncAPI](https://www.asyncapi.com/docs) illustrates machine-readable asynchronous message
  contracts and generated documentation, but specifications, generators, and published references
  must be versioned and kept aligned with implementations.
- [OpenTelemetry](https://opentelemetry.io/docs/) illustrates traces, metrics, and logs correlated
  across process or service boundaries, while instrumentation, collector and backend capacity,
  cardinality control, and privacy review add operational cost.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Transport | Child stdin/stdout pipes | Broker, gateway, or managed stream |
| Delivery | Process-local ordered writes | Acknowledgement, retry, deduplication, retention |
| Scale | One active session | Partitioned multi-tenant concurrency |
| Recovery | Visible child failure; restart app | Resume/replay from durable offsets |
| Observability | Deterministic tests and stderr | Correlated traces, service metrics, alerts |
| Cost | No service operations | Capacity, schemas, tenancy, and on-call ownership |

### Trade-offs and graduation signals

The implementation confirmed that pipes make ordering and ownership inspectable with almost no
operational cost. Publishing `task.submitted` before the command write was necessary to remove a
fast-child correlation race, but publication can occur only after the exact command has passed
encoding and byte-limit validation. This ordering prevents both an early child event and a phantom
local session caused by invalid user input. A pure reducer also gave the supervisor and renderer one
transition contract, but CAH-005 deliberately recognizes only the successful mock tape;
cancellation and failure terminal events must expand it later. Injectable checkpoints made Python
timing evidence strong, while the genuine process test still uses short polling because OS process
discovery and pipe delivery are external scheduling boundaries. Draining a fixed 150 ms mock
simplifies shutdown, but is not suitable for an unbounded provider call; CAH-006 must replace that
assumption with an authoritative cancellation outcome.

A broker improves durability and horizontal decoupling but introduces delivery semantics, schema
governance, retention, security, and failure modes that obscure the M0 lesson. Graduate when
measured concurrent demand, reconnect requirements, cross-host workers, or unacceptable event loss
make process-local delivery insufficient—not merely because distributed streaming is common
elsewhere.

## Practical exercises

1. Change the mock from three deltas to five and predict every intermediate render.
2. Deliberately swap two sequence numbers and verify the boundary rejects or diagnoses the stream.
3. Make the second session reuse the first ID and write the smallest regression assertion that catches it.
4. Inject a child exit after delta two and define the exact UI state that should remain visible.
5. Compare a controllable scheduling gate with a wall-clock sleep and explain which yields stronger evidence.

## Key takeaways

- Ink owns input and rendering; Python owns the authoritative mocked lifecycle.
- Streaming is proven by observable intermediate state, not by a final string that was once chunked.
- Correlation identifies causality, while sequence numbers establish session order.
- A second session gets a new identity and its own sequence; history is projection state, not wire
  sequence continuation.
- Draining the bounded mock is shutdown behavior, not cancellation; CAH-006 owns interruption.
- The local pipe is the right learning boundary until durability or multi-host scale is demonstrated.

## Glossary

- **Accumulation:** complete assistant text formed from accepted deltas in sequence.
- **Backpressure:** a mechanism that prevents a producer from outrunning a consumer indefinitely.
- **Correlation ID:** command identity copied to directly related events.
- **Delta:** one ordered fragment of streamed assistant text.
- **Deterministic mock:** fixed behavior controlled by tests without a provider or network.
- **Vertical slice:** a minimal feature crossing every real architectural layer.

See the shared [project glossary](../glossary.md) for session, event, sequence, runtime, and TUI.

## Further reading

- [CAH-005 user story](../../user-stories/cah-005-stream-mocked-session.md)
- [Visual lesson presentation](assets/cah-005-mocked-streaming-session.pptx)
- [Process protocol](../protocol.md)
- [Evaluation strategy](../evaluation.md)
- [Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [Versioned NDJSON decision](../adr/0003-ndjson-protocol.md)
- [Apache Kafka documentation](https://kafka.apache.org/documentation/)
- [NATS JetStream documentation](https://docs.nats.io/nats-concepts/jetstream)
- [AsyncAPI documentation](https://www.asyncapi.com/docs)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
