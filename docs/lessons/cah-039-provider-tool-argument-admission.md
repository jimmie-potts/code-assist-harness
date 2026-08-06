# CAH-039 lesson: Provider tool-argument admission

- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Admit one provider tool argument object](../../user-stories/cah-039-admit-provider-tool-arguments.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned JSON trust boundary, exact failure precedence, and zero-effect
  handoff before tool execution
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Tool system](../tool-system.md), [Agent loop](../agent-loop.md), and
  [Safety model](../safety-model.md)

## Quick summary

CAH-039 turns one raw model tool call into a typed, non-executed native request—or one fixed safe
error. It centralizes lookup, bounded JSON admission, duplicate detection, exact keys, and strict
Pydantic validation so the later round trip can teach orchestration instead of hiding a second parser.

## Learning objectives

After this unit, you should be able to:

- explain why valid JSON is not yet a valid tool request;
- trace exact lookup -> preflight -> pair decode -> duplicate -> key -> type precedence;
- explain why duplicate names must be found before a dictionary exists;
- distinguish preparing a call from authorizing or executing it; and
- design bounded adversarial tests that prove later stages had zero effects.

## Why this unit matters

A model controls the tool name and argument bytes. If an SDK, ordinary dictionary decoder, or native
model silently repairs them, the harness loses the exact request it is authorizing. This unit keeps
that trust boundary explicit and reusable on every agent-loop iteration.

## Junior engineer foundation

JSON objects are written as name/value pairs. Python's normal decoder converts them to a dictionary,
where a repeated name usually keeps only the last value:

```text
raw:        {"path":"safe","path":"other"}
dictionary: {"path":"other"}       # the first proposal disappeared
```

The harness must see both pairs before choosing anything. Likewise, a 5,000-digit number can fail in
Python conversion before a later byte check, and deeply nested arrays can hit an interpreter
recursion limit. A small byte cap bounds width, while an explicit structural cap bounds height.

A common misconception is that “prepared” means “approved.” `PreparedReadToolCall` only means the
untrusted shape became one typed local candidate. CAH-034 still owns the cancellation/deadline guard
and CAH-031 dispatch.

Path limits do not move earlier merely because they are security-sensitive. For a known tool, the
strict native Pydantic stage inherits CAH-024/026's 4,095-byte, 256-component, and 255-byte-name
contract. Unknown lookup, structural/decode/duplicate work, and the exact-key gate keep their
existing precedence; an over-bound path then becomes `invalid_read_tool_input` before dispatch.

## Key concepts

- **Raw call:** CAH-032 call ID, exact tool name, and unparsed bounded `arguments_json`.
- **Atomic catalog:** `build_read_tool_catalog(registry)` accepts only one exact CAH-031 registry,
  invokes CAH-038's definition bridge internally, pairs exact entries with definitions and explicit
  required-key tuples, and re-exposes those definitions for requests.
- **Catalog entry:** exact `read_tool`, `definition`, and `required_keys` fields; exact-name lookup
  returns this owned value or `None` without a descriptor-forwarding shortcut;
  `required_keys is definition.required_keys` is an identity invariant.
- **Preflight:** one iterative scan for root/depth/delimiter/quote and numeric-token rules.
- **Pair-preserving decode:** JSON decoding that retains every object member occurrence and order.
- **Duplicate walk:** non-recursive exact-code-point uniqueness check at every object depth.
- **Exact-key gate:** model keys must equal every advertised required key before defaults.
- **Prepared call:** the exact local fields `call_id`, `catalog_identity`, `read_tool`, and `request`,
  bound to one catalog/registry entry with no execution authority.
- **Failure precedence:** the first failing stage wins and every later stage remains uncalled.
- **Native path admission:** one inherited byte/component/name rule at the final Pydantic stage, not
  a second raw-JSON parser rule.

## Architecture and design

