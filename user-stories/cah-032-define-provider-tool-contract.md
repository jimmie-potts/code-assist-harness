# CAH-032 - Define the provider-neutral tool-turn contract

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit
  agent loop (supporting E3 read tools)
- **Dependencies:** CAH-030, CAH-031, CAH-038
- **Lesson:** [Provider-neutral tool-turn contract](../docs/lessons/cah-032-provider-tool-contract.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** How the harness represents a paused tool-aware model turn without giving a
  provider ownership of context, execution, or loop continuation.

## User story

> As an agent-loop developer, I want provider-neutral call, result, continuation, history, and
> request values so that the harness can stage tool-aware turns without importing an SDK or
> delegating orchestration to a provider.

## Single responsibility

CAH-032 extends the provider port and strict fake with the bounded values needed to represent one
tool-aware request and its ordered history. It consumes immutable CAH-038 definitions and projects
one CAH-030 context snapshot, but it does not generate or validate schemas, interpret arguments,
enforce argument keys, dispatch a tool, enrich context, run another model turn, or map an SDK.

## Scope

- Add immutable `ProviderToolCall`, `ProviderToolResult`, and `ProviderOpaqueContinuation` values.
- Preserve the shipped `ProviderRequest.conversation` field while widening it to ordered tool-aware
  history; add one immutable tuple of CAH-038 tool definitions and a pure scope-preserving projection
  of one CAH-030 context package.
- Add top-level `provider_context.py` with the sole pure CAH-030-to-CAH-032 context projection bridge.
- Define and validate the closed sequential history grammar for calls, matching results,
  continuations, and messages.
- Apply exact string, identifier, item, result-envelope, and complete-request limits without
  truncation or content-bearing diagnostics.
- Refactor `ProviderToolCallRequested` to carry the shared call value rather than duplicate fields.
- Teach the strict fake to compare complete requests and script call-request observations.
- Preserve CAH-023 text-only behavior and keep protocol, TUI, transcript, filesystem, subprocess,
  network, and live-provider behavior unchanged.

## Locked contract

### Calls and results

`ProviderToolContractError` is the sole CAH-032 construction/projection failure. It has code
`invalid_provider_tool_value` and fixed message `Provider tool value is invalid.` Its string and
representation contain only that code/message. Call, result, continuation, stream-wrapper,
tool-aware request, context projection, and canonical request-projection failures use it without raw
values, exception chaining, parser/serializer text, or partial state. The existing normalized
`ProviderFailure` value remains a provider observation rather than this programmer/input-contract
exception.

- `ProviderToolCall` contains one call ID, one exact tool name, and the provider's unparsed JSON
  argument string. Call IDs match `[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}`; names match
  `[a-z][a-z0-9_]{0,63}`. Each field must be an exact built-in `str`, not a subclass. Before regex,
  scalar inspection, or UTF-8 encoding, apply its O(1) `len(...)` character ceiling: 256 for the call
  ID, 64 for the name, and 16,384 for arguments. The complete argument string is then at most 16,384
  strict UTF-8 bytes.
- CAH-031 owns the inventory-side descriptor grammar. Because core provider models cannot import the
  tool registry, CAH-032 independently re-admits the same exact `[a-z][a-z0-9_]{0,63}` grammar at its
  untrusted call-carrier boundary. A parity test imports neither owner into the other and mutates every
  character class, endpoint, case, and Unicode form so the two copies cannot silently drift.
- Construction preserves admitted argument bytes exactly. It does not parse JSON, inspect or compare
  keys, normalize names or values, reject duplicate members, apply numeric grammar, invoke Pydantic,
  perform tool lookup, or dispatch. CAH-039 owns pair-preserving argument admission and the exact
  pre-Pydantic key gate.
- `ProviderToolResult` contains the matching call ID, status `success` or `error`, and one canonical
  `output_json` envelope. A success is byte-for-byte CAH-031's compact
  `{"result":<allowlisted-value>}` envelope. An error is exactly
  `{"error":{"code":"<code>","message":"<fixed message>"}}`; its code matches
  `[a-z][a-z0-9_]{0,63}` and its non-empty message is at most 1,024 UTF-8 bytes. No other top-level or
  nested error key is allowed.
- Result construction first runs one iterative, quote-and-escape-aware preflight over the complete
  envelope. The outer object is structural depth 1; objects and arrays may reach depth 64; delimiters
  inside strings add no depth. One 65,536-byte/work budget covers the whole envelope and never resets
  for a subtree. The scanner stops at the first excess byte, work unit, or level before JSON decode.
- Only an admitted envelope is decoded. An integer callback rejects overlong or out-of-signed-64-bit
  tokens before Python decimal conversion; floats and non-finite constants are inadmissible. An
  iterative post-decode walk checks the JSON-safe tree and integer range without Python call
  recursion under one derived non-resetting work counter. Decoder `RecursionError` or `ValueError`
  maps to one fixed, content-suppressed invalid-result failure.
- The admitted tree is compactly reserialized with sorted keys, strict Unicode, and no NaN, then
  required to equal `output_json` byte-for-byte. Status `success` requires the sole top-level
  `result` key; status `error` requires the sole top-level `error` key. Mismatched status, malformed
  or noncanonical JSON, extra keys, invalid scalars, floats, signed-64-bit overflow, depth 65, or byte
  65,537 fails before history construction. The standard decoder creates a fresh acyclic JSON tree;
  cycle rejection remains CAH-031's responsibility for arbitrary projector candidates and is not an
  invented CAH-032 test state. Serializer `RecursionError` or `ValueError`
  becomes the same fixed failure.
- Ordinary call/result representations and errors omit raw arguments, output JSON, provider content,
  exception text, credentials, and host paths. CAH-031's local `instruction_scopes` never enter a
  result envelope or provider history.

### Continuations and ordered history

- `ProviderOpaqueContinuation` contains one non-empty provider-owned payload. It must round-trip
  strict UTF-8 unchanged, contain no literal NUL, and encode to at most 65,536 bytes. Core code
  preserves exact equality but never parses, normalizes, logs, serializes to protocol/transcript, or
  reveals it in ordinary representations and mismatch diagnostics.
- The shipped `ProviderRequest.conversation` name remains authoritative; CAH-032 adds no `input`
  field, property, or alias. Its type widens from `tuple[ProviderMessage, ...]` to the exact built-in
  immutable `tuple[ProviderMessage | ProviderOpaqueContinuation | ProviderToolCall |
  ProviderToolResult, ...]` and contains at most 16 items. Existing text-only construction through
  `ProviderRequest(conversation=..., repository_instructions=...)` therefore remains source
  compatible.
- A continuation is a positional provider-output item. It must immediately precede the provider
  call or assistant message it belongs to. It is invalid at history start or end, before a user
  message, result, or second continuation, or while a prior call is unresolved.
- A tool result follows its one unmatched call and uses the same call ID. Orphan results, duplicate
  call IDs, multiple unresolved calls, mismatched IDs, text before a pending result, and a request
  ending with an unresolved call fail construction. The M2 replay order is original conversation,
  optional
  continuation, call, matching result; multiple completed groups may follow sequentially.
- `ProviderOpaqueContinuationObserved` is the only stream carrier for continuation data. It has
  exact field `continuation: ProviderOpaqueContinuation` and fixed kind
  `opaque_continuation.observed`; `ProviderStreamEvent` includes this wrapper, never the bare history
  value. The wrapper may appear only through the producer/collector grammar CAH-033 owns.
- `ProviderToolCallRequested` has fixed kind `tool.call_requested` and exact field
  `call: ProviderToolCall`. Neither
  the observation nor strict fake interprets arguments, performs lookup, executes a tool, authorizes
  continuation, or starts another exchange.

### Context, definitions, request admission, and strict fake

- `ProviderRequest` retains its shipped field order and constructor names, then appends new defaults:
  `conversation`, `repository_instructions=()`, `repository_context=()`, and `tools=()`. There is no
  second history carrier. `repository_context` is an exact built-in tuple of three frozen variants:
  `ProviderInstructionContext(path, applies_to, precedence, content, content_bytes, truncated)`,
  `ProviderFocusContext(path, start_line, end_line, content, content_bytes, truncated)`, and
  `ProviderSearchContext(path, query_rank, line, column, content, content_bytes, truncated)`.
  Together they are the closed `ProviderRepositoryContextItem` union and are the exact immutable
  ordered projection of one successful CAH-030 package. Instruction items copy canonical source,
  candidate-owner `applies_to`, numeric
  owner-depth precedence including legal gaps, content, byte count, and truncation state exactly.
  Focus and search items preserve their kind-specific provenance. Projection neither re-resolves,
  selects, deduplicates, reorders, renumbers, nor mutates an item.
- `ProviderSearchContext.query_rank` is the exact strict non-Boolean 1-through-4 value already owned
  by CAH-030: the one-based position in its exact-deduplicated query tuple. The bridge copies it
  unchanged. Input queries `("todo", "todo", "fix")` therefore project ranks 1 and 2, never 1 and 3;
  the strict fake and CAH-036 snapshots may not derive rank from provider-array position.
- `build_provider_context(package: ContextPackage) -> tuple[ProviderRepositoryContextItem, ...]` in
  top-level `provider_context.py` is the sole integration bridge. It shape-projects each admitted
  CAH-030 item in order into exactly one matching frozen variant and copies every field named above.
  It does no selection, discovery, merge, filesystem access, or provider work. That top-level module
  alone may import both CAH-030 context types and provider-domain models; `provider/models.py` does not
  import the context builder, and CAH-030 does not import provider values. Impossible kind/field/type
  drift raises exact content-suppressed `ProviderToolContractError` with no partial tuple. CAH-034/035
  call this bridge for every initial or enriched snapshot rather than inventing a local projector.
- The context inherits CAH-030's 16-binding, 24-item, and 96-KiB content limits. Its inclusion report
  is harness evidence and never model input. CAH-031 local instruction scopes are also omitted.
  Legacy `repository_instructions` remains valid only when `repository_context` is empty; supplying
  both fails rather than creating two priority systems.
- Every request is an immutable snapshot. Later orchestration may construct a second request from an
  atomically enriched CAH-030 package; CAH-032 neither performs enrichment nor compares cross-request
  monotonicity. The earlier request remains unchanged.
- `ProviderRequest.tools` consumes an immutable ordered tuple of CAH-038
  `ProviderToolDefinition` values. It contains at most 16 unique names; M2 composition supplies
  exactly four. `conversation`, `repository_instructions`, `repository_context`, and `tools` must all
  be exact built-in tuples. Their O(1) cardinality gates run before any element iteration, equality
  comparison, or projection: 1-16 conversation items, 0-16 legacy instructions, 0-24 context items,
  and 0-16 definitions. Only exact owned element variants are accepted; subclasses or mixed legacy/
  new context fail before projection. Its explicit request
  projector calls each definition's bounded `materialize_parameters()` to place a fresh JSON object,
  not an escaped schema string, into canonical request bytes. CAH-032 does not generate,
  canonicalize, validate, repair, or semantically interpret parameter schemas. An empty tools
  tuple preserves CAH-023 text-only semantics.
- The complete request projection contains at most 16 history items, 16 definitions, and the bounded
  context. Before constructing its proxy, every direct provider string—including existing message
  content and legacy instruction fields plus call, result, continuation, and context fields—must be
  an exact built-in `str`. An O(1) character-length check applies the field's tighter ceiling when one
  exists and otherwise the 524,288-byte request ceiling as a necessary character ceiling before any
  scalar walk, strict UTF-8 encode, escaping, or serializer call. Subclasses fail before their hooks.
  The shape-directed projector then copies and incrementally charges every model-facing field and JSON
  escape exactly once into a canonical compact sorted-key JSON proxy capped at 524,288 UTF-8 bytes.
  It never calls `json.dumps`, `JSONEncoder.encode`, or `JSONEncoder.iterencode` on the request or a
  caller-owned string before those type, O(1) length, tuple-cardinality, and per-field byte checks, so
  an encoder cannot first materialize an unbounded escaped string. The sink stops before retaining
  byte 524,289; rejection is atomic and never truncates a component. This is deterministic admission
  evidence, not a provider token count or a claim about adapter wire bytes.
- The 524,288-byte limit is reapplied independently to each complete request snapshot. Later turns
  carry cumulative conversation/context values inside that snapshot, so replayed bytes count again
  within the new request, but the harness does not sum whole-request sizes across provider starts or
  invent a CAH-022 cumulative request-byte counter.
- Provider adapters receive already-selected context and definitions. They may frame admitted
  values for their API but may not add, omit, select, rank, mutate, or reinterpret them. Adapter role
  framing remains provider-specific work.
- The strict fake scripts exact requests and exact outcomes, including call observations. It compares
  definitions by immutable value and compares every history/context field, opaque payload, call, and
  result exactly. A mismatch identifies only an exchange number and structural field path; it never
  embeds message, context, schema, argument, result, or continuation content or calls `repr()` on the
  request.

### Strict strings and fixed bounds

Every CAH-032-owned or directly projected string must be an exact built-in `str`. Its O(1) character
ceiling is checked before scalar inspection or encoding, followed by strict UTF-8 encode, strict
decode, and exact equality. Lone surrogates and literal NUL fail; valid Unicode scalar values remain
unchanged and are never normalized. Bounds count the complete strict UTF-8 value named and are
inclusive. A string without a tighter field ceiling uses 524,288 characters as the necessary
pre-encoding ceiling; the complete request byte gate remains authoritative.

| Value | Hard maximum or grammar |
| --- | --- |
| Available CAH-038 definitions | 16 unique names; M2 composition supplies 4 |
| Call ID | 1-256 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}` |
| Tool name in call | 1-64 ASCII characters matching `[a-z][a-z0-9_]{0,63}` |
| Complete serialized call arguments | 16,384 UTF-8 bytes; retained but uninterpreted |
| Opaque continuation payload | 65,536 UTF-8 bytes, non-empty |
| Error code/message | code grammar above; non-empty message at most 1,024 UTF-8 bytes |
| Complete canonical tool-result envelope | 65,536 UTF-8 bytes and 64 object/list levels, outer object depth 1, under one non-resetting preflight/work budget |
| Ordered `conversation` items | 16 per request |
| Complete provider-neutral request projection | 524,288 UTF-8 bytes |

## Reviewability budget

- **Estimated production-code churn:** 425-575 changed lines.
- **Delivered production-code churn:** Not started; replace with additions plus deletions before Done.
- **Counted paths:** `src/code_assist_harness/` and `tui/src/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: immutable CAH-038 definitions and CAH-030
  context -> bounded provider request/history -> strict fake observation.
