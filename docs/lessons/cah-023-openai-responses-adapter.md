# CAH-023 lesson: Add the OpenAI Responses adapter

- **Unit:** CAH-023
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done
- **Story:** [CAH-023](../../user-stories/cah-023-add-openai-responses-adapter.md)
- **Visual companion:** [OpenAI Responses adapter](assets/cah-023-openai-responses-adapter.pptx)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Safety model](../safety-model.md)

> This lesson describes the implemented CAH-023 boundary and the deterministic evidence used to
> verify it. The live provider smoke remains optional and was not used as completion evidence.

## Quick summary

CAH-023 puts one strict Luna Responses adapter behind the provider-neutral turn. It teaches the
central harness rule: the SDK may transport model observations, but the harness still owns
configuration admission, loop limits, cancellation, terminal truth, and evidence.

## Learning objectives

After completing this unit, you should be able to:

- locate the adapter inside the TUI-to-provider system;
- explain why an SDK stream is untrusted input;
- trace one text delta from Responses into the harness;
- distinguish operation closure from resource cleanup; and
- explain why deterministic fakes, not a live request, are the default proof.

## Why this unit matters

CAH-020 defined the provider port, CAH-021 consumed one provider turn, and CAH-022 bounded that turn.
CAH-023 proves a real vendor can enter through that seam without taking ownership of the loop. This
keeps later model, tool, and provider changes from rewriting session orchestration.

## Junior engineer foundation

An **adapter** knows two interfaces and translates between them. Here it knows the OpenAI SDK shape
and the repository-owned `ProviderStreamEvent` shape. No other core module needs SDK types.

Server-sent events arrive over time. Arrival does not make them valid: an event can be duplicated,
out of order, refer to another response, or contain an unsupported tool item. The adapter therefore
uses a state machine before emitting a harness event.

A common misconception is that cancelling the task that is waiting for cleanup also cancels cleanup
itself. CAH-023 creates one shared cleanup owner and shields it from its joiners. A cancelled joiner
remains cancellation control flow; it does not rewrite resource truth.

## Key concepts

- **Composition root:** validates provider, model, and environment before importing the SDK.
- **Closed automaton:** accepts only the exact event sequence the harness knows how to interpret.
- **Opaque reasoning envelope:** structural Luna output that is validated but never exposed as model
  reasoning, transcript evidence, or a harness event.
- **Provider-neutral event:** a small domain value such as `ProviderTextDelta`; never an SDK object.
- **Terminal pending:** cleanup has settled, but usage/completion has not all crossed the port yet.
- **Fail closed:** unsupported observations become a fixed safe failure rather than guessed behavior.

## Architecture and design

```text
User flags + explicit dev.env reader
   |
   v
TypeScript TUI launcher ---- NDJSON UI commands/events ---- Python runtime
   |                                                     composition root
   |                                                            |
   |                                                            v
   |                          CAH-021 session + CAH-022 limits/terminal guard
   |                                                            |
   |                                                            v
   |                         Provider port <== [CAH-023 Luna adapter] ==> Responses API
   |                                              |                         (untrusted SSE)
   |                                              +--> strict automaton + owned cleanup
   |
   +-- provider/model are child arguments, not protocol fields

Evidence boundary: validated provider events -> session events -> transcript/replay
Tool boundary: unavailable here; this text-only request declares no tool schema
```

The feature is deliberately narrow. The TUI forwards an explicit provider/model pair; Python
validates it again. Only then does the composition root import the adapter. The adapter maps one
foreground request, validates the stream, and returns repository-owned observations. `ProviderSession`
still decides completion and enforces limits.

Three invariants hold the boundary together:

1. **Configuration before capability.** Mock remains the default. OpenAI requires the exact allowlisted
   Luna model and a locally valid `OPENAI_API_KEY`; other `OPENAI_*` variables are rejected before SDK
   import or client construction.
2. **Validation before meaning.** Sequence, response identity, item identity, indices, text snapshots,
   model, and usage must reconcile before completion is trusted.
3. **Cleanup before terminal release.** A natural terminal is buffered until stream and client close
   have both been attempted. Cancellation and natural completion share the same cleanup task.

The request sets `stream=True`, `background=False`, `store=False`, reasoning effort `none`, reasoning
context `current_turn`, and a generated-token cap of 8,192. It omits tools, disables SDK retries,
rejects redirects and ambient proxy routing, and fixes the official API endpoint. Luna may still
send one opaque empty reasoning item before its message; the adapter validates its identity and
placement while deliberately ignoring encrypted content. Local transcript opt-out and provider
storage are separate controls.

## Practical walkthrough

1. Start at the TUI provider configuration and follow the shell-free child arguments into
   `runtime.py`.
2. Observe that SDK-free validation completes before `_create_openai_provider()` imports the
   concrete adapter.
3. Follow `_map_request()` into the async create call. `Provider.start()` itself performs no I/O.
4. Step through `_ResponsesAutomaton.accept()`: structural events change adapter state, text events
   cross the port, and the terminal is buffered for cleanup.
5. Read the cancellation tests beside the operation state machine. They prove blocked create/read,
   terminal-pending, cleanup failure, and cancelled-joiner behavior without HTTP.

## Implementation code samples

### Important path: exact request mapping

From [`openai_responses.py`](../../src/code_assist_harness/provider/openai_responses.py):

```python
mapped: dict[str, object] = {
    "model": model,
    "input": [
        {"role": message.role, "content": message.content}
        for message in request.conversation
    ],
    "reasoning": {"effort": "none", "context": "current_turn"},
    "max_output_tokens": OPENAI_MAX_OUTPUT_TOKENS,
    "stream": True,
    "background": False,
    "store": False,
}
```

