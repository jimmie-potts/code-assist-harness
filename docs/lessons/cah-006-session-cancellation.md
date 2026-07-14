# CAH-006 lesson: Session cancellation

- **Unit:** CAH-006
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; no cancellable session runtime exists yet
- **Story:** [CAH-006](../../user-stories/cah-006-cancel-active-session.md)
- **Related architecture:** [Agent loop](../agent-loop.md), [protocol](../protocol.md),
  [architecture](../architecture.md), and [ADR 0002](../adr/0002-ink-python-process-boundary.md)

> This lesson describes accepted cancellation semantics and planned mock-runtime behavior. Provider,
> tool, and subprocess cancellation remain later work.

## Quick summary

CAH-006 will turn cancellation into a protocol-visible lifecycle outcome rather than a local keypress
or leaked task exception. Ink requests cancellation; Python stops active mock work and chooses exactly
one terminal event even when completion races with the request.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a cancellation request from an acknowledged cancelled outcome;
- explain cooperative cancellation and why active work may not stop instantaneously;
- design idempotent handling for repeated or late cancellation commands;
- test completion/cancellation races with controlled scheduling; and
- compare one-process task cancellation with distributed workflow cancellation.

## Why this unit matters

An agent can stream indefinitely, wait on a provider, or supervise a long-running tool. If a keypress
only changes the TUI, Python may continue consuming resources and later emit contradictory events.
CAH-006 establishes user control and terminal-state discipline before expensive provider or tool
operations are introduced.

## Key concepts

**Cancellation request:** `session.cancel` expresses intent. It is not proof that active work stopped.

**Cancellation acknowledgement:** `session.cancelled` is Python's authoritative terminal event after
the runtime accepts cancellation and prevents further session output.

**Cooperative cancellation:** an operation receives a signal and exits at an explicit checkpoint.
Cleanup must still run, and some external work may finish before it observes the signal.

**Idempotency:** repeating the same cancellation request has no additional terminal effect.

**Race:** completion and cancellation can become eligible concurrently. A terminal-state guard must
allow one valid outcome to win and make later terminal attempts harmless or diagnostic.

## Architecture and design

```text
keypress -> Ink writes session.cancel -> Python validates session identity
                                      -> active mock task observes cancellation
                                      -> terminal guard selects cancelled or prior completion
                                      -> ordered writer emits one terminal event
                                      -> Ink renders authoritative outcome
```

| Concern | Owner | Invariant |
| --- | --- | --- |
| Key binding and hint | Ink TUI | A user can discover how to request cancellation. |
| Active task and cancellation signal | Python runtime | Work is owned and reaped by Python. |
| Terminal selection | Python session lifecycle | Exactly one terminal event wins. |
| Visible result | TUI reducer | Cancelled is distinct from failed and completed. |
| Application exit | Ink supervisor plus Python cleanup | No orphan child remains. |

The TUI must not declare a session cancelled immediately after sending the command. It may show a
local pending interaction, but the authoritative terminal state comes from Python. After Python
accepts cancellation, no later `assistant.delta` may be emitted for that session. A request received
after normal completion cannot rewrite history into cancellation.

CAH-006 exercises the mocked stream only. It establishes semantics that CAH-020/021 will later apply
to providers and later tool stories will apply to subprocess trees.

## Practical walkthrough

1. Define the visible cancel action and display its hint only while a session is active.
2. Send a validated `session.cancel` naming the active session and carrying a new command ID.
3. Route the command to the Python-owned session task rather than cancelling from React code.
4. Add explicit scheduling checkpoints before the first delta and between later deltas.
5. Signal and await the active task's cleanup without blocking the command reader indefinitely.
6. Pass completion and cancellation through one atomic or otherwise serialized terminal guard.
7. Emit `session.cancelled` only when cancellation wins; emit nothing terminal when a prior outcome won.
8. Reduce the event into a clearly cancelled UI, then permit a new task.
9. On application exit, terminate and reap the child even if a session is still active.

