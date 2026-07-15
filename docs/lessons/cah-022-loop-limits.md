# CAH-022 lesson: Enforce loop limits

- **Unit:** CAH-022
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no limit configuration or enforcement exists yet
- **Story:** [CAH-022](../../user-stories/cah-022-enforce-loop-limits.md)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Safety model](../safety-model.md)

> This lesson describes accepted bounded-loop principles and planned limit behavior. The repository
> does not yet enforce model-turn, tool-call, output, or session-deadline limits.

## Quick summary

This unit plans hard limits for model turns, tool calls, assistant output, and elapsed session time.
It teaches that a limit is an explicit domain rule checked before costly work and during streaming,
not merely a provider setting or UI warning.

## Learning objectives

After completing this unit, you should be able to:

- distinguish count, size, and time limits and identify their correct enforcement points;
- use a monotonic, injectable clock for deterministic deadline behavior;
- preserve exactly-one-terminal-event semantics when limits race other outcomes; and
- compare local session bounds with layered production quotas and rate controls.

## Why this unit matters

Even a one-turn loop can stream excessive output or wait indefinitely. Later tool iterations add
more ways to consume time and resources. Without typed limits, a model, provider, configuration
mistake, or future tool sequence can run longer or cost more than the user intended. Stable failure
codes also make evaluation and support distinguish exhaustion from provider failure.

## Key concepts

- **Hard limit:** a bound that cannot be weakened by the active session or model.
- **Preflight check:** enforcement immediately before starting a provider operation or future tool
  operation.
- **Streaming check:** incremental enforcement while output arrives, before unbounded content is
  emitted to the TUI or transcript.
- **Monotonic deadline:** elapsed-time bound based on a clock unaffected by wall-clock corrections.
- **Counter ownership:** the Python loop records accepted model turns, provider-requested tool calls,
  and output units using one documented accounting rule.
- **Limit failure:** a distinct structured terminal failure naming the exhausted resource and safe
  counters, rather than masquerading as provider failure.

## Architecture and design

```text
validated Limits configuration
          |
          v
loop preflight --> start current provider / future tool operation
     |                       |
     +-- reject with         +--> stream accounting --> bounded events
         limit code                    |
                                      +--> stop with limit code
```

Python owns configuration validation, counters, deadline checks, output accounting, and terminal
failure selection. A provider may receive a narrower output setting as defense in depth, but its
setting does not replace harness enforcement. The TUI renders the stable failure and a safe next
step; it cannot increase an active session's limits.

Important invariants:

- zero, negative, invalid, or unreasonably large values follow an explicit reject-or-clamp policy;
- every applicable limit is checked before a costly operation begins;
- no provider or future tool operation starts after its budget is exhausted;
- emitted assistant content never exceeds the harness output bound;
- provider-requested tool calls are counted even before tool execution exists; and
- deadline, cancellation, completion, and provider failure races still yield exactly one terminal
  session event with bounded counters in the transcript and summary.

## Practical walkthrough

1. Define one typed immutable limits configuration with validated defaults for model turns, tool
   calls, assistant output, and session duration. Document units and maximum accepted values.
2. Inject a monotonic clock into a small limit tracker. Capture the absolute deadline once so checks
   do not accumulate wall-clock drift.
3. Define precisely when counters are consumed. A model turn should be accounted before or when its
   provider operation starts, while each provider-requested tool call counts before any future
   validation or execution.
4. Add one preflight function that returns either permission plus remaining budget or a stable limit
   failure. Call it before every current and future costly operation.
5. Account for accepted output incrementally. Keep the visible prefix within the bound, cancel or
   stop the provider operation, and emit the selected output-limit failure without forwarding the
   overflowing content.
6. Route limit exhaustion through the same terminal guard used for cancellation and completion. The
   first valid terminal transition wins; later attempts cannot emit a second terminal event.
7. Include limit type and bounded counters in validated transcript and summary data. Never include
   the rejected content merely to explain the failure.
8. Use an injected fake clock and strict fake provider for one-below, exact-boundary, and over-limit
   tests. CAH-021 exposes only one model turn, so exercise an already-exhausted model-turn counter at
   the limit-tracker/preflight seam rather than adding multi-turn orchestration to this story.

