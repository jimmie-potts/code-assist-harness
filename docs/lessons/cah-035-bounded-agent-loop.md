# CAH-035 lesson: Run the bounded agent loop

- **Unit:** CAH-035
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; only a one-call round trip is specified first
- **Story:** [CAH-035](../../user-stories/cah-035-run-bounded-agent-loop.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned state transitions, atomic scoped-instruction accumulation,
  cumulative accounting, reachable stop conditions, and defense-in-depth guards
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Architecture](../architecture.md), and
  [Safety model](../safety-model.md)

> This lesson describes planned loop behavior. Pseudocode is not shipped-code evidence.

## Quick summary

CAH-035 turns one proven call/result cycle into an explicit sequential state machine with at most
four model turns and three admitted calls. Successful requested paths can accumulate applicable
instructions between turns. The Python harness—not a provider or tool—owns progress and context.

## Learning objectives

After this unit, you should be able to:

- locate agency in explicit states and transitions;
- prove termination from hard turn/call ceilings;
- distinguish reachable limit precedence from defense-in-depth checks;
- trace atomic context enrichment across nested, repeated, alias, and sibling target scopes;
- carry history, usage, deadline, and output accounting cumulatively;
- explain why every synchronous guard first yields to the event loop; and
- explain where a future MCP adapter fits without owning the loop.

## Why this unit matters

An “agent” is not mysterious autonomy. Here it is a small state machine that repeatedly admits one
model outcome, optionally runs one tool, appends one result, and decides whether another turn is safe.

## Junior engineer foundation

A state machine names legal states and transitions. If code cannot name a transition, it must fail.

```text
MODEL -> FINAL
MODEL -> CALL -> VALIDATE -> YIELD/GUARD -> TOOL -> YIELD/GUARD
      -> DISCOVER -> YIELD/GUARD -> MERGE -> YIELD/GUARD
      -> STAGE REQUEST -> YIELD/GUARD -> ADMIT -> COMMIT/START MODEL
```

A common misconception is that every configured limit must be reachable normally. With three call
slots, a fourth call fails before it could request turn five; the fifth-turn guard still protects
against corrupted/seeded state.

Another misconception is that paths named in tool output select policy. They do not. Only the
validated requested `path` from a successful call becomes a `target_scope`; broad list/search results
need a later specific path-targeting call before their nested instructions apply.

One more subtle misconception is that calling a synchronous cancellation guard is enough. While a
synchronous tool owns the event-loop thread, the cancel command cannot run and update session state.
CAH-034's reusable checkpoint must first `await asyncio.sleep(0)` outside locks, optionally cross a
deterministic test gate, and only then read cancellation/deadline state.
An awaited gate is useful for pausing a stage but cannot by itself prove the production yield exists;
the separate no-hook queued-cancel test observes state at guard entry and mutation-tests removal of
the yield.

## Key concepts

- **Agent loop:** harness-owned repeated model/tool cycle.
- **Cumulative ledger:** limits that never reset between turns.
- **Reachable stop:** failure possible from a fresh legal session.
- **Defense in depth:** redundant guard tested through seeded internal state.
- **Sequentiality:** at most one active provider or tool operation.
- **Cooperative checkpoint:** CAH-034's yield, optional test hook, then established guard sequence.
- **Scoped accumulation:** atomically add newly applicable instruction items after successful reads.
- **Idempotent scope:** a repeated candidate-owner binding adds nothing only when its source,
  content, and original byte count match; one source under another owner remains distinct.
- **Positional replay:** append each optional continuation immediately before its call and matching
  result in one immutable history tuple.

## Architecture and design

```text
Ink TUI                 Python harness loop                     Provider
 final only <----- [publish accepted FINAL] <-------------- admitted text
                           ^        |
                           |        +---- next request -------> model
                           |             current context ^
         APPEND opaque? -> call -> result <---- bounded replay
                           ^
             VALIDATE -> YIELD/GUARD -> TOOL ----> native read registry
                                           | local dispatch candidate
                                           v
                  YIELD/GUARD -> CAH-025 discover -> YIELD/GUARD
                                           |
                                  CAH-030 merge -> YIELD/GUARD
                                           |
                          stage local result/context/history/request
                                           |
                              YIELD/GUARD -> admission -> commit/start

Ceilings: 4 provider starts / 3 within-budget calls / one rejecting fourth observation at most
Context: root-only start; up to 3 atomic scoped enrichments; recheck context/request every turn
Evidence: one final transcript-v3 usage aggregate; no calls/results/opaque content
MCP: future registry/executor adapter below the loop, never the loop owner
```

The fourth admitted call is charged and rejected before dispatch. Starting turn five is therefore
unreachable normally and tested by seeding the turn ledger immediately before admission.

## Practical walkthrough

1. Validate the full request and charge a model start.
2. Collect one atomic CAH-033 outcome.
3. Publish and finish on final text.
4. Otherwise charge the call and validate. Reuse CAH-034's cooperative checkpoint immediately
   before dispatch, execute the bounded synchronous tool, then checkpoint again.
5. For success, discover the validated requested scope, checkpoint, atomically merge its
   instructions, and checkpoint again; for a known error, retain the current context candidate
   after the required post-dispatch checkpoint.
6. Stage optional continuation, call, result, context, history, and the complete bounded request
   locally. Checkpoint at `before_provider_start`, admit the next model turn, then commit/start and
   repeat.
7. Persist one checked usage aggregate only after successful final text.

