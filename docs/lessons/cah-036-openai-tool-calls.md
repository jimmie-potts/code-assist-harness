# CAH-036 lesson: Map OpenAI Responses tool calls

- **Unit:** CAH-036
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; the OpenAI adapter remains text-only
- **Story:** [CAH-036](../../user-stories/cah-036-map-openai-tool-calls.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Strict SDK translation, scoped-instruction serialization, full stateless replay
  of canonical reasoning-item envelopes, explicit repository egress, and adapter-versus-loop
  ownership
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Architecture](../architecture.md), [Agent loop](../agent-loop.md), and
  [Safety model](../safety-model.md)

> This lesson describes planned mapping. SDK-shaped pseudocode is not implementation evidence.

## Quick summary

CAH-036 maps the proven neutral loop to OpenAI Responses local function calling. Every request is a
complete stateless replay, including every stored reasoning-item field and its exact input projection,
and explicitly asks the API to return encrypted reasoning for later replay. Omitted or null optional
reasoning `content`/`status` become canonical null markers and are omitted again on input replay.
Every context snapshot serializes an instruction's canonical `source` and `applies_to` scope, so
nested and sibling applicability survives request mapping. Every response must match one exact
message-or-call grammar before the loop sees it.

## Learning objectives

After this unit, you should be able to:

- map neutral definitions/calls/results without leaking SDK types into core;
- serialize growing scoped instructions without inventing cross-sibling precedence;
- explain why `store=false` requires complete ordered replay;
- preserve a complete reasoning replay item without letting core interpret or record it;
- separate tool semantic status from SDK lifecycle status; and
- bound text at the first producer while leaving limit policy in the harness; and
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

Function-call arguments cross this adapter as bounded raw text. Parsing them here would blur provider
translation with harness policy and can silently collapse repeated names into a last-value-wins
dictionary. CAH-036 instead preserves the exact fragments and completed value; CAH-039 is the only
duplicate-aware argument-admission path.

A downstream 8-KiB check cannot protect memory if the adapter has already retained or repeatedly
joined a huge SDK string. CAH-036 therefore saturates assistant text at the first producer. Normal
neutral text carriers stay bounded; overflow becomes a content-free marker that CAH-033—not the
adapter—turns into the harness-owned limit result.

An incremental JSON encoder does not make an unbounded SDK string safe by itself: it may construct a
whole escaped string as one chunk. Before building the six-key reasoning envelope, CAH-036 therefore
requires exact built-in `str` values, checks O(1) character ceilings of 256 for `id` and 65,536 for
`encrypted_content`, and then checks strict UTF-8 byte ceilings. Huge values and subclasses fail
before scalar walks, canonical copying, escaping, or JSON serializer entry.

Instructions need both identity and applicability. `pkg/AGENTS.md` may resolve to
`shared/rules.md` while still guiding `pkg/file.py`, not `shared/file.py` or `other/file.py`.
Sending content without its canonical source and separately preserved candidate-owner `applies_to`
would erase the harness's scope decision at the provider boundary.

## Key concepts

- **Stateless replay:** send complete locally owned ordered history every turn.
- **Replay-payload selection:** request `reasoning.encrypted_content` on every turn, including turn one.
- **Opaque reasoning envelope:** canonical six-key replay item preserved by core, parsed only by the
  adapter; null marks an absent optional input field.
- **Direct SDK pre-bound:** exact-string and O(1) character checks before UTF-8 or serialization keep
  hostile provider fields from turning a final-size check into unbounded construction work.
- **Strict adapter grammar:** `[reasoning?, function_call]` or `[reasoning?, message]` only.
- **Egress consent:** explicit OpenAI selection authorizes bounded admitted repository content.
- **Semantic result:** CAH-032's matching neutral status and compact function-output JSON; OpenAI
  sends the JSON to the model while client-produced output omits SDK lifecycle `status`; any status
  on a returned item remains a separate transport fact.
- **Raw argument preservation:** byte-exact function-call text forwarded without parsing or
  duplicate-member collapse.
- **Saturating text producer:** retain at most 8,192 UTF-8 bytes, then emit one content-free 8,193
  marker after transport validation.
- **Iterative event pump:** mapped-empty SDK events advance a loop, not recursive self-awaits; raw
  terminal observations are drained through EOF before neutral release.
- **Scoped instruction:** content paired with canonical source, separately preserved candidate-owner
  directory, and unchanged canonical-depth precedence rank.
- **Chain precedence:** root-to-nearest ordering inside one canonical ancestor chain; siblings do not
  override one another.

## Architecture and design

