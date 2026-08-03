# CAH-032 - Define the provider-neutral tool contract

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop (supporting E3 read tools)
- **Dependencies:** CAH-030, CAH-031
- **Lesson:** [Provider-neutral tool contract](../docs/lessons/cah-032-provider-tool-contract.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** The language-neutral seam for scoped context, tool semantics, and
  provider-specific function-calling APIs.

## User story

> As an agent-loop developer, I want tool definitions, requested calls, and tool results represented
> in provider-neutral values so that the loop can reason about tool use without importing an SDK or
> delegating orchestration to a provider.

## Single responsibility

CAH-032 extends the provider port and strict fake with the complete provider-neutral request and
history values needed for tool-assisted turns, including an ordered opaque-continuation carrier and
an immutable, scope-preserving projection of one CAH-030 context snapshot. It permits later requests
to carry a newly enriched snapshot but does not discover or merge instructions, compare session
transitions, parse or dispatch a call, run a second model turn, map OpenAI SDK events, or expose MCP.

## Scope

- Add immutable provider-neutral values for one function-like tool definition, one requested call,
  one tool result, and a bounded opaque-continuation item type.
- Extend `ProviderRequest` with ordered model input history and an ordered tuple of available tool
  definitions while preserving text-only requests.
- Add a pure projection from CAH-030's package into ordered provider request context, including each
  instruction's explicit `applies_to`, without sending the inclusion report or flattening repository
  evidence into user/assistant history.
- Refactor `ProviderToolCallRequested` to carry the shared call value rather than duplicating fields.
- Teach the strict fake to compare the complete tool-aware request and script tool-call observations.
- Add one pure harness bridge that maps CAH-031 registry descriptors and native Pydantic input models
  into the portable provider definitions; neither the registry nor provider-domain package imports
  the other.
- Add one pure model-facing argument-key gate that accepts an already decoded JSON object and checks
  its exact key set against the portable definition before native Pydantic validation can apply a
  default. Keep the native request models and their direct-Python defaults unchanged.
- Add exact canonicalization plus strict Unicode-scalar/UTF-8 validation and bounded,
  content-suppressed representations for identifiers, descriptions, schemas, arguments,
  continuations, and result envelopes.

## Locked contract

### Exact portable schema subset

- `ProviderToolDefinition` contains a stable name, bounded description, and a deeply immutable
  canonical parameter schema from this closed JSON Schema Draft 2020-12 subset. The canonical root
  contains exactly `type`, `properties`, `required`, and `additionalProperties`; `type` is exactly
  `"object"`, `additionalProperties` is exactly `false`, and `required` contains every property name
  exactly once in property-name UTF-8 order. Zero through 32 properties are allowed.

| Location / property type | Required keywords | Optional keywords | Rejected examples |
| --- | --- | --- | --- |
| root object | `type`, `properties`, `required`, `additionalProperties` | none | `title`, `$schema`, `$id`, `$ref`, `$defs`, `allOf`, `anyOf`, `oneOf`, `not`, `patternProperties`, `unevaluatedProperties` |
| `string` property | `type: "string"` | `description`, `enum`, `pattern`, `minLength`, `maxLength` | `format`, `default`, `const`, arrays, nested schemas |
| `integer` property | `type: "integer"` | `description`, `enum`, `minimum`, `maximum` | floats, `multipleOf`, exclusive bounds, `default`, nested schemas |
| `boolean` property | `type: "boolean"` | `description`, `enum` | numeric/string constraints, `default`, nested schemas |

- Property names match `[a-z][a-z0-9_]{0,63}`. Length bounds are non-boolean integers at least zero
  with `minLength <= maxLength`; numeric bounds are integers (not booleans) with
  `minimum <= maximum`. `enum`, when present, is a non-empty list of unique values of the declared
  property type; integer enums reject booleans. Every description, pattern, enum string, property
  name, and other schema string passes the strict scalar/UTF-8 rule below. Every keyword or shape
  not named in the table is rejected.
- Canonicalization makes a defensive deep copy, validates the closed table, orders `properties` by
  property-name UTF-8 bytes, rebuilds `required` from that order, preserves declared enum order, and
  freezes the result. Its canonical bytes are produced with
  `json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True,
  allow_nan=False).encode("utf-8", "strict")`. Schema size is measured from those bytes. No
  normalization, reference resolution, coercion, inferred constraint, or general JSON-Schema engine
  is permitted.
- The separate pure bridge function `build_provider_tool_definitions(registry)` owns conversion from
  CAH-031 descriptors/Pydantic request models. It may discard only Pydantic's annotation-only
  `title` and native `default` entries, then must reject every remaining unsupported keyword or
  shape, make every property model-required, canonicalize, and return all definitions atomically in
  registry order. `ProviderToolDefinition` has no `from_descriptor` method, the registry does not
  import provider models, and no hand-maintained second tool catalog exists.
- The separate pure `require_provider_tool_argument_keys(definition, arguments)` gate accepts only
  an already JSON-decoded object and compares its keys exactly with the definition's canonical
  `required` names. Missing keys—including fields for which the native Pydantic model has a
  default—and additional keys fail with a bounded content-safe validation error before
  `model_validate(...)` is called. The gate neither parses JSON nor performs native type validation,
  coercion, lookup, or dispatch. It does not modify the CAH-031 request models: trusted direct Python
  callers may still construct and validate those native models with their existing defaults.

### Calls, result envelopes, and history

- `ProviderToolCall` contains a bounded call ID, exact registered name, and the provider's unparsed
  JSON argument string. A call ID matches `[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}` exactly. The tool name
  uses the lower-snake grammar above. Construction validates those identifiers plus strict
  scalar/UTF-8 and byte limits but deliberately does not parse arguments.
- `ProviderToolResult` contains the matching call ID, an explicit `success` or `error` status, and
  one canonical `output_json` envelope. Success is byte-for-byte the CAH-031 compact envelope
  `{"result":<allowlisted-value>}`. Error is exactly
  `{"error":{"code":"<code>","message":"<fixed message>"}}`, where `code` matches
  `[a-z][a-z0-9_]{0,63}` and message is non-empty. No other top-level or nested key is allowed.
- Result construction parses only to validate the closed envelope, JSON-safe value tree, and exact
  reserialization. `status="success"` is legal only with the sole top-level `result` key;
  `status="error"` only with the sole top-level `error` key. A mismatched status, noncanonical
  bytes, float, extra key, malformed JSON, lone surrogate, or oversized envelope fails before it
  enters history. Results contain no exception, absolute path, credential, raw OS error, or provider
  object, and their ordinary representation suppresses `output_json`.
- `ProviderOpaqueContinuation` contains one non-empty `payload` string owned by the active provider
  adapter. Construction requires an exact strict Unicode-scalar/UTF-8 round-trip, rejects literal
  NUL, performs no normalization, and caps the encoded payload at 65,536 bytes inclusive. Core code
  preserves exact equality but never parses or interprets the value. Its ordinary representation,
  validation errors, strict-fake mismatches, logs, protocol, and transcripts reveal no payload.
- Provider request input is an immutable ordered tuple whose admitted item types are user/assistant
  messages, opaque continuations, prior tool calls, and matching tool results. A continuation is a
  positional provider-output item, not a separate request field or adapter side channel: it must
  immediately precede the provider-produced call or assistant message it belongs to. It is invalid at
  history start or end, before a user message, result, or second continuation, or while a prior call
  remains unresolved. A tool result must follow its one unmatched call; duplicate IDs, orphan results,
  unresolved prior calls, and text after an unresolved call are rejected at construction. The M2
  round-trip order is therefore original input, optional continuation, call, matching result.
- `ProviderRequest.repository_context` is the exact immutable ordered `ContextItem` tuple projected
  from one successful CAH-030 package. An instruction projection includes canonical source,
  canonical candidate-owner `applies_to`, path-local precedence, exact admitted content, byte count,
  and truncation state; `applies_to` is copied and never derived from a possibly symlink-resolved
  source. Focus and search items retain their existing kind-specific provenance. It inherits that
  package's 16-binding, 24-item, and 96-KiB content bounds. The inclusion report remains
  harness evidence and never becomes model input. The existing `repository_instructions` field
  remains valid for CAH-020 through CAH-023 compatibility only when `repository_context` is empty.
  Supplying both representations fails construction, so no source is duplicated or silently given
  another priority.
- Every `ProviderRequest` is an immutable snapshot. Later orchestration may build a successive request
  from CAH-030's atomically enriched package; the earlier request remains unchanged. CAH-032 neither
  invokes enrichment nor proves a transition monotonic in isolation, while the strict fake can
  compare exact successive snapshots. No constructor requires all requests in unrelated sessions to
  share a context value.
- Provider adapters receive already-selected context. They may serialize item kind, canonical
  workspace label, instruction `applies_to` and path-local precedence, line provenance, and content,
  but may not add, omit, deduplicate, rank, select, or mutate items. A sibling scope's serialization
  order does not create precedence. Adapter-specific role/framing is deferred to that adapter's
  mapping story.
- Available definitions are an immutable ordered tuple with unique names. Empty definitions retain
  the exact CAH-023 text-only request semantics.
- Native request defaults remain available to direct Python callers, but the bridge removes
  `default` annotations and makes every field model-required. The raw-key gate enforces that
  distinction before native Pydantic validation, avoiding either an adapter or the native model
  silently filling a value the model omitted.
- `ProviderToolCallRequested` is still only an observation. Neither its construction nor the fake
  parses arguments, performs lookup, executes a tool, or authorizes another turn.
- CAH-031's local `ReadToolSuccess.target_scope` never enters `ProviderToolResult`, request context,
  history, schema, or the canonical result envelope. Later harness orchestration may use it to obtain
  a CAH-025 bundle and ask CAH-030 for a new snapshot; providers receive only the resulting admitted
  context items.
- Fake request mismatch diagnostics remain bounded and content-safe: they may identify a structural
  field path and exchange number but never include message text, schema content, arguments, result
  output, or `repr()` of the request.
- The contract models local function-like tools and does not claim direct MCP compatibility. A
  later generalized registry port would snapshot an MCP catalog, re-admit every tool through the
  local name/schema filters, classify remote/network capability separately from `read_workspace`,
  and map MCP `structuredContent`, `outputSchema`, and `isError` into these canonical success/error
  semantics. It must also own transport trust, authentication, catalog change/revocation,
  timeouts, cancellation, and bounded remote output. None of that transport, discovery, or remote
  execution is part of M2.

### Strict string and byte admission

- Every CAH-032-owned model-facing string is checked after JSON parsing by strict UTF-8 encode,
  strict UTF-8 decode, and exact equality. Lone surrogates and literal NUL are rejected; valid
  Unicode scalar values remain unchanged and are never normalized. Identifier grammars apply after
  this check. The raw argument string may contain the literal characters of an escaped JSON value
  such as `\\u0000`, but not an actual NUL; CAH-034 owns JSON decoding, the CAH-032 key gate, and
  subsequent native-field admission.
- Bounds below count the strict UTF-8 bytes of the complete value named. Rejection is atomic and
  never truncates a string, schema, result, history, or request projection.

### Exact provider-domain bounds

| Value | Hard maximum or grammar |
| --- | --- |
| Available tool definitions | 16 per request; M2 composition supplies exactly 4 |
| Tool name | 64 ASCII characters matching `[a-z][a-z0-9_]*` |
| Tool description | 1,024 UTF-8 bytes, non-empty |
| Canonical parameter schema | 16 KiB (16,384 UTF-8 bytes) and 32 root properties |
| Call ID | 1-256 ASCII characters matching `[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}` |
| Serialized call arguments | 16 KiB (16,384 UTF-8 bytes) |
| Opaque continuation payload | 64 KiB (65,536 UTF-8 bytes), non-empty |
| Error code / message | code matches `[a-z][a-z0-9_]{0,63}`; non-empty message is at most 1,024 UTF-8 bytes |
| Complete canonical tool-result envelope | 64 KiB (65,536 UTF-8 bytes), including escaping, keys, punctuation, and wrapper |
| Ordered conversation/history items | 16 per request |
| Complete provider-neutral request projection | 512 KiB (524,288 UTF-8 bytes), including context labels and instruction `applies_to` metadata |

Every byte bound uses the strict UTF-8 rules above. Construction rejects a value above its bound
rather than truncating it, and ordinary representations omit schema, argument, result, continuation,
and message content. A continuation counts as one of the 16 history items. Its tagged projection is
exactly `{"kind":"opaque_continuation","payload":<string>}`. The complete request bound is the
length of one compact, sorted-key JSON projection using the same serializer options over messages,
every context field including `applies_to`, definitions, continuations, calls, and results; the
tagged continuation and its JSON escaping are charged exactly once. It is a deterministic admission
proxy, not a provider token count or a claim about an adapter's exact wire bytes.

## Reviewability budget

- **Estimated production-code churn:** 450-600 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- Split schema canonicalization into an earlier contract unit if implementation requires a general
  JSON-Schema engine, scoped projection requires orchestration/session state, or the unit is likely
  to exceed 600 production lines. Do not broaden this contract to make room implicitly.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. Tool definitions, calls, results, and opaque continuations are immutable, typed, SDK-free
   provider-domain values.
2. Tool-aware history enforces exact continuation position and call/result pairing while existing
   text-only requests remain valid; no continuation uses a separate request field or side channel.
3. Definitions require unique names, the exact keyword/type table, and canonical schema bytes;
   mutable input cannot mutate a constructed request and the bridge owns all descriptor conversion.
4. Calls use the exact call-ID grammar and preserve argument bytes without parsing; results use the
   exact canonical success/error envelopes and status always agrees with the sole top-level key.
5. The strict fake matches exact tool definitions and history, including opaque payload equality,
   emits scripted call requests, and reports structural mismatches without content leakage.
6. The pure registry-to-definition bridge maps all four operations exactly or fails atomically
   before provider work, without reverse imports or a duplicate catalog.
7. One successful CAH-030 package projects into exact ordered request context including instruction
   `applies_to`; reports and CAH-031 local target scope are omitted, legacy instruction-only requests
   remain valid, and mixed legacy/new context is rejected.
8. Every owned model-facing string proves strict Unicode-scalar/UTF-8 round-trip admission and fixed
   byte boundaries without normalization or content leakage.
9. An already decoded model-facing argument object must contain exactly every canonical required key
   before native Pydantic validation runs; omitted defaulted fields and extras fail while direct
   Python callers retain the native request models' defaults.
10. Continuations are non-empty strict Unicode-scalar/UTF-8 values bounded at 65,536 bytes, count once
    toward both history-item and request-projection limits, and never enter representations or
    diagnostics.
11. Independently immutable successive requests may carry an atomically enriched context snapshot;
    the strict fake compares each exact value, all context metadata is charged once to the 512-KiB
    request bound, and neither this contract nor an adapter selects or removes an item.
12. No dispatch, extra model turn, OpenAI mapping, MCP transport, protocol, or TUI behavior is added.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3 | Constructor/property tests cover every numeric bound below/at/above, immutability, defensive copying, all rows and constraints in the keyword table, title/default bridge filtering, canonical property/required order, compact sorted-key snapshot bytes, and every unsupported keyword/shape. |
| 4, 8 | Call tests exercise the ID grammar's first/last/invalid characters and lengths 1/256/257; string tests accept unchanged multibyte scalars and reject high/low lone surrogates plus literal NUL before fake/provider work. Result snapshots prove byte-for-byte CAH-031 success reuse and the exact error envelope, then reject status/key mismatch, extras, floats, malformed/noncanonical JSON, and 65,537-byte output without leaks. |
| 2, 10 | Table tests cover valid text-only, `continuation? -> call -> result`, `continuation? -> assistant`, and multiple separated continuation/call/result groups in one history; reject start/end, orphan, duplicate, unresolved, reordered, and wrongly followed continuations; and prove 16/17-item plus 65,535/65,536/65,537-byte boundaries, NUL/lone-surrogate rejection, multibyte counting, safe `repr`, and exact per-item single-charge request projections at 524,287/524,288/524,289 bytes. |
| 5 | Strict-fake tests accept one exact tool request and reject changed order, definition, continuation payload, call, and result fields with only a structural mismatch path. |
| 6, 9 | `build_provider_tool_definitions` tests compare all four descriptors and exact generated schema snapshots, then inject duplicate, drifted, and unsupported shapes and assert atomic failure before provider start; an import test forbids `from_descriptor`/reverse imports. Argument-gate tests use a native model with a default, prove an omitted defaulted key and an extra key fail before a spy `model_validate` call, prove the exact key set reaches native validation unchanged, and prove direct native construction still applies the default. |
| 7, 11 | Context-projection tests assert exact order/source/candidate-owner `applies_to`/path-local precedence/content, including source and applicability that differ, report and local-target-scope omission, inherited 16-binding/24-item/96-KiB bounds, and exact 512-KiB charging. Two-request fake scripts prove the first snapshot is unchanged while the second contains CAH-030's enriched instruction block; sibling serialization is not treated as precedence. |
| 7 | Compatibility tests preserve legacy instruction-only requests and reject mixed legacy/new context. |
| 12 | Integration tests assert fake observation alone executes no registry tool and starts no second provider exchange; import-policy checks remain green. |

## Validation

- Run focused provider-model and fake-provider tests, including distinctive secret-like sentinels in
  negative cases and assertions that diagnostics omit them.
- Snapshot canonical schema JSON for all four native definitions and both result-envelope statuses.
  Cover strict scalar round-trip, every call-ID grammar boundary, complete envelope bytes at
  65,536/65,537, and insertion-order-independent canonicalization.
- Run deterministic argument-key tests that prove missing and additional model-facing keys fail
  before native Pydantic validation/default application while direct native callers retain defaults.
- Prove continuation order, item counting, tagged canonical request projection, exact strict-fake
  equality, 65,536-byte payload admission, and content-suppressed failures without parsing payloads.
- Snapshot initial and enriched context requests, including `applies_to` and boundary-changing label
  bytes, and prove adapters/fakes cannot omit, select, or reorder an admitted item.
- Re-run existing text-only adapter/session tests unchanged or with narrow construction updates.
- Run the canonical network-free repository gate.

## Documentation impact

Update provider-interface, agent-loop, glossary, safety, story-index, and backlog documentation. The
lesson traces definition -> call observation -> result history and explains why an MCP integration
would be an adapter to these concepts, not a replacement for the harness-owned loop. No presentation
changes are permitted.

## Exclusions

- Registry dispatch, JSON argument validation against a native tool input, tool execution, context
  enrichment, transition validation, or a second provider turn.
- OpenAI Responses SDK mapping; direct MCP compatibility; remote MCP/hosted tools; catalog
  snapshot/re-admission; remote/network capability, auth, timeout, cancellation, or
  `structuredContent`/`outputSchema`/`isError` mapping; dynamic discovery; or provider-managed
  conversation state.
- Protocol/TUI tool events, transcript tool content, writes, approvals, retries, or parallel calls.

## Definition of done

- Exact constructors, schema table/canonicalization, pre-Pydantic argument-key gate, call-ID grammar,
  result envelopes, ordered opaque continuations, scoped initial/enriched context snapshots, and fake
  behavior have happy and meaningful failure tests.
- Existing text-only provider behavior remains compatible and the provider port remains SDK-free.
- Production-code churn does not exceed 600 lines; any broader schema or orchestration concern is
  split out.
- Public APIs and the concise Markdown lesson are verified against code, with a compact text
  architecture diagram and no presentation work.
- Focused checks and the full repository gate pass before review handoff.

## Planned evidence

- Provider-domain tests for immutable definition/call/result/continuation values and ordered history
  grammar.
- Strict-fake tests proving exact content-safe initial/enriched request matching and script
  completion, including `applies_to` projection and request-byte charging.
- Import-policy evidence that SDK and MCP types remain outside the provider-neutral contract.

## Deferred work

- CAH-033 stages and validates one complete tool-aware provider response before publication or
  dispatch.
- CAH-034 consumes the admitted outcome in one explicit fake-backed read-tool round trip.
- CAH-035 generalizes that teaching slice into a bounded iterative loop, and CAH-036 maps the same
  values to OpenAI Responses. A later milestone may add a generalized MCP registry port.
