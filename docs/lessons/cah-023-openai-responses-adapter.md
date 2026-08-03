# CAH-023 lesson: Add the OpenAI Responses adapter

- **Unit:** CAH-023
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done
- **Story:** [CAH-023](../../user-stories/cah-023-add-openai-responses-adapter.md)
- **Visual companion:** None; the Markdown lesson and compact text diagram are authoritative
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
- distinguish operation closure, resource cleanup failure, and cleanup-task cancellation; and
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
remains cancellation control flow; it does not rewrite resource truth. The exception is the harness's
explicit escalation after the five-second grace: `force_cancel_cleanup()` bypasses the shield and
reaps the real owner so no local provider work survives.

## Key concepts

- **Composition root:** validates provider, model, and environment before importing the SDK.
- **Closed automaton:** accepts only the exact event sequence the harness knows how to interpret.
- **Opaque reasoning envelope:** structural Luna output that is validated but never exposed as model
  reasoning, transcript evidence, or a harness event.
- **Provider-neutral event:** a small domain value such as `ProviderTextDelta`; never an SDK object.
- **Terminal pending:** cleanup has settled, but usage/completion has not all crossed the port yet.
- **Authoritative force-reap:** session-only cleanup escalation that ends local work without claiming
  remote release.
- **Fail closed:** unsupported observations become a fixed safe failure rather than guessed behavior.

## Architecture and design

```text
safe --init -> ignored mode-0600 dev.env -> explicit reader
                                              |
User provider/model flags --------------------+
   |
   v
TypeScript TUI launcher -- validated NDJSON commands/events -- Python runtime
   |                 session task: Unicode scalars only            |
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
   Luna model and a locally valid `OPENAI_API_KEY`; other `OPENAI_*` variables and `SSLKEYLOGFILE` are
   rejected before SDK import or client construction. The normal child also starts Python with `-E`.
2. **Validation before meaning.** Sequence, response identity, item identity, indices, text snapshots,
   message statuses, model, reasoning mode, and usage must reconcile before completion is trusted.
   Completed output tokens cannot exceed the request's fixed 8,192-token cap; an over-cap report
   becomes `invalid_response` before usage or completion crosses the port.
   A `session.start` task must contain only Unicode scalar values at both wire schemas, so a JSON lone
   surrogate cannot reach provider-session construction.
   Assistant text admits TAB/LF layout but rejects every other C0/C1 terminal control before it can
   become a provider-neutral event.
3. **Cleanup before terminal release.** A natural terminal is buffered until stream and client close
   have both been attempted. Cancellation and natural completion share the same cleanup task; an
   independently raised close-time `CancelledError` is failure evidence, not owner cancellation.
   Ordinary joiners shield the owner. If the harness grace expires, it cancels/reaps its barrier and
   invokes authoritative force-reap; genuine owner cancellation stops later sequential closes.

The same distinction applies before cleanup: if an SDK create or stream-read awaitable independently
raises `CancelledError`, the adapter emits a bounded provider failure and still closes every resource
it acquired. Only harness-selected cancellation ends the event stream silently.

The request sets `stream=True`, `background=False`, `store=False`, reasoning effort `none`, reasoning
context `current_turn`, and a generated-token cap of 8,192. It omits tools, disables SDK retries,
rejects redirects and ambient proxy routing, and fixes the official API endpoint. Luna may still
send one opaque empty reasoning item before its message; the adapter validates its identity and
placement while deliberately ignoring encrypted content. The message must move from `in_progress`
to `completed`, and the final response must echo `none`/`current_turn`. Local transcript opt-out and
provider storage are separate controls.

## Practical walkthrough

1. Start at the TUI provider configuration and follow the shell-free child arguments into
   `runtime.py`.
2. Observe that the launcher removes TLS key logging, starts Python with `-E`, and completes SDK-free
   validation before `_create_openai_provider()` imports the concrete adapter.
3. Follow `_map_request()` into the async create call. `Provider.start()` itself performs no I/O.
4. Step through `_ResponsesAutomaton.accept()`: structural events change adapter state, text events
   cross the port, and the terminal is buffered for cleanup.
5. Read the cancellation tests beside the operation state machine. They prove blocked create/read,
   terminal-pending, cleanup failure, cancelled-joiner behavior, and force-reap at all three pending
   resource stages without HTTP.

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
    try:
        delta = _require_terminal_safe_text(_field(event, "delta"), "OpenAI text delta")
    except (TypeError, ValueError):
        raise InvalidSDKObservation from None
    observation = ProviderTextDelta(delta)
    self._text_fragments.append(observation.text)
    self._state = "delta_or_done"
    return (observation,)
```

