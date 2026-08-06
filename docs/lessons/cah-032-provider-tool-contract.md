# CAH-032 lesson: Provider-neutral tool turns

- **Unit:** CAH-032
- **Milestone:** M2 - Read-only coding assistant
- **Learning emphasis:** Core learning unit
- **Review focus:** Representing a paused tool-aware model turn while the harness retains context,
  execution, and continuation authority
- **Lesson status:** Planned
- **Implementation status:** Planned; tool-aware provider request/history values do not exist yet
- **Story:** [CAH-032](../../user-stories/cah-032-define-provider-tool-contract.md)
- **Visual companion:** None; do not add or revise presentation files
- **Related architecture:** [Architecture](../architecture.md), [Agent loop](../agent-loop.md), and
  [Context engineering](../context-engineering.md)

> This lesson explains accepted planned behavior. Its code blocks are pseudocode, not shipped
> evidence.

## Quick summary

CAH-032 gives the harness provider-neutral values for calls, canonical results, opaque continuation
items, ordered history, scoped context, and bounded requests. It teaches a central agent-loop rule:
a provider may request a tool, but only the harness represents and later advances that paused turn.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a provider call observation from permission to execute or continue;
- explain the sequential continuation/call/result history grammar;
- trace CAH-030 context and CAH-038 definitions into an immutable provider request;
- explain complete-envelope depth/work admission for canonical tool results; and
- locate argument parsing/key enforcement, dispatch, context enrichment, and adapter mapping in
  their later owning stories.

## Why this unit matters

An explicit agent loop needs a stable language between core orchestration and provider adapters. If
SDK objects, mutable context, raw result data, or provider-managed conversation state become that
language, the harness cannot independently test ordering and safety. CAH-032 creates the values and
strict fake needed to test a tool-aware turn before any real provider or tool execution is involved.

## Junior engineer foundation

A model's tool call is data, not a Python function call. For example:

```text
call ID: call_1
tool:    read_file
args:    {"path":"src/app.py"}
```

CAH-032 preserves that bounded argument string but does not parse it. A repeated `path`, a floating
number, or a missing required key is still only raw text here. CAH-039 later admits pairs and numbers,
checks exact required keys, and prepares a native request without executing it; CAH-034 owns the
guarded CAH-031 dispatch. A common misconception is that constructing `ProviderToolCall` means the
call is safe; it only means its carrier is bounded.

A continuation is opaque provider state needed to resume some APIs. “Opaque” means core code keeps
the exact bytes but cannot interpret them. It belongs in ordered history immediately before the
provider output it qualifies. Treating it as a side field would hide ordering from the loop and fake.

Canonical tool results need more than a final byte check. A deeply nested or extremely wide JSON
candidate can strain the decoder before its final size is considered. CAH-032 scans the complete
envelope iteratively, counts the outer object as depth 1, shares one budget across every subtree, and
only then decodes and checks canonical equality.

The same idea applies before encoding a request. `JSONEncoder.iterencode()` is incremental between
chunks, but one chunk may already contain a whole escaped string. CAH-032 therefore accepts only exact
built-in strings, rejects an O(1) character count above the applicable byte ceiling, and checks the
field's UTF-8 bytes before any request serializer sees it. Exact conversation, legacy-instruction,
repository-context, and tools tuple cardinalities are also checked before iteration. Incremental
request output is useful only after these input bounds.

## Key concepts

- **Provider-neutral value:** an SDK-free immutable value understood by the harness and adapters.
- **Call observation:** a provider request represented as data; it grants no execution authority.
- **Canonical result envelope:** exact compact success or error JSON that can safely enter history.
- **Opaque continuation:** bounded provider state whose order and equality are visible but whose
  content is never interpreted or exposed by core code.
- **Stream wrapper:** `ProviderOpaqueContinuationObserved(continuation=...)` is the only way opaque
  state enters `ProviderStreamEvent`; the bare value exists only in admitted conversation history.
