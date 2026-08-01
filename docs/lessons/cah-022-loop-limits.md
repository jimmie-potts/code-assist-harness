# CAH-022 lesson: Enforce loop limits

- **Unit:** CAH-022
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; the provider-neutral turn now enforces four harness-owned limits
- **Story:** [CAH-022](../../user-stories/cah-022-enforce-loop-limits.md)
- **Visual companion:** [Loop limits deck](assets/cah-022-loop-limits.pptx)
- **Related architecture:** [Agent loop](../agent-loop.md), [Safety model](../safety-model.md), and
  [ADR 0001](../adr/0001-own-the-agent-loop.md)

> This lesson describes the implemented local harness. CAH-023 will add the first network adapter;
> no live provider or tool execution is implied here.

## Quick summary

CAH-022 bounds one provider-backed session by model turns, provider-work time, accepted assistant
bytes, and observed tool calls. The main system-design lesson is ownership: the Python harness
charges work, resolves races, cleans up the provider operation, and records evidence; the TUI and
provider adapter do not make those decisions.

## Learning objectives

After completing this unit, you should be able to:

- locate loop-safety policy in the harness architecture;
- explain where each budget is charged and why charging happens before acceptance;
- reason about deadline, completion, and cleanup races; and
- test an agent-loop limit without a live model or wall-clock sleep.

## Why this unit matters

A one-turn loop can still wait forever, accept an unbounded stream, or receive unexpected tool
requests. These limits establish a provider-independent safety boundary before CAH-023 introduces
network and billable work.

## Junior engineer foundation

A **budget** is work the system may admit. A **counter** records admitted work. A **deadline** is an
absolute point on a monotonic clock, which measures elapsed time without being affected by wall-clock
corrections.

For a three-byte budget, accepting `"ab"` leaves one byte. A two-byte delta must be rejected whole;
accepting one byte and truncating the rest would silently change the model's output. The common
mistake is checking only before the provider request. Admission limits how many operations start;
streaming limits must also run before each observation reaches wire, reducer, or transcript state.

## Key concepts

- **Reserve before accept:** charge a complete delta or tool observation before publishing it.
- **Independent deadline watcher:** wake even when the provider emits nothing or a local sink is
  blocked.
- **First-winner terminal guard:** completion, failure, cancellation, and limits converge on one
  terminal selection.
- **Single cleanup owner:** the watcher and finalizer join one shared cleanup task rather than calling
  the provider concurrently.
- **Bounded evidence:** transcript v3 records configuration, counters, and the exhausted limit without
  provider payloads or monotonic timestamps.

## Architecture and design

CAH-022 is positioned inside the Python harness, around the provider port:

```text
                        validated NDJSON events
 +----------+        <---------------------------        +------------------+
 | Ink TUI  |                                             | Transcript v3    |
 | renders  |        --------------------------->         | bounded evidence |
 +----------+          validated commands                 +---------^--------+
                                                                  |
                    +---------------------------------------------+-------------+
                    | Python harness                              |             |
                    |  Runtime                                    |             |
                    |    +----------------------------------------+---------+   |
                    |    | ProviderSession  <--- CAH-022 lives here         |   |
                    |    | LoopLimitTracker + deadline + terminal guard     |---+
                    |    +----------------------+---------------------------+   |
                    |                           | tool request: count, then     |
                    |                           | fail unavailable (no tools)   |
                    +---------------------------+-------------------------------+
                                                |
                                                v
                                      +-------------------+
                                      | Provider port     |
                                      | fake now; adapter |
                                      | in CAH-023        |
                                      +-------------------+
```

The TUI displays validated events. The provider port translates model activity. Neither owns budget
policy. `ProviderSession` coordinates an immutable `LoopLimits`, a fresh per-session tracker, an
absolute deadline captured at session allocation, and the shared terminal/cleanup paths.