Tests should control the race rather than repeat it until it happens. Hold the mock at a named
checkpoint, send cancellation, release the task, and assert the exact remaining event sequence.
Repeat for cancellation before output, between deltas, repeated requests, and after completion.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe outcome |
| --- | --- | --- | --- |
| TUI cancels locally only | Spinner stops but Python emits later | Ownership boundary | UI waits for Python outcome. |
| Cancellation wins, then a delta arrives | Text changes after terminal state | Python task/writer | Post-terminal output is prevented and tested. |
| Completion and cancellation both emit | Two terminal events | Terminal guard | First valid outcome is the only terminal event. |
| Repeated request raises | Session fails after user retries key | Command handling | Duplicate request is harmless. |
| Wrong session ID is accepted | Another task is interrupted | Validation/routing | Structured safe rejection; no active work changes. |
| TUI exits during work | Orphan Python process remains | Child supervisor | Child is terminated and reaped. |

## Production expansion

### Example enterprise scenario

Consider a multi-service code-analysis workflow that schedules builds, sandbox jobs, and provider
requests across regions. The initiator can disconnect, workers can be partitioned, and some actions
cannot be rolled back after they start. Cancellation needs authenticated propagation, deadlines,
durable intent, compensation policy, and telemetry showing which components actually stopped.

### Typical production capabilities and tools

These are representative capabilities, not required dependencies or endorsements:

- [Python asyncio task cancellation](https://docs.python.org/3/library/asyncio-task.html#task-cancellation)
  documents the local cooperative cancellation primitive used by the planned runtime.
- [gRPC cancellation](https://grpc.io/docs/guides/cancellation/) illustrates propagating cancellation
  across RPC boundaries while handlers still perform cleanup.
- [Temporal documentation](https://docs.temporal.io/) illustrates durable workflow state, cancellation,
  retries, and compensation across workers.
- [Kubernetes pod termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination)
  illustrates grace periods followed by forced process termination.
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) illustrate correlating
  cancellation latency and cleanup across services.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One Python child and one active session | Distributed workers and nested operations |
| Intent storage | In-memory command handling | Durable authenticated cancellation record |
| Propagation | Direct task signal | RPC/workflow propagation with deadlines |
| Cleanup | Await task and reap child | Grace periods, compensation, forced termination |
| Evidence | Deterministic event assertions | Traces, metrics, audit records, alerts |
| Failure model | Process-local race | Partitions, retries, duplicate delivery, abandoned work |

### Trade-offs and graduation signals

The local design makes the race understandable and cheap to test. Durable workflow machinery can
recover intent after crashes and coordinate many workers, but it adds storage, identity, retry,
compensation, and operations. Graduate when sessions outlive one process, side effects span services,
or cancellation-loss and cleanup-latency objectives cannot be met by direct task ownership.

## Practical exercises

1. Draw the two legal outcomes when cancel and completion become ready together.
2. Add a controlled gate before delta one and prove cancellation produces no assistant output.
3. Send the same cancel command twice and identify every event that should and should not appear.
4. Simulate a task that catches cancellation and delays cleanup; decide what the UI should display.
5. Explain why a process kill is a fallback for shutdown, not a substitute for session cancellation.

## Key takeaways

- Ink requests cancellation; Python owns active work and the terminal result.
- Cancellation is a protocol lifecycle, not merely an exception or optimistic UI update.
- Exactly one terminal event is the central race invariant.
- Distributed cancellation is justified when work and intent outlive the local process boundary.

## Glossary

- **Cancellation acknowledgement:** authoritative evidence that cancellation won the session race.
- **Cancellation checkpoint:** a place where active work observes and responds to a request.
- **Cooperative cancellation:** cleanup-aware stopping performed by the active operation.
- **Idempotent request:** a repeated request whose additional application changes nothing.
- **Terminal guard:** the single mechanism that selects one final session outcome.
- **Forced termination:** stopping a process after cooperative cleanup does not finish in time.

See the shared [project glossary](../glossary.md) for cancellation, session, terminal event, and runtime.

## Further reading

- [CAH-006 user story](../../user-stories/cah-006-cancel-active-session.md)
- [Agent-loop cancellation model](../agent-loop.md)
- [Protocol lifecycle](../protocol.md)
- [Process-boundary decision](../adr/0002-ink-python-process-boundary.md)
- [Evaluation scenarios](../evaluation.md)