- **Closed history grammar:** legal sequential states for messages, continuation, call, and matching
  result; impossible states fail at construction.
- **Context projection:** exact model-facing CAH-030 items, including instruction applicability and
  precedence, without harness-only evidence.
- **Pre-encoding admission:** exact type, O(1) character/cardinality, and UTF-8 byte checks that keep
  an incremental encoder from first materializing an unbounded caller string.
- **Strict fake:** deterministic provider test double that compares complete values without leaking
  their content.

## Architecture and design

```text
Ink TUI                    Python harness                             Provider
 task/events                    |                                        |
      |            CAH-030 context snapshot                             |
      |            CAH-038 frozen definitions                           |
      |                       |                                          |
      |                       v                                          |
      |             [CAH-032 provider request] ------------------------>|
      |      messages + opaque continuation + call/result history        |
      |                       ^                                          |
      |                       | ProviderOpaqueContinuationObserved?      |
      |                       | ProviderToolCallRequested                 |
      |                 strict fake first                                |
      |                       |                                          |
      |       later CAH-039 parse/key gate -> prepared request            |
      |       later CAH-034 guard/CAH-031 dispatch/context/replay         |
      +--------------- no protocol/TUI change in CAH-032 ----------------+

Evidence boundary: exact constructor, grammar, projection, byte, and strict-fake tests
```

The provider port owns translation between neutral values and an adapter. The harness owns which
context and definitions are present, whether a call can execute, and whether another exchange may
start. CAH-032 consumes CAH-038 definitions unchanged; schema generation and validation do not leak
back into this unit. Instruction `source`, candidate-owner `applies_to`, and content are copied as
selected; numeric precedence is likewise copied exactly from CAH-030 and is not recomputed from
tuple position.

The shipped request name remains `conversation`; there is no `input` alias. Its four exact fields are
`conversation`, legacy `repository_instructions`, new `repository_context`, and `tools`, with empty
defaults after the required conversation. Context projection uses three frozen variants:
`ProviderInstructionContext`, `ProviderFocusContext`, and `ProviderSearchContext`. Their exact
kind-specific fields keep impossible combinations out of the request instead of relying on nullable
metadata.

`ProviderSearchContext.query_rank` is a strict one-based value from 1 through 4, copied from
CAH-030's exact-deduplicated query order. For input queries `("todo", "todo", "fix")`, context uses
ranks 1 and 2; neither the bridge, strict fake, nor CAH-036 may preserve the original gap or renumber
from a provider array index.

Top-level `provider_context.py` owns the sole
`build_provider_context(package: ContextPackage) -> tuple[ProviderRepositoryContextItem, ...]`
bridge. It is the only module allowed to import both CAH-030 context values and provider models. It
copies admitted items exactly or raises the content-suppressed `ProviderToolContractError` on
impossible drift; CAH-030 and `provider/models.py` never import one another. CAH-034/035 use this
bridge for every context snapshot.

All four request collections are exact built-in tuples before iteration: conversation has 1-16
items, legacy instructions 0-16, repository context 0-24, and tools 0-16. Exact element variants are
then checked before projection. This keeps the compatibility carrier from becoming an unbounded or
subclass-hook path.

All CAH-032-owned construction and projection failures use
`ProviderToolContractError(code="invalid_provider_tool_value", message="Provider tool value is invalid.")`.
The failure is content-suppressed and never chains parser, serializer, or candidate details.

## Practical walkthrough

Build and test in this order:

1. Require exact built-in strings and exact conversation/instruction/context/tools tuples. Apply O(1)
   character and cardinality gates before scalar walks, UTF-8 encoding, escaping, element iteration,
   or serializer entry.
2. Construct bounded calls that preserve raw arguments exactly and bounded opaque continuations that
   core code cannot inspect.
3. For each result, preflight the complete envelope iteratively under one 65,536-byte/work budget and
   64-level ceiling; only then decode, walk signed-64-bit JSON values, reserialize, and require exact
   status/envelope equality.
