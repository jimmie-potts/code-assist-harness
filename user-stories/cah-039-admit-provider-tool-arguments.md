# CAH-039 - Admit one provider tool argument object

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E4 - Tool registry and controlled
  execution
- **Learning emphasis:** Core learning unit
- **Dependencies:** CAH-031, CAH-032, CAH-038
- **Lesson:** [Provider tool-argument admission](../docs/lessons/cah-039-provider-tool-argument-admission.md)
- **Review focus:** Raw-JSON trust-boundary admission, exact failure precedence, and zero-effect
  preparation of one typed native request.

## User story

> As a user, I want every model-proposed read-tool argument admitted through one bounded,
> duplicate-aware harness path so that malformed or ambiguous JSON cannot reach repository I/O.

## Planning PR scope

- **Contract neighborhood:** Provider call -> raw JSON admission -> typed native request.
- **Why this story is separate:** The JSON trust-boundary engine is reusable by the one-round-trip
  and bounded-loop stories. Keeping it here leaves CAH-034 responsible for orchestration rather than
  parser construction.
- **Review lenses:** Closed JSON grammar and interpreter bounds; lookup/key/type failure precedence;
  and zero-effect handoff into later dispatch.

## Single responsibility

Transform one CAH-032 raw provider call into either one typed, non-executed CAH-031 invocation or one
fixed safe tool error. This story performs no tool dispatch, filesystem access, context construction,
provider start, loop transition, transcript write, protocol change, or TUI work.

## Scope

- Add immutable provider-neutral `ReadToolCatalog` and `PreparedReadToolCall` local values. Add one
  pure `prepare_read_tool_call(call: ProviderToolCall, catalog: ReadToolCatalog) ->
  PreparedReadToolCall | ProviderToolResult` admission operation.
- Add one `build_read_tool_catalog(registry) -> ReadToolCatalog` factory whose only public input is the exact CAH-031
  registry. It invokes CAH-038's sole definition bridge internally, pairs exact registry entries
  with those definitions, and re-exposes the resulting ordered tuple.
- Put the catalog, pair-preserving parser, and prepared-call API in top-level
  `src/code_assist_harness/tool_admission.py`. This integration module may import CAH-031 and the
  CAH-032/038 provider-neutral value contracts, but no provider SDK, adapter, port, operation, or
  start path.
- Own exact lookup precedence, structural/numeric preflight, constant-safe pair decoding,
  every-depth duplicate rejection, exact required-key admission, and strict native Pydantic
  validation.
- Return only `call_id`, the catalog identity, its exact bound CAH-031 `read_tool` entry, and a
  validated native `request` on success; return one canonical CAH-032 `ProviderToolResult` on an
  expected rejected call. The original CAH-032 call remains in admitted response/history state and
  is not duplicated inside the prepared value.

## Locked contract

### Atomic catalog and lookup

- Composition constructs one immutable catalog from one exact CAH-031 registry before provider
  work. `build_read_tool_catalog(registry)` is the only public construction path and invokes
  CAH-038's `build_provider_tool_definitions(registry)` itself; callers cannot supply a second
  definition tuple. The catalog retains that registry's identity and the bridge's exact ordered
  definition tuple. Each catalog entry pairs the registry's exact CAH-031 entry—including
  its descriptor/executor identity—with the same-name definition and exact required-key tuple.
  Duplicate, missing, reordered, name-mismatched, foreign-entry, or required-key-identity drift fails
  catalog construction atomically. CAH-039 trusts each already-valid CAH-038 definition value; it has
  no second schema grammar with which to detect arbitrary same-name schema drift, repair a definition,
  or later join independently held registries/definitions.
- `ReadToolCatalog` exposes the stable opaque `identity`, exact `registry`, bridge-produced
  `definitions`, and exact-name entry lookup used by both preparation and CAH-034. Its identity token
  is created once with the catalog and is compared only by `is`.
- `ReadToolCatalogEntry` contains exactly `read_tool: ReadTool`,
  `definition: ProviderToolDefinition`, and `required_keys: tuple[str, ...]`. Catalog
  `lookup_exact(name) -> ReadToolCatalogEntry | None` returns that immutable owned object; it has no
  forwarding `descriptor` or executor field. Native validation therefore uses
  `entry.read_tool.descriptor.input_model` from CAH-031's named descriptor contract. Its
  `required_keys` is the exact tuple object from `definition.required_keys`, not a copied or parsed
  second source.
- `ReadToolCatalogError` is the sole catalog/invariant failure. It has code
  `invalid_read_tool_catalog` and fixed message `Read tool catalog is invalid.` Its string and
  representation contain only that code/message. The factory catches CAH-038 definition failure and
  maps it without chaining; name/order/required-key-identity drift, a foreign registry entry, and CAH-034 cross-catalog
  identity failure use this same non-replayable value. It is never converted into a
  `ProviderToolResult`.
