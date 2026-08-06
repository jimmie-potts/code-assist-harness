# CAH-038 - Canonicalize provider tool definitions

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit
  agent loop (supporting contract unit)
- **Dependencies:** CAH-031
- **Lesson:** [Bounded provider tool definitions](../docs/lessons/cah-038-bounded-provider-tool-definitions.md)
- **Learning emphasis:** Supporting implementation unit
- **Review focus:** Bounded, provider-neutral schema admission at the harness-to-provider boundary.

## User story

> As an agent-loop developer, I want each native read-tool descriptor converted into one immutable,
> canonical provider definition so that providers receive a deterministic definition tuple without
> importing native Pydantic models or trusting unbounded schema data.

## Single responsibility

CAH-038 owns `ProviderToolDefinition` construction and the atomic bridge from CAH-031 descriptors
and Pydantic-generated input schemas into that value. It owns no call, result, continuation,
history, context, fake-provider, dispatch, argument-parser, or runtime argument-key behavior.

## Scope

- Add the immutable, SDK-free `ProviderToolDefinition` value with exact fields `name`, `description`,
  `parameters_json`, and `required_keys`. The schema is retained only as a bounded canonical JSON
  string plus its immutable required-name tuple, never as a mutable mapping.
- Admit only the closed, flat JSON Schema Draft 2020-12 subset below.
- Apply O(1) cardinality gates, signed-64-bit schema-integer checks, one non-resetting validation-work
  budget, a shape-directed fresh copy, and an incremental canonical-byte limit.
- Add `build_provider_tool_definitions(registry) -> tuple[ProviderToolDefinition, ...]`, the sole
  bridge from the CAH-031 registry and its native Pydantic request models to provider definitions.
  Put this integration bridge in top-level `src/code_assist_harness/tool_definitions.py`, outside the
  provider package that owns the SDK-free value.
- Preserve registry order and publish either the complete converted definition tuple or no tuple.
- Keep provider SDK, protocol, TUI, filesystem, subprocess, network, transcript, and model behavior
  unchanged.

## Locked contract

### Closed flat schema grammar

`ProviderToolDefinition` is created only through
`provider_tool_definition(name, description, candidate)`, for already-canonical direct candidates,
or the private trusted-generator path used by `build_provider_tool_definitions`. Callers cannot
inject `parameters_json` or `required_keys` into the frozen value. It contains exact built-in strings `name`, `description`, and
`parameters_json`, plus `required_keys: tuple[str, ...]`. `parameters_json` is the compact,
sorted-key, strict-Unicode encoding admitted by the bounded pipeline below; it is the sole stored
schema representation. Its decoded root contains exactly `type`, `properties`, `required`, and
`additionalProperties`; `type` is
exactly `"object"`, `additionalProperties` is exactly `false`, and zero through 32 properties are
allowed. A direct canonical candidate's `required` collection must contain every property name
exactly once, with no missing, additional, or duplicate name. The trusted generated mode instead
admits the exact Pydantic-required subset and default placement described below, then intentionally
rebuilds canonical `required` from every property in property-name UTF-8 byte order. The frozen
definition therefore carries the exact model-required name set that CAH-039 later enforces at
runtime, independently of trusted Python construction defaults.

`required_keys` is the exact same ordered tuple encoded in the canonical `required` array. The
constructor validates both from one fresh candidate before storing either. The only materialization
API is `materialize_parameters() -> dict[str, object]`, which decodes the already bounded, flat
canonical string into a fresh built-in JSON object for CAH-032 request projection or CAH-036 SDK
mapping. Callers cannot mutate the definition through that fresh object; a second call returns a
distinct equal tree. Decode/root-shape failure is a content-suppressed programmer invariant, not
provider input or a repair opportunity.

`ProviderToolDefinitionError` is the sole construction/bridge failure. It has code
`invalid_provider_tool_definition` and fixed message `Provider tool definition is invalid.` Its
string and representation contain only that code/message. Constructor, generator-pair, schema-drift,
incremental-encoder, and impossible materialization failures use it without exception chaining,
candidate content, Pydantic diagnostics, or a partial tuple.

The table below is the canonical/direct/post-canonical grammar. The trusted generated source has the
separate, explicitly consumed root/property annotation and default exceptions listed in the bounded
pipeline; those source-only keys never enter the frozen schema.