4. Validate ordered history: a continuation immediately qualifies one call or assistant message,
   and every call has one following result with the same ID before later text. Later CAH-039
   validates and prepares admitted arguments without executing them; CAH-034 applies its guard and
   dispatches the prepared invocation through CAH-031.
5. Call `build_provider_context` for one immutable CAH-030 package, omitting its inclusion report and
   CAH-031 local instruction scopes, then consume the immutable CAH-038 definition tuple unchanged.
6. Shape-project every model-facing field, then incrementally measure the complete canonical request
   proxy once against 524,288 bytes. No generic JSON encoder receives an unbounded caller string.
7. Script the strict fake with exact requests and outcomes; mismatches report only the exchange and
   structural field path.

This order keeps failures local. Invalid result bytes never reach a JSON decoder, invalid history
never reaches request measurement, and an invalid request never reaches the fake.

## Implementation code samples

### Planned pseudocode: one completed tool-aware request

```python
call = ProviderToolCall(
    call_id="call_1",
    name="read_file",
    arguments_json='{"path":"src/app.py"}',
)
result = ProviderToolResult(
    call_id="call_1",
    status="success",
    output_json='{"result":{"path":"src/app.py","text":"..."}}',
)
request = ProviderRequest(
    repository_context=build_provider_context(context_package),
    conversation=(user_message, opaque_continuation, call, result),
    tools=provider_definitions,  # immutable CAH-038 values
)
```

The call keeps argument bytes uninterpreted. Result construction admits the complete canonical
envelope before history uses it. The continuation appears immediately before the call it qualifies,
and the matching result closes that call. `build_provider_context` copies selected CAH-030 values; it does
not discover or merge instructions.

### Planned pseudocode: result admission order

```python
preflight_complete_envelope(output_json, bytes=65_536, depth=64)
candidate = bounded_json_decode(output_json)
validate_json_tree_iteratively(candidate)
require_status_shape(status, candidate)
require_canonical_equality(output_json, candidate)
```

The preflight is quote-and-escape-aware, so braces inside strings do not add depth. Its budget never
restarts for a nested value. The integer decoder refuses an overlong token before Python creates a
huge integer. Only the canonical, correctly tagged candidate becomes a result.

### Planned pseudocode: request pre-encoding order

```python
require_exact_tuple_and_count(request.conversation, maximum=16)
require_exact_tuple_and_count(request.repository_instructions, maximum=16)
require_exact_tuple_and_count(request.repository_context, maximum=24)
require_exact_tuple_and_count(request.tools, maximum=16)
for field in direct_provider_strings(request):
    require_exact_str_and_character_ceiling(field)
    require_strict_utf8_within_field_limit(field)
proxy = shape_project_request(request)
encode_proxy_incrementally(proxy, maximum_bytes=524_288)
```

The projector visits only the closed request shape. A hostile `str` subclass fails before its hooks,
and an exact huge string fails on `len(...)` before UTF-8, escaping, or JSON-encoder entry. The final
byte limit still counts the complete proxy, including punctuation and every escape. Each provider
start reapplies this limit to its own complete snapshot. History is cumulative inside that snapshot;
whole-request byte counts are not summed across starts.

### Planned pseudocode: orphan-result failure

```python
with raises(ProviderToolContractError):
    ProviderRequest(conversation=(user_message, result), tools=provider_definitions)
```

The important behavior is construction-time rejection: neither a provider, a tool, nor another
exchange runs for impossible history.

## Failure scenarios to study