- `prepare_read_tool_call` first performs exact, case-sensitive name lookup. An absent name returns
  CAH-031's compact fixed `unknown_read_tool` error before scanning or decoding `arguments_json`.
  Within CAH-032's already-admitted lowercase ASCII name grammar, aliases and prefixes are absent
  and no normalization or case folding occurs. Uppercase, non-ASCII, or otherwise malformed names
  fail at the CAH-032 carrier boundary and never reach this lookup.
- A successful lookup does not authorize execution. The prepared value is local, immutable, and has
  a content-suppressed representation; only CAH-034 may later cross its dispatch checkpoint.

### One bounded structural and numeric preflight

- CAH-032 has already bounded the complete raw argument string to 16,384 strict UTF-8 bytes. CAH-039
  scans that complete value exactly once with an iterative quote-and-escape-aware state machine.
  Braces, brackets, numeric-looking text, and escaped quotes inside strings do not affect structural
  or numeric state.
- The root must be one JSON object at structural depth 1. Objects and arrays may nest through depth
  64; depth 65, mismatched/unfinished containers, trailing structural content, or a non-object root
  is `invalid_read_tool_input`. The byte ceiling bounds width and the explicit depth ceiling bounds
  height; neither counter resets for a subtree.
- Outside strings, every numeric token must use exact JSON integer grammar and fit the inclusive
  signed 64-bit range before Python conversion. Booleans are not integer tokens. Fractions,
  exponents, leading-zero forms other than `0`, signed overflow, and a 5,000-digit candidate fail in
  preflight. Numeric-looking strings remain byte-for-byte text.
- Preflight is not a second semantic JSON parser. It owns delimiter, quote/escape, root/depth, and
  numeric-token admission only; the next stage still owns complete JSON syntax and values.

### Pair-preserving decode and duplicate grammar

- Only preflighted input reaches `json.loads`. It uses a rejecting `parse_constant` callback for
  `NaN`, `Infinity`, and `-Infinity`, a bounded integer callback as defense in depth, and an
  `object_pairs_hook` that retains ordered decoded member pairs instead of constructing a dictionary.
- A non-recursive walk visits the complete decoded tree under the already admitted byte/depth work
  bounds. At every object depth, it compares decoded names by exact Unicode code point and rejects a
  repeated name before any dictionary exists. Thus `"path"` conflicts with `"pa\u0074h"`; same-value,
  conflicting-value, reversed, nested, and array-contained duplicates all have one outcome. There is
  no case folding or Unicode normalization.
- Only after the duplicate walk succeeds are pair nodes converted into normal dictionaries. A
  defensive decoder or conversion `RecursionError`/`ValueError` maps to the fixed
  `invalid_read_tool_input` result without exception text, partial values, or a later-stage call.

### Exact key gate and native validation

- The decoded root key set must equal the CAH-038 definition's canonical required names exactly.
  Missing keys—including native fields with defaults—and additional keys fail before Pydantic. This
  model-facing rule does not change direct trusted Python construction, where native defaults remain
  available.
- Only the exact key set reaches the descriptor's strict, frozen Pydantic v2 input model. Type,
  field-range, query/path scalar, and operation-specific failures map to
  `invalid_read_tool_input`; no coercion, raw validation detail, supplied value, path, or query enters
  the error.
- For `list_files`, `stat_path`, `read_file`, and `search_text`, native path fields inherit
  CAH-024/026's inclusive 4,095-byte, 256-normalized-component, and 255-byte-name admission. This
  check occurs only at the existing strict-Pydantic stage: CAH-032's 16-KiB carrier gate, unknown-tool
  lookup, structural/numeric preflight, pair decode/duplicate rejection, and required-key check retain
  their current precedence. An over-bound known-tool path becomes `invalid_read_tool_input` before
  CAH-031 dispatch or filesystem work.
- `PreparedReadToolCall` contains exactly `call_id`, `catalog_identity`, `read_tool`, and `request`.
  It never contains a duplicate name/raw call, provider SDK object, decoded pair node, filesystem
  result, instruction scope, or context. `prepare_read_tool_call` returns this value or a correlated
  CAH-032 `ProviderToolResult` directly—there is no third wrapper type. CAH-034 dispatches only through the same catalog-owned
  registry and exact entry. Catalog identity uses exact object identity (`is`), not equality: a
  prepared value from a distinct catalog over the same registry, or from another registry, is a
  `ReadToolCatalogError` before handler I/O, result replay, or follow-up provider work—not a
  model-correctable tool error.

### Failure precedence and effects

The exact stages are:

```text
lookup -> structural + numeric preflight -> constant-rejecting pair decode
       -> iterative duplicate walk -> dictionary construction
       -> exact-key gate -> strict Pydantic validation -> prepared call
```