| Budget | Default | Charge point | Stable failure code |
| --- | ---: | --- | --- |
| Model turns | `1` | Immediately before `Provider.start()` | `model_turn_limit_exceeded` |
| Provider work | `120s` | Deadline latch at or after the absolute deadline | `provider_work_deadline_exceeded` |
| Assistant output | `4096` bytes | Before accepting a complete UTF-8 delta | `assistant_output_limit_exceeded` |
| Tool calls | `1` | Before parsing or unavailable-tool handling | `tool_call_limit_exceeded` |

The allowed maxima are 16 turns, 3,600 seconds, 8,192 bytes, and 64 tool calls. Invalid values are
rejected rather than clamped.

Three invariants shape the agent loop:

1. **Deadline precedence:** after a stream wait wakes, `now >= deadline` wins even if an event is
   ready in the same scheduler turn. The event is reaped without acceptance.
2. **Publication integrity:** an event transaction admitted before expiry finishes its ordered,
   non-interleaved write/reducer/transcript attempt. The watcher can start provider cancellation
   while that local sink is blocked, and the deadline terminal is selected next.
3. **One cleanup task:** cancellation or close is invoked once and joined with a fixed five-second
   grace. A cleanup exception or grace expiry emits the payload-free `provider_cleanup_failed`
   diagnostic without replacing the selected terminal result.

The deadline bounds provider work, not local terminal latency. A provider that suppresses task
cancellation cannot be forcefully contained by this in-process port; process isolation is deferred.

Transcript writer version 3 adds one transcript-only `loop.limits_observed` record immediately before
the session terminal. Replay accepts versions 1, 2, and 3. A provider-backed terminal path records at
most one observation; a mock session may omit it because it never enters this loop. Writer and replay
also require an exhausted limit to match its exact adjacent failure code, so stored evidence cannot
claim a limit failure beside completion, cancellation, or a different failure. In version 3, a
reserved limit-failure code cannot appear without the preceding evidence record either.

## Practical walkthrough

1. `ProviderSessionRunner` gives every session the same immutable configuration and a fresh tracker.
2. Session allocation captures `monotonic_now() + timeout`; setup time therefore consumes budget.
3. Admission checks the deadline and charges the model turn before the lazy provider start.
4. Streaming checks the deadline after every wake, then reserves full UTF-8 deltas or counts tool
   observations before publication or inspection.
5. A limit selects one safe failure, starts or joins the shared cleanup task, and emits one terminal.
6. Immediately before that terminal, the runtime asks the transcript to record the bounded snapshot.

## Implementation code samples

### Reserve a whole output delta

From [`loop_limits.py`](../../src/code_assist_harness/loop_limits.py):

```python
remaining = self._limits.max_assistant_output_bytes - self._assistant_output_bytes
if candidate_bytes > remaining:
    self._exhausted = "assistant_output"
    return False
self._assistant_output_bytes += candidate_bytes
return True
```

The subtraction derives the remaining budget. The comparison rejects the complete candidate and
records the first exhausted class. Only an admitted candidate changes the byte counter.

### Make time win before observation acceptance

From [`provider_session.py`](../../src/code_assist_harness/provider_session.py):

```python
if self._deadline_latched or self._deadline_is_due():
    await self._cancel_and_reap_pending_event()
    await self._select_provider_deadline()
    return

try:
    observation = pending.result()
```

The clock check occurs after the wait but before reading the provider result. Reaping first prevents
the tied observation from leaking into an event or transcript.

### Persist bounded evidence immediately before the terminal

From [`provider_session.py`](../../src/code_assist_harness/provider_session.py):

```python
await self._notify_loop_limits_once()
session_failed = await self._writer.emit_session(
    "session.failed",
    self._session_id,
    {
        "code": selection.failure_code,
        "message": selection.failure_message,
    },
    correlation_id=self._command.command_id,
)
```

The observer runs once before the terminal append. The wire failure stays small and stable; limit
values and counters live only in bounded transcript evidence.

### Prove a silent provider cannot evade the deadline