| Canonical location / property type | Required keywords | Optional keywords | Rejected examples |
| --- | --- | --- | --- |
| root object | `type`, `properties`, `required`, `additionalProperties` | none | `$ref`, `$defs`, unions, combinators, nested objects |
| `string` property | `type: "string"` | `description`, `enum`, `pattern`, `minLength`, `maxLength` | `format`, `default`, `const`, arrays |
| `integer` property | `type: "integer"` | `description`, `enum`, `minimum`, `maximum` | floats, `multipleOf`, exclusive bounds, `default` |
| `boolean` property | `type: "boolean"` | `description`, `enum` | numeric or string constraints, `default` |

- Tool/property names and the tool description must be exact built-in `str` values. Names match
  `[a-z][a-z0-9_]{0,63}` and the description is non-empty and at most 1,024 strict UTF-8 bytes. Apply
  the O(1) 64/1,024-character necessary ceilings before regex, scalar inspection, UTF-8 encoding, or
  canonicalization. Every schema string is a valid Unicode-scalar sequence, contains no literal NUL,
  round-trips through strict UTF-8 unchanged, and is never normalized.
- CAH-031 owns the inventory-side descriptor grammar. Because the integration bridge cannot make the
  provider-domain value import the registry, CAH-038 independently re-admits the same exact
  `[a-z][a-z0-9_]{0,63}` grammar. Parity tests mutate both boundaries without a reverse import.
- Candidate containers and scalars must be exact built-in `dict`, `list`, `str`, `int`, and `bool`
  values in their admitted positions; arbitrary mappings, sequences, iterators, and subclasses are
  rejected before calling their hooks. This makes the claimed cardinality gates and bounded copy
  independent of caller-defined Python behavior.
- Every schema integer is a non-boolean value in the inclusive signed 64-bit range
  `-9,223,372,036,854,775,808` through `9,223,372,036,854,775,807`. Length bounds are non-negative
  and satisfy `minLength <= maxLength`; numeric bounds satisfy `minimum <= maximum`.
- JSON Schema `minLength`/`maxLength` count string characters, not strict-UTF-8 bytes, and the flat
  grammar has no portable exact expression for CAH-024's aggregate byte or component-count budget.
  M2 path definitions may advertise `maxLength: 4095` only as a coarse necessary character cap;
  they must not claim it proves the 4,095-byte, 256-component, or 255-byte-name native invariant.
  CAH-039's strict native request validation remains authoritative.
- An `enum` is non-empty, contains at most 256 unique values of its declared scalar type, and
  preserves admitted order. Integer enums reject booleans and out-of-range values. Unknown fields,
  wrong scalar types, nested schemas, arrays as property types, and every keyword outside the table
  fail closed.

### Bounded canonicalization pipeline

Construction uses this exact order and publishes nothing until every stage succeeds:

1. Validate the exact built-in definition name and description with O(1) character gates, then
   inspect only expected exact built-in root containers.
2. Apply O(1) `len(...)` gates before iteration. A direct constructor candidate has exactly the four
   canonical root entries and at most six entries per property. A trusted generated-schema candidate
   may additionally have one root `title`, one root `description`, and one property `title` plus one
   property `default`, so it has at most six root entries and eight per property before those
   annotations are consumed.
   `properties` and any present `required` have at most 32 and every enum has at most 256 values.
3. Build a new candidate with a shape-directed copier under one non-resetting 16,384-unit work
   budget. In generated-schema mode, that same pass recognizes and discards only root `title` and
   `description`, property `title`, and property `default` at those exact expected positions; it never
   runs a generic recursive strip/filter pre-pass. Annotation values must be exact built-in strings,
   and defaults exact
   built-in scalars compatible with the declared property type. Their keys and values are checked and
   charged before omission. Charge every visited container, member, and list item plus every Unicode
   scalar. Before iterating a string or collection, require its O(1) length to fit the remaining
   applicable budget.
4. Validate scalar types, signed-64-bit integers, keyword combinations, bounds, enum uniqueness, and
   mode-specific required/default membership. Direct mode requires every property exactly once in
   `required` and permits no `default`. Trusted generated mode uses this fixed producer contract:

   | Model | Generated `required` | Generated default-bearing properties |
   | --- | --- | --- |
   | `ListFilesRequest` | key absent | `path`, `recursive`, `max_depth`, `max_items` |
   | `StatPathRequest` | exact list `path` | none |
   | `ReadFileRequest` | exact list `path` | `start_line`, `max_lines`, `max_bytes` |
   | `SearchTextRequest` | exact list `query` | `path`, `max_depth`, `max_matches` |

   The all-default list model must omit the root `required` key; an injected empty list is drift.
   For the other models, `required` must be one exact built-in list with the expected unique known
   subset. Each omitted property must carry exactly one compatible generated `default`, and each
   required property must omit `default`; unknown/duplicate required names, missing or misplaced
   defaults, and a default on a required field fail. After charging and omitting defaults, order at
   most 32 properties by property-name UTF-8 bytes and rebuild `required` from every property.
