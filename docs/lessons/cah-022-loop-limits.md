# CAH-022 lesson: Enforce loop limits

- **Unit:** CAH-022
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; CAH-021's provider-neutral turn is implemented, but the hard
  limits in this unit are not
- **Story:** [CAH-022](../../user-stories/cah-022-enforce-loop-limits.md)
- **Related architecture:** [Agent loop](../agent-loop.md), [Safety model](../safety-model.md), and
  [ADR 0001](../adr/0001-own-the-agent-loop.md)

> This lesson describes the accepted safety-budget design around CAH-021's implemented
> provider-neutral turn. It does not claim that provider work is currently deadline-bounded or that
> a network adapter exists.

## Quick summary

CAH-022 plans four harness-owned limits around one provider-neutral turn: admission count, monotonic
provider-work deadline, accepted UTF-8 output bytes, and observed tool calls. It teaches that a
configured number is not a safety control until admission, streaming, cancellation, evidence, and
races all enforce it.

## Learning objectives

After completing this unit, you should be able to:

- distinguish admission, provider-work time, output, and tool-call budgets;
- identify the exact moment each budget is charged;
- explain why a deadline must wake while a provider is silent;
- test limit boundaries without wall-clock sleeps; and
- preserve one terminal outcome when a limit races cancellation or completion.

## Why this unit matters

A one-turn loop removes multi-step unboundedness but not a slow connection, unlimited stream, or
unexpected tool request. CAH-022 puts deterministic domain budgets around the provider-neutral
path before CAH-023 activates a network and billable provider. This sequence prevents vendor
configuration from becoming the first safety boundary.

## Junior engineer foundation

A **limit** is a maximum amount of work. A **counter** records work already admitted. A **deadline**
is a point on a monotonic clock after which work must stop. Monotonic time moves forward even when
the wall clock is corrected, which makes elapsed-time comparisons reliable.

```python
# Planned teaching example, not shipped CAH-022 code.
if accepted_bytes + len(delta.encode("utf-8")) > maximum_bytes:
    fail_without_emitting(delta)
```

UTF-8 matters because one visible character may occupy more than one byte. A common misconception is
that checking a budget only before the request is enough. Admission prevents extra operations, but
streaming limits must also be checked before each observation enters events or persistence.

## Key concepts

- **Admission control:** refuse a costly operation before it starts.
- **Provider-work deadline:** an absolute stop point for provider activity derived from elapsed time,
  not calendar time or local sink latency.
- **Cumulative output budget:** UTF-8 bytes already accepted across all deltas in the turn.
- **Observed tool-call budget:** provider requests counted before parsing or execution.
- **Cleanup barrier:** awaited provider cancellation that guarantees no later observation can arrive.
- **Limit race:** competition between a budget failure and another terminal outcome.

## Architecture and design

```text
validated limits
      |
      +--> admission check ---- denied --> session.failed
      |          |
      |        allowed
      |          v
      |    Provider.start()
      |          |
      +--> deadline waiter -----+
      +--> output accountant ---+--> terminal guard --> one terminal event
      +--> tool-call counter ----+
                    |
             limit wins
                    v
          cancel + await cleanup
```

The configuration is immutable and rejects invalid values; it never silently clamps. The loop
charges a model turn immediately before provider start, output bytes before emission, and tool calls
before CAH-021's unavailable-tool failure. A deadline waiter races every awaited stream step, so a
provider that emits nothing cannot keep provider work active forever.

The exact configuration is intentionally small and finite:

| Field | Default | Allowed range |
| --- | ---: | ---: |
| `max_model_turns` | `1` | `1..16` |
| `provider_work_timeout_seconds` | `120` | `1..3600` |
| `max_assistant_output_bytes` | `4096` | `1..8192` |
| `max_observed_tool_calls` | `1` | `1..64` |

The deadline is `monotonic_now() + provider_work_timeout_seconds`; the clock value is never truncated.
After any stream wait wakes, the loop checks the clock again. At or after the deadline, time wins
even if an event became ready in the same scheduler turn, and that event is reaped without being
accepted.

This is a provider-work deadline, not a promise that a protocol or transcript sink finishes within
120 seconds. An independent watcher latches expiry and starts supervised provider cancellation
without waiting for the session publication lock. If a delta transaction was admitted first, its
wire write, reducer acceptance, and transcript-observer attempt still finish together. Every
terminal-selection path checks the expiry latch as soon as that transaction releases the lock, so
the deadline wins before another provider observation. The cancellation attempt starts on time and
a conforming provider stops; failed or timed-out cleanup remains unconfirmed. A blocked local sink
may delay the eventual terminal event, and local sink timeouts are future work.

The configurable output check runs before CAH-021's fixed 8192-byte protocol-fit ceiling. If both
would reject one delta, `assistant_output_limit_exceeded` is the terminal code. This makes the
configurable safety budget authoritative without weakening the transport ceiling.

The stable terminal codes are:

