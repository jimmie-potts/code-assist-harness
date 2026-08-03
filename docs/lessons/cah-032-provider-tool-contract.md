# CAH-032 lesson: Define the provider-neutral tool contract

- **Unit:** CAH-032
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; tool-aware provider requests are not implemented
- **Story:** [CAH-032](../../user-stories/cah-032-define-provider-tool-contract.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Provider-neutral scoped context snapshots, definitions, opaque continuation,
  calls, and results that adapters can map without owning the loop
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Architecture](../architecture.md),
  [Agent loop](../agent-loop.md), and [Tool system](../tool-system.md)

> This lesson describes an accepted contract plan. All code is labeled pseudocode and is not
> implementation evidence.

## Quick summary

CAH-032 defines immutable, provider-neutral context snapshots, canonical tool schemas, opaque
continuation, calls, and exact result envelopes and teaches the strict fake to compare them. A later
request may carry CAH-030's enriched snapshot without mutating the earlier request. Provider
integrations translate these harness values rather than exporting SDK types or selecting context.

## Learning objectives

After this unit, you should be able to:

- separate a tool definition, a requested call, and a returned result;
- project selected context, including instruction `applies_to`, without sending its local inclusion
  report or CAH-031 target scope;
- distinguish immutable successive context snapshots from in-place mutation;
- explain why arguments remain unparsed at the provider boundary;
- explain why model-facing required keys must be checked before native defaults can apply;
- validate the exact call-ID grammar and strict Unicode-scalar/UTF-8 boundaries;
- distinguish CAH-031's canonical success envelope from the canonical error envelope;
- preserve bounded provider state at its exact ordered history position without interpreting it;
- validate ordered continuation/call/result history independently of an SDK; and
- locate function calling and MCP on opposite sides of the same provider-neutral seam.

## Why this unit matters

The agent loop cannot safely reason over raw SDK events. A small domain contract lets the fake prove
tool-shaped conversations before either dispatch or OpenAI mapping is allowed.

## Junior engineer foundation

A model tool exchange has three different values:

```text
definition: read_file accepts {path: string}
call:       call_1 asks for read_file with raw JSON arguments
result:     call_1 receives bounded text or a bounded error
```

The call ID pairs the result with the request. A common misconception is that JSON text is already a
validated tool input. CAH-032 preserves argument bytes; CAH-034 will parse and validate them after
CAH-033 admits the complete provider response. A
second misconception is that any valid JSON Schema is portable. The reviewed M2 subset is flat and
requires every property plus `additionalProperties: false`, matching strict function-tool rules.
Python callers may still use native request defaults; the model-facing schema requires explicit
values. A schema declaration alone is insufficient: after CAH-034 decodes a model call, a pure
CAH-032 key gate compares the raw object keys with the canonical `required` list *before* Pydantic
can fill a missing default. The native request model itself stays unchanged, so trusted direct
Python callers retain its normal defaults. The bridge that performs schema conversion is a separate
harness function—not a `ProviderToolDefinition.from_descriptor` method—so neither the registry nor
provider-domain class imports and reshapes the other boundary.

Some providers return an opaque state item before a call. It is neither a message nor a tool result,
but a stateless follow-up must keep its position. CAH-032 therefore models one bounded
`ProviderOpaqueContinuation` in the same ordered history tuple. A separate request field would lose
which later call or assistant item it belongs to after several turns; core preserves the payload but
does not understand it.

Repository context has a similar ownership rule. CAH-030 decides which items exist. CAH-032 copies
one complete immutable snapshot and charges every field—including an instruction's canonical
candidate-owner `applies_to` directory—to the request bound. That scope is copied from CAH-025 and
may differ from a symlink-resolved `source`; CAH-032 never reconstructs it from provenance. If later
orchestration enriches context, it constructs a new request; an adapter may serialize that value but
may not omit or select an item. Sibling scopes remain unrelated even when serialization needs one
deterministic order.

## Key concepts

- **Provider-neutral value:** harness type containing no SDK object.
- **Definition:** name, description, and strict object schema offered to a model.
- **Call:** provider observation carrying an ID, registered name, and unparsed JSON.
- **Result:** bounded success/error output paired to one call ID.
- **Opaque continuation:** non-empty provider-owned state, capped at 65,536 UTF-8 bytes and preserved
  immediately before its call or assistant item without parsing or display.
- **Canonical envelope:** sorted-key compact UTF-8 JSON; success is exactly
  `{"result":...}`, error exactly `{"error":{"code":...,"message":...}}`.
- **History grammar:** rules preventing orphan, duplicate, or unresolved call/result items.
- **Context projection:** the exact admitted CAH-030 items and instruction `applies_to`, without its
  local omission report or CAH-031 success-only target scope.
- **Context snapshot:** one immutable per-request value; a later enriched request does not mutate the
  earlier one.
