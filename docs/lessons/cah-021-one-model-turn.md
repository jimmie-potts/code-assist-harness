# CAH-021 lesson: Run one provider-neutral turn

- **Unit:** CAH-021
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no provider-backed turn is connected to the session runtime
- **Story:** [CAH-021](../../user-stories/cah-021-complete-one-model-turn.md)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Protocol](../protocol.md)

> This lesson describes an accepted provider-neutral design. The current launched application still
> runs `MockSession`; the loop, usage evidence, and provider injection seam below are not implemented.
> CAH-023, not this unit, will add and activate an OpenAI adapter.

## Quick summary

CAH-021 plans the smallest harness-owned model-turn boundary: one task becomes one
`ProviderRequest`, one provider operation streams observations, and the session selects one terminal
outcome. The strict fake proves orchestration without HTTP, credentials, provider SDK types, or hard
limits.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a session, provider operation, and model turn;
- trace provider-neutral observations into ordered session events and local evidence;
- explain why reconciliation and one terminal guard make streaming trustworthy;
- test cancellation and malformed streams without wall-clock sleeps; and
- identify which concerns belong to later limit, provider, context, and tool units.

## Why this unit matters

CAH-020 proves that the provider port and fake behave correctly in isolation. The harness still needs
to prove that it owns request construction, stream grammar, cancellation cleanup, and session
completion. Keeping the first turn provider-neutral separates those lifecycle decisions from a
vendor SDK and lets CAH-022 add hard limits before CAH-023 enables network or billable work.

## Junior engineer foundation

An asynchronous stream is a sequence whose next value may arrive later. An `async for` loop waits
without blocking every other task on the event loop:

```python
# Planned teaching example, not shipped CAH-021 code.
async for event in operation.events():
    handle(event)
```

The loop does not mean the provider owns the session. The provider reports observations; the harness
decides which observations are legal and whether the session completed, failed, or was cancelled.

A terminal event means no later work is accepted for that session. A common beginner misconception
is that stopping the stream automatically means success. The connection could close because of a
failure, cancellation, or malformed implementation, so CAH-021 requires an explicit provider
terminal observation and a separate harness terminal decision.

## Key concepts

- **Provider-neutral request:** immutable conversation and already-resolved repository instructions
  expressed only with harness-owned types.
- **Provider operation:** one single-consumer stream plus awaited cancellation and cleanup.
- **Stream grammar:** the legal order and cardinality of text, completion, usage, failure, and tool
  observations.
- **Completion reconciliation:** byte-for-byte comparison of completed text with the concatenation
  of accepted deltas.
- **Terminal guard:** the session mechanism through which completion, failure, and cancellation
  compete for one final outcome.
- **Trusted usage evidence:** optional bounded counters persisted through a transcript-only
  `model.usage_observed` record. They are neither lifecycle state, protocol-v1 UI state, nor proof
  of billing.

## Architecture and design

```text
validated session task
        |
        v
one-turn loop ---- builds ----> ProviderRequest
        |                              |
        |                       Provider.start()
        |                              |
        +<---- one ProviderOperation --+
        |
        +--> ordered session events --> reducer / protocol writer
        +--> model.usage_observed --> transcript / replay evidence / summary
        +--> cancel + await cleanup --> terminal guard
```

The loop owns request construction, event acceptance, reconciliation, cancellation propagation, and
the terminal result. The provider owns only its operation and cleanup contract. The ordered writer
owns protocol sequence numbers, while the transcript observes accepted facts without becoming
lifecycle authority.

The successful grammar is deliberately narrow:

1. one or more non-empty `ProviderTextDelta` values;
2. exactly one `ProviderTextCompleted` equal to their concatenation;
3. optionally one bounded `ProviderUsageReported`;
4. exactly one `ProviderCompleted`.

`ProviderFailed` may terminate before or after partial text. A tool-call request is not ignored: it
becomes `tool_unavailable`, cancellation is requested, the cleanup barrier is awaited, and no second
turn begins. Missing, duplicate, out-of-order, empty, or mismatched successful observations become
`provider_invalid_response` without copying content into diagnostics.

Accepted deltas also share a fixed `8192`-byte cumulative UTF-8 compatibility ceiling. The delta that
would cross it is rejected in full before emission. This is a protocol-fit invariant, not CAH-022's
configurable safety budget; that later budget must be no larger than the ceiling.

`ProviderTextCompleted` remains a reconciled candidate until `ProviderCompleted` validates the whole
success grammar and the loop finishes its `wait_closed()` attempt. Only then does the loop emit
`assistant.completed` and `session.completed`. If that barrier raises, the selected completion stays
authoritative and the loop first emits the bounded cleanup diagnostic. A later usage failure,
provider failure, or early stream close before `ProviderCompleted` cannot leave a completed assistant
in a failed session.