| Budget | Failure code | Admission moment | Fixed safe message |
| --- | --- | --- | --- |
| Model turns | `model_turn_limit_exceeded` | Immediately before `Provider.start()` | `The model-turn limit was reached.` |
| Provider work | `provider_work_deadline_exceeded` | When the monotonic deadline wins | `Provider work exceeded its time limit.` |
| Assistant output | `assistant_output_limit_exceeded` | Before accepting a delta's UTF-8 bytes | `Assistant output exceeded its byte limit.` |
| Tool calls | `tool_call_limit_exceeded` | Before accepting a provider tool request | `The provider tool-call limit was reached.` |

Provider-reported tokens remain observational. They can differ by provider or arrive only at
completion, so they neither replace harness counters nor grant additional budget.

CAH-022 advances new transcripts to version 3. A provider-backed session writes at most one
`loop.limits_observed` evidence record. With persistence enabled and healthy through the terminal
write, it writes exactly one immediately before that terminal with the four configured values,
three observed counters, and an optional exhausted-limit enum. Disabled persistence, persistence
failure before the record, or teardown before terminal preparation writes none; teardown or
persistence failure after the record may leave a replayable one-record prefix without a terminal.
Replay keeps versions 1 and 2 compatible, validates version-3 order and bounds, and exposes limit
evidence beside usage for summary generation. A mock session may have a version-3 transcript without
this record because it never enters the provider-backed path.

`exhausted_limit` is null or exactly `model_turns`, `provider_work`, `assistant_output`, or
`tool_calls`. `model_turns_started` and `assistant_output_bytes` record admitted work and remain
within their maxima; the provider-work limit is represented by the exhausted-limit classification,
not an elapsed-time counter. When the tool budget is exhausted, `tool_calls_observed` is exactly
maximum plus one because the rejecting request is itself an observation; otherwise it remains within
the maximum.

## Practical walkthrough

1. Validate limits before creating the tracker; reject booleans, zero, negatives, and excessive
   values.
2. Derive one absolute deadline from an injected monotonic clock when the provider-backed session
   object is allocated, before observer/transcript setup or provider admission; pass it into the
   later task.
3. Ask the tracker to admit a model turn immediately before provider start.
4. Race each next stream observation against an injected deadline waiter.
5. Encode each delta as UTF-8 and reserve its full size before emitting it.
6. Charge each tool request before inspecting its name or serialized arguments.
7. When any reservation fails, select the stable failure, cancel active provider work, and await
   cleanup.
8. Route the failure through the same terminal guard as provider completion and user cancellation.
9. On an enabled, healthy terminal path, persist exactly one bounded version-3
   `loop.limits_observed` record and the stable limit classification; otherwise preserve the
   at-most-one/prefix rules above.

CAH-021 ends the session on its first admitted tool request. Integration can therefore prove the
first-call boundary only; focused tracker tests seed prior tool counts to prove exact exhaustion and
over-limit behavior until a later multi-turn/tool-continuation story makes those states reachable.
`tool_calls_observed` increments before the decision: admitted calls remain at or below the maximum,
while the rejecting observation is recorded as maximum plus one. Model turns and assistant bytes,
by contrast, record admitted work and never exceed their configured maxima.

Cleanup gets a separate fixed five-second grace. It is not a fifth user-configurable work budget;
it is a defensive bound on awaiting a provider that has already violated its cleanup contract. On
expiry, the local cleanup-join awaitable is cancelled and reaped, the selected outcome remains, and
the harness reports cleanup as unconfirmed rather than pretending remote work stopped. A provider
may internally shield a sole cleanup owner, as CAH-023 plans to do; that owner may continue after the
bounded join ends. The local bound requires the port awaitable itself to propagate task cancellation,
as every conforming in-process provider must. Python cannot forcefully reap a task that suppresses
`CancelledError`; handling that implementation would require future process isolation or escalation.

## Implementation code samples

No CAH-022 implementation exists yet. Planned control flow:

```text
limits = validate(configuration)
deadline = monotonic_now_at_session_allocation() + limits.provider_work_timeout_seconds
tracker = start_tracker(deadline)
deadline_watcher = start_expiry_latch_and_provider_cancel_without_publication_lock(deadline)
under the deadline-admission guard:
    if deadline_expiry_is_latched or monotonic_now() >= deadline:
        reserve provider_work_deadline_exceeded without starting provider work
    else:
        tracker.admit_model_turn()
        operation = provider.start(request)  # synchronous and lazy
while provider operation is active:
    observation = await next_owned_provider_event()
    if monotonic_now() >= deadline:
        reject observation and select provider_work_deadline_exceeded
    if text delta:
        tracker.reserve_output(utf8_size(delta))
    if tool request:
        tracker.increment_observed_tool_calls_then_check_limit()
    publish admitted event as one shielded wire/reducer/transcript transaction
    if deadline_expiry_is_latched:
        select provider_work_deadline_exceeded before accepting another observation
on limit failure:
    if terminal_guard.select_failed(limit_code, safe_message):
        supervise operation.cancel() with the fixed five-second cleanup grace
        emit provider_cleanup_failed if the join raises or exceeds the grace
        emit selected session.failed
finally:
    cancel and reap deadline_watcher when it has not already finished
```