- **Concrete counted-path estimate:** `provider/models.py` 275-350 lines for immutable
  call/result/continuation/history/request admission; `provider/fake.py` 90-125 for exact request
  scripting; `provider/port.py` plus `provider/__init__.py` 20-35 for intentional APIs; and 40-65
  additions plus deletions for provider-package integration, totaling 425-575 changed production
  lines. Tests and documentation remain excluded.
- **Pre-implementation checkpoint:** Re-estimate from the proposed file diff before coding. Split
  result admission into a prerequisite if the counted estimate exceeds 575, if the strict fake
  needs a second runtime behavior, or if request construction stops being one atomic exchange
  contract.
- **Split rule:** Stop and refine another story before review if this unit gains schema work,
  argument admission/key enforcement, dispatch, context enrichment, or is likely to exceed roughly
  600 production lines.

## Acceptance criteria

1. Calls, results, and opaque continuations are immutable, SDK-free, bounded values with fixed
   content-suppressed failures.
2. Calls preserve bounded argument bytes without parsing or key admission; results enforce the exact
   success/error grammar through complete-envelope depth/work preflight and canonical equality.
3. Ordered history admits only the closed continuation/message/call/matching-result grammar and
   rejects every orphan, duplicate, unresolved, or misordered state atomically.
4. The sole top-level bridge projects one CAH-030 package to exact immutable request context,
   including `applies_to` and unchanged numeric precedence, while reports and local instruction
   scopes remain harness-only and dependency direction stays acyclic.