## Implementation code samples

### Planned pseudocode: explicit loop

```python
ledger.admit_model_start()
outcome = await collect_one_turn(provider.start(build_initial_request()))
while True:
    if isinstance(outcome, AcceptedFinalText):
        return await publish_final(outcome, aggregate_usage)
    ledger.admit_tool_call()
    await cooperate_then_guard("before_dispatch")
    dispatch_candidate = dispatch_one(outcome.call)
    await cooperate_then_guard("after_dispatch")
    context_candidate = context
    if dispatch_candidate.succeeded:
        discovered_candidate = instructions.discover(dispatch_candidate.target_scope)
        await cooperate_then_guard("after_discovery")
        context_candidate = context_builder.merge_atomically(context, discovered_candidate)
        await cooperate_then_guard("after_merge")
    result_candidate = dispatch_candidate.provider_result
    history_candidate = append_turn(history, outcome, result_candidate)
    request_candidate = build_bounded_request(context_candidate, history_candidate)
    await cooperate_then_guard("before_provider_start")
    ledger.admit_model_start()
    context, history = context_candidate, history_candidate
    outcome = await collect_one_turn(provider.start(request_candidate))
```

Every helper has a single admission or transition responsibility. In implementation the initial
start is admitted once before the loop and each continuation is admitted at its final guarded
transition. The opaque value remains in the same CAH-032 history tuple immediately before its call;
there is no adapter side channel. Context is replaced only after complete discovery/merge
validation, the final cooperative checkpoint, and model admission. Exact repeated/alias scopes are
no-ops; changed owner snapshots fail rather than silently replacing an earlier instruction, while
the same source under another owner remains a separately charged binding.
Each bounded synchronous value and the complete next request remain local candidates until that
final checkpoint wins.

### Planned pseudocode: fifth-turn defense

```python
ledger = seeded_ledger(model_turns=4)
assert start_next_turn(ledger, provider_spy).code == "model_turn_limit_exceeded"
assert provider_spy.starts == 0
```

This test does not invent an impossible fifth-turn provider transcript.

## Failure scenarios to study

| Scenario | First rejecting boundary | Safe result |
| --- | --- | --- |
| fourth call on turn four | call admission | no fourth dispatch |
| seeded fifth start | model admission | zero provider starts |
| request grows past 512 KiB | request construction | no next start |
| cancellation during sync tool | `after_dispatch` yields, then guards | late result discarded |
| cancellation during discovery/merge | following checkpoint yields, then guards | late bundle/package discarded |
| instruction source changes between scopes | atomic merge | prior context retained; terminal |
| nested/sibling merge exceeds context budget | atomic merge | no pending result/context publication |
| list/search returns a nested path | scope selection | returned path alone adds no instruction |
| invalid mixed response | CAH-033 collector | no tool/publication |
| usage sum overflows | aggregate admission | no transcript aggregate |

## Production expansion

### Example enterprise scenario

A production agent may schedule remote tools, retries, and subagents. Each feature multiplies states,
so transition tracing, idempotency, quotas, and recovery become operational requirements.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  provides call turns; application loop control and budgets remain local work.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) standardizes remote
  capability boundaries; authentication and availability add cost.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html) provide cancellation;
  task ownership and race tests add complexity.
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) expose transitions;
  privacy, sampling, and storage governance add cost.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Turns/calls | 4 / 3 | policy/model-specific quotas |
| Context | requested-path instruction accumulation | indexed retrieval and versioned context policy |
| Scheduling | one sequential operation | bounded concurrency and idempotency |
| Recovery | foreground fail closed | durable checkpoints/resumption |
| Evidence | aggregate only | redacted transition traces |
| Cost | simple, deterministic | orchestration and telemetry operations |

### Trade-offs and graduation signals

Small fixed ceilings may stop useful work, but make safety and cost testable. Increase or specialize
them only with eval evidence; add parallelism only after ordering, cancellation, and evidence rules
are designed.

## Practical exercises

1. Trace three calls followed by final text and count every turn.
2. Explain why a fourth call wins before a fifth-turn limit.
3. Trace nested then sibling reads; explain why precedence applies within each chain but one sibling
   does not override the other.
4. Design a request-growth test crossing 512 KiB without truncation.
5. Design named `asyncio.Event` gates for each synchronous checkpoint and explain why elapsed sleeps
   would make the cancellation test nondeterministic.
6. Explain why the no-hook guard-spy test, not an awaited Event hook, proves the unconditional yield.
7. Teach back why an MCP server cannot decide the next model turn or select instruction scope.

## Key takeaways

- The explicit Python state machine is the agent's control plane.
- Context growth is a guarded transition: requested-path discovery and merge succeed atomically or
  the loop stops without a next provider start.
- The guard observes queued cancellation only after CAH-034's reusable checkpoint yields to the
  event loop; staged candidates prevent partial state when it loses.
- Cumulative limits and exact precedence make termination provable.
- Defense-in-depth tests should seed the guarded state instead of inventing illegal histories.

## Glossary

- **Control plane:** component that decides transitions and policy.
- **Limit precedence:** which guard wins when more than one could reject work.
- **Seeded state:** deliberate test setup at an internal boundary.
- **Terminal winner:** the single completion/failure/cancellation selected for a session.
- **Sibling scope:** a different ancestor chain whose instructions retain separate applicability.

## Further reading

- [CAH-035 delivery contract](../../user-stories/cah-035-run-bounded-agent-loop.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
