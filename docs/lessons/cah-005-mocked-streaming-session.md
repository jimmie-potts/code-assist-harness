# CAH-005 lesson: Mocked streaming session

- **Unit:** CAH-005
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; no mocked Node-Python session exists yet
- **Story:** [CAH-005](../../user-stories/cah-005-stream-mocked-session.md)
- **Related architecture:** [Architecture](../architecture.md), [protocol](../protocol.md),
  [ADR 0002](../adr/0002-ink-python-process-boundary.md), and
  [ADR 0003](../adr/0003-ndjson-protocol.md)

> This lesson explains accepted design and planned behavior. It must be revised with actual module,
> fixture, and command names after CAH-005 is implemented.

## Quick summary

CAH-005 will prove the first complete vertical path: Ink sends a task to the Python child, Python
emits deliberately delayed mock events, and the TUI renders text before the response is complete.
The lesson is streaming and process integration, not model intelligence.

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
Python process, pipes, protocol validators, reducers, and renderer while replacing only agent output.

**Delta:** an ordered fragment appended to the active assistant message. A delta is observable before
`assistant.completed`; otherwise the implementation is buffering, not streaming.

**Correlation:** `session.started` refers to the initiating `session.start` command ID. Correlation
answers “which request caused this?” while a session sequence answers “what happened next?”

**Deterministic mock:** Python emits a known sequence at controlled scheduling points. It is not the
M1 fake provider and must not introduce provider interfaces early.

**Projection:** the TUI validates events and reduces them into visible state. Python remains the
authority for session lifecycle; React components do not decide completion.

## Architecture and design

```text
user input
   -> Ink validates local input and writes session.start
   -> Python validates the command and creates a session
   -> ordered writer emits started, deltas, assistant completion, session completion
   -> Ink validates each line, reduces state, and renders immediately
```

| Concern | Owner | Planned invariant |
| --- | --- | --- |
| Terminal input and intermediate rendering | Ink/TypeScript | Pending input is UI state, not protocol authority. |
| Mock scheduling and session outcome | Python runtime | One active session emits one terminal event. |
| Framing and validation | Both boundaries | One complete JSON object occupies each stdout line. |
| Event order | Python ordered writer | Session sequence numbers strictly increase. |
| Visible accumulation | TUI reducer | Completed text equals accepted deltas in order. |

The M0 mock performs no model call, filesystem mutation, transcript write, tool call, approval, or
subprocess execution. Delays exist only to expose intermediate states and must be short and
controllable in tests. Backpressure and output bounds should be considered at the seam, but CAH-005
does not add a distributed broker or production telemetry stack.

## Practical walkthrough

1. Start from the CAH-004 protocol validators and CAH-003 child supervisor.
2. Add a non-empty-input path that creates a command ID and writes one `session.start` line.
3. Reject whitespace-only input locally with understandable feedback and no protocol command.
4. In Python, create a distinct session ID and emit `session.started` with sequence 1.
5. Emit at least three known `assistant.delta` values at injectable scheduling checkpoints.
6. Route each parsed event through the TUI reducer before the next delta arrives.
7. Emit `assistant.completed` with the exact accumulation, then one `session.completed` event.
8. Return to a state that accepts another task without restarting either process.
9. Exercise the real npm/Node-to-`uv`/Python boundary in an integration test.

Observe more than the final screen. Capture reducer snapshots or renderer frames after each delta,
verify command correlation and sequence order, and assert that the second session has a new ID and
its own sequence. Use controlled checkpoints rather than long sleeps so the suite remains fast.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe evidence |
| --- | --- | --- | --- |
| Final response is buffered | No partial text appears | TUI read/reduce/render path | Test observes frames between deltas. |
| Delta is duplicated or reordered | Completed text differs | Ordered writer or reducer | Sequence and accumulation assertions fail. |
| Whitespace starts work | Empty session appears | Ink input validation | No command is written. |
| Second task reuses state | Old text or sequence leaks | Session initialization | Two-session integration test fails. |
| Diagnostic reaches stdout | NDJSON parser fails | Python output discipline | Every captured stdout line parses. |
| Child exits mid-stream | UI hangs or reports success | Child supervisor | Visible failure and reaped child are asserted. |

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

Pipes make ordering and ownership inspectable and have almost no operational cost. A broker improves
durability and horizontal decoupling but introduces delivery semantics, schema governance, retention,
security, and failure modes that obscure the M0 lesson. Graduate when measured concurrent demand,
reconnect requirements, cross-host workers, or unacceptable event loss make process-local delivery
insufficient—not merely because distributed streaming is common elsewhere.

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
- [Process protocol](../protocol.md)
- [Evaluation strategy](../evaluation.md)
- [Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [Versioned NDJSON decision](../adr/0003-ndjson-protocol.md)
- [Apache Kafka documentation](https://kafka.apache.org/documentation/)
- [NATS JetStream documentation](https://docs.nats.io/nats-concepts/jetstream)
- [AsyncAPI documentation](https://www.asyncapi.com/docs)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
