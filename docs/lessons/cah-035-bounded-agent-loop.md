# CAH-035 lesson: Run the bounded agent loop

- **Unit:** CAH-035
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; only a one-call round trip is specified first
- **Story:** [CAH-035](../../user-stories/cah-035-run-bounded-agent-loop.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned state transitions, cumulative accounting, reachable stop
  conditions, and defense-in-depth guards
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Architecture](../architecture.md), and
  [Safety model](../safety-model.md)

> This lesson describes planned loop behavior. Pseudocode is not shipped-code evidence.

## Quick summary

CAH-035 turns one proven call/result cycle into an explicit sequential state machine with at most
four model turns and three admitted calls. The Python harness—not a provider or tool—owns progress.

## Learning objectives

After this unit, you should be able to:

- locate agency in explicit states and transitions;
- prove termination from hard turn/call ceilings;
- distinguish reachable limit precedence from defense-in-depth checks;
- carry history, usage, deadline, and output accounting cumulatively; and
- explain where a future MCP adapter fits without owning the loop.

## Why this unit matters

An “agent” is not mysterious autonomy. Here it is a small state machine that repeatedly admits one
model outcome, optionally runs one tool, appends one result, and decides whether another turn is safe.

## Junior engineer foundation

A state machine names legal states and transitions. If code cannot name a transition, it must fail.

```text
MODEL -> FINAL
MODEL -> CALL -> VALIDATE -> TOOL -> APPEND -> MODEL
```

A common misconception is that every configured limit must be reachable normally. With three call
slots, a fourth call fails before it could request turn five; the fifth-turn guard still protects
against corrupted/seeded state.

## Key concepts

- **Agent loop:** harness-owned repeated model/tool cycle.
- **Cumulative ledger:** limits that never reset between turns.
- **Reachable stop:** failure possible from a fresh legal session.
- **Defense in depth:** redundant guard tested through seeded internal state.
- **Sequentiality:** at most one active provider or tool operation.

## Architecture and design

```text
Ink TUI                 Python harness loop                     Provider
 final only <----- [publish accepted FINAL] <-------------- admitted text
                           ^        |
                           |        +---- next request -------> model
                           |                    ^
                    APPEND RESULT <---- bounded replay
                           ^
                    VALIDATE + TOOL ----> native read registry

Ceilings: 4 provider starts / 3 within-budget calls / one rejecting fourth observation at most
Evidence: one final transcript-v3 usage aggregate; no calls/results/opaque content
MCP: future registry/executor adapter below the loop, never the loop owner
```

The fourth admitted call is charged and rejected before dispatch. Starting turn five is therefore
unreachable normally and tested by seeding the turn ledger immediately before admission.

## Practical walkthrough

1. Validate the full request and charge a model start.
2. Collect one atomic CAH-033 outcome.
3. Publish and finish on final text.
4. Otherwise charge the call, validate, dispatch, and append its result.
5. Repeat while all cumulative checks pass.
6. Persist one checked usage aggregate only after successful final text.

## Implementation code samples

### Planned pseudocode: explicit loop

```python
while True:
    ledger.admit_model_start()
    outcome = await collect_one_turn(provider.start(build_request(history)))
    if isinstance(outcome, AcceptedFinalText):
        return await publish_final(outcome, aggregate_usage)
    ledger.admit_tool_call()
    history += (outcome.call, dispatch_one(outcome.call))
```

Every helper has a single admission or transition responsibility.

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
| cancellation during sync tool | post-dispatch guard | late result discarded |
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
3. Design a request-growth test crossing 512 KiB without truncation.
4. Teach back why an MCP server cannot decide the next model turn.

## Key takeaways

- The explicit Python state machine is the agent's control plane.
- Cumulative limits and exact precedence make termination provable.
- Defense-in-depth tests should seed the guarded state instead of inventing illegal histories.

## Glossary

- **Control plane:** component that decides transitions and policy.
- **Limit precedence:** which guard wins when more than one could reject work.
- **Seeded state:** deliberate test setup at an internal boundary.
- **Terminal winner:** the single completion/failure/cancellation selected for a session.

## Further reading

- [CAH-035 delivery contract](../../user-stories/cah-035-run-bounded-agent-loop.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
