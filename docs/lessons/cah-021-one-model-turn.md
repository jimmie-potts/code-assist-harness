# CAH-021 lesson: Complete one model turn

- **Unit:** CAH-021
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no model-backed agent turn or OpenAI adapter exists yet
- **Story:** [CAH-021](../../user-stories/cah-021-complete-one-model-turn.md)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Protocol](../protocol.md)

> This lesson describes the accepted ownership boundary and the planned one-turn slice. Provider
> calls, streaming events, and live smoke tests are not currently implemented.

## Quick summary

This unit plans the smallest real conversational path: one user task becomes one provider-neutral
request, streamed text becomes ordered session events, and one terminal outcome closes the session.
It teaches how an agent loop owns lifecycle even when a provider adapter owns API translation.

## Learning objectives

After completing this unit, you should be able to:

- trace one task from session input through a provider adapter and back to session events;
- reconcile streamed deltas with a completed assistant message using an explicit rule;
- normalize provider failure, usage, and cancellation without leaking SDK objects; and
- compare the local one-turn slice with resilient, observable production inference traffic.

## Why this unit matters

CAH-021 is the first real model capability, but keeping it to one turn isolates streaming and
lifecycle mechanics from tools and multi-step orchestration. If the adapter decides completion or
the TUI infers it from stopped text, terminal races become inconsistent. If live calls are required
for tests, ordinary development becomes slow, costly, and credential-dependent.

## Key concepts

- **Model turn:** one provider request and its complete streamed response.
- **Streaming normalization:** mapping provider-specific chunks into ordered harness events.
- **Completion reconciliation:** one documented rule for relating accumulated deltas to the final
  completed text.
- **Terminal guard:** the session mechanism that allows exactly one completion, cancellation, or
  failure outcome to win.
- **Usage data:** bounded provider-supplied counters represented in harness-owned types, not treated
  as proof of billing.
- **Opt-in smoke test:** a separately selected credentialed check that supplements, never replaces,
  deterministic default tests.

## Architecture and design

```text
session task
   |
   +--> agent loop --> Provider port --> OpenAI adapter --> Responses API
   |        ^                |
   |        |                +--> normalized stream events
   |        +--> fake provider in default tests
   |
   +--> ordered session events --> TUI and redacted transcript
```

The Python loop owns request construction, accepted delta order, reconciliation, cancellation, and
the terminal result. The OpenAI adapter owns SDK calls and converts provider objects into the port
defined by CAH-020. The event writer owns final session sequence numbers. The TUI renders those
events and never decides that the provider operation finished successfully.

Important invariants:

- exactly one provider operation is active for the session;
- accepted deltas become ordered `assistant.delta` events;
- normal completion produces one `assistant.completed` event followed by exactly one
  `session.completed` event;
- completed text follows the documented reconciliation rule;
- provider errors and usage become bounded harness data, never raw response objects; and
- cancellation, completion, and failure races still produce exactly one terminal session event.

## Practical walkthrough

1. Begin with a session containing one user task and applicable repository-level instructions.
   Construct a provider-neutral request without importing the OpenAI SDK in the loop.
2. Run the path first against CAH-020's strict fake. Script delayed deltas, usage, completion, and
   cancellation so behavior is observable without HTTP.
3. For each accepted text delta, emit an `assistant.delta` domain event through the ordered writer.
   Accumulate only accepted text, not arbitrary raw chunks.
4. Choose and document one reconciliation rule. For example, require completed text to equal the
   accumulated accepted deltas and fail normalization when it does not.
5. On normal provider completion, emit `assistant.completed`, then ask the terminal guard to emit
   `session.completed`. A second completion attempt must be a no-op or bounded diagnostic.
6. Translate provider exceptions at the adapter boundary into stable failure categories and safe
   messages. Preserve useful cause classification without persisting raw payloads.
7. Propagate session cancellation to the active foreground provider operation by aborting or
   terminating its client connection, then await the adapter's documented cleanup contract. Test
   both cancellation-before-output and cancellation-versus-completion races.
8. Add the OpenAI Responses API adapter only after fake-path behavior passes. Mapping tests use SDK
   fakes or mocks; an optional live smoke test remains outside default validation.
9. Verify CAH-011 redaction and `--no-transcript` behavior for local files. Configure provider-side
   response storage separately according to the adapter's data policy; the local transcript flag
   must not be described as a provider-retention control.

The vertical slice works when fake-backed tests prove event order, text reconciliation, transcript
content, and terminal state without an API key, and the adapter can be replaced without changing the
loop or reducer.

