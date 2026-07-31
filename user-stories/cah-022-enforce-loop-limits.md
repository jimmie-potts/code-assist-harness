# CAH-022 - Enforce loop limits

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-021
- **Lesson:** [Loop limits](../docs/lessons/cah-022-loop-limits.md)

## User story

> As a user, I want provider work in every provider-backed session to stop predictably at hard limits
> so that network or billable work cannot run without a harness-owned safety budget.

## Scope

- Introduce one immutable, validated limits configuration for model-turn admission, elapsed provider
  work, cumulative accepted assistant-output bytes, and observed provider tool calls.
- Check admission before `Provider.start()`, enforce the deadline while awaiting stream progress, and
  enforce output and tool-call limits before accepting their observations.
- Cancel the active provider operation and await its cleanup barrier whenever a limit wins after an
  operation exists; admission denial starts and cancels nothing.
- Route limit, provider completion, provider failure, and user cancellation through CAH-021's shared
  terminal guard.
- Exercise every boundary deterministically with the fake provider, an injected monotonic clock, and
  an injected deadline waiter.

## Locked limit contract

- Configuration rejects booleans, zero or negative values, and values above documented maximums; it
  never silently clamps or disables a limit.
- Integer configuration fields and ranges are:
  - `max_model_turns`: default `1`, allowed `1..16`;
  - `provider_work_timeout_seconds`: default `120`, allowed `1..3600`;
  - `max_assistant_output_bytes`: default `4096`, allowed `1..8192`; and
  - `max_observed_tool_calls`: default `1`, allowed `1..64`.
- One model turn is charged immediately before `Provider.start()`. Tests may seed an exhausted
  tracker to prove denial until multi-turn orchestration exists.
- The integer timeout configuration is converted without truncating the clock:
  `deadline = monotonic_now() + provider_work_timeout_seconds`. This happens when the provider-backed
  session object is allocated for an accepted command, before lifecycle observers/transcript setup
  or provider admission. The later task receives that captured absolute deadline. A separate
  deadline waiter races every awaited provider-stream step so a silent provider cannot evade it.
- Deadline checks precede admission and observation acceptance. After a stream wait wakes, the loop
  reads the injected clock again; if `monotonic_now() >= deadline`, the deadline wins even when the
  next provider event became ready in the same scheduler turn. The event waiter is cancelled and
  reaped without accepting that observation.
- Provider admission and deadline latching share a small deadline-state guard, separate from the
  publication lock. Under it, admission rechecks the latch and clock, charges the model turn, and
  calls the synchronous, lazy `Provider.start()` without an intervening await. Latch-first starts no
  operation; admission-first installs the operation for the watcher to cancel if expiry follows.
- The deadline is specifically a provider-work deadline, not a wall-clock promise for protocol or
  transcript sink latency. Its independent watcher latches expiry and starts supervised provider
  cancellation without acquiring CAH-021's event-publication lock. An event transaction admitted
  before expiry still finishes its wire write, reducer acceptance, and transcript-observer attempt;
  after it releases the lock, every terminal-selection path checks the expiry latch first and selects
  the deadline before accepting another provider observation. Thus the cancellation attempt begins
  at the deadline even if a sink is blocked; a conforming provider stops, while failed or timed-out
  cleanup remains explicitly unconfirmed. Terminal publication may finish later. Timeouts or
  force-close policy for local sinks remain separate future work.
- Assistant output is charged in cumulative UTF-8 bytes before an `assistant.delta` is emitted or
  persisted. The delta that would exceed the budget is rejected in full. This configurable check
  precedes CAH-021's fixed 8192-byte compatibility ceiling, so
  `assistant_output_limit_exceeded` wins whenever both checks would reject the same delta.
- Each `ProviderToolCallRequested` increments `tool_calls_observed` before its budget decision and
  before CAH-021's `tool_unavailable` handling. Counts `1..max_observed_tool_calls` are admitted; the
  rejecting attempt is retained as `max_observed_tool_calls + 1` and wins as
  `tool_call_limit_exceeded` without parsing arguments. Because CAH-021 terminates on its first
  admitted tool request, integration covers the first-call boundary and seeded tracker tests cover
  exact exhaustion and the one over-limit observation until multi-turn work exists.
- Stable terminal codes are `model_turn_limit_exceeded`, `provider_work_deadline_exceeded`,
  `assistant_output_limit_exceeded`, and `tool_call_limit_exceeded`.
- Their exact safe messages are, respectively, `The model-turn limit was reached.`,
  `Provider work exceeded its time limit.`, `Assistant output exceeded its byte limit.`, and
  `The provider tool-call limit was reached.` No configured value or provider content is included.
- Provider-reported token usage is observational metadata and never authorizes more work or replaces
  the harness's own counters.
- If a non-conforming provider raises from its cleanup barrier, the already-selected limit remains
  the session terminal outcome. CAH-021's payload-free `provider_cleanup_failed` runtime diagnostic
  is emitted and any separate pending `anext` task is cancelled and awaited; raw exception text
  never becomes evidence, and provider-resource cleanup remains explicitly unconfirmed.