Optional usage produces at most one transcript-only `model.usage_observed` record after text
completion and before provider completion. Enabled, healthy persistence writes exactly one; disabled
or failed persistence writes none. The record contains the session ID and safe-integer input/output
counts, consumes no protocol sequence, and does not enter either lifecycle reducer. The CAH-021 writer
always emits version 2; replay accepts versions 1 and 2 and restores version-2 usage into a separate
evidence projection before building the summary. Protocol v1 and CAH-010's shared lifecycle fixtures
stay unchanged. Usage admission is nevertheless a shielded transaction under the session decision
lock: usage-first finishes its persistence attempt before a terminal can win, while terminal-first
discards the observation. A CAH-022 deadline reservation has priority before usage admission.

The request accepts an injected tuple of instructions because discovery and precedence are separate
context-engineering responsibilities. The planned CAH-021 seam supplies an empty tuple until E3
implements that work. CAH-021 also adds an injection seam, but `main()` remains on the visible M0
mock until CAH-023 can select and configure a real adapter honestly. The mock response and
cancellation path stays the same even though the shared transcript writer advances to version 2.

Session outcome authority is fixed before loop-initiated cleanup. Normal paths select the terminal
guard first; CAH-022's independent watcher instead latches an irrevocable deadline reservation before
starting cancellation, and the session formalizes that reserved failure after any admitted event
transaction completes. Provider-internal natural cleanup may occur before an adapter exposes its
terminal observation and cannot select session state. The wire terminal waits until the loop's own
cleanup attempt finishes. This keeps one outcome authoritative without claiming that an unclosed
provider is healthy; a cleanup-contract violation adds only the safe runtime diagnostic.

That diagnostic is an existing protocol-v1 `runtime.error`, not a new session event. It is emitted
at most once with start-command correlation and exactly the fields
`code=provider_cleanup_failed`, `message=Provider cleanup could not be confirmed.`, and
`recoverable=true`.
It follows the failed cleanup attempt and precedes any already-selected session terminal. Because it
is recoverable and never enters the lifecycle reducers or transcript, the TUI can still accept the
authoritative terminal that follows. Teardown-first may emit the diagnostic but invents no session
terminal.

Each accepted lifecycle event is a smaller transaction under the same session decision lock. The
session writes the event through `OrderedEventWriter`, accepts it in the Python reducer, and finishes
the transcript-observer attempt as one shielded unit. This matters because the ordered writer may
finish a sink write and then propagate task cancellation. If the event transaction won admission,
the session lets all three views catch up before cancellation competes; if cancellation selected a
terminal outcome first, no later delta starts. A committed wire delta therefore cannot disappear
from the authoritative reducer or enabled, healthy transcript merely because cancellation arrived
during its sink call.

## Practical walkthrough

1. Build one `ProviderMessage(role="user", content=task)` and combine it with the caller-supplied
   instruction tuple.
2. Call `Provider.start()` once and claim `events()` once.
3. Reserve each text delta against the fixed protocol ceiling, accumulate it, and publish its
   existing `assistant.delta` as one shielded wire/reducer/transcript-observer transaction.
4. Validate text completion against the accumulated buffer but retain it as a candidate.
5. Validate at most one usage report and attempt its transcript-only version-2 evidence persistence.
6. Accept `ProviderCompleted` only after valid text completion and select completion in the terminal
   guard. When it wins, await `wait_closed()`, then emit `assistant.completed` and
   `session.completed`.
7. On failure, invalid structure, or an unavailable tool request, first select one safe failure;
   when it wins, cancel if work remains, await cleanup, and then emit `session.failed`.
8. Let user cancellation compete in the same guard. Only when cancellation wins does it await
   `operation.cancel()` and then emit `session.cancelled`.
9. Let runtime shutdown, stdin EOF, or outer-task cancellation enter the same guard. If teardown
   wins, cancel and await the operation without inventing a user-cancelled wire event or summary. If
   a session outcome already won, shield it through cleanup, wire terminal emission, and summary.
10. Assert the strict fake is complete so an abandoned stream or unconsumed scripted suffix cannot
   hide orchestration drift.

## Implementation code samples

No CAH-021 implementation exists yet. The following pseudocode states the intended ownership, not a
repository-backed sample:

```text
request = build_request(task, resolved_instructions)
operation = provider.start(request)
try:
    for each provider observation:
        validate grammar
        under the session decision lock:
            shield wire write + reducer acceptance + transcript-observer attempt
            await the transaction result before propagating outer cancellation
        for optional bounded model.usage_observed:
            under the session decision lock, shield the evidence persistence attempt
            discard it when a terminal/deadline reservation already owns the outcome
    require reconciled text completion and provider completion
    if terminal_guard.select_completed():
        await operation.wait_closed()
        emit assistant.completed and session.completed
on a naturally observed ProviderFailed:
    if terminal_guard.select_failed(safe_code, safe_message):
        await operation.wait_closed(), reporting bounded cleanup failure separately
        emit selected session.failed
on invalid grammar or another harness-rejected observation:
    if terminal_guard.select_failed(safe_code, safe_message):
        await operation.cancel(), reporting bounded cleanup failure separately
        emit selected session.failed
```