From [`test_provider_session.py`](../../tests/test_provider_session.py):

```python
await asyncio.wait_for(operation.iteration_started.wait(), timeout=1)
await asyncio.wait_for(clock.wait_for_waiter(10.0), timeout=1)
clock.advance_to(10.0)
await asyncio.wait_for(running, timeout=1)

assert operation.cancel_calls == 1
assert _wire_events(lines)[-1]["payload"] == {
    "code": "provider_work_deadline_exceeded",
    "message": "Provider work exceeded its time limit.",
}
```

The fake blocks stream progress. Advancing an injected clock releases the deterministic waiter, so
the test proves watcher-driven cancellation without sleeping or contacting a provider.

## Failure scenarios to study

| Failure | Responsible boundary | Safe outcome | Evidence |
| --- | --- | --- | --- |
| Provider stays silent | Deadline watcher | Cancel once; deadline failure | Controlled clock test |
| Delta exceeds bytes | Tracker before publication | Reject whole delta | Wire, reducer, and counter assertions |
| Deadline and event tie | Session coordinator | Deadline wins; event reaped | Exact-tie regression test |
| Sink blocks after admission | Watcher plus publication lock | Cancellation starts; admitted transaction settles; deadline terminal follows | Blocked-sink race test |
| Cleanup raises or times out | Shared cleanup supervisor | Keep original terminal; emit safe diagnostic | Exception and grace tests |
| Transcript terminal append fails | Transcript writer | Preserve replayable limit-record prefix | Persistence rollback/prefix tests |

## Production expansion

### Example enterprise scenario

A hosted agent may need tenant quotas, cross-replica concurrency limits, upstream deadline
propagation, and spend controls. Those policies can feed the same admission points, but they require
durable coordination and operational ownership beyond one process.

### Typical production capabilities and tools

- [Python asyncio timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts) provide
  monotonic timeout primitives.
- [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
  adds shared upstream admission bounds.
- [OpenTelemetry metrics](https://opentelemetry.io/docs/concepts/signals/metrics/) supports centralized
  counters and alerts, with privacy and cardinality costs.
- [Kubernetes resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) illustrate
  aggregate multi-tenant resource governance.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One process and active session | Tenants, replicas, and provider accounts |
| Reliability | Deterministic local guard and replay | Durable quota service and upstream deadlines |
| Operations | Fake-provider tests and safe diagnostics | Metrics, alerts, overrides, and runbooks |
| Cost | Low setup and explicit control flow | Distributed state and governance ownership |

### Trade-offs and graduation signals

Local counters are auditable but cannot coordinate replicas. Graduate when concurrent sessions make
local accounting inaccurate, measured provider spend requires shared enforcement, or service-level
objectives require upstream deadline propagation.

## Practical exercises

1. Change an output limit and predict whether an emoji delta fits by UTF-8 bytes.
2. Advance the fake clock at the same moment as a final event and confirm the deadline wins.
3. Seed the tool-call tracker at its maximum and confirm arguments are never inspected.

## Key takeaways

- The harness, not the TUI or provider adapter, owns agent-loop safety budgets.
- Charge work before acceptance and converge every ending on one terminal and cleanup owner.
- Shared production quotas add coordination power at the cost of distributed state and operations.

## Glossary

- **Admission:** the decision to begin costly work.
- **Budget reservation:** accounting completed before accepting an observation.
- **Deadline latch:** first-winner state recording that provider work has expired.
- **Cleanup grace:** fixed local bound for joining provider cancellation or close.

See the shared [project glossary](../glossary.md) for session, model turn, provider, and tool call.

## Further reading

- [CAH-022 story](../../user-stories/cah-022-enforce-loop-limits.md)
- [Agent loop](../agent-loop.md), [safety model](../safety-model.md), and
  [evaluation](../evaluation.md)
- [CAH-021 provider-neutral turn](cah-021-one-model-turn.md)
- [CAH-023 OpenAI adapter](cah-023-openai-responses-adapter.md)