5. Requests consume immutable CAH-038 definitions without schema generation or validation, preserve
   text-only compatibility, and enforce exact item and 512-KiB complete-projection limits.
6. The strict fake matches complete request values, scripts shared call observations, and emits only
   bounded structural mismatch diagnostics.
7. No argument interpretation/key gate, dispatch, context enrichment, second provider turn, OpenAI
   mapping, MCP transport, protocol, transcript, TUI, filesystem, subprocess, or network behavior is
   added.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Call preservation | Exercise call-ID/name grammar, Unicode, and argument bytes 16,383/16,384/16,385 with duplicate members, deep delimiters, floats, and non-finite spellings | Unit | Admitted bytes remain exact and uninterpreted; over-bound/faulty identifiers fail before fake work |
| Result grammar and bounds | Snapshot CAH-031 success and fixed error envelopes; test bytes 65,535/65,536/65,537 and complete depths 63/64/65 including quoted delimiters | Unit | One complete-envelope preflight; invalid input never reaches decode/history |
| Result runtime defenses | Exercise malformed/noncanonical JSON, status/key mismatch, floats, signed-64-bit endpoints/overflow, a 5,000-digit token, wide late sentinel, and injected decoder/serializer failures | Unit | Iterative bounded work, exact canonical equality, and one fixed non-leaking failure |
| History grammar and migration | Table-test shipped text-only `conversation`, optional continuation -> call -> result, optional continuation -> assistant, and multiple completed groups; mutate every invalid order/ID and reject an invented `input` argument | Unit | Exact admitted tuples and source-compatible text-only calls; orphan, duplicate, pending, misplaced, or second-carrier states reject atomically |
| Continuation and item bounds | Exercise payload bytes 65,535/65,536/65,537 and histories of 15/16/17 items | Unit | Inclusive limits, strict scalar admission, exact equality, safe representations |
| Context projection | Drive real CAH-030 focus/search/instruction packages, including source/applicability differences and rank gaps, through the sole `build_provider_context` bridge; inject impossible kind/field drift | Integration | Exact fields/order/provenance and content-suppressed fixed failure; report and local scopes omitted; provider models and CAH-030 keep one-way imports |
| Definition consumption and request bound | Supply exact CAH-038 tuples of 0, 4, 16, and 17 definitions; vary all four request tuple subclasses and counts at 16/17 legacy instructions, 24/25 context items, and 15/16/17 conversation/tool items; encode requests at 524,287/524,288/524,289 bytes | Unit/integration | All O(1) tuple/cardinality/element gates precede iteration; no schema generation/validation; unique ordered values; incremental request rejection without truncation |
| Fixed failure contract | Mutate every CAH-032-owned constructor/projector and inject decoder/serializer failures | Unit | Exact `ProviderToolContractError` type/code/message, no chained/content-bearing detail, and no partial request/history |
| Pre-encoding string bounds | Supply exact huge message/instruction/call/result/continuation/context strings plus `str` subclasses with encoding/iteration hooks; install projection and JSON-encoder spies | Unit | Exact type and O(1) character gates reject before UTF-8, escaping, projection, serializer, or subclass hooks; no unbounded escaped string is materialized |
| Strict fake | Script text-only, call, result-history, opaque continuation, and enriched-context requests; change each field with a secret-like sentinel | Unit | Exact outcomes; mismatches report exchange/path only and start no tool or extra exchange |
| Ownership exclusion | Import/static tests and dispatch/provider spies | Policy/integration | No SDK, schema bridge, argument parser/key gate, dispatch, filesystem, network, protocol, or TUI behavior |