```text
Ink TUI                         Python harness                              Provider
 unchanged        CAH-031 registry -> build_read_tool_catalog(registry)        |
                                      | calls CAH-038 bridge internally         |
                                      v                                         |
                                ATOMIC CATALOG -- catalog.definitions --------> tools
                         owns registry identity + exact entries                 |
                                      | retained catalog                        | raw call
                                      v                                         v
                               [CAH-039 ADMISSION] <-----------------------------+
                                                   |
 LOOKUP -> STRUCTURAL + NUMERIC PREFLIGHT -> CONSTANT-REJECTING PAIR DECODE
                                                   |
                                      ITERATIVE DUPLICATE WALK
                                                   |
                           DICTIONARY -> EXACT-KEY GATE -> STRICT PYDANTIC
                                                   |
                 +--------- PreparedReadToolCall (catalog + exact entry; local only)
                 |                                 |
                 |              CAH-034 guard -> CAH-031 dispatch (later)
                 |
                 +--------- ProviderToolResult(error, matching call_id)
                                                   |
                                      zero dispatch; replayed later

Repository I/O -------- absent     Context/loop -------- absent     Evidence -------- absent
```

The invariant is stronger than “parse JSON”: no dictionary, default, typed request, filesystem
operation, or provider continuation exists until every earlier admission stage succeeds.

CAH-039 trusts each valid CAH-038 definition rather than maintaining a second schema grammar. It can
detect cardinality/name/order/exact-reference/required-key-identity drift while building the catalog.
Those construction failures and cross-catalog dispatch fail only as
`ReadToolCatalogError(code="invalid_read_tool_catalog", message="Read tool catalog is invalid.")`.
This content-suppressed invariant is never a replayable tool result; CAH-034 terminates before handler
I/O, replay, or another provider start.

## Practical walkthrough

1. Call the registry-only catalog factory before provider work. It invokes CAH-038 internally,
   retains the exact registry identity, and re-exposes the exact definition tuple used by requests;
   there is no public input for independently supplied definitions. Each entry retains exact
   `read_tool` and `definition` objects and the identical `definition.required_keys` tuple.
2. Look up the exact CAH-032-admitted lowercase ASCII name. An unknown valid name wins even when
   arguments are malformed; malformed name spellings never reach this unit.
3. Scan the already bounded 16-KiB value once. Require one root object, at most 64 object/list levels,
   matched delimiters, correct quote escapes, and signed-64-bit integer-only numeric tokens outside
   strings.
4. Pair-decode with non-finite constants rejected, then iteratively reject duplicate decoded names at
   every depth.
5. Construct dictionaries only after uniqueness is proven.
6. Require exactly the advertised CAH-038 keys, then call the strict native Pydantic model, including
   the shared path budget.
7. Return `PreparedReadToolCall | ProviderToolResult` directly; do not invent a wrapper or dispatch.

## Implementation code samples

No implementation exists yet. This is planned pseudocode:

```python
catalog = build_read_tool_catalog(registry)  # sole public constructor; calls CAH-038

def prepare_read_tool_call(
    call: ProviderToolCall,
    catalog: ReadToolCatalog,
) -> PreparedReadToolCall | ProviderToolResult:
    entry = catalog.lookup_exact(call.name)  # unknown wins before argument work
    if entry is None:
        return fixed_tool_error(call.call_id, "unknown_read_tool")

    preflight_structure_and_signed64_numbers(call.arguments_json, max_depth=64)
    pairs = decode_pairs(call.arguments_json, reject_constants=True)
    reject_duplicate_names_iteratively(pairs)
    arguments = pairs_to_dicts(pairs)
    require_exact_keys(arguments, entry.required_keys)
    request = entry.read_tool.descriptor.input_model.model_validate(arguments)
    return PreparedReadToolCall(
        call_id=call.call_id,
        catalog_identity=catalog.identity,
        read_tool=entry.read_tool,
        request=request,
    )
```

Each line owns one stage. `fixed_tool_error` returns the correlated CAH-032 `ProviderToolResult`;
there is no admission-result wrapper. The production implementation maps the expected exceptions to fixed
`unknown_read_tool` or `invalid_read_tool_input` envelopes and suppresses content. It does not catch
an error only to continue at a later stage.

## Failure scenarios to study

