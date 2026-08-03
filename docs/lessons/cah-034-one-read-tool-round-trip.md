# CAH-034 lesson: Run one read-tool round trip

- **Unit:** CAH-034
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; the harness still rejects tool requests
- **Story:** [CAH-034](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** One observe-validate-dispatch-result-follow-up sequence, exact safe envelopes,
  non-preemptive tool cancellation boundaries, and one aggregate usage record
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Tool system](../tool-system.md), and
  [Context engineering](../context-engineering.md)

> This lesson describes planned behavior. Pseudocode is not evidence of an implemented round trip.

## Quick summary

CAH-034 takes one atomically admitted call, validates and executes one native read tool, feeds one
bounded result into one follow-up model turn, and publishes only the admitted final answer.

## Learning objectives

After this unit, you should be able to:

- trace ownership across model, registry, native tool, and follow-up request;
- distinguish a tool's semantic error from a provider transport status;
- explain cancellation around bounded synchronous work;
- build immutable stateless call/result replay; and
- aggregate usage without persisting partial turns.

## Why this unit matters

Function calling is a protocol: the model proposes, the application validates and executes, and the
result returns in another request. A two-turn slice exposes every trust boundary before a loop hides
the sequence inside iteration.

## Junior engineer foundation

Synchronous Python code cannot be cancelled halfway through an instruction. The harness checks
before and after bounded work, then discards a result if cancellation won while it ran.

```text
check -> bounded sync tool -> check again -> admit or discard result
```

A common misconception is that returning an error result means the provider request failed. Tool
success/error is model-facing JSON; the provider transport completed normally in both cases.

## Key concepts

- **Dispatch:** invoke the registered implementation after validation.
- **Safe envelope:** fixed compact JSON containing validated result or fixed error.
- **Full replay:** resend original history plus call/result in exact order.
- **Late result:** work that returns after cancellation/deadline selected another outcome.
- **Aggregate usage:** checked sum persisted once after successful final text.

## Architecture and design

```text
Ink TUI                Python harness                              Provider
 final text <--- publish accepted turn <---------------------- turn 2 final
                       ^                                      /
                       | full input + call + result + opaque
                 CAH-034 two-turn owner
                       |
          lookup -> parse -> validate -> dispatch -> render JSON
                       |                          |
                 CAH-031 registry          native read tool

Evidence: existing transcript-v3 session usage aggregate only; no per-call/content record
```

The first call is already atomic from CAH-033. Unknown or invalid input becomes an exact error JSON
result; a programmer defect fails the session. No third turn exists in this teaching slice.

## Practical walkthrough

1. Build the exact four-tool catalog before provider work.
2. Admit the first response; charge its one call before lookup/parsing.
3. Validate and run one bounded synchronous native tool.
4. Render exact compact success/error JSON and build the matching result.
5. Replay context, definitions, optional opaque state, call, and result into turn two.
6. Admit final text, publish its chunks, then persist one checked usage aggregate.

## Implementation code samples

### Planned pseudocode: ordered dispatch

```python
descriptor = registry.lookup(call.name)
arguments = descriptor.input_model.model_validate_json_object(call.arguments_json)
check_cancel_and_deadline()
native_result = registry.dispatch(descriptor, arguments)
check_cancel_and_deadline()
result = render_compact_envelope(native_result)
```

Every failed line prevents the following line. A late native result is discarded after the second
check.

### Planned pseudocode: one follow-up

```python
history = (*original_history, call, result)
final_turn = await collect_one_turn(provider.start(request.with_history(history)))
require_final_text(final_turn)
```

The code is intentionally not a `while` loop.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| malformed/non-object JSON | exact `invalid_read_tool_input` envelope | zero native calls |
| unknown name | exact `unknown_read_tool` envelope | fixed message only |
| missing file | exact repository error envelope | no OS/path leak |
| cancellation during sync tool | late return discarded | no turn two start |
| turn two calls again | `tool_call_limit_exceeded` | zero third starts |
| usage sum overflows | session failure | no aggregate persisted |

## Production expansion

### Example enterprise scenario

A production registry may combine local and remote tools. It still needs application-owned input
validation, result envelopes, deadlines, idempotency, and audit policy for every executor.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  standardizes call/result exchange; schema/version maintenance costs remain local.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) can provide
  remote discovery/execution; authentication, network failure, and trust add cost.
- [Pydantic](https://docs.pydantic.dev/latest/) provides typed validation; schema discipline and
  upgrades require maintenance.
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) improves portability; common-subset
  constraints reduce expressiveness.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Calls | exactly one | bounded repeated/parallel scheduling |
| Executor | local synchronous reads | local/remote async executors |
| Errors | closed fixed JSON | versioned capability error taxonomy |
| Evidence | one session aggregate | governed per-call traces |
| Cost | simple and reviewable | availability, auth, idempotency operations |

### Trade-offs and graduation signals

One call is artificial but makes ownership auditable. Generalize only after exact validation,
late-result handling, replay, and aggregate evidence pass adversarial tests.

## Practical exercises

1. Trace malformed arguments and name every stage that must not run.
2. Explain why a tool error still uses a completed function-output transport item.
3. Design a fake synchronous tool whose result must be discarded after cancellation.
4. Teach back why usage is persisted only after accepted final text.

## Key takeaways

- The model proposes; the harness validates, dispatches, and decides continuation.
- Safe JSON errors let the model explain bounded failures without exposing internals.
- Cancellation around synchronous tools is cooperative at explicit before/after boundaries.

## Glossary

- **Semantic status:** tool success/error meaning inside the result payload.
- **Transport status:** provider lifecycle state for delivering that payload.
- **Non-preemptive:** cannot be interrupted mid-execution by task cancellation.
- **Replay:** reconstructed ordered input sent in a stateless follow-up.

## Further reading

- [CAH-034 delivery contract](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Pydantic](https://docs.pydantic.dev/latest/)