The first failure wins and no later stage runs. Expected rejections produce only
`unknown_read_tool` or `invalid_read_tool_input`; internal catalog/programmer invariant failures are
exact `ReadToolCatalogError` values, not model-correctable tool results. Every outcome is synchronous,
bounded, provider-neutral, and side-effect free.

## Reviewability budget

- **Estimated production-code churn:** 300-450 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-032/033 admitted raw call -> catalog-bound
  lookup and argument gates -> immutable prepared invocation -> CAH-034 guarded consumer.
- **Split rule:** split before review if this unit gains dispatch, filesystem access, context merge,
  provider iteration, a general JSON-Schema engine, or is likely to exceed roughly 600 production
  lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One registry-only factory owns the exact CAH-031 registry identity, internally obtains the
   CAH-038 definition tuple, atomically pairs every exact registry entry with its same-name
   definition/required-key tuple, and performs one exact lookup before any argument work.
2. One complete-value scanner enforces the 16-KiB, root-object, 64-level, delimiter, quote/escape,
   and signed-64-bit integer-only grammar before Python numeric conversion.
3. Constant-safe pair decoding plus one iterative full-tree walk rejects repeated decoded names at
   every admitted object depth before dictionary construction.
4. Exact required keys are admitted before strict native Pydantic validation or default application.
   The exact public return is `PreparedReadToolCall | ProviderToolResult`; a prepared value has only
   `call_id`, `catalog_identity`, `read_tool`, and `request` and remains non-executed/content-suppressed.
5. Every expected rejection uses one fixed, correlated CAH-032 error envelope and causes zero key,
   validation, dispatch, filesystem, context, provider, transcript, protocol, or TUI work after its
   failing stage.
6. Public APIs are typed/documented, deterministic tests are network-free, and the linked lesson
   teaches the trust boundary and failure precedence without implying dispatch.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1 | Static/signature tests prove `build_read_tool_catalog` accepts only one registry and is the sole public path; callers cannot inject definitions. Catalog tests compare all four exact `read_tool`, `definition`, and `required_keys` fields, assert `entry.required_keys is entry.definition.required_keys`, and retain the re-exposed definition tuple. Inject CAH-038 failure plus cardinality/name/order/exact-reference/required-key-identity drift and assert exact unchained `ReadToolCatalogError` before provider work; arbitrary schema revalidation is explicitly CAH-038's responsibility. A prepared value from a distinct catalog over the same registry and one from a same-shaped second registry both fail by `is` identity with that same exact error before handler I/O, replay, or provider follow-up. Unknown but CAH-032-valid exact names such as `readfile` and `read_files` return `unknown_read_tool` with zero scanner/decoder/key/Pydantic calls even when arguments are hostile; CAH-032 dependency tests prove malformed case/Unicode names cannot reach this unit. |
| 2 | CAH-032 dependency evidence admits complete argument values at 16,383/16,384 bytes and rejects 16,385 before CAH-039; the CAH-039 public path scans both reachable endpoints, while a focused scanner test retains the defensive over-bound rejection. Object/array depths 63/64/65 exercise quoted braces/brackets, escaped quotes/backslashes, mismatched/unfinished containers, trailing values, and non-object roots. Signed-64 endpoints and valid `-0` pass; adjacent overflow, illegal leading zeros, fractions, exponents, and a 5,000-digit integer prove bounded failure before Python conversion. |
| 3 | `NaN`/infinities, injected decoder `RecursionError`/`ValueError`, and same-value/conflicting/reversed/escape-equivalent duplicates at root, nested objects, and objects inside arrays assert exact stage counters. Deepest admitted duplicates fail before dictionary/key/Pydantic work; numeric-looking and delimiter-containing strings remain unchanged. |
| 4 | Signature/type tests lock the direct `PreparedReadToolCall | ProviderToolResult` return and exact prepared fields, with no wrapper carrier. A native request with defaults proves an omitted model key and an extra key stop at the exact-key gate, wrong types reach only strict Pydantic, and each known path field exercises 4,094/4,095/4,096 total bytes, 254/255/256 name bytes, and 255/256/257 components. Valid endpoints yield one immutable `PreparedReadToolCall`; above-bound paths map to `invalid_read_tool_input` with zero dispatch; direct native construction still applies defaults. Unknown-tool plus over-bound path still stops at lookup, malformed JSON stops before decode/key/Pydantic, and extra-key plus over-bound path stops at the exact-key gate. |
| 5 | Leak sentinels in names, values, paths, queries, decoder/Pydantic errors, pair nodes, and prepared values never enter fixed errors or representations. Spies prove zero registry execution, repository I/O, instruction/context work, provider starts, transcript writes, or protocol/TUI events. |
| 6 | Import-policy tests allow only CAH-031 plus CAH-032/038 provider-neutral value contracts and forbid filesystem/provider SDK/adapter/port/operation/start, transcript, protocol, and TUI dependencies; focused tests and the canonical non-live gate pass. |