| Scenario | First owner | Required evidence |
| --- | --- | --- |
| unknown name plus hostile JSON | exact lookup | zero scanner/decoder/key/Pydantic calls |
| uppercase, non-ASCII, or over-16-KiB call | earlier CAH-032 carrier | CAH-039 is never invoked |
| depth 65 or mismatched container | iterative preflight | zero JSON decode |
| fraction, exponent, signed overflow, 5,000-digit integer | numeric preflight | zero Python integer conversion |
| `NaN` or infinity | rejecting decoder callback | zero duplicate/key work |
| `"path"` plus `"pa\u0074h"` | duplicate walk | zero dictionary construction |
| missing defaulted key or extra key | exact-key gate | zero Pydantic call |
| wrong strict field type | native Pydantic model | fixed error, no validation detail |
| known tool with 4,096-byte path, 257 components, or 256-byte name | native Pydantic model | `invalid_read_tool_input`; zero dispatch or repository I/O |
| valid object | prepared-call constructor | exact catalog/entry identity; zero dispatch or I/O |
| prepared value from catalog A reaches catalog B over the same registry | CAH-034 identity check | exact `ReadToolCatalogError` before handler I/O/replay/follow-up |
| prepared value from a same-shaped second registry | CAH-034 entry binding | same exact non-replayable error before either handler |

## Production expansion

### Example enterprise scenario

A production harness may admit versioned tool catalogs from several providers or remote MCP
servers. It still needs one host-owned snapshot, bounded grammar, duplicate policy, schema
compatibility gate, and authorization step before execution.

### Representative production tools

- [Python `json`](https://docs.python.org/3/library/json.html) supports `object_pairs_hook` and
  `parse_constant`; it is local and small, but the harness must add depth, numeric, and duplicate
  policy.
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) provides typed field
  admission after wire-shape checks; it must not erase the earlier raw-key boundary.
- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) defines a broad schema language;
  CAH-038 deliberately uses a much smaller portable subset.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) add remote catalog
  and result semantics, with transport, authentication, and changing-catalog operational cost.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Catalog | four immutable native reads | versioned/re-admitted local and remote snapshots |
| Grammar | one object, integer/string/boolean fields | reviewed richer schemas and migrations |
| Execution | explicitly absent in this unit | separate authorization, isolation, and auditing |
| Cost | bounded local scan/decode | compatibility, telemetry, and remote operations |

### Trade-offs and graduation signals

Rejecting fractions/exponents and multiple calls is intentionally conservative for the four M2
tools. Broaden the grammar only when a reviewed capability needs it and boundary/evaluation evidence
proves deterministic mapping. A generalized MCP port should be a separate trust-boundary unit.

## Practical exercises

1. Trace `{"path":"a","pa\u0074h":"b"}` and name the last stage that may run.
2. Explain why unknown lookup must win before parsing hostile arguments.
3. Compare the 16-KiB width bound with the 64-level height bound.
4. Put a duplicate object inside an array at depth 64; identify why recursion is unnecessary.
5. Omit a native-defaulted key and explain why a trusted Python caller and a model call differ.
6. Teach back why `PreparedReadToolCall` grants no filesystem authority.

## Key takeaways

- The harness, not the provider SDK or Pydantic defaults, owns argument admission.
- Preserve pairs first; dictionaries are safe only after every object proves uniqueness.
- Bound width, height, and numeric conversion before interpreter limits can become behavior.
- Exact keys precede native types, and preparation precedes dispatch.
- One named stage order makes failure precedence and zero-effect tests reviewable.
- Boundary ownership matters: CAH-032 proves unreachable malformed carriers; CAH-039 tests only
  admitted calls plus clearly labeled defense-in-depth helpers.

## Glossary

- **Constant rejection:** rejecting Python JSON extensions such as `NaN` and `Infinity`.
- **Exact code point:** compare decoded Unicode characters without case folding or normalization.
- **Integer token:** numeric text outside a JSON string; M2 admits only signed-64-bit JSON integers.
- **Late-stage spy:** test double proving an earlier rejection did not call a later operation.
- **Prepared invocation:** validated local candidate that has not crossed the dispatch guard.

## Further reading

- [Python JSON decoder customization](https://docs.python.org/3/library/json.html#json.JSONDecoder)
- [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/)
- [OWASP input validation](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