## Validation

- Add focused provider-domain tests for call/result/continuation constructors, result preflight and
  iterative walk, history grammar, the top-level CAH-030 projection bridge, all four request tuple
  gates, request limits, and strict-fake matching.
- Cover every identifier, item, depth, integer, continuation, result-byte, and request-byte boundary
  below, at, and above its limit, with multibyte Unicode and content-leak sentinels.
- Prove raw arguments containing duplicate members and invalid later-CAH-039 numeric/key forms remain
  byte-exact and are never parsed by constructors or the fake.
- Use scanner/visitor/parser/serializer spies to prove an over-deep or over-wide result stops at the
  documented stage under the one complete-envelope budget.
- Use huge exact-string sentinels, hostile `str` subclasses, tuple iteration spies, and JSON encoder
  spies to prove direct string and all four request-collection cardinality gates run before UTF-8, escaping, element
  traversal, request projection, or serialization. Include a string whose escaped representation
  would exceed the request bound and assert no encoder entry.
- Snapshot initial and enriched context requests, including exact `applies_to`, legal precedence
  gaps, and omission of reports/local scopes; prove the first request remains unchanged.
- Re-run existing CAH-023 text-only provider/session tests and CAH-038 definition tests as dependency
  evidence, then run `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check`. Validation remains
  model-free and network-free.