The state check rejects a delta outside the open text phase; the automaton's global sequence check
rejects repeated sequence numbers. Coordinate checks bind the delta to the expected message and
content part. The provider-domain validator rejects unsafe C0/C1 controls before
`ProviderTextDelta` is constructed; the adapter translates that rejection to
`InvalidSDKObservation` before the fragment is retained or emitted. The value constructor repeats
the invariant as defense in depth. Only validated text crosses the port, and the SDK event never
leaves this module.

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
| Non-string/unsupported provider, model, or ambient SDK/TLS logging | Composition root | Fixed startup error before SDK import | configuration and runtime tests |
| Escaped lone surrogate in `session.start.task` | TUI and Python wire schemas | local rejection, or recoverable `invalid_payload`; no session or HTTP | shared fixture and supervisor/runtime tests |
| Out-of-order, mismatched, tool, or reasoning-text event | Adapter automaton | `invalid_response`; no raw payload | parameterized malformed-stream tests |
| OSC, CSI, carriage return, or another unsupported text control | Provider value plus adapter automaton | `invalid_response`; unsafe fragment never reaches protocol/TUI | domain and hostile-delta tests |
| Provider exception after partial text | Adapter failure table | One fixed provider failure | closed-table exception tests |
| Create or stream read independently raises `CancelledError` | Operation lifecycle | fixed provider failure; acquired resources close | hostile SDK-cancellation tests |
| Cancellation during create or next event | Operation lifecycle | owned task reaped; no later event | blocked-create/read tests |
| Stream/client close fails or independently raises `CancelledError` | Cleanup owner | both closes attempted; completion replaced or prior failure preserved; bounded cleanup error | hostile close-failure matrix |
| Cleanup owner exceeds five-second grace | Session plus provider operation | local barrier and real owner reaped; remote release unconfirmed; safe diagnostic | force-reap tests at create/stream/client stages |
| Completed usage reports more than 8,192 output tokens | Adapter automaton | `invalid_response`; no usage or completion observation | exact-cap and over-cap tests |

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
| Credentials | exclusive mode-`0600` plaintext `dev.env` initializer, then explicit process injection | managed identity, rotation, audit |
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
3. Explain why an independent close-time `CancelledError` is cleanup failure but task cancellation of
   the cleanup owner remains control flow.
4. Explain why force-reap can guarantee no local task remains but cannot confirm remote release.
5. Run the adapter tests and identify which ones prove “no HTTP by default.”
6. Compare TAB/LF with carriage return and OSC-52, then explain why rejection preserves the exact
   delta/completion reconciliation rule.

## Key takeaways

- The adapter owns vendor translation; the harness owns agent-loop truth.
- Every external observation is validated before it gains domain meaning.
- Terminal-safe assistant text is a provider-domain and protocol invariant, not a React rendering
  decision.
- Strict local evidence is cheap and deterministic; broader production capability adds operational
  ownership as well as resilience.

## Glossary

- **Adapter:** translator between a vendor interface and a repository-owned port.
- **Automaton:** state machine that accepts only legal event transitions.
- **Foreground stream:** request whose work follows the active connection.
- **Force-reap:** authoritative cancellation and awaiting of all operation-owned local tasks after
  ordinary cleanup exceeds its grace.
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