```text
Ink TUI              Python harness domain                     OpenAI Responses
 final only <---- CAH-035 loop/policy
                         ^                                      ^       |
                         | atomic final/call/overflow           |       v
                    CAH-033 admission <--- CAH-036 strict SDK mapper
                         ^                  saturating text + exact replay/argument gates
                         |                  full replay: one ordered neutral history
                         |                  + opaque? -> call -> result positions
                  local read registry
                         |
              CAH-035 context snapshots: root -> nested/sibling instruction growth

Request: store=false, parallel_tool_calls=false,
         include=["reasoning.encrypted_content"], no previous_response_id
Instructions: [{source, applies_to, precedence, content}, ...] from current immutable snapshot
Egress: explicit OpenAI selection; bounded source may leave host; no content secret scan
Evidence: no SDK payload, source content, arguments/results, or reasoning envelope
```

The adapter accepts exactly one optional reasoning item first and then one function call or assistant
message. It may emit bounded validated neutral deltas while SDK events arrive. If text saturates, it
suppresses the crossing delta/tail and later emits only `ProviderTextOverflowObserved(8193)` in the
validated terminal tuple. CAH-033 alone stages observations and exposes an atomic outcome only after
terminal and EOF. A later SDK mismatch therefore discards the whole turn before publication or
dispatch even if an earlier neutral delta crossed the provider port.

For a function call, the shared `created -> queued? -> in_progress` prefix and optional complete
reasoning pair are followed exactly by:

```text
output_item.added(function_call, status=in_progress, arguments="")
  -> function_call_arguments.delta*          # same item ID/output index
  -> function_call_arguments.done            # name + full exact concatenation
  -> output_item.done(function_call, status=completed)
  -> response.completed(status=completed, exact [reasoning?, call])
```

The call output index is 0 without reasoning and 1 with it. Added/done items repeat exact item ID,
call ID, name, and arguments; `caller` and `namespace` are absent or null in every call snapshot.
Delta/done events have no content index or lifecycle-status field. Each argument value is an exact
built-in string and passes an O(1) character gate plus strict UTF-8 admission before comparison or
retention. Non-empty bounded deltas accumulate in a list and are joined once. The arguments-done
event also repeats the exact name. Missing, extra, reordered, wrong-status,
wrong-index, namespaced/program-produced, or post-terminal values fail before a neutral call. This returned item lifecycle is
separate from replayed client `function_call_output`, whose `status` is always omitted.

The message branch keeps CAH-023's exact lifecycle. Every delta is an exact built-in string and a
saturating scalar/terminal-safety/UTF-8-width scan inspects only the remaining 8,192-byte allowance
plus one byte. Normal fragments join once at text-done and that cached bounded value is reused for
later equality. On overflow, fragments are cleared and later text snapshots are checked only for
exact type/presence plus surrounding identity/order/status; discarded content is never scanned,
encoded, joined, retained, or compared. After a raw completed/failed terminal, the adapter drains the
SDK iterator to EOF before releasing its staged neutral terminal tuple. SDK events that map to no
neutral value advance an iterative loop, so 16,384 legal one-byte call fragments do not consume
Python stack frames.

## Practical walkthrough

1. Map the current snapshot's selected instructions as exact `source`, `applies_to`, `precedence`,
   and content; preserve root-to-nearest order within each chain and distinct sibling applicability.
2. Map strict local function definitions by calling each definition's bounded
   `materialize_parameters()` once, using the fresh object as SDK `parameters`, then map the complete
   positional neutral history.
3. Set stateless/sequential options, request encrypted reasoning replay, and omit continuation IDs.
4. Reconcile exactly one of the two legal output-item sequences. For a call, enforce the exact
   added/delta*/arguments-done/item-done/response-completed automaton and preserve argument bytes
   without constructing a dictionary. For a message, saturate text at 8,193 and join only the bounded
   normal path once.
5. Before reasoning canonicalization, require exact `id`/`encrypted_content` strings and apply their
   O(1) character and strict UTF-8 byte ceilings.
6. Copy exactly six admitted fields, incrementally canonicalize the replay item, and construct one
   bounded opaque neutral value. No generic serializer sees the raw SDK object or unbounded string.
7. Pump mapped-empty SDK observations iteratively, drain a raw terminal through EOF, then release the
   validated neutral terminal tuple. Let CAH-033 stage the full turn atomically and CAH-035 decide
   dispatch or completion.

## Implementation code samples

### Planned pseudocode: stateless request

```python
sdk_request = {
    "input": map_all_items(request.conversation),
    "instructions": map_scoped_instructions(request.repository_context),
    "tools": map_strict_functions(request.tools),
    "store": False,
    "parallel_tool_calls": False,
    "include": ["reasoning.encrypted_content"],
    "reasoning": {"effort": "none", "context": "current_turn"},
}
```