## Validation

- Run focused catalog and argument-admission tests with deterministic spies and no provider/network.
- Assert every stage counter and mutation case in the table, including deletion mutations for
  lookup-first order, structural/numeric preflight, `parse_constant`, pair preservation, iterative
  duplicate detection, exact-key admission, and strict Pydantic validation.
- Separate public producer evidence from defense-in-depth helper evidence: do not construct an
  impossible `ProviderToolCall` merely to make CAH-039 appear to own CAH-032's name or byte limit.
- Run `uv run ruff check .`, `uv run ruff format --check .`, focused pytest, and
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check`.

## Documentation impact

- Keep [Tool system](../docs/tool-system.md), [Agent loop](../docs/agent-loop.md),
  [Safety model](../docs/safety-model.md), and [Evaluation](../docs/evaluation.md) aligned with this
  sole pre-dispatch admission owner.
- Keep the linked lesson's diagram, pseudocode, and test stages in the exact order above.
- Add no presentation artifact.

## Exclusions

- Tool execution, repository I/O, instruction discovery, context selection, checkpoints, and loops.
- Provider-response admission, adapter mapping, model starts, transcripts, protocol, and TUI changes.
- General JSON Schema, floating-point arguments, parallel/multiple calls, MCP, writes, commands,
  approvals, subprocesses, or network tools.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Keep the catalog object/token identity, exact CAH-031 registry/entry identity, bridge-produced CAH-038 definition and required-key tuple, CAH-032 raw call, prepared `call_id`/typed request, and later result distinct; the prepared value does not duplicate the raw name/arguments, and path identity remains inside the later handler. |
| End-to-end contract | Trace registry -> sole catalog factory -> internal CAH-038 bridge -> `catalog.definitions` request -> CAH-032/033 call carrier -> lookup/preflight/decode/key/type gates -> catalog-bound prepared invocation -> CAH-034 identity guard -> CAH-031 `dispatch_bound(entry, request)`. |
| Failure and atomicity | Expected call rejection yields one fixed correlated `ProviderToolResult` error and zero typed candidate/tool I/O; CAH-038 failure, detectable catalog identity drift, and cross-catalog/entry mismatch are content-suppressed session failures with zero handler I/O, result replay, or provider follow-up—not tool errors. |
| Reachable boundaries | Drive admitted at-or-below-16-KiB carriers through CAH-032/033 into the public path; exercise 63/64/65 levels, signed-64-bit edges, decoded-name duplicates, and decoder limits there, while impossible carrier states remain explicit helper defense-in-depth tests. |
| Closed grammar and cardinality | Lock lookup-first precedence, one JSON object root, exact property set, code-point duplicate comparison after escape decoding, constant rejection, signed-64-bit integers, and one immutable prepared result or fixed error. |
| Artifact parity | Story, lesson, diagram, pseudocode, tool-system docs, and tests preserve lookup -> preflight -> pair decode -> duplicate walk -> exact-key gate -> strict Pydantic -> prepare, with no dispatch in this unit. |
| Independent lenses | JSON/security review fixed lookup precedence, numeric/depth work, pair-preserved duplicate rejection, and leak-free errors; catalog/handoff review fixed exact `read_tool`/`definition`/`required_keys` identities while removing impossible independent schema-drift detection; parser/runtime review added reachable-carrier, decoder-failure, cross-catalog, and zero-dispatch mutations. |

## Definition of done

- The immutable catalog and sole prepared-call admission path satisfy the full stage matrix.
- Happy path plus malformed, duplicate, overflow, key, type, and leak failures are deterministic.
- Production churn is recorded and remains reviewable; otherwise the unit is split before review.
- The Markdown lesson is updated from planned pseudocode to repository-backed code and test evidence.
- The canonical repository gate passes before the story is marked Done.

## Planned evidence

- Focused catalog and admission tests prove exact lookup, structural/numeric preflight,
  pair-preserved duplicate rejection, exact keys, strict native validation, and zero dispatch.
- Dependency tests distinguish malformed CAH-032 carriers from reachable CAH-039 inputs, while
  focused helper tests retain explicit defense-in-depth bounds.
- Import and interaction checks prove the prepared value opens no filesystem, provider operation,
  SDK/adapter/port,
  transcript, TUI, subprocess, or network path.

## Deferred work

- CAH-034 owns the guarded dispatch, known-error replay, instruction-scope discovery, context merge,
  and one follow-up provider request for a prepared invocation.
- CAH-035 owns repeated bounded loop transitions; CAH-036 owns OpenAI SDK mapping.
- A future generalized MCP port must separately re-admit changing remote catalogs, transports,
  capabilities, schemas, structured results, authentication, deadlines, and cancellation.