After implementation, replace this block with exact success and failure excerpts from the loop and
its fake-provider tests, then explain the important lines in small logical chunks.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Failure before output | No assistant delta | One normalized failed terminal state |
| Failure after output | A partial prefix is visible | Prefix remains evidence; no assistant completion is invented |
| Completed text differs | Reconciliation rejects the stream | `provider_invalid_response` without content in diagnostics |
| Output crosses 8192 bytes | Candidate delta would exceed protocol-fit ceiling | Whole delta rejected before TUI or transcript |
| Tool request arrives | Provider asks for unsupported work | `tool_unavailable`, cancellation, and awaited cleanup |
| Stream closes early | No provider terminal observation | Structured invalid-stream failure |
| Cancellation arrives during delta sink | Ordered writer may commit before cancellation propagates | Finish reducer and transcript-observer attempt for that delta, then let cancellation compete |
| Cancellation races completion | Two terminal paths contend | Exactly one session terminal event wins |
| Usage overflows its bound | Counter cannot enter trusted evidence | Invalid-stream failure; no oversized metadata is persisted |
| Runtime pipe closes | No correlated user-cancel command exists | Cancellation and cleanup attempted; incomplete transcript, no invented terminal |
| Provider cleanup raises | Selected outcome already owns the session | One recoverable, start-correlated `provider_cleanup_failed` runtime error, then the unchanged terminal when one was selected |

## Production expansion

### Example enterprise scenario

A multi-tenant coding assistant may run thousands of concurrent streams across regions and provider
versions. It needs deadlines, admission control, retry budgets, telemetry, privacy policy, and
provider conformance testing while preserving the same rule: adapters report observations and the
harness owns session truth.

### Typical production capabilities and tools

These are comparisons, not repository dependencies:

- [OpenAI Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
  illustrates typed provider events that a later adapter can normalize.
- [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
  illustrates connection, request, and pending-work bounds around remote operations.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate interoperable operation telemetry with an additional privacy and operations burden.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html) document the task and
  cancellation primitives used by the local runtime.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Traffic | One local active operation | Concurrent tenants, regions, and provider versions |
| Reliability | Deterministic fake and one terminal guard | Deadlines, retry budgets, circuit breakers, and failover |
| Evidence | Local redacted transcript metadata | Traces, metrics, cost allocation, and retention governance |
| Testing | Scripted fake with logical checkpoints | Conformance, canary, load, and fault-injection suites |
| Operations | No provider network in this unit | Credential rotation, quota monitoring, and on-call ownership |

### Trade-offs and graduation signals

The narrow grammar is easy to teach and test but intentionally rejects tool-only, multimodal, and
multi-turn responses. Expand it only when a later user story names the new outcome and supplies
fixtures for every added observation. Adopt production routing or resilience controls when measured
concurrency, latency, availability, or organizational ownership requires their cost.

## Practical exercises

1. Script two deltas and matching completion, then list the exact provider and session event order.
2. Change one character in completed text and predict which evidence remains accepted.
3. Put a logical cancellation checkpoint before output and between deltas; prove cleanup in both.
4. Emit a tool request with secret-looking arguments and verify diagnostics contain neither value.
5. Explain why an empty instruction tuple is honest while automatic `AGENTS.md` discovery is not yet
   implemented.

## Key takeaways

- The Python loop, not the provider or TUI, owns turn and session semantics.
- Strict stream grammar, reconciliation, cleanup, and one terminal guard make asynchronous behavior
  deterministic.
- Vendor integration and production resilience remain separate units because they introduce
  different risks and reasons to change.

## Glossary

- **Model turn:** one provider request and all observations from its operation.
- **Provider operation:** the single-use stream plus its cancellation and cleanup boundary.
- **Reconciliation:** validation that completed text matches accepted incremental text.
- **Stream grammar:** legal provider-observation order and cardinality.
- **Terminal guard:** the authority that selects one final session outcome.
- **Trusted usage evidence:** bounded non-authoritative counters restored from a transcript-only
  evidence record.

See the shared [project glossary](../glossary.md) for session, provider, assistant delta, and usage.

## Further reading

- [CAH-021 user story](../../user-stories/cah-021-complete-one-model-turn.md)
- Project design: [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [agent loop](../agent-loop.md), [protocol](../protocol.md), and
  [context engineering](../context-engineering.md)
- Provider-port precursor: [CAH-020 lesson](cah-020-provider-interface-and-fake.md)
- Later network boundary: [CAH-023 lesson](cah-023-openai-responses-adapter.md)
- Production references: [OpenAI Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
  [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking),
  [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
  and [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