The exact one-element `include` appears unchanged on every request, not only follow-up turns.
`map_scoped_instructions` preserves each context item's fields as `source`, `applies_to`,
`precedence`, then `content`; it copies the rank unchanged rather than deriving it from array index or
closing a missing-ancestor gap, and consumes the snapshot supplied for that turn rather than caching turn one.
`map_all_items` reconstructs every prior reasoning item's ID, empty summary, encrypted content, and
type from its canonical opaque envelope at that history position. The canonical envelope always has
six keys: omitted or null output `content`/`status` is stored as null and omitted from the later input;
an empty content list and a completed status remain present. It then preserves each call and function
output. A call replay has exactly `type="function_call"`, `call_id`, `name`, and `arguments` copied
from the neutral call; SDK output-only `id`, `status`, `caller`, and `namespace` are omitted because
core neither retains nor invents them. There is no `previous_response_id` or separate continuation
field.

```json
{"content":null,"encrypted_content":"opaque-token","id":"rs_1","status":null,"summary":[],"type":"reasoning"}
```

This fixed canonical shape makes absence deterministic without requiring the provider to send either
optional field.

### Planned pseudocode: bounded reasoning fields

```python
reasoning_id = require_exact_sdk_string(item.id, characters=256, utf8_bytes=256)
encrypted = require_exact_sdk_string(
    item.encrypted_content,
    characters=65_536,
    utf8_bytes=65_536,
)
candidate = copy_six_reasoning_fields(item, reasoning_id, encrypted)
payload = encode_canonical_incrementally(candidate, maximum_bytes=65_536)
```

The character gates are necessary early bounds, while strict UTF-8 and the complete-envelope cap are
the authoritative byte checks. A serializer spy must remain untouched for an exact huge string or a
hostile `str` subclass.

### Planned pseudocode: first-producer text saturation

```python
text_fragments: list[str] = []
text_bytes = 0
overflowed = False

for delta in sdk_text_deltas:
    require_exact_builtin_str(delta)
    if overflowed:
        continue  # structure/identity already checked; discarded text gets no scalar work
    accepted, accepted_bytes, crossed = scan_at_most_remaining_plus_one(
        delta, remaining=8_192 - text_bytes
    )
    if crossed:
        text_fragments.clear()
        overflowed = True
    else:
        text_fragments.append(accepted)
        text_bytes += accepted_bytes
        emit(ProviderTextDelta(accepted))

if overflowed:
    validate_later_text_shapes_without_content_work()
    terminal_events.append(ProviderTextOverflowObserved(required_bytes=8_193))
else:
    completed_text = "".join(text_fragments)  # the sole bounded join
    reconcile_all_later_text_snapshots(completed_text)
    terminal_events.append(ProviderTextCompleted(completed_text))
```

The saturating scan validates scalar and terminal safety only while content could still become
model-visible. Once overflowed, required SDK fields and structural identities still reconcile, but
discarded text never re-enters an encoder, equality check, join, or retained carrier.

### Planned pseudocode: iterative SDK pump and terminal drain

```python
while not pending_neutral_events:
    raw = await anext(raw_sdk_events)
    mapped = reconcile_one_raw_event(raw)
    if mapped.is_raw_terminal:
        await require_raw_eof(raw_sdk_events)  # any extra raw event is invalid
        pending_neutral_events.extend(mapped.staged_terminal_tuple)
    elif mapped.neutral_event is not None:
        pending_neutral_events.append(mapped.neutral_event)
return pending_neutral_events.popleft()
```

There is no recursive “read again” call when an SDK event maps to `None`. That matters because a legal
bounded function call can contain 16,384 one-byte argument deltas before one neutral call is ready.

### Planned pseudocode: semantic result

```python
item = {
    "type": "function_call_output",
    "call_id": result.call_id,
    "output": result.output_json,
}
```

`result.output_json` already contains exact compact success/error JSON. Client-produced
`function_call_output` omits `id`, `caller`, and `status` for both outcomes; any lifecycle status on
an SDK-returned item is a transport observation, never a policy decision.

### Planned pseudocode: call replay

```python
item = {
    "type": "function_call",
    "call_id": call.call_id,
    "name": call.name,
    "arguments": call.arguments_json,
}
```

The four keys are exact. Replay omits `id`, `status`, `caller`, and `namespace`; those SDK output-item
fields are transport state outside the provider-neutral history contract.

### Planned pseudocode: raw function arguments

```python
call = ProviderToolCall(
    call_id=reconciled_call_id,
    name=reconciled_name,
    arguments_json=reconciled_argument_text,
)
```