- Every `cancel()` or `wait_closed()` cleanup await is supervised by one fixed, non-configurable
  five-second cleanup grace using the injected monotonic waiter. If the barrier raises or the grace
  expires, its local awaitable task is cancelled and awaited, the same payload-free
  `provider_cleanup_failed` diagnostic is emitted, and the selected terminal outcome remains. This
  local bound requires the provider awaitable to propagate task cancellation, as every conforming
  in-process implementation must; it does not claim remote/provider cleanup succeeded. An
  implementation that suppresses `CancelledError` cannot be contained by this port and requires a
  future process-isolation or escalation policy.
- CAH-022 advances the transcript writer to version 3. A provider-backed session writes at most one
  transcript-only `loop.limits_observed` record. With persistence enabled and healthy through the
  terminal write, it writes exactly one immediately before its terminal session event. A disabled
  transcript, persistence failure before that record, or teardown before terminal preparation
  writes none; teardown or persistence failure after the record may leave a replayable one-record
  prefix without a terminal. The record contains `session_id`, the four configured limits,
  `model_turns_started`,
  `assistant_output_bytes`, `tool_calls_observed`, and an optional exhausted-limit enum; it omits
  monotonic timestamps and raw provider values. Model turns and assistant bytes count admitted work;
  tool calls count observations, so replay permits `tool_calls_observed` through the configured
  maximum plus one only when the tool budget is exhausted. `exhausted_limit` is exactly null or one
  of `model_turns`, `provider_work`, `assistant_output`, and `tool_calls`; `tool_calls` requires the
  observed count to equal its configured maximum plus one, while every other value requires the
  observed count to remain at or below that maximum.
- Replay accepts transcript versions 1, 2, and 3. It validates the version-3 record's session,
  cardinality, order, configured ranges, and counter bounds, exposes it beside CAH-021 usage in the
  replay-evidence projection, and derives the human summary from that projection. Mock sessions may
  use version 3 without a limit record because they do not enter the provider-backed path.

## Acceptance criteria

1. One typed configuration exposes exactly the four locked integer fields, defaults, and ranges.
2. Invalid types and out-of-range values are rejected before a session or provider operation starts.
3. Exhausted model-turn admission emits one failure without calling `Provider.start()`.
4. Provider-work deadline enforcement uses only an injected monotonic clock, wakes even when no
   provider event arrives, and requests provider cancellation independently of a blocked admitted
   event publication; it does not claim a local sink or terminal-latency timeout.
5. The delta that would exceed the cumulative UTF-8 output budget is never emitted to the TUI or
   transcript.
6. Tool-call accounting occurs before unsupported-tool handling and cannot imply tool execution or
   another model turn; seeded tracker tests prove exhaustion that the one-turn integration cannot
   naturally reach.
7. Every limit winner with an active provider operation requests cancellation and supervises the
   cleanup barrier through success, safe failure, or the fixed cleanup grace before the session task
   returns; admission failures never call `Provider.start()` or cancellation.
8. Each limit emits its distinct safe code and an actionable bounded message.
9. Exactly one terminal event is emitted when a limit races completion, provider failure, or user
   cancellation.
10. Transcript and summary evidence identify the exhausted limit and bounded harness-owned counters;
    disabled transcripts create no local evidence. Version-1 and version-2 replay stays compatible.
11. Fake-provider integration tests cover every naturally reachable boundary; focused tracker tests
    seed model-turn and tool-call counts to cover one below, exactly at, and one beyond otherwise
    unreachable multi-operation boundaries. No costly operation or oversized observation is admitted.
12. The default repository gate remains deterministic, credential-free, and network-free.

## Validation

- Parameterize boundary tests for every numeric limit and invalid configuration value.
- Use injected clocks, deadline waiters, and logical fake-provider checkpoints; do not use
  timing-sensitive sleeps.
- Cover the exact deadline/event tie and prove the deadline observation-precedence rule. Block an
  admitted delta sink across expiry and prove the delta transaction finishes consistently while
  provider cancellation begins at the deadline and the deadline terminal wins afterward.
- Expire the deadline during provider-backed session setup before admission and race the dedicated
  deadline-state guard in both orders. Assert latch-first makes zero `Provider.start()` calls, while
  admission-first installs exactly one lazy operation that the watcher then cancels.
- Cover cleanup success, cleanup exception, and a cancellation-responsive never-finishing cleanup
  awaitable with the injected five-second grace; assert the local task propagates cancellation and
  is reaped, while remote resource cleanup is not overclaimed. Document that an awaitable which
  suppresses task cancellation is outside the current in-process containment contract.
- Assert provider-start counts, provider cancellation and cleanup, accepted UTF-8 bytes, observed
  tool calls, terminal event count, reducer state, transcript/summary evidence, and safe messages.
- Run the full repository-wide non-live gate.

## Documentation impact

Update the agent-loop, safety, configuration, evaluation, protocol-failure, and glossary documents
with units, defaults, validation, accounting moments, race semantics, and stable codes. Complete the
linked written lesson and required visual lesson when the unit is implemented.

## Out of scope

- OpenAI or another adapter, provider-specific timeouts, token/cost/rate quotas, retries, backoff, or
  adaptive budget increases.
- Multiple model turns, tool execution, subprocess timeouts, or approval workflows.
- Process isolation or forceful escalation for a provider implementation that suppresses task
  cancellation.
- Protocol-sink, transcript-sink, or whole-session terminal-latency timeouts.
- An interface that lets an active session weaken its own limits.