| Scenario | Owner | Safe result | Planned evidence |
| --- | --- | --- | --- |
| raw arguments contain duplicate keys or invalid later numeric grammar | CAH-039, not CAH-032 | preserve bounded bytes without interpretation | call-constructor parser spy |
| result depth 65 or byte 65,537 | complete-envelope preflight | reject before decode | depth/byte boundary and parser spy |
| result contains float, 5,000-digit integer, or noncanonical JSON | bounded decode/canonicalizer | fixed invalid-result failure | token, serializer, and snapshot tests |
| continuation starts/ends history or precedes the wrong item | history grammar | reject request atomically | positional table tests |
| orphan, mismatched, duplicate, or unresolved call | history grammar | reject before fake/provider work | call-ID state-machine table |
| legacy and scoped context both supplied | request constructor | reject competing context systems | compatibility test |
| CAH-030 report or CAH-031 scopes enter the request | projection boundary | omit/reject harness-only evidence | exact projection snapshot |
| exact huge string or hostile `str` subclass enters a direct field | pre-encoding admission | reject before UTF-8, escaping, projection, or serializer | encoding/JSON-encoder/hook spies |
| conversation or tools has 17 items | O(1) tuple cardinality gate | reject before element iteration or equality | tuple-bound and traversal spy |
| complete request reaches byte 524,289 | request incremental sink | reject without truncation or excess retention | exact byte test |
| fake request differs in secret-like content | strict fake | exchange/path-only mismatch | leak-sentinel test |

## Production expansion

### Example enterprise scenario

A production harness may resume conversations across processes and multiple providers. It would need
versioned durable history, encrypted provider continuation state, migration rules, and replay/audit
controls while preserving the same core ownership: adapters translate; the harness advances turns.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) is one
  adapter target for neutral calls and results, with provider-specific item rules.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) standardizes remote
  tool interactions but adds transport trust, catalog, authentication, and cancellation concerns.
- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259) defines JSON interoperability constraints;
  harness canonicalization deliberately chooses a stricter bounded subset.
- [Python `json`](https://docs.python.org/3/library/json.html) supplies parsing hooks and incremental
  encoding, while application code must still impose depth, integer, and work limits.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Turn state | immutable in-process values | durable versioned conversation records |
| Provider | strict fake before one adapter | multiple adapters and compatibility suites |
| Continuation | bounded opaque string | encrypted provider-scoped state lifecycle |
| Limits | fixed local byte/item/depth bounds | per-provider policy and telemetry |
| Cost | explicit small state machine | storage, migration, and operations ownership |

### Trade-offs and graduation signals

The strict sequential grammar excludes parallel calls and provider-managed history, but it makes one
M2 round trip easy to reason about. Expand only when evaluation demonstrates a need and new states
have deterministic replay, cancellation, and content-safety tests.

## Practical exercises

1. Draw the legal history states for `user -> continuation? -> call -> result` and identify the
   earliest rejection point for an orphan result.
2. Create a JSON string with braces inside quoted text and predict why the preflight depth is
   unchanged.
3. Change an instruction's `applies_to` while leaving its source equal and explain why the strict
   fake must reject the context snapshot.
4. Explain why a 16-KiB raw argument bound is not evidence that its keys or numbers are valid.

## Key takeaways

- A provider tool call is an observation; the harness still owns execution and continuation.
- Complete result and request envelopes are admitted atomically under non-resetting bounds.
- CAH-032 consumes frozen definitions and selected context but owns neither schema admission nor
  runtime argument interpretation.

## Glossary

- **Tool-aware turn:** a model exchange whose ordered state includes a requested tool call and later
  matching result.
- **Complete-envelope preflight:** iterative scan of the whole JSON wrapper before decode, with one
  depth and work budget.
- **Opaque continuation:** exact bounded provider state that core code carries but never interprets.
- **Structural mismatch:** safe diagnostic naming a field location without embedding its content.

See the shared [glossary](../glossary.md) for provider port, agent loop, and context-package terms.

## Further reading

- [CAH-032 delivery contract](../../user-stories/cah-032-define-provider-tool-contract.md)
- [CAH-038 bounded definitions](../../user-stories/cah-038-canonicalize-provider-tool-definitions.md)
- [Agent loop](../agent-loop.md)
- [Architecture](../architecture.md)
- [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259)