This unit uses foreground streaming. OpenAI documents synchronous cancellation as terminating the
connection; its background-response lifecycle is a separate adapter mode. Likewise,
`--no-transcript` disables the harness's local files only. Provider `store` configuration and any
organizational retention or Zero Data Retention policy must be chosen and documented independently.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Provider fails before a delta | No assistant text arrives | One normalized actionable failure and one failed terminal state |
| Provider fails after partial text | Some deltas are already visible | Accepted prefix remains bounded; failure is distinct from successful completion |
| Final text differs from deltas | Reconciliation detects inconsistent content | Documented normalization failure rather than silently rewriting visible history |
| Cancellation races completion | Both paths attempt a terminal transition | Terminal guard accepts one outcome and suppresses the other deterministically |
| Adapter receives unknown SDK event | Mapping has no valid domain variant | Adapter fails safely without leaking the object or inventing a session event |
| Transcript is disabled | Provider call still completes | Same session events and provider request policy; no local transcript or summary files are created |

## Production expansion

### Example enterprise scenario

Imagine a customer-support copilot serving thousands of concurrent agents with a latency objective,
regional provider endpoints, per-tenant privacy controls, and an incident-response rotation.
Operators need timeouts, retry budgets, circuit breaking, trace correlation, safe sampling, and cost
visibility. Those controls surround the provider port; they do not transfer session ownership to a
proxy or SDK.

### Typical production capabilities and tools

These official references illustrate capabilities, not repository requirements or endorsements:

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) documents the
  concrete response, streaming, usage, and tool surface for the first adapter. The
  [background-mode limits](https://developers.openai.com/api/docs/guides/background#limits)
  distinguish terminating a synchronous connection from background operation, while the
  [statefulness guidance](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
  makes provider storage an explicit API concern rather than a local transcript setting. Its
  operational burden includes credential rotation, quota and spend monitoring, API compatibility,
  and provider-retention governance.
- [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
  illustrates network-level connection, pending-request, request, and retry bounds. Its operational
  burden includes proxy deployment, safe configuration rollout, capacity tuning, and another
  production failure domain to operate.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate interoperable operation telemetry while leaving content capture and privacy decisions
  to the application. Their operational burden includes collector pipelines, sampling and
  cardinality policy, telemetry storage, privacy review, and on-call ownership.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Traffic | One local active session | Concurrent tenants, regions, endpoints, and deployment versions |
| Reliability | One operation with explicit failure and cancellation | Deadlines, retry budgets, circuit breakers, failover, and SLOs |
| Testing | Deterministic fake and mocked adapter mapping | Conformance suites, canaries, load tests, and controlled live probes |
| Telemetry | Bounded usage and local transcript | Traces, metrics, sampled logs, cost allocation, and alerts |
| Privacy | Redaction and transcript opt-out | Tenant policy, access controls, retention, residency, and content sampling rules |
| Cost | Direct and inspectable | Added proxies, telemetry pipelines, capacity planning, and on-call ownership |

### Trade-offs and graduation signals

Retries and failover can improve availability but may multiply cost, latency, and duplicate effects;
telemetry can improve diagnosis while increasing sensitive-data exposure. Graduate when measured
tail latency or error rates violate an SLO, concurrent demand saturates a provider path, regional
outage requirements are explicit, or multiple teams need consistent operational controls. Keep
provider-specific resilience outside the core domain contract where possible.

## Practical exercises

1. Script three deltas and completion with the fake, then write the exact expected session-event
   order and final reducer state.
2. Deliberately make completed text differ from accumulated deltas and compare two possible
   reconciliation policies before choosing one.
3. Race a fake cancellation checkpoint against completion repeatedly with a deterministic scheduler;
   assert one terminal event every time.
4. Map a fake SDK exception containing a fake credential and prove events, diagnostics, and
   transcript contain only the normalized safe fields.
5. Design an opt-in live smoke marker and show that the default test command never selects it.

## Key takeaways

- The adapter translates provider syntax; the Python loop owns model-turn and session semantics.
- Ordered deltas, explicit reconciliation, and one terminal winner make streaming trustworthy.
- Production resilience is valuable when measured service objectives require it, but it adds cost,
  privacy, and failure-mode complexity around the same core boundary.

## Glossary

- **Completion reconciliation:** the rule connecting accepted deltas to final assistant text.
- **Model turn:** one provider request and all stream events produced for it.
- **Normalized failure:** a bounded domain error derived from provider-specific detail.
- **Retry budget:** a cap that prevents recovery attempts from creating unbounded extra load.
- **Smoke test:** a small opt-in check against a real external integration.
- **Terminal guard:** the mechanism selecting exactly one terminal session outcome.

See the shared [project glossary](../glossary.md) for provider, assistant delta, session, and usage.

## Further reading

- [CAH-021 user story](../../user-stories/cah-021-complete-one-model-turn.md)
- Project design: [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [bounded loop](../agent-loop.md#bounded-loop), and
  [protocol lifecycle](../protocol.md#lifecycle-and-cancellation)
- Production references:
  [OpenAI Responses](https://platform.openai.com/docs/api-reference/responses),
  [background-mode limits](https://developers.openai.com/api/docs/guides/background#limits),
  [statefulness guidance](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness),
  [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking),
  and [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