5. Feed only the fresh admitted candidate to
   `json.JSONEncoder(ensure_ascii=False, separators=(",", ":"), sort_keys=True,
   allow_nan=False).iterencode(...)`. Strictly UTF-8 encode each chunk and stop before retaining the
   16,385th byte.
6. Freeze `parameters_json` and its matching immutable `required_keys` only after the incremental
   encoder admits at most 16,384 bytes. Retain no candidate container.

The work budget never restarts for a property or enum. The implementation never calls `deepcopy`,
retains caller-owned containers, generically traverses or strips an unexpected subtree, sorts an
over-bound collection, or serializes an unvalidated candidate. A huge ignored annotation fails its
O(1) length/work gate rather than evading accounting; an annotation subclass fails before hooks.
Cycles and deep/wrong-shaped containers fail at the field where the flat grammar rejects them.
Numeric overflow fails before encoding. Defensive serializer `RecursionError` or `ValueError` maps
to one fixed content-suppressed construction failure.

### CAH-031 bridge and ownership

- `build_provider_tool_definitions(registry) -> tuple[ProviderToolDefinition, ...]` is a pure harness
  integration bridge in `tool_definitions.py`. It walks `registry.entries` once in registry order,
  reading each exact `read_tool.descriptor.input_model`. The only trusted schema-generation calls are the exact
  class identities of the four closed M2 native Pydantic input models, paired with `list_files`,
  `stat_path`, `read_file`, and `search_text`. An arbitrary model, subclass, callable, or swapped
  name/model pair fails before `model_json_schema()` or any caller-defined hook executes. This is an
  explicit trust in four repository-owned generators, not a claim that schema generation is bounded
  for arbitrary models.
- Generated output is still boundary data. The bridge may discard only annotation-only root
  `title`/`description`, property `title`, and Pydantic-emitted property `default` fields at the exact
  positions above, within the same bounded shape-directed admission pass. It has no generic
  annotation-removal walk. It rejects every other
  unsupported keyword, annotation position, hook-bearing value, or shape. It validates the exact
  real-producer required/default pairing above before it makes every advertised property
  model-required, and returns an immutable ordered tuple only when every descriptor succeeds.
- There is no hand-maintained second definition list. `ProviderToolDefinition` has no `from_descriptor`
  method, CAH-031 does not import provider-domain models, and the provider-domain package does not
  import the read registry. The top-level integration bridge is the only module allowed to import
  both contracts.
- Definition names are unique because CAH-031 already rejects duplicate descriptor names; the bridge
  still fails atomically if the input violates that invariant. M2 produces exactly four definitions,
  while a later request may carry at most 16.
- The canonical `required` names are data in the frozen definition. CAH-038 does not inspect model
  call arguments. The pre-Pydantic exact-key gate, including rejection of an omitted defaulted field
  or an additional field, belongs to CAH-039 after pair-preserving JSON admission.
- Ordinary representations and fixed failures omit description and schema content, source objects,
  Pydantic diagnostics, and candidate values. No provider or model starts during definition
  construction.

## Reviewability budget