The list comprehension preserves conversation order one message at a time. The reasoning settings
stop Luna from inheriting broader defaults, while the token cap bounds hidden as well as visible
generation. The three booleans lock this unit to a foreground, streamed, non-stateful request. There
is intentionally no `tools` or `tool_choice` key because the provider port cannot yet declare a tool
contract.

### Important path: validate before emitting

From [`openai_responses.py`](../../src/code_assist_harness/provider/openai_responses.py):

```python
def _text_delta(self, event: object) -> tuple[ProviderStreamEvent, ...]:
    if self._state not in {"delta", "delta_or_done"}:
        raise InvalidSDKObservation
    self._require_item_coordinates(event)
    _require_absent_or_empty_list(_optional_field(event, "logprobs"))
    delta = _required_string(_field(event, "delta"))
    self._text_fragments.append(delta)
    self._state = "delta_or_done"
    return (ProviderTextDelta(delta),)
```

The state check rejects a delta outside the open text phase; the automaton's global sequence check
rejects repeated sequence numbers. Coordinate checks bind the delta to the expected message and
content part. Only the validated string becomes a provider-neutral event; the SDK event never leaves
this module.

### Failure path: cancellation owns blocked work

From [`test_openai_responses.py`](../../tests/provider/test_openai_responses.py):

```python
def test_cancellation_interrupts_pending_create_and_closes_client() -> None:
    async def scenario():
        gate = asyncio.Event()
        stream = _FakeStream(_success_events())
        provider, responses, client, _created = _provider_with(stream, create_gate=gate)
        operation = provider.start(_request())
        iterator = operation.events()
        pending = asyncio.create_task(anext(iterator))
        await responses.started.wait()
        result = await operation.cancel()
        with pytest.raises(StopAsyncIteration):
            await pending
        return result, responses, client, stream

    result, responses, client, stream = asyncio.run(scenario())

    assert result == "cancelled"
    assert responses.cancelled.is_set()
    assert stream.close_calls == 0
    assert client.close_calls == 1
```

The fake holds `responses.create()` open. Cancellation interrupts that owned task, joins cleanup, and
proves the iterator cannot later manufacture an event. The assertions test the harness contract,
not timing against a network service.

## Failure scenarios to study

| Scenario | Responsible boundary | Safe result | Evidence |
| --- | --- | --- | --- |
| Unsupported model or ambient SDK routing | Composition root | Fixed startup error before SDK import | configuration and runtime tests |
| Out-of-order, mismatched, tool, or reasoning-text event | Adapter automaton | `invalid_response`; no raw payload | parameterized malformed-stream tests |
| Provider exception after partial text | Adapter failure table | One fixed provider failure | closed-table exception tests |
| Cancellation during create or next event | Operation lifecycle | owned task reaped; no later event | blocked-create/read tests |
| Stream or client close fails | Cleanup owner | completion replaced or prior failure preserved; bounded cleanup error | close-failure matrix |

## Production expansion

### Example enterprise scenario

A multi-tenant service may route by region, rotate credentials, apply per-tenant data rules, and
canary SDK/model upgrades. Those controls surround this adapter seam; they should not move terminal
authority into the SDK.

### Typical production capabilities and tools

- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses):
  typed event transport and stream handling.
- [OpenAI Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness):
  request-level state controls.
- [OpenAI Python SDK](https://github.com/openai/openai-python): async client and typed API surface.
- [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/): a possible
  telemetry vocabulary, with added privacy and operations work.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Routing | One explicit provider and Luna model | regions, projects, canaries, failover |
| Reliability | one bounded foreground stream | SLOs, reconnect or background workflows |
| Credentials | ignored mode-`0600` plaintext `dev.env`, explicitly injected into the process environment | managed identity, rotation, audit |
| Evidence | deterministic fakes plus optional smoke | conformance, load, and fault injection |
| Cost | low setup and cognitive load | governance services and on-call ownership |

### Trade-offs and graduation signals

The strict subset is easy to reason about but intentionally rejects new model output shapes. Its
opaque reasoning envelope is structural compatibility, not permission to expose chain-of-thought. Expand
only when observed needs justify the extra states: sustained disconnects may justify resumable
background work; multiple production routes may justify routing policy; a new model requires stream
conformance evidence before allowlisting.

## Practical exercises

1. Point to the first line where an SDK value becomes a harness value.
2. Mutate one response identity in the success fixture and predict the normalized result.
3. Explain why `wait_closed()` cannot return between usage and completion.
4. Run the adapter tests and identify which ones prove “no HTTP by default.”

## Key takeaways

- The adapter owns vendor translation; the harness owns agent-loop truth.
- Every external observation is validated before it gains domain meaning.
- Strict local evidence is cheap and deterministic; broader production capability adds operational
  ownership as well as resilience.

## Glossary

- **Adapter:** translator between a vendor interface and a repository-owned port.
- **Automaton:** state machine that accepts only legal event transitions.
- **Foreground stream:** request whose work follows the active connection.
- **Opaque reasoning envelope:** a validated structural item whose encrypted payload is ignored.
- **Terminal pending:** cleanup is settled while final domain observations remain buffered.
- **SSE:** server-sent events delivered incrementally over one HTTP response.

See the shared [project glossary](../glossary.md) for provider, model turn, usage, and transcript.

## Further reading

- [CAH-023 delivery contract](../../user-stories/cah-023-add-openai-responses-adapter.md)
- [CAH-021 provider-neutral turn](cah-021-one-model-turn.md)
- [CAH-022 hard loop limits](cah-022-loop-limits.md)
- [Agent loop](../agent-loop.md) and [Safety model](../safety-model.md)
- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [GPT-5.6 reasoning parameters](https://developers.openai.com/api/docs/guides/latest-model#update-api-and-model-parameters)
