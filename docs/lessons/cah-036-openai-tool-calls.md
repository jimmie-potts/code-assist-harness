# CAH-036 lesson: Map OpenAI Responses tool calls

- **Unit:** CAH-036
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; the OpenAI adapter remains text-only
- **Story:** [CAH-036](../../user-stories/cah-036-map-openai-tool-calls.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Strict SDK translation, full stateless replay of canonical reasoning-item envelopes,
  explicit repository egress, and adapter-versus-loop ownership
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Architecture](../architecture.md), [Agent loop](../agent-loop.md), and
  [Safety model](../safety-model.md)

> This lesson describes planned mapping. SDK-shaped pseudocode is not implementation evidence.

## Quick summary

CAH-036 maps the proven neutral loop to OpenAI Responses local function calling. Every request is a
complete stateless replay, including every stored reasoning-item field and its exact input projection,
and explicitly asks the API to return encrypted reasoning for later replay. Every response must match
one exact message-or-call grammar before the loop sees it.

## Learning objectives

After this unit, you should be able to:

- map neutral definitions/calls/results without leaking SDK types into core;
- explain why `store=false` requires complete ordered replay;
- preserve a complete reasoning replay item without letting core interpret or record it;
- separate tool semantic status from SDK lifecycle status; and
- identify the consent and warning around repository-content egress.

## Why this unit matters

An SDK event stream is a provider transport, not the agent loop. Strict translation lets the harness
retain history, tool policy, admission, and continuation decisions while still using provider-native
function-call syntax.

## Junior engineer foundation

Stateless means the next request supplies all state the model needs. That includes opaque reasoning
output items, not just visible messages and tool calls. With `store=false`, the request also has to ask
for the replay payload: every turn sets exactly `include=["reasoning.encrypted_content"]`. Applying it
only after the first tool call is too late—the initial response would not be guaranteed to contain the
encrypted content needed to construct turn two.

```text
turn 1 output: [complete reasoning item, function call]
turn 2 input:  [...original input, complete reasoning item, function call, function output]
```

`reasoning.context="current_turn"` does not make it safe to drop replayed output items. A common
misconception is also that `parallel_tool_calls=false` validates output count; the adapter still must.

## Key concepts

- **Stateless replay:** send complete locally owned ordered history every turn.
- **Replay-payload selection:** request `reasoning.encrypted_content` on every turn, including turn one.
- **Opaque reasoning envelope:** canonical full replay item preserved by core, parsed only by adapter.
- **Strict adapter grammar:** `[reasoning?, function_call]` or `[reasoning?, message]` only.
- **Egress consent:** explicit OpenAI selection authorizes bounded admitted repository content.
- **Semantic result:** compact function-output JSON interpreted by the model, not SDK lifecycle.

## Architecture and design

```text
Ink TUI              Python harness domain                     OpenAI Responses
 final only <---- CAH-035 loop/policy
                         ^                                      ^       |
                         | atomic final/call                    |       v
                    CAH-033 admission <--- CAH-036 strict SDK mapper
                         ^                  full replay: context + calls/results
                         |                  + every full opaque reasoning envelope
                  local read registry

Request: store=false, parallel_tool_calls=false,
         include=["reasoning.encrypted_content"], no previous_response_id
Egress: explicit OpenAI selection; bounded source may leave host; no content secret scan
Evidence: no SDK payload, source content, arguments/results, or reasoning envelope
```

The adapter accepts exactly one optional reasoning item first and then one function call or assistant
message. All streamed IDs, indices, fragments, done values, statuses, usage, and snapshots reconcile
before CAH-033 exposes an atomic outcome.

## Practical walkthrough

1. Map selected instructions and explicitly untrusted repository evidence.
2. Map strict local function definitions and complete neutral history.
3. Set stateless/sequential options, request encrypted reasoning replay, and omit continuation IDs.
4. Reconcile exactly one of the two legal output-item sequences.
5. Canonicalize the complete reasoning replay item into one bounded opaque neutral value.
6. Return atomic neutral output; let CAH-035 decide dispatch or completion.

## Implementation code samples

### Planned pseudocode: stateless request

```python
sdk_request = {
    "input": map_all_items(request),
    "tools": map_strict_functions(request.tools),
    "store": False,
    "parallel_tool_calls": False,
    "include": ["reasoning.encrypted_content"],
    "reasoning": {"effort": "none", "context": "current_turn"},
}
```

The exact one-element `include` appears unchanged on every request, not only follow-up turns.
`map_all_items` reconstructs every prior reasoning item's ID, empty summary, encrypted content,
completed status, and type from its canonical opaque envelope. An empty output content list remains
empty; a null output content value becomes an omitted input key because that input field is optional
but non-nullable. It then preserves each call and function output. There is no `previous_response_id`.

### Planned pseudocode: semantic result

```python
item = FunctionCallOutput(call_id=result.call_id, output=result.output_json)
```

`result.output_json` already contains exact compact success/error JSON. Any SDK lifecycle status is one
fixed transport value, never a policy decision.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| message plus function call | invalid response | no neutral value escapes |
| two calls despite parallel=false | invalid response | output-count mutation |
| encrypted-content include missing on any turn | outbound contract failure | turn-one-through-four snapshots |
| reasoning item omitted on replay | request mismatch | exact turn-two snapshot |
| full reasoning envelope exceeds bound | invalid response | safe redacted representation |
| result error mapped to SDK failure | mapping test fails | fixed transport status |
| source content sentinel excluded | sentinel absent | request snapshot |

## Production expansion

### Example enterprise scenario

A production provider layer may use stored Responses, multiple models, and remote tools. It needs
retention/deletion policy, compatibility tests, failover semantics, and egress governance.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  defines local function exchange; schema and result validation stay application-owned.
- [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning) explains reasoning
  items and continuation; replay, retention, and cost require deliberate policy.
- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
  lowers latency; strict event reconciliation and cleanup add complexity.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) enable remote
  tool catalogs; trust, auth, network, and catalog-change operations add cost.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| State | full local replay | reviewed stored continuation |
| Output | one message or call | versioned richer item grammar |
| Tools | local strict functions | governed hosted/MCP catalogs |
| Egress | explicit provider choice | organizational DLP/approval policy |
| Cost | repeated input bytes | retention, migration, remote operations |

### Trade-offs and graduation signals

Full replay costs input but keeps the harness authoritative. Consider stored continuation only after
retention/recovery/deletion semantics exist. Add content scanning only as a separately evaluated
security control; do not imply path policy already scans file contents.

## Practical exercises

1. Write the exact turn-two order after a reasoning item and call.
2. Explain why the encrypted-content include must be present before the first response.
3. Explain why `current_turn` does not authorize dropping prior opaque output.
4. Show why tool-error JSON still uses a completed transport item.
5. Teach back what explicit OpenAI selection authorizes and what it does not protect.

## Key takeaways

- The adapter translates; the harness admits, dispatches, and continues.
- Every stateless request asks for `reasoning.encrypted_content`; otherwise later full replay is not
  guaranteed to be constructible.
- Stateless replay preserves every required reasoning field in order and handles optional content by
  one exact, tested null-to-omitted mapping.
- Explicit provider selection permits bounded egress, but M2 does not scan admitted content for secrets.

## Glossary

- **SDK lifecycle status:** transport progress/completion, not tool semantics.
- **Opaque replay:** preserving provider state without reading its contents.
- **Repository egress:** source-derived content leaving the local host.
- **DLP:** controls that detect or prevent sensitive-data disclosure; deferred here.

## Further reading

- [CAH-036 delivery contract](../../user-stories/cah-036-map-openai-tool-calls.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