- **Raw-key gate:** exact model-facing key-set admission before native validation or defaults.

## Architecture and design

```text
Ink TUI                 Python harness domain                    Adapters
task/events   context snapshot -> [CAH-032 neutral contract]   OpenAI function calling
    |      scoped context / definition / opaque / call / result <-> future provider adapter
    |                           ^
    |                           |
    |                    strict fake provider
    |                    exact request scripts
    |                           |
    +--------------- final text later                    Tool dispatch: absent
                                                        Evidence: absent

Future MCP: catalog snapshot + re-admission -> generalized registry port -> neutral envelopes
            (not direct plug compatibility; transport/auth/timeouts/cancellation remain future)

Later CAH-034 dispatch:
raw JSON -> decode object -> [CAH-032 exact key gate] -> native Pydantic -> read tool
                              missing/defaulted keys stop here

Later context flow:
CAH-031 local target_scope -> CAH-025 bundle -> CAH-030 merge -> new CAH-032 request snapshot
```

Definitions use a closed schema table: the root has exactly `type`, `properties`, `required`, and
`additionalProperties`; flat properties are only string, integer, or boolean with their reviewed
type-specific constraints. Calls use
`[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}` and preserve raw arguments. Every owned string must round-trip
strict UTF-8 after JSON parsing; lone surrogates and literal NUL fail without normalization. Result
status must match its sole top-level envelope key. Ordered history rejects orphan results and
unresolved calls, and a continuation that does not immediately precede its provider-produced call or
assistant message. Context preserves CAH-030 order/content/`applies_to` while omitting its report and
local target-scope metadata. Every metadata byte is part of the 512-KiB request projection.

## Practical walkthrough

1. Add immutable definition, continuation, call, and result values to the provider domain.
2. Extend one request-history tuple with legal user/assistant/continuation/call/result items; do not
   add an adapter side channel.
3. Project one CAH-030 package with instruction `applies_to`, but without its inclusion report or
   CAH-031 target scope.
4. Call the separate pure bridge to filter Pydantic `title`/`default`, reject every other unsupported
   keyword, require all fields, and canonicalize all definitions atomically.
5. Add the separate pure raw-key gate that CAH-034 will run after JSON-object decoding and before
   native Pydantic validation.
6. Make the strict fake compare initial and enriched context snapshots, definitions, and history
   exactly without mutating the initial request.
7. Prove every byte/item bound, including `applies_to`, and that mismatch messages reveal structure,
   never content.

## Implementation code samples

### Planned pseudocode: complete neutral history

```python
context = project_context(context_package)
definitions = build_provider_tool_definitions(read_file_registry)
definition = definitions[0]
call = ProviderToolCall("call_1", "read_file", '{"path":"src/app.py"}')
opaque = ProviderOpaqueContinuation(canonical_provider_payload)
result = ProviderToolResult(
    "call_1", status="success", output_json='{"result":{"text":"..."}}'
)
request = ProviderRequest(
    context=context,
    input=(user, opaque, call, result),
    tools=(definition,),
)

enriched_request = ProviderRequest(
    context=project_context(enriched_package),
    input=(user, opaque, call, result),
    tools=(definition,),
)
assert request.context != enriched_request.context
```

The bridge—not the provider value—converts a registry descriptor. The call preserves untrusted
arguments. The opaque payload is one content-suppressed history item immediately before that call and
counts once toward both the 16-item and 512-KiB request limits. The result reuses CAH-031's exact
canonical success envelope and is admitted only after the matching call. The local
`ReadToolSuccess.target_scope` is deliberately absent; only CAH-030's admitted scoped items enter the
new request.

### Exact schema subset

| Type | Allowed property keywords |
| --- | --- |
| string | `type`, `description`, `enum`, `pattern`, `minLength`, `maxLength` |
| integer | `type`, `description`, `enum`, `minimum`, `maximum` |
| boolean | `type`, `description`, `enum` |

The root has no optional keywords. Property names are lower snake case, all properties are required,
and `additionalProperties` is false. Canonicalization orders properties/required by UTF-8 label,
then uses `ensure_ascii=False`, compact separators, sorted keys, and `allow_nan=False`. References,
nested values, arrays, unions/combinators, formats, defaults, floats, and unknown keywords fail.

### Planned pseudocode: required keys before native defaults

```python
decoded = decode_json_object(call.arguments_json)  # CAH-034 owns decoding
require_provider_tool_argument_keys(definition, decoded)  # CAH-032 pure gate
native_request = descriptor.input_model.model_validate(decoded)
```

If `decoded` omits a field that has a native default, line two still rejects it and line three never
runs. A trusted direct Python caller may use the unchanged native model and receive that default.

### Planned pseudocode: orphan-result failure

```python
with raises(ValueError):
    ProviderRequest(input=(user, result), tools=(definition,))
```

