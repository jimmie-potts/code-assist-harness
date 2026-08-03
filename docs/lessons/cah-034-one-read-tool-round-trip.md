# CAH-034 lesson: Run one read-tool round trip

- **Unit:** CAH-034
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; the harness still rejects tool requests
- **Story:** [CAH-034](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** One observe-validate-dispatch-enrich-result-follow-up sequence, scoped
  instructions, exact safe envelopes, non-preemptive tool cancellation boundaries, and one
  aggregate usage record
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Tool system](../tool-system.md), and
  [Context engineering](../context-engineering.md)

> This lesson describes planned behavior. Pseudocode is not evidence of an implemented round trip.

## Quick summary

CAH-034 takes one atomically admitted call, validates and executes one native read tool, atomically
refreshes instructions for its successful requested path, feeds one bounded result and the resulting
context into one follow-up model turn, and publishes only the admitted final answer.

## Learning objectives

After this unit, you should be able to:

- trace ownership across model, registry, native tool, and follow-up request;
- explain why a successful requested path can add instructions while returned paths cannot;
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

Repository instructions are scoped control-plane input. The first turn sees root instructions. Once
a successful call validates a narrower requested path, the harness—not the model result—discovers the
applicable ancestor chain and replaces the context snapshot atomically.

## Key concepts

- **Dispatch:** invoke the registered implementation after validation.
- **Safe envelope:** fixed compact JSON containing validated result or fixed error.
- **Full replay:** resend original history plus `continuation? -> call -> result` in exact order.
- **Target scope:** the validated request `path` from one successful native read.
- **Atomic enrichment:** replace the whole immutable context snapshot or keep the prior one.
- **Late result:** work that returns after cancellation/deadline selected another outcome.
- **Aggregate usage:** checked sum persisted once after successful final text.

## Architecture and design

```text
Ink TUI                Python harness                              Provider
 final text <--- publish accepted turn <---------------------- turn 2 final
                       ^                                      /
                       | enriched context + [opaque? -> call -> result]
                 CAH-034 two-turn owner
                       |
 lookup -> decode -> key gate -> Pydantic -> dispatch/render -> check
                       |                          |                |
                 CAH-031 registry          native read tool       v
                                           CAH-025 discover -> check
                                                               |
                                           CAH-030 merge candidate -> check
                                                               |
                                           commit history/context -> pre-start check

Evidence: existing transcript-v3 session usage aggregate only; no per-call/content record
```

The first call is already atomic from CAH-033. Unknown or invalid input becomes an exact error JSON
result and keeps the initial context; a programmer defect or discovery/merge failure fails the
session. No third turn exists in this teaching slice.

## Practical walkthrough

1. Build the exact four-tool catalog before provider work.
2. Admit the first response; charge its one call before lookup/decoding.
3. Validate and run one bounded synchronous native tool.
4. Render exact compact success/error JSON and run the post-dispatch cancellation/deadline check.
5. On success, take CAH-031's validated request `path`, discover its instruction chain through
   CAH-025, check cancellation/deadline, atomically merge it through CAH-030, and check again. On a
   known tool error, keep the initial context.
6. Only after those guards, commit the selected context plus optional opaque state, call, and result
   to the one history tuple in that exact order; run the pre-start guard and replay turn two with
   unchanged definitions.
7. Admit final text, publish its chunks, then persist one checked usage aggregate.

## Implementation code samples

### Planned pseudocode: ordered dispatch

```python
descriptor = registry.lookup(call.name)
decoded = decode_json_object(call.arguments_json)
require_provider_tool_argument_keys(definition, decoded)
arguments = descriptor.input_model.model_validate(decoded)
check_cancel_and_deadline()
dispatch = registry.dispatch(descriptor, arguments)
check_cancel_and_deadline()
if dispatch.succeeded:
    discovered = instructions.discover(dispatch.target_scope)
    check_cancel_and_deadline()
    candidate_context = context_builder.merge_atomically(context, discovered)
    check_cancel_and_deadline()
    context = candidate_context
result = ProviderToolResult(output_json=dispatch.output_json)
```

The CAH-032 key gate rejects omitted model-facing fields—even when the unchanged native model has a
default—and additional fields before Pydantic runs. Every failed line prevents the following line.
A late native result is discarded after the second check. Discovery and merge each have their own
post-return guard because they are also bounded synchronous operations. The candidate context and
pending result become history only after every guard, so cancellation yields no observable change.

### Planned pseudocode: one follow-up

```python
turn_items = (opaque, call, result) if opaque is not None else (call, result)
history = (*original_history, *turn_items)
follow_up = request.with_context(context).with_history(history)
check_cancel_and_deadline()
final_turn = await collect_one_turn(provider.start(follow_up))
require_final_text(final_turn)
```

The code is intentionally not a `while` loop. `opaque` is the CAH-032 positional history item, not a
separate request field.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| malformed/non-object JSON | exact `invalid_read_tool_input` envelope | zero native calls |
| omitted defaulted model key | exact `invalid_read_tool_input` envelope | zero Pydantic/dispatch calls |
| unknown name | exact `unknown_read_tool` envelope | fixed message only |
| missing file | exact repository error envelope | no OS/path leak |
| cancellation during sync tool | late return discarded | no turn two start |
| cancellation during discovery/merge | late bundle/package discarded | no result/context commit |
| instruction discovery/merge fails | safe session failure | no result/context publication or turn two |
| broad list/search returns nested paths | no inferred scope | only the requested path may enrich |
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
4. Explain why `list_files` returning `pkg/file.py` cannot load `pkg/AGENTS.md` until a successful
   path-targeting call requests that path.
5. Teach back why usage is persisted only after accepted final text.

## Key takeaways

- The model proposes; the harness validates, dispatches, and decides continuation.
- Successful requested paths refresh applicable instructions atomically before continuation;
  model-returned paths have no such authority.
- Safe JSON errors let the model explain bounded failures without exposing internals.
- Cancellation around synchronous tools is cooperative at explicit before/after boundaries.

## Glossary

- **Semantic status:** tool success/error meaning inside the result payload.
- **Transport status:** provider lifecycle state for delivering that payload.
- **Non-preemptive:** cannot be interrupted mid-execution by task cancellation.
- **Replay:** reconstructed ordered input sent in a stateless follow-up.
- **Context snapshot:** one immutable, fully validated context package used by a provider request.

## Further reading

- [CAH-034 delivery contract](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Pydantic](https://docs.pydantic.dev/latest/)