- **Estimated production-code churn:** 275-425 changed lines.
- **Delivered production-code churn:** Not started; replace with additions plus deletions before Done.
- **Counted paths:** `src/code_assist_harness/` and `tui/src/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-031 descriptor/Pydantic schema producer ->
  bounded definition bridge -> immutable provider-definition consumer.
- **Split rule:** Stop and refine another story before review if this unit acquires runtime argument
  admission, provider request/history behavior, or is likely to exceed roughly 600 production lines.

## Acceptance criteria

1. `ProviderToolDefinition` is immutable, SDK-free, content-suppressed, stores only exact
   `name`/`description`/`parameters_json` strings plus `required_keys`, and admits only the exact
   schema grammar, integer range, and byte limits above.
2. Shape and cardinality checks bound work before traversal, uniqueness, sorting, or serialization;
   the fresh canonical copy shares no mutable container with its caller.
3. One global 16,384-unit validation-work budget and one incremental 16,384-byte canonical encoder
   fail atomically without subtree budget resets, excess-byte retention, or interpreter text.
4. Canonical `properties` and `required` order is deterministic; stored `required_keys` exactly
   matches the encoded array, and fresh `materialize_parameters()` output shares no mutable value
   with the definition or another call so CAH-032/036 can project it safely and CAH-039 can enforce
   the same model-facing key set.
5. The bridge invokes only the exact four trusted CAH-031 Pydantic model identities, validates their
   exact partial-or-absent `required` and default pairing, consumes only expected root
   `title`/`description` and property `title`/`default`
   annotations inside the bounded shape-directed pass, makes every field required, and publishes all
   definitions or none.
6. No call/result/history/context/fake, dispatch, parser, runtime key gate, provider SDK, protocol,
   TUI, filesystem, subprocess, or network behavior is introduced.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Closed schema happy path | Construct string, integer, and boolean definitions in different input orders; reject missing/additional/duplicate required names | Unit | Byte-identical canonical schemas; properties and exact required names in UTF-8 order |
| Scalar and semantic bounds | Exercise signed-64-bit endpoints/overflow, booleans-as-integers, min/max relations, scalar Unicode, NUL, and unknown keywords | Unit | Exact admission at endpoints and one fixed content-safe rejection outside them |
| O(1) cardinality gates | Exercise properties 31/32/33, enum 255/256/257, huge late-sentinel containers, and hostile container/scalar subclasses | Unit | Over-limit or non-built-in inputs stop before caller hooks, element visits, uniqueness, sorting, or encoding |
| Non-resetting work budget | Use many individually small fields whose aggregate work is 16,383/16,384/16,385 units | Unit | One aggregate budget; no per-property or per-enum reset |
| Incremental encoder | Produce canonical output at 16,383/16,384/16,385 UTF-8 bytes and inject serializer failures | Unit | Excess byte is never retained; `RecursionError`/`ValueError` maps to fixed failure |
| Path-schema honesty | Inspect all native path properties and use multibyte values whose character and UTF-8 byte counts differ | Schema/bridge | Any `maxLength: 4095` is only a coarse character cap; no schema or lesson claims exact native byte/component/name enforcement |
| Immutable carrier and fresh materialization | Mutate every source container and every object returned by `materialize_parameters()`; call it twice; supply cyclic/deep wrong-shaped candidates and inject impossible decode/root drift | Unit | Definition retains only canonical JSON/required tuple; calls return distinct equal built-in trees; invalid subtree is neither copied nor recursively traversed; impossible stored-value failure is content-suppressed |
| Bounded annotation handling | Inject root title/description, property titles/defaults, huge annotation strings, hostile subclasses/hooks, nested/misplaced annotations, and an unrelated keyword | Unit/bridge | Only expected annotations are charged and omitted inside the shape-directed pass; no generic pre-pass, hook, sort, or encoder runs |
| Real-producer required/default parity | Snapshot `model_json_schema()` for all four exact documented models, including their root `description`, absent `required` for all-default `ListFilesRequest`, and partial lists for the other three; mutate root annotation presence/type/position, required presence/order/membership, and each required/default pairing | Integration | The actual Pydantic producers pass; every drift fails with exact `ProviderToolDefinitionError` before canonical publication; canonical output nevertheless omits root annotations and requires every property |
| Trusted generator set | Use the exact four CAH-031 model identities, then swap a model/name pair and supply model subclasses/callables with generation hooks | Integration/static | Only four repository-owned generators run; foreign hooks remain untouched and failure publishes no definition tuple |
| Atomic registry bridge | Snapshot all four CAH-031 definitions; inject unsupported, duplicate, defaulted, and drifted generated-schema candidates after the trusted generation seam | Integration | Registry order, only bounded in-pass title/default omission, exact source pairing, every canonical property required, all-or-nothing publication, zero provider starts |
| Ownership exclusion | Import/static policy and spies | Policy | Only top-level `tool_definitions.py` imports both registry and provider-neutral definition contracts; no reverse import, duplicate definition list, argument inspection, dispatch, provider SDK, filesystem, network, protocol, or TUI work |

## Validation

- Add focused definition-constructor tests for every grammar row, semantic relationship, strict
  scalar rule, integer endpoint, and canonical-order invariant.
- Use length/visit/sort/encoder spies for 32/33 properties, 256/257 enum values, huge strings and
  containers, aggregate work 16,383/16,384/16,385, and canonical bytes 16,383/16,384/16,385.
- Prove root `title`/`description`, property `title`, and property `default` are handled only inside the bounded
  shape-directed pass: huge annotation values reject before scalar traversal or encoding, hostile
  annotation subclasses invoke no hooks, and misplaced/nested annotations fail without a recursive
  removal walk.
- Inject serializer `RecursionError` and `ValueError` and assert the fixed failure reveals no schema,
  Pydantic diagnostic, secret-like sentinel, or candidate representation.
- Snapshot the four definitions produced from the exact real CAH-031 model identities. Reject a
  swapped/foreign/subclassed model before its generation hook; after trusted generation, inject one
  schema drift at a time, including absent/partial `required` and required/default-pair mutations, and
  prove an invalid member publishes no partial tuple and starts no provider work.
- Run focused Python type, lint, format, and tests, then
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done. All validation is model-free
  and network-free.

## Documentation impact

Keep this story and its concise Markdown lesson synchronized with the implementation, and update the
provider-interface, tool-system, glossary, indexes, backlog, and planning note when the unit ships.
The lesson's text diagram locates the definition bridge between CAH-031 and provider requests. Do not
add or revise presentation files.

## Exclusions

- `ProviderToolCall`, `ProviderToolResult`, `ProviderOpaqueContinuation`, ordered history, CAH-030
  context projection, request-size admission, and strict-fake behavior; CAH-032 owns those.
- Raw JSON parsing, duplicate-name detection, numeric-token admission, native input validation,
  lookup, dispatch, execution, and result replay.
- The pre-Pydantic exact required-key gate; CAH-039 owns that runtime boundary.
- OpenAI mapping, MCP discovery/transport, remote tools, protocol/TUI events, transcripts, writes,
  approvals, subprocesses, network access, and general JSON Schema support.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Descriptor name and native model are CAH-031 inputs; canonical definition name/schema are fresh provider-facing values. No filesystem or path identity exists here. |
| End-to-end contract | Trace the exact four CAH-031 descriptor/model identities -> trusted generation -> bounded in-pass annotation handling -> `ProviderToolDefinition` -> CAH-032 request tuple, and separately trace `required` names -> future CAH-039 key gate. |
| Failure and atomicity | Every constructor/bridge failure publishes no definition tuple and starts provider work zero times; cancellation/deadline are N/A because conversion is synchronous and bounded. |
| Reachable boundaries | Drive property, enum, work, integer, string, annotation, and byte edges through both the constructor and real four-descriptor bridge; prove foreign model and annotation hooks remain untouched. |
| Closed grammar and cardinality | Label the canonical grammar separately from generated-source exceptions; snapshot the exact root shape, required-name order, duplicate policy, six-entry generated root, 32-property and 256-enum ceilings, shared work budget, and incremental byte ceiling. |
| Artifact parity | Story, lesson, diagram, pseudocode, conceptual docs, and tests use the same gate -> copy -> validate/order -> encode -> freeze stage order. |
| Independent lenses | Security/identity review fixed exact types, fresh copies, and content-suppressed errors; real-producer composition review added all four documented Pydantic snapshots, root-description admission, exact required/default drift mutations, and independent name-grammar parity; limit/runtime review added O(1) generated-root/property gates, one work budget, incremental encoding, and hook spies. |

## Definition of done

1. Every schema variant, semantic relation, trusted-generator/annotation bridge path, and happy path
   has deterministic evidence, plus meaningful malformed, over-bound, hook, drift, mutation, and
   serializer-failure paths.
2. Integer, property, enum, validation-work, and encoded-byte limits are tested below, at, and above
   their boundaries through the lowest useful constructor and the real bridge.
3. Definitions and failures reveal no schema content, Pydantic diagnostic, secret, host path, or
   source-container representation.
4. Public contracts are typed and documented; only the closed flat schema subset is accepted.
5. Focused checks and the canonical offline `./scripts/check` pass without a live model or network.
6. Provider, protocol, transcript, and TUI behavior remain unchanged and are covered by the nearest
   import/integration parity assertion.
7. The Markdown lesson includes exact implementation and failure-test excerpts after code exists;
   no presentation work is introduced.
8. Conceptual docs, indexes, backlog, planning note, story status, and lesson status agree at Done.
9. Delivered production churn is recorded within the planned 275-425 range or the unit is split
   before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- `provider/models.py` owns the SDK-free definition value; top-level `tool_definitions.py` owns only
  the typed registry bridge and its one-way imports.
- Provider-definition unit tests for closed schema admission, immutability, canonical bytes, and
  bounded failure behavior.
- A real-registry bridge snapshot proving exact four-definition order, exact required names, and
  atomic failure.
- Import and interaction evidence proving no provider start, argument inspection, dispatch, or
  reverse registry/provider dependency.

## Deferred work

- CAH-032 consumes the immutable definition tuple in bounded provider requests and adds calls,
  results, continuations, history grammar, context projection, and strict-fake evidence.
- CAH-039 admits pair-preserved model arguments and enforces the definition's exact required key set
  before native Pydantic validation or defaults.
- CAH-036 later maps the provider-neutral definitions to OpenAI; a future milestone may re-admit an
  MCP catalog through a generalized registry boundary.
