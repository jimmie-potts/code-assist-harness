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
- explain why cancellation around bounded synchronous work requires an event-loop yield before its
  state guard;
- build immutable stateless call/result replay; and
- aggregate usage without persisting partial turns.

## Why this unit matters

Function calling is a protocol: the model proposes, the application validates and executes, and the
result returns in another request. A two-turn slice exposes every trust boundary before a loop hides
the sequence inside iteration.

## Junior engineer foundation

Synchronous Python code cannot be cancelled halfway through an instruction. A cancel command also
cannot update session state while that code holds the event-loop thread. The harness therefore
yields once before each state guard, then discards a candidate if cancellation won while bounded
work ran.

```text
yield -> guard -> bounded sync tool -> yield -> guard -> admit or discard candidate
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
 lookup -> decode -> key gate -> Pydantic -> yield/guard -> dispatch -> yield/guard
                       |                                         |
                 CAH-031 registry                         local candidate
                                                               v
                         CAH-025 discover -> yield/guard -> CAH-030 merge -> yield/guard
                                                               |
                                      build local history/context/request candidate
                                                               |
                                              yield/guard -> model admission -> commit/start

Evidence: existing transcript-v3 session usage aggregate only; no per-call/content record
```

The first call is already atomic from CAH-033. Unknown or invalid input becomes an exact error JSON
result and keeps the initial context; a programmer defect or discovery/merge failure fails the
session. No third turn exists in this teaching slice.

## Practical walkthrough

1. Build the exact four-tool catalog before provider work.
2. Admit the first response; charge its one call before lookup/decoding.
3. Validate and run one bounded synchronous native tool.
4. Render exact compact success/error JSON and run the cooperative post-dispatch checkpoint: yield
   to the event loop, then apply the cancellation/deadline guard.
5. On success, take CAH-031's validated request `path`, discover its instruction chain through
   CAH-025, check cancellation/deadline, atomically merge it through CAH-030, and check again. On a
   known tool error, keep the initial context.
6. Build the selected context, optional opaque state, call, result, history, and bounded follow-up
   request as local candidates. Yield and guard at `before_provider_start`, admit the model start,
   then commit and replay turn two with unchanged definitions.
7. Admit final text, publish its chunks, then persist one checked usage aggregate.

## Implementation code samples

### Planned pseudocode: reusable cooperative checkpoint

```python
async def cooperate_then_guard(checkpoint):
    await asyncio.sleep(0)  # no harness lock is held
    if checkpoint_observer is not None:  # deterministic tests only
        await checkpoint_observer(checkpoint)
    check_cancel_and_deadline()  # preserve the established winner precedence
```

CAH-034 owns this one seam; CAH-035 calls it rather than wrapping or copying it. An
`asyncio.Event`-backed observer can pause a named checkpoint while a test admits a cancel command,
without relying on elapsed time. Production installs no observer.

The critical yield regression does **not** install that awaited observer, because the observer could
hide a missing production yield. It queues a same-loop cancellation task, calls the production-mode
seam with `checkpoint_observer=None`, and lets a synchronous guard spy assert that cancellation ran
before guard entry. Removing `await asyncio.sleep(0)` makes that deterministic test fail. Injected
clocks separately lock the existing winner when cancellation and deadline coincide.

### Planned pseudocode: ordered dispatch

```python
descriptor = registry.lookup(call.name)
decoded = decode_json_object(call.arguments_json)
require_provider_tool_argument_keys(definition, decoded)
arguments = descriptor.input_model.model_validate(decoded)
await cooperate_then_guard("before_dispatch")
dispatch_candidate = registry.dispatch(descriptor, arguments)
await cooperate_then_guard("after_dispatch")
if dispatch_candidate.succeeded:
    discovered_candidate = instructions.discover(dispatch_candidate.target_scope)
    await cooperate_then_guard("after_discovery")
    context_candidate = context_builder.merge_atomically(context, discovered_candidate)
    await cooperate_then_guard("after_merge")
else:
    context_candidate = context
result_candidate = ProviderToolResult(output_json=dispatch_candidate.output_json)
```

The CAH-032 key gate rejects omitted model-facing fields—even when the unchanged native model has a
default—and additional fields before Pydantic runs. Every failed line prevents the following line.
A late native result is discarded after the second checkpoint. Discovery and merge each have their
own post-return checkpoint because they are also bounded synchronous operations. Every checkpoint
unconditionally `await asyncio.sleep(0)` outside locks, optionally invokes an injected deterministic
test gate, then applies the existing guard. That order lets a queued cancel command update state
before it is read. The candidate context and pending result remain local, so cancellation yields no
observable change.

### Planned pseudocode: one follow-up

```python
turn_items = (
    (opaque, call, result_candidate)
    if opaque is not None
    else (call, result_candidate)
)
history_candidate = (*original_history, *turn_items)
request_candidate = build_bounded_request(context_candidate, history_candidate)
await cooperate_then_guard("before_provider_start")
ledger.admit_model_start()
context, history = context_candidate, history_candidate
final_turn = await collect_one_turn(provider.start(request_candidate))
require_final_text(final_turn)
```

The code is intentionally not a `while` loop. `opaque` is the CAH-032 positional history item, not a
separate request field.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| malformed/non-object JSON | exact `invalid_read_tool_input` envelope | zero native calls |
| omitted defaulted model key | exact `invalid_read_tool_input` envelope | zero Pydantic/dispatch calls |
| production yield removed | queued cancellation is not latched | no-hook guard spy fails before dispatch |
| unknown name | exact `unknown_read_tool` envelope | fixed message only |
| missing file | exact repository error envelope | no OS/path leak |
| cancellation during sync tool | `after_dispatch` yields before guarding | no turn two start |
| cancellation during discovery/merge | following checkpoint yields before guarding | no result/context commit |
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
3. Design the no-observer queued-cancel test that fails if production's unconditional yield is
   removed; explain why an awaited Event gate alone cannot prove this.
4. Design a fake synchronous tool and named `asyncio.Event` gate that proves its result is discarded
   after a queued cancel command without using elapsed sleeps.
5. Explain why `list_files` returning `pkg/file.py` cannot load `pkg/AGENTS.md` until a successful
   path-targeting call requests that path.
6. Teach back why usage is persisted only after accepted final text.

## Key takeaways

- The model proposes; the harness validates, dispatches, and decides continuation.
- Successful requested paths refresh applicable instructions atomically before continuation;
  model-returned paths have no such authority.
- Safe JSON errors let the model explain bounded failures without exposing internals.
- Cancellation around synchronous tools is cooperative: each named boundary must yield before it
  reads cancellation/deadline state.

## Glossary

- **Semantic status:** tool success/error meaning inside the result payload.
- **Transport status:** provider lifecycle state for delivering that payload.
- **Non-preemptive:** cannot be interrupted mid-execution by task cancellation.
- **Cooperative checkpoint:** an unconditional event-loop yield, optional deterministic test hook,
  then the established cancellation/deadline guard.
- **Replay:** reconstructed ordered input sent in a stateless follow-up.
- **Context snapshot:** one immutable, fully validated context package used by a provider request.

## Further reading

- [CAH-034 delivery contract](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Pydantic](https://docs.pydantic.dev/latest/)