## Documentation impact

Keep this story and its concise Markdown lesson synchronized with implementation, and update the
provider-interface, agent-loop, context, safety, glossary, indexes, backlog, and planning note when
the unit ships. The diagram traces definition/context inputs through provider history and the strict
fake. Do not add or revise presentation files.

## Exclusions

- Provider-definition schema generation, admission, canonicalization, or CAH-031 bridge behavior;
  CAH-038 owns those immutable inputs.
- Raw argument parsing, duplicate-member/numeric admission, exact lookup, the pre-Pydantic key gate,
  or native input validation; CAH-039 owns that non-executing preparation boundary. CAH-034 alone
  guards and dispatches its prepared value through CAH-031.
- Tool execution, instruction discovery/context enrichment, transition validation, or another model
  exchange; CAH-034 and CAH-035 own those loop stages.
- OpenAI mapping, direct MCP compatibility, remote tools, provider-managed state, protocol/TUI tool
  events, transcript tool content, writes, approvals, retries, parallel calls, subprocess, or network.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish CAH-038 definition name, provider call ID/name, result call ID, continuation payload, CAH-030 canonical source/`applies_to`, and provider-visible labels. No filesystem alias is resolved here. |
| End-to-end contract | Trace CAH-038 definitions + CAH-030 package -> sole top-level context bridge -> request -> strict fake -> call observation, and CAH-031 envelope -> `ProviderToolResult` -> ordered history; exact imports remain CAH-030/provider models -> integration bridge -> orchestration. |
| Failure and atomicity | Invalid calls/results/history/requests publish no partial value; fake mismatch starts no tool or extra exchange. Cancellation/deadline are N/A because this unit constructs bounded synchronous values only. |
| Reachable boundaries | Drive result envelopes through the real CAH-031 projector and definitions through CAH-038; exercise continuation/history/request limits in the strict fake, including exact huge-string, hostile-subclass, all-four-collection tuple, and pre-encoder rejection. |
| Closed grammar and cardinality | Snapshot call/result/status grammar, continuation position, call/result pairing, 16-item/definition ceilings, 64-level result depth, and byte limits. |
| Artifact parity | Story, lesson, diagram, pseudocode, conceptual docs, and tests use the same call preservation, result preflight/decode/canonicalization, history, request, and fake order. |
| Independent lenses | Security/identity review fixed exact strings, context provenance, and content-suppressed failures; producer/consumer review added the sole CAH-030 context bridge and real CAH-038/031 projections; limit/runtime review added all-four-collection O(1) gates, per-snapshot accounting, encoder spies, and independent name-grammar parity. |