The strongest evidence is negative: an exhausted preflight does not start a provider operation,
output does not grow after its streaming bound, and only one stable failure reaches the reducer,
TUI, and transcript.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Model-turn budget is exhausted | An isolated preflight attempts to admit a provider request | Request count remains unchanged and the model-turn limit code terminates once; no multi-turn loop is implied |
| Output crosses the boundary | Next delta would exceed accepted size | Overflow is not emitted or stored; provider work stops; output-limit failure is bounded |
| Deadline and completion coincide | Fake clock reaches deadline as completion arrives | Terminal guard selects one documented result and suppresses the other |
| Tool-call burst arrives | Provider requests more calls than configured | Every requested call is counted; none beyond the limit can reach execution |
| Configuration is negative or enormous | Startup validation receives unsafe values | Configuration fails or clamps according to the documented policy, never silently disables limits |
| Wall clock changes | System time jumps while a session runs | Monotonic deadline behavior remains unchanged in an injected-clock test |

## Production expansion

### Example enterprise scenario

Imagine a multi-tenant coding service with hundreds of concurrent sessions. Each tenant has monthly
cost allocation, requests have latency objectives, shared provider capacity must resist noisy
neighbors, and runaway workloads must not exhaust cluster resources. Session limits remain useful,
but gateways and infrastructure must also enforce tenant, service, and cluster budgets.

### Typical production capabilities and tools

These official references show representative capabilities, not endorsed project dependencies:

- [Python `asyncio` timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts)
  document the local cancellation-based timeout primitive available to the planned runtime.
- [Kubernetes ResourceQuota](https://kubernetes.io/docs/concepts/policy/resource-quotas/) illustrates
  namespace-level aggregate resource constraints that protect shared clusters.
- [Envoy local rate limiting](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/local_rate_limit_filter)
  illustrates request-rate enforcement at a network boundary.
- [Prometheus histograms](https://prometheus.io/docs/practices/histograms/) illustrate latency and
  size distributions used to evaluate objectives and choose defensible thresholds.
- [OpenTelemetry metrics data model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
  illustrates interoperable transport of pre-aggregated measurements across telemetry systems.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One session in one WSL process | Per-request, tenant, service, provider, and cluster limits |
| Time | Injected monotonic session deadline | End-to-end deadline propagation and queue-time accounting |
| Volume | Turn, call, and output counters | Distributed quotas, rate limits, concurrency caps, and budgets |
| Enforcement | Python loop and provider cancellation | Layered application, gateway, scheduler, and infrastructure controls |
| Evidence | Fake-clock tests and transcript counters | Metrics, alerts, SLOs, billing attribution, and capacity forecasts |
| Cost | Small explicit tracker | Coordinated configuration, telemetry, distributed state, and operations |

### Trade-offs and graduation signals

Distributed controls improve fairness and capacity protection but introduce coordination lag,
eventual consistency, policy rollout risk, and infrastructure cost. Graduate when concurrent users
compete for shared capacity, provider spend needs tenant attribution, observed tail latency violates
an objective, or one process's limits cannot protect an upstream or cluster. Keep local hard limits
even after adding outer layers because each boundary protects a different resource.

## Practical exercises

1. Create a table defining the accounting instant and unit for every planned limit.
2. With a fake monotonic clock, test just before, exactly at, and just after the deadline without any
   real sleep.
3. Script a delta whose final character crosses the output limit; prove the stored and rendered
   prefix stays within the bound.
4. Script one response with more tool-call requests than allowed and assert that calls beyond the
   budget are not admitted. Do not add tool execution or another provider turn.
5. Race deadline, cancellation, and completion under deterministic scheduling and assert exactly one
   terminal event and one transcript explanation.

## Key takeaways

- Python owns limits and checks them before cost is incurred; provider options are only additional
  defenses.
- Deterministic clocks, explicit accounting, bounded streaming, and one terminal winner make limits
  testable rather than aspirational.
- Production quotas add fairness across shared resources, but they complement rather than replace
  local session bounds.

## Glossary

- **Budget:** the configured amount of a resource a session may consume.
- **Deadline:** an absolute monotonic point after which new work is prohibited.
- **Hard limit:** a bound the active model or session cannot weaken.
- **Preflight:** a check immediately before beginning a costly operation.
- **Rate limit:** a bound on operations admitted during a time interval.

See the shared [project glossary](../glossary.md) for limit, model turn, tool call, and terminal event.

## Further reading

- [CAH-022 user story](../../user-stories/cah-022-enforce-loop-limits.md)
- Project design: [ADR invariants](../adr/0001-own-the-agent-loop.md#invariants),
  [loop limits](../agent-loop.md#limits-and-failures), and
  [bounded work](../safety-model.md#cancellation-and-bounded-work)
- Production references: [Python timeouts](https://docs.python.org/3/library/asyncio-task.html#timeouts), [Kubernetes quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/), [Envoy rate limits](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/local_rate_limit_filter),
  [Prometheus histograms](https://prometheus.io/docs/practices/histograms/), and [OpenTelemetry metrics](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)