The adapter reconciles fragment and completed values but never calls a JSON decoder on function-call
arguments or `arguments_json`. If the raw object contains two `path` members, both remain present in
the neutral call so CAH-039 can reject the ambiguity before its exact-key gate and Pydantic validation.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| message plus function call | invalid response | CAH-033 discards all staged observations; zero publication/dispatch |
| two calls despite parallel=false | invalid response | output-count mutation |
| function-call event is missing/reordered or its ID/index/name/status/done value drifts | invalid response | no neutral call or admitted usage; CAH-033 discards any earlier staged observation |
| function call supplies `caller` or `namespace` | invalid response | mutate each field at added, item-done, and completed snapshots |
| delta/done/item/completed arguments are huge or subclassed | invalid response before comparison/retention | encoder/equality/join/retention spies; one final fragment join |
| text is 8,191/8,192/8,193 bytes across ASCII or multibyte splits | bounded normal text or exact overflow marker | one normal join; no overflow-tail encode/equality/join/retention |
| overflowed text later has structural drift | invalid response | limit cannot launder item/order/status grammar |
| legal provider failure follows an overflow prefix | normalized failure | no overflow outcome or content escapes |
| 16,384 mapped-empty one-byte call deltas | valid call with constant stack depth | iterative-pump spy; 16,385th byte rejects |
| SDK event follows a raw terminal | invalid response before neutral terminal release | terminal tuple is withheld until raw EOF |
| SDK iterator raises after raw terminal | fixed invalid response; staged tuple discarded | no success or second failure release; lifecycle winner retained |
| one call repeats the `path` argument member | exact raw neutral call; CAH-039 later rejects input | byte snapshot and zero adapter JSON-decode calls on function-call arguments |
| encrypted-content include missing on any turn | outbound contract failure | turn-one-through-four snapshots |
| reasoning item omitted on replay | request mismatch | exact turn-two snapshot |
| `source`, `applies_to`, or `precedence` omitted/renumbered | outbound contract failure | exact instruction JSON snapshot with rank gap |
| sibling treated as overriding | mapping-order failure | both distinct scopes remain present |
| successful nested read has no context growth | request mismatch | turn-by-turn context snapshots |
| completed reasoning omits `content` or `status` | canonical null marker, then omitted input key | optional-field cross-product |
| reasoning has non-empty content, wrong status, missing required field, or extra key | invalid response | no opaque/call/text/usage escapes |
| huge or subclassed reasoning `id`/`encrypted_content` | invalid response before construction | UTF-8/canonicalizer/serializer and subclass-hook spies remain untouched |
| full reasoning envelope exceeds bound | invalid response | safe redacted representation |
| client-produced output gains SDK `status` | mapping test fails | exact field absence for success and error |
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
4. Show why tool-error JSON is model-visible while client-produced output still omits lifecycle
   `status`.
5. Teach back what explicit OpenAI selection authorizes and what it does not protect.
6. Map omitted, null, and present `content`/`status` through canonical storage and input replay.
7. Serialize root, `pkg/api`, and sibling `other` instructions with a missing `pkg` candidate;
   identify why ranks `0, 2, 1` are copied values rather than array positions and why equal-depth
   siblings do not override one another.
8. Explain why decoding duplicate-member arguments in the adapter would erase evidence CAH-039 needs
   to reject the call deterministically.
9. Explain why an 8-KiB check in CAH-033 is too late if the SDK mapper already retained 100 MiB.
10. Explain why mapped-empty events require an iterative pump and why raw terminal does not mean EOF.

## Key takeaways

- The adapter translates; the harness admits, dispatches, and continues.
- Function-call arguments remain byte-exact raw text through the adapter; CAH-039 alone decodes and
  rejects repeated member names.
- Every mapped instruction carries canonical `source`, `applies_to`, and unchanged depth
  `precedence`; ordering expresses root-to-nearest precedence only inside an ancestor chain, never
  sibling override or rank renumbering.
- Every stateless request asks for `reasoning.encrypted_content`; otherwise later full replay is not
  guaranteed to be constructible.
- Stateless replay preserves every required reasoning field in order and handles optional fields
  through exact, tested null-to-omitted mappings for both `content` and `status`, while retaining
  empty content and completed status when present.
- Exact type plus O(1) character and UTF-8 byte gates protect reasoning `id` and encrypted content
  before canonical JSON construction; an incremental encoder is not the first line of defense.
- First-producer text saturation bounds memory without moving the assistant-output limit decision out
  of the harness.
- Iterative mapped-empty pumping and raw terminal-to-EOF draining close transport gaps that a neutral
  consumer grammar cannot see.
- Explicit provider selection permits bounded egress, but M2 does not scan admitted content for secrets.

## Glossary

- **SDK lifecycle status:** transport progress/completion, not tool semantics.
- **Opaque replay:** preserving provider state without reading its contents.
- **Repository egress:** source-derived content leaving the local host.
- **DLP:** controls that detect or prevent sensitive-data disclosure; deferred here.
- **Applies-to scope:** canonical workspace-relative directory governed by an instruction item.

## Further reading

- [CAH-036 delivery contract](../../user-stories/cah-036-map-openai-tool-calls.md)
- [CAH-039 argument-admission lesson](cah-039-provider-tool-argument-admission.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
