# CAH-031 - Register and dispatch read-only tools

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E4 - Tool registry and controlled
  execution (read-only kernel only)
- **Dependencies:** CAH-027, CAH-028, CAH-029
- **Lesson:** [Read-tool registry](../docs/lessons/cah-031-read-tool-registry.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** How a harness separates tool capability, complete typed instruction-scope
  metadata, dispatch, and side-effect policy before any model can request a tool.

## User story

> As an agent-loop developer, I want the native repository-read tools behind one typed read-only
> registry so that later model tool calls can select a known capability without gaining an
> unreviewed execution path.

## Single responsibility

CAH-031 owns registration, typed instruction-scope extraction, dispatch, and one canonical bounded
success-result projection for the native read tools delivered by CAH-027 through CAH-029. It does
not discover repository instructions, enrich context, define model-facing input schemas, parse
provider arguments, execute an agent loop, expose tool activity through NDJSON, or admit any
side-effecting capability.

## Scope

- Define one generic, immutable registry of harness-owned read tools.
- Give every registered tool one stable name, description, typed input contract, typed result, and
  explicit `read_workspace` capability classification.
- Give every `ReadTool` one pure typed instruction-scope extractor that returns the complete ordered
  set of execution-time canonical request and result-derived scopes required before later result
  replay.
- Pair each tool with an explicit allowlisted native-result projector; after exact result-type
  validation, emit one compact canonical JSON success envelope for the later provider contract.
- Register `list_files`, `stat_path`, `read_file`, and `search_text` in one deterministic order.
- Add `build_read_tool_registry(metadata_reader: RepositoryMetadataReader, text_reader:
  RepositoryTextReader, searcher: RepositoryTextSearcher) -> ReadToolRegistry` as the sole M2
  production factory for those four bound tools.
- Dispatch an already-typed input to exactly one registered implementation.
- Expose exact registry entries for the later CAH-039 catalog and one identity-safe
  `dispatch_bound(read_tool, validated_input)` path that accepts only an entry owned by this
  registry; it imports no provider or prepared-call type.
- Reject duplicate names, unknown tools, mismatched input types, and every capability other than
  `read_workspace` before implementation code runs.
- Prove registry construction and dispatch with native fakes or temporary workspaces only.

## Locked contract

- The Python harness owns `ReadTool`, `ReadToolDescriptor`, and `ReadToolRegistry`; provider adapters,
  the TUI, and repository files cannot register or dispatch tools.
- A descriptor contains exactly `name`, `description`, `input_model`, `result_type`, and `capability`:
  an exact built-in name matching `[a-z][a-z0-9_]{0,63}`, an exact built-in non-empty description of
  at most 1,024 strict UTF-8 bytes, the concrete strict Pydantic request-model class, the concrete
  validated result type, and the literal capability `read_workspace`. Before regex, scalar
  inspection, or encoding, exact-type and O(1) character gates apply 64 to name and 1,024 to
  description; subclasses fail before hooks. Description rejects NUL and lone surrogates, preserves
  admitted Unicode without normalization. CAH-031 is the inventory-side owner of this exact grammar;
  CAH-032 and CAH-038 independently re-admit the same literal at their separate untrusted boundaries,
  with parity tests preventing drift and no reverse provider import. A descriptor contains no callable, JSON Schema, provider object, approval
  decision, or environment value.
- A `ReadTool` pairs one descriptor with one pure `instruction_scopes(validated_result)` extractor,
  one synchronous bounded
  `execute(validated_input)` operation, and one explicit
  `project_result(validated_result)` operation. The input has already passed the native tool's
  Pydantic validation; CAH-031 performs a defensive exact input-type check before execution and an
  exact result-type check before either scope extraction or projection. Each extractor reads only
  reviewed typed result path fields, returns an immutable tuple, and performs no resolution,
  policy, filesystem, network, provider, instruction, environment, clock, global-state, or
  JSON-parsing work. Each projector names the allowed
  fields from its native result (and nested entry/match values) explicitly. It may not use a generic
  `model_dump`, dataclass reflection, `__dict__`, `repr`, or arbitrary-object JSON fallback that could
  expose a future field accidentally.
- The four production extractors are trusted, closed harness code rather than untrusted runtime
  plugins. Import/static policy and interaction tests enforce their intended purity. At runtime the
  registry can validate exact return types, strings, duplicate-free shape, and bounds and can map an extractor that
  raises or returns an invalid value to `invalid_read_tool_result`; it cannot detect or roll back an
  arbitrary side effect or infer the semantically correct candidate order after invoking a Python
  callable and does not claim to do either.
- Registry construction consumes an immutable tuple, exposes it unchanged as
  `entries: tuple[ReadTool, ...]`, preserves that order for discovery, and fails
  atomically on an invalid descriptor, duplicate name, or non-read capability. There is no
  last-registration-wins behavior and no mutation after construction.
- `build_read_tool_registry(metadata_reader, text_reader, searcher)` requires
  `searcher.metadata_reader is metadata_reader`, `searcher.text_reader is text_reader`, and one
  shared `policy` identity before it constructs any descriptor or handler. It binds
  `list_files`/`stat_path` to the supplied metadata reader, `read_file` to the supplied text reader,
  and `search_text` to the supplied searcher, then returns the exact four-entry order above. Identity
  drift raises `invalid_read_tool_registration` before tool or filesystem I/O. Direct
  `ReadToolRegistry(entries)` remains the generic/test constructor, not a second M2 composition root.
- Exact lookup returns the registry's immutable `ReadTool` entry, not a copied descriptor or a
  name-only executor token. `dispatch_bound(read_tool, validated_input)` verifies by object identity
  that the entry belongs to this registry before its exact input-type check or handler call. A
  same-shaped entry from a second registry—including the same descriptor/schema with a distinctive
  handler—fails content-suppressed before either handler runs. The convenience
  `dispatch(name, validated_input)` path uses exact, case-sensitive lookup and delegates to that
  bound path; neither method imports CAH-039 or provider-domain values. Unknown names, foreign
  entries, and input-type mismatches return a
  bounded harness-owned dispatch failure without invoking any tool or echoing the supplied name or
  input. Successful dispatch returns an immutable `ReadToolSuccess` whose content-suppressed
  `output_json` is the canonical envelope specified below and whose local, content-suppressed
  `instruction_scopes` is the complete extracted ordered tuple. Neither value appears in ordinary
  representations. Instruction scopes are harness control-plane metadata: they are not included in
  `output_json`, provider-visible content, protocol, transcript, or diagnostics. The unprojected
  native result does not cross this registry boundary.
- Tool-domain operational failures remain the native tool's bounded result or exception contract;
  the registry neither catches programmer defects as tool results nor converts filesystem content
  into diagnostics. A known native or registry failure carries no instruction scopes. The tuple is
  attached only to a fully validated `ReadToolSuccess`, so later orchestration cannot treat a
  rejected request or invalid result path as admitted instruction scope.
- The M2 registry contains exactly the four native operations delivered by CAH-027 through CAH-029.
  Filesystem
  writes, subprocesses, network access, MCP servers, provider-hosted tools, and dynamically imported
  plugins are structurally inadmissible.
- This is the sole intentional E4 overlap in M2: it teaches registry ownership but does not implement
  general policy composition, approvals, executors, write capabilities, or extension loading.

### Typed instruction-scope extraction

- Every extractor starts its candidate sequence with the execution-time canonical request scope
  captured by the validated native result: `ListFilesResult.canonical_request_scope`,
  `StatPathResult.path`, `ReadFileResult.path`, or
  `SearchTextResult.canonical_request_scope`. Those fields come from each operation's final
  access-time admission and therefore exist even for an empty listing, an empty file slice, or a
  no-match search. The extractor never reads or re-resolves the original `request.path` after
  dispatch and never falls back to that alias.
- After that canonical first candidate, the extractor appends only owner scopes derived from
  provider-visible path records in the exact validated native result. It removes exact string
  duplicates by first occurrence and preserves the resulting order. It does not perform canonical
  or symlink deduplication; CAH-025 freshly admits each captured path and CAH-030 makes repeated
  candidate-owner snapshots idempotent later. CAH-030 requires each discovered bundle's
  `canonical_scope` to equal the captured candidate before merge. If the label is stale, retargeted,
  or unavailable, later work fails the whole transaction rather than retrying the supplied alias.
- The four extractors append result-derived owners exactly as follows:
  - `list_files`: for each returned entry in result order, append the canonical entry path when its
    kind is `directory`, otherwise append the canonical file's parent directory;
  - `stat_path`: append the canonical result path for a directory or its parent for a file;
  - `read_file`: append the canonical result file's parent directory; and
  - `search_text`: append each canonical match file's parent directory in canonical match order.
  The parent of a root-level file is `.`. Omitted, skipped, unavailable, or truncated-away paths are
  absent because they are not present in the provider-visible success result.
- Scope extraction occurs only after exact native-result validation. It must inspect the typed native
  result directly; parsing, walking, consulting the original request alias, or otherwise deriving
  authority from `output_json` is prohibited. The serialized envelope remains data for later replay,
  never a control-plane input. The dedicated list/search `canonical_request_scope` fields and the
  complete local tuple are omitted by every projector and from `output_json`, providers, protocol,
  transcripts, diagnostics, and ordinary representations. Existing stat/read canonical `path`
  fields may remain ordinary allowlisted result provenance, but their control-plane role is never
  serialized.
- Extraction is bounded by the native result contracts: at most 501 pre-deduplication candidates for
  `list_files` (one request plus 500 entries), 201 for `search_text` (one request plus 200 matches),
  and two for `stat_path` or `read_file`. A result that violates its native item bound, an extractor
  that raises, returns a non-string or duplicate label, or exceeds those bounds fails as
  `invalid_read_tool_result` and yields no success value or partial tuple. Production extractor
  purity and exact semantic order are proven by closed composition and interaction/static snapshot
  tests, not inferred from that runtime failure mapping.
- Native defaults remain available to direct Python callers, while the later provider key gate still
  requires the model to supply every advertised field. A wrong input type is rejected before
  extraction or execution.
- CAH-031 does not implement a second path parser or work budget. The exact native request type has
  already inherited CAH-024/026's path admission; CAH-031 checks only exact input type. A forged or
  wrong request type remains `invalid_read_tool_input`, while a provider-originated path failure is
  owned by CAH-039 before this registry can execute.
- An extracted label is not proof of containment by itself. Native execution owns CAH-026 access-time
  admission; only successful execution, exact result validation, complete scope extraction,
  projection, and envelope validation produce `ReadToolSuccess`. CAH-025 and CAH-030 later discover
  and merge every successful scope before orchestration may replay the result.

### Canonical bounded success projection

- `project_result` returns a finite, acyclic tree containing only JSON `null`, booleans, integers,
  Unicode-scalar strings, lists, and objects with Unicode-scalar string keys. Floats (including
  finite floats, NaN, and infinities), bytes, tuples, sets, non-string keys, duplicate logical keys,
  arbitrary objects, cycles, and lone surrogates are invalid tool results. Integers are restricted to
  the inclusive signed 64-bit range `-9,223,372,036,854,775,808` through
  `9,223,372,036,854,775,807`; Python booleans are not admitted through the integer branch.
- The complete wrapped `{"result":<projected>}` envelope may contain at most 64 object/list levels;
  the outer envelope object is depth 1 and scalar values add no level. The finite allowlist walk is
  iterative, detects cycles, checks this depth before serialization, and never relies on Python call
  recursion. Production shapes are much shallower, but the boundary rejects a hostile projector
  before `json.dumps` can reach its interpreter recursion limit.
- The same walk has one 65,536-unit work budget. It charges one unit for every visited value or
  container, one for every object member name, and one for every Unicode scalar in a key or string
  value. Container lengths are checked against the remaining budget before their children are
  visited, and string lengths are checked before scalar validation. Those charges are a lower bound
  on the complete JSON envelope, so no envelope that could fit the 65,536-byte output limit is
  rejected. An over-wide tree fails before dictionary-key sorting or full traversal; neither an
  enormous container nor a shared-subtree expansion can turn validation into unbounded work.
- The `search_text` projector copies CAH-029's already-validated `limit_reasons` tuple without
  reordering it and copies `truncated` unchanged. CAH-029 owns the exact
  `matches`, `candidate_bytes`, `listing` order and the invariant
  `truncated == bool(limit_reasons)`; the registry neither repairs nor accepts inconsistent results.
- The registry wraps the projected tree exactly as `{"result": <projected>}` and serializes it with
  Python `json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True,
  allow_nan=False)`. A pre-serialization walk enforces the allowlist, so the serializer is not an
  implicit object converter. It checks integer range and complete-envelope depth before conversion,
  and a defensive serializer `RecursionError` or `ValueError` maps to
  `invalid_read_tool_result` without error text. No Unicode
  normalization or content redaction occurs at this layer.
- The UTF-8 encoding of the complete wrapped envelope may contain at most 65,536 bytes. The limit is
  inclusive and applies after JSON string escaping, keys, punctuation, and the outer `result`
  wrapper have been added. A value above the bound fails completely; the registry never truncates a
  string, list, object, or serialized envelope.
- Instruction-scope-extractor/projector failures, unsupported values, non-scalar strings, and
  result-type drift use `invalid_read_tool_result`. An otherwise valid projection above 65,536 bytes
  uses the distinct fixed oversize failure. Ordinary exception and result representations never
  include instruction scopes, native result, projected tree, or serialized output.
- This projection is the model-facing success envelope reused by CAH-032. Native read limits and the
  envelope limit are independent: a valid `ReadFileResult` at its native 65,536-byte text maximum
  can exceed 65,536 bytes after metadata and JSON wrapping and must fail rather than be trimmed.

### Fixed, non-leaking registry failures

`ReadToolRegistryError` contains exactly one stable code and fixed message. It never includes the
candidate name, arguments, result, type representation, workspace path, or implementation error.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_read_tool_registration` | `Read tool registration is invalid.` | a descriptor, duplicate, or capability candidate is invalid |
| `invalid_read_tool_binding` | `Read tool binding is invalid.` | `dispatch_bound` receives a same-shaped or otherwise foreign registry entry |
| `unknown_read_tool` | `Read tool is not available.` | exact lookup finds no registered name |
| `invalid_read_tool_input` | `Read tool input is invalid.` | the validated input type does not match the descriptor |
| `invalid_read_tool_result` | `Read tool returned an invalid result.` | an implementation, projector, or instruction-scope extractor violates its declared result contract |
| `read_tool_output_too_large` | `Read tool output exceeds the byte limit.` | a valid canonical success envelope exceeds 65,536 UTF-8 bytes |

## Reviewability budget

- **Estimated production-code churn:** 500-600 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- If fitting the four operations, complete typed instruction-scope extraction, and bounded projection
  requires changing native filesystem behavior/public result contracts or is likely to exceed 600
  production lines, split a focused prerequisite instead of expanding this story.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-027-029 typed native operations -> immutable
  read registry, local instruction scopes, and bounded `ReadToolSuccess` -> CAH-038 definitions,
  CAH-032 exchange, and CAH-034 orchestration consumers.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. The sole M2 production factory accepts one exact shared metadata/text/search service graph and
   exposes its four native read operations through one immutable registry in deterministic order.
2. Every descriptor is typed, documented, bounded, uniquely named, and classified only as
   `read_workspace`; its `ReadTool` has one pure bounded instruction-scope extractor over the exact
   validated result type.
3. Exact-name dispatch resolves one registry-owned entry; identity-safe bound dispatch rejects a
   same-shaped foreign entry before handler work, otherwise invokes that exact implementation once
   with the exact validated input, validates its declared result type, runs only that tool's
   explicit allowlisted projector, and returns the exact canonical `{"result":...}` success envelope
   plus the exact ordered, local, content-suppressed instruction-scope tuple.
4. Duplicate names, unknown names, wrong input types, raising or invalid instruction-scope extractors,
   result-scope bound violations, wrong result types/projector values, side-effecting capability
   candidates, and oversized projections use fixed non-leaking failures; extractor/result drift maps
   to `invalid_read_tool_result`, and every rejected path returns no instruction scopes or rejected
   output.
5. Registry code imports no provider SDK, protocol model, subprocess surface, network client, MCP
   client, or write-tool implementation.
6. Focused tests cover construction, ordering, each dispatch path, exact canonical snapshots,
   scalar/container rejection, and every byte boundary without credentials or network access.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1-2 | Factory tests pass one exact shared metadata/text/search service graph, reject equal-but-distinct or cross-wired identities before descriptor construction/I/O, and assert exact ordered descriptors, immutability, uniqueness, capability values, `[a-z][a-z0-9_]{0,63}` boundaries, exact built-in string/O(1) pre-gates, and pure extraction only after exact result validation. Scope snapshots cover the execution-time canonical request scope first; list entry directory/file owners; stat directory/file owners; read-file parent; search-match parents; root parent `.`; exact first-occurrence deduplication; and no request-alias or `output_json` authority. |
| 3 | Parameterized tests resolve each registry-owned entry, dispatch one typed request through `dispatch_bound`, and snapshot the exact UTF-8 `{"result":...}` string plus ordered local `instruction_scopes`, including sorted nested keys, compact separators, unescaped multibyte scalars, every explicitly projected field, and absence of the canonical request scope and every derived scope from JSON/repr. Two registries with identical names/descriptors/types but distinctive handlers prove a foreign entry raises exact `invalid_read_tool_binding` by identity before input inspection or either handler, while the owning entry executes only its handler. Search snapshots preserve multi-reason canonical order and reject reason/truncation inconsistency. Empty-list and no-match alias cases retarget `alias -> A` to `B` after dispatch and retain exactly `(A,)`. |
| 4 | Spy tools prove duplicate, unknown, wrong-input, raising/non-string/duplicate/over-bound extractor returns, over-bound list/search results, and non-read candidates leak no scope; wrong-result/projector spies execute once but leak no value. Separate interaction/static snapshots prove the four closed production extractors derive the exact documented order and perform no filesystem, policy, provider, instruction, alias-resolution, or JSON work; no runtime test claims arbitrary side effects or a semantically reordered but structurally valid tuple can be detected or undone. Tables reject floats, bytes, tuples, non-string keys, cycles, lone surrogates, signed-64-bit under/overflow, complete-envelope object/list depths 63/64/65, and injected serializer `RecursionError`/`ValueError` with exact safe failures. A very wide projected tree uses visit/sort/serializer spies to prove the 65,536-unit validation budget fails before full traversal, sorting, or serialization. Tests accept 500 list entries and 200 search matches, reject 501/201 before success, and prove exact deduplication can only reduce the 501/201 candidate ceilings. |
| 4, 6 | Byte tests accept a complete envelope at 65,536 bytes, reject 65,537 with `read_tool_output_too_large`, and prove that a valid native read at its 65,536-byte text maximum fails when JSON metadata/wrapping pushes the envelope over the bound; no truncation or content appears in the failure. |
| 5 | Repository-policy/import test denies provider, subprocess, network, MCP, and write surfaces from the registry module. |
| 6 | The focused suite and canonical non-live gate pass with the network guard enabled. |

## Validation

- Add focused registry unit tests using deterministic spies and the native tool fixtures.
- Build same-shaped registries with distinctive handlers; prove exact lookup returns the owning
  entry, `dispatch_bound` uses object identity, a foreign entry executes zero times, and static
  imports keep this API independent of CAH-039/provider values.
- Assert exact canonical snapshots for all four operations and prove a different dictionary
  insertion order produces byte-identical output.
- Test signed 64-bit integers immediately below, at, and above both endpoints, complete wrapped
  envelope depths 63/64/65, a 5,000-digit integer fake, and injected serializer
  `RecursionError`/`ValueError`; every invalid value becomes the fixed
  non-leaking invalid-result failure before unbounded decimal conversion.
- Build a projected list wider than the validation budget and assert bounded visited-node counts,
  zero key sorting/serialization, and the fixed `read_tool_output_too_large` failure because the
  exhausted work count is a proven lower bound on the eventual encoded bytes.
- Assert values and failure representations do not reveal supplied arguments, instruction scopes,
  workspace paths, native/projected results, or serialized tool output. Include the native-maximum/
  wrapped-overflow regression and exact 65,536/65,537-byte envelope boundaries.
- Assert every successful tool carries the exact ordered local scope tuple outside `output_json`,
  every known failure carries none, extraction runs only after result validation, and it performs no
  filesystem, policy, provider, instruction, request-alias, or serialized-JSON work. Exercise the
  exact per-tool result-scope maxima and first-occurrence deduplication. Retarget empty-list and
  no-match internal aliases after native return and prove the tuple retains only the execution-time
  canonical scope; removal of that scope later fails discovery rather than falling back to the alias.
- Run Python type, lint, format, and focused tests, then `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache
  ./scripts/check`.

## Documentation impact

Update the architecture, safety model, glossary, backlog, story index, and linked Markdown lesson.
The lesson emphasizes the registry as a harness policy boundary and contrasts native registration
with a future MCP registry adapter. Do not add or revise a presentation.

## Exclusions

- Model-facing input definitions, JSON Schema generation, JSON argument parsing, provider error
  envelopes, or provider history messages. This story owns only typed native instruction-scope
  metadata and the shared canonical success envelope.
- Instruction discovery, context merge, deciding when another model turn starts, or interpreting the
  target path as authorization. Later harness orchestration consumes successful scope metadata.
- Agent-loop turns, retries, parallel calls, protocol/TUI tool events, or transcript content.
- Direct MCP compatibility, MCP clients or servers, remote/hosted tools, plugins, dynamic imports,
  writes, subprocesses, approvals, and general E4 policy composition. A future generalized registry
  port must snapshot and re-admit a remote catalog, filter names/schemas, classify remote/network
  capability, map MCP `structuredContent`, `outputSchema`, and `isError`, and own authentication,
  timeouts, and cancellation; an MCP server cannot plug directly into this local read registry.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish registry identity, its exact `ReadTool` entry/handler, name/descriptor, validated input/result, execution-time canonical request scope, result-owner scopes, `instruction_scopes`, projected fields, and `output_json`. A copied or same-shaped entry is not the owned executor; model-visible JSON contains no native/control object. |
| End-to-end contract | Exact CAH-027/028/029 service graph -> sole M2 registry factory -> four immutable tools -> exact entry lookup -> identity-safe `dispatch_bound(entry, input)` -> result validation -> scope extraction/projection -> bounded `ReadToolSuccess`; CAH-038 consumes descriptors, CAH-039 binds the exact entries, and CAH-034 passes entry/input without CAH-031 importing later types. |
| Failure and atomicity | Invalid/duplicate registration fails the whole registry; unknown name, foreign entry, or wrong input executes zero tools; a raising/invalid extractor, result, projector, or envelope yields no success/scope/output after at most one owned execution. Known errors carry no scopes; scheduler rollback is deferred to orchestration. |
| Reachable boundaries | Real native maxima and dispatch spies exercise descriptor name/description edges, list/search candidate scopes 501/201 before deduplication and two for stat/read, signed-64-bit endpoints, complete-envelope depths 63/64/65, the 65,536-unit walk, and serialized envelopes at 65,536/65,537 bytes. Scheduler timing is N/A here. |
| Closed grammar and cardinality | Registry order contains exactly four `read_workspace` tools with unique names matching `[a-z][a-z0-9_]{0,63}`; parity tests lock the same grammar at CAH-032/038 boundaries. Exact result types feed four closed extractors/projectors. Projection admits only the finite JSON tree grammar inside one `{"result":...}` envelope, with no floats/arbitrary objects/cycles and exact depth/work/byte bounds. |
| Artifact parity | Story, lesson, diagram, tool/architecture/safety docs, pseudocode, and tests agree on lookup -> entry identity -> input type -> one execution -> result type -> scope extraction -> explicit projection -> bounded envelope, and on the CAH-032/033 -> CAH-039 -> CAH-034 guard -> CAH-031 route without a reverse import. |
| Independent lenses | Security/identity review covers registry ownership, exact lookup, scope provenance, and projection leaks; handoff/composition review covers all native producers plus CAH-038/032/039/034 consumers; provider/protocol/limits/scheduler review covers JSON bounds and confirms provider SDK, protocol, MCP, and scheduler behavior remain outside this unit. |

## Definition of done

- All acceptance criteria have direct automated evidence, including exact successful ordered scope
  metadata, no scopes on every known failure, a meaningful no-execution path, four exact output
  snapshots, and native-maximum envelope overflow.
- Public APIs are typed and documented; fixed failures and representations are content-safe.
- Production-code churn is at or below 600 lines and the final diff is reviewed for one
  responsibility.
- The story and concise Markdown lesson are verified against implementation, with a compact
  architecture diagram and no presentation changes.
- Focused checks and the canonical repository gate pass; the completed unit is published through
  the repository's review workflow.

## Planned evidence

- A focused registry module and tests proving immutable registration, deterministic discovery, pure
  bounded instruction-scope extraction, typed dispatch, and fail-closed capability admission.
- Repository-policy evidence that registration cannot open a provider, network, subprocess, MCP, or
  write path.
- A lesson that makes the registry-versus-executor and native-tool-versus-MCP distinctions explicit.

## Deferred work

- CAH-038 bridges descriptors into bounded provider-neutral definitions. CAH-032 then adds calls,
  results, scoped context projection, ordered history, and strict-fake support; neither exposes
  local instruction-scope metadata to a provider.
- CAH-033 admits one complete tool-aware response without parsing or dispatch. CAH-039 is the sole
  argument-admission owner; CAH-034 is the first unit allowed to dispatch its prepared request
  through this registry.
- General E4 policy, approvals, side effects, MCP adapters, and dynamic extension loading remain
  later milestones.