The constructor rejects impossible history before an adapter or model sees it.

## Failure scenarios to study

| Scenario | Owner | Safe result | Planned evidence |
| --- | --- | --- | --- |
| mutable/malformed schema | definition constructor | reject before request | schema-boundary tests |
| non-strict or unsupported schema keyword | definition bridge | reject the catalog atomically | portable-subset table |
| orphan or duplicate call ID | history grammar | reject request | table-driven grammar tests |
| continuation at start/end, duplicated, reordered, or before the wrong item | history grammar | reject request without exposing payload | positional-history table |
| continuation above 65,536 bytes or request above 512 KiB | continuation/request constructor | reject atomically | below/at/above byte snapshots |
| legacy and new context both supplied | request constructor | reject duplicate priority models | compatibility test |
| missing/changed instruction `applies_to` | context projection/fake | reject the mismatched snapshot | exact-context snapshot |
| CAH-031 local target scope enters request/result | projection boundary | reject the extra field | omission sentinel test |
| request projection above 512 KiB | request constructor | reject without truncation | byte-bound test |
| raw malformed arguments | later dispatcher, not CAH-032 | preserve bytes without execution | constructor test |
| omitted defaulted or additional model key | CAH-032 raw-key gate | reject before Pydantic/defaults | spy-validator key-set tests |
| oversized result | result constructor | fixed bounded failure | byte-bound test |
| status/envelope mismatch | result constructor | reject before history | exact success/error snapshots |
| lone surrogate or invalid call ID | string/identifier admission | reject before fake/provider work | scalar and grammar boundary tests |
| fake mismatch with secret-like content | strict fake | structural path only | leak-sentinel test |

## Production expansion

### Example enterprise scenario

A multi-provider harness may translate the same internal definitions to OpenAI function tools and
an on-prem provider. MCP requires a future generalized registry port, not direct compatibility: it
must snapshot and re-admit catalogs, filter names/schemas, classify remote/network capability, map
`structuredContent`, `outputSchema`, and `isError`, and own auth, timeouts, cancellation, and catalog
revocation.

### Typical production capabilities and tools

- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) defines a portable schema
  vocabulary, with compatibility and validator-version cost.
- [Pydantic JSON Schema](https://docs.pydantic.dev/latest/concepts/json_schema/) can derive schemas
  from Python models, but emitted schemas still need review and canonicalization.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) is one
  provider mapping, not the core contract.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) offers a standard
  client/server capability boundary with additional remote trust and operations.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Contract | small immutable Python values | versioned cross-service schemas |
| Providers | strict fake first | multiple adapters and compatibility suites |
| History | sequential positional continuation/call/result items and immutable context snapshots | durable resumable conversations |
| Security | bounded local values | schema governance and remote trust |
| Cost | explicit, narrow seam | migration and interoperability ownership |

### Trade-offs and graduation signals

Canonical immutable values cost some mapping code but keep orchestration testable. Add broader schema
features or MCP only when a real reviewed capability requires them and compatibility tests exist.

## Practical exercises

1. Explain why `arguments_json` must not be parsed inside a provider adapter.
2. Move an opaque continuation after its call and predict the constructor failure.
3. Teach back how function calling differs from tool execution.
4. Draw the snapshot, re-admission, remote execution, and result-mapping stages a future MCP port
   needs without owning the loop.
5. Explain why the inclusion report stays local even though admitted context goes to the model.
6. Explain why status plus `{"error":...}` is valid but status plus `{"result":...}` is not.
7. Teach back why keeping a native Python default does not make that field optional for the model.
8. Compare initial and enriched requests and identify every `applies_to` byte charged to the latter.

## Key takeaways

- The harness contract, not an SDK, defines tool meaning inside the loop.
- Calls and results pair exactly; raw arguments are not validated inputs.
- Opaque provider state stays in the same ordered history as its call; it is bounded and preserved,
  never interpreted or stored in evidence.
- Model-facing required keys are admitted before native Pydantic defaults; local callers keep their
  native defaults.
- Each request is an immutable scoped-context snapshot; adapters serialize the whole admitted value
  and never receive CAH-031's local target scope.
- OpenAI maps this neutral seam directly; MCP needs a future generalized registry port with explicit
  re-admission and remote-operation ownership.

## Glossary

- **Anti-corruption boundary:** translation layer that prevents external types from shaping core APIs.
- **Canonical schema:** one stable immutable representation of a reviewed schema.
- **Call ID:** bounded identifier correlating a call with its result.
- **History grammar:** allowed ordering and pairing of model input items.
- **Positional continuation:** opaque provider state whose location next to an output item is part of
  its meaning.
- **Scoped context snapshot:** immutable per-request projection whose instruction items retain their
  canonical `applies_to` directories.

## Further reading

- [CAH-032 delivery contract](../../user-stories/cah-032-define-provider-tool-contract.md)
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