## Definition of done

1. Calls, results, continuations, history, context projection, request admission, and strict-fake
   behavior have deterministic happy, boundary, and meaningful failure evidence.
2. Identifier, argument, result byte/depth/work, continuation, item, definition-count, and request
   limits are tested below, at, and above their boundaries.
3. Failures, fake diagnostics, and ordinary representations reveal no message, schema, argument,
   result, continuation, host path, credential, or interpreter content.
4. Public contracts are typed and documented; closed grammars reject unsupported values and fields.
5. Focused checks and canonical offline `./scripts/check` pass without a live model or network.
6. Provider SDK, protocol, transcript, and TUI behavior remain unchanged and have nearest parity
   evidence; text-only provider behavior remains compatible.
7. The Markdown lesson includes exact implementation and failure-test excerpts after code exists;
   no presentation work is introduced.
8. Conceptual docs, indexes, backlog, planning note, story status, and lesson status agree at Done.
9. Delivered production churn is recorded within the planned 425-575 range or the work is split
   before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- Provider-domain tests for immutable call/result/continuation values, closed history grammar,
  complete-envelope preflight, and bounded request construction.
- Context-projection and strict-fake snapshots proving exact initial/enriched requests and
  content-safe mismatches.
- Integration/import evidence that immutable CAH-038 definitions are consumed unchanged and no
  argument admission, dispatch, SDK, protocol, or network boundary is crossed.

## Deferred work

- CAH-039 parses pair-preserved raw arguments, enforces exact required keys before Pydantic defaults,
  and returns one validated but non-executed prepared request or fixed error.
- CAH-034 is the first unit that guards and dispatches that prepared value through CAH-031, then
  stages one fake-backed read-tool result replay after instruction discovery and context enrichment;
  CAH-035 generalizes it into a bounded loop.
- CAH-036 maps the same provider-neutral values to OpenAI Responses. A future milestone may add a
  generalized MCP registry port with separate transport trust and capability policy.