After implementation, replace this pseudocode with exact excerpts from the tracker, loop integration,
and at least one deterministic boundary test.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Turn budget already exhausted | Provider would otherwise start | No `Provider.start()` call; one failed terminal |
| Provider remains silent | No event reaches the loop | Provider-work deadline requests cancellation; cleanup is confirmed or reported unconfirmed after the grace |
| Delta sink is blocked at expiry | An admitted publication transaction is unfinished | Independent watcher starts provider cancellation; the delta finishes all three views, then the deadline terminal wins |
| Delta crosses byte budget | Candidate output is too large | Entire delta rejected before TUI or transcript |
| Seeded tool counter is exhausted | Another request is proposed | No parsing or execution; stable limit failure |
| Limit races completion | Two terminal paths contend | Shared guard records one winner |
| Event and deadline wake together | Both awaitables are ready | Deadline wins before observation acceptance |
| Cleanup contract is violated | Provider cancellation raises | Limit stays terminal; payload-free runtime diagnostic |
| Cleanup barrier never returns | Awaitable blocks but propagates task cancellation | Five-second injected grace cancels and reaps the local await; provider cleanup remains unconfirmed |
| Cleanup awaitable suppresses cancellation | In-process task refuses to stop | Outside the current port contract; no false reaping claim, and future process isolation is required |

## Production expansion

### Example enterprise scenario

A hosted coding assistant may need per-tenant quotas, regional deadlines, concurrency admission,
provider rate limits, and cost budgets. Those policies can feed the same preflight and streaming
accountants, but they require durable coordination and operational ownership beyond one local process.

### Typical production capabilities and tools

These official references illustrate capabilities rather than dependencies:

- [Python asyncio timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts) document
  monotonic-loop deadline primitives suitable for the local implementation.
- [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
  illustrates shared connection and request admission bounds.
- [OpenTelemetry metrics](https://opentelemetry.io/docs/concepts/signals/metrics/) illustrate
  centralized limit counters and alerts, with added cardinality and privacy policy.
- [Kubernetes resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/) illustrate
  multi-tenant aggregate budgets that require cluster-wide enforcement.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One process and one active session | Tenants, regions, replicas, and provider accounts |
| Provider time | Injected monotonic provider-work deadline | Distributed deadlines and upstream timeout propagation |
| Output | Local cumulative UTF-8 bytes | Content, token, cost, and transport budgets |
| Admission | In-memory tracker | Durable quota and concurrency service |
| Operations | Deterministic fake tests | Metrics, alerts, override governance, and runbooks |

### Trade-offs and graduation signals

Local immutable limits are easy to audit but cannot coordinate multiple processes. Graduate to a
shared quota system when concurrency or multi-tenant requirements make local counters inaccurate.
Add provider-specific budgets only when measured spend, rate-limit behavior, or service objectives
justify their extra configuration and failure modes.

## Practical exercises

1. Calculate the UTF-8 budget for ASCII text and an emoji, then predict which delta is rejected.
2. Seed a turn counter at its maximum and prove the fake records no request.
3. Seed a tool counter at its maximum and prove no second natural provider turn is implied.
4. Hold a fake provider at a logical gate and advance the injected deadline.
5. Race a final provider completion with an output-budget failure and identify the terminal guard's
   required evidence.
6. Explain why reported tokens cannot stop a stream before the report arrives.

## Key takeaways

- The harness owns budgets and charges them before admitting work or evidence.
- A deadline, streaming accountant, cleanup barrier, and terminal guard must work together.
- Distributed quotas and telemetry improve multi-process control but add operational cost and new
  failure domains.

## Glossary

- **Admission control:** decision made before costly work begins.
- **Budget reservation:** accounting performed before an observation is accepted.
- **Deadline waiter:** cancellable task that wakes at the monotonic provider-work deadline.
- **Hard limit:** validated maximum that active work cannot weaken.
- **Limit race:** concurrent attempts by a limit and another path to end a session.

See the shared [project glossary](../glossary.md) for session, model turn, provider, and tool call.

## Further reading

- [CAH-022 user story](../../user-stories/cah-022-enforce-loop-limits.md)
- [CAH-021 provider-neutral turn](cah-021-one-model-turn.md)
- Project design: [agent loop](../agent-loop.md), [safety model](../safety-model.md), and
  [evaluation](../evaluation.md)
- Later network boundary: [CAH-023 lesson](cah-023-openai-responses-adapter.md)
- Production references: [Python asyncio timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts),
  [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking),
  [OpenTelemetry metrics](https://opentelemetry.io/docs/concepts/signals/metrics/), and
  [Kubernetes resource quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
