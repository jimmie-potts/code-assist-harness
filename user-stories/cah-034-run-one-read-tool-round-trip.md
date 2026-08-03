# CAH-034 - Run one read-tool round trip

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop (integrating E3 repository tools)
- **Dependencies:** CAH-030, CAH-031, CAH-032, CAH-033
- **Lesson:** [One read-tool round trip](../docs/lessons/cah-034-one-read-tool-round-trip.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** One visible harness-owned observe-validate-dispatch-enrich-result-follow-up
  sequence, including scoped-instruction refresh, exact safe result envelopes, cancellation
  boundaries, and aggregate usage evidence.

## User story

> As a learner building an agent loop, I want one accepted model call to run one repository-read tool
> and receive its result in one follow-up model request so that validation, dispatch, replay, and
> evidence ownership are explicit before iteration is introduced.

## Single responsibility

CAH-034 implements exactly one fake-backed, two-turn read-tool round trip using CAH-033's atomic
turn outcomes. It deliberately does not introduce a general loop, provider-specific SDK mapping,
another tool capability, or new transcript schema.

## Scope

- Accept one CAH-033 tool-call outcome, validate and dispatch it through CAH-031, and construct one
  matching provider-neutral result.
- After one successful read, discover instructions for every ordered CAH-031 instruction scope from
  the validated request and model-visible result paths, then atomically enrich the CAH-030 context
  before starting exactly one follow-up provider turn.
- Start that follow-up with full immutable call/result replay, the resulting context snapshot, and
  the same CAH-032 definitions.
- Publish only CAH-033-admitted final text through the existing protocol lifecycle.
- Aggregate optional usage from the two accepted turns with checked arithmetic and persist one
  existing session-level model-usage aggregate only after accepted final text.
- Reuse the existing transcript-v3 aggregate loop evidence; add no per-call record or migration.
- Prove validation order, bounded synchronous execution, cancellation, and exact safe result JSON
  with deterministic fakes through one reusable cooperative scheduling seam.

## Locked contract

- Before the first provider start, CAH-032's pure bridge produces the exact ordered four-tool
  catalog. Bridge failure performs zero provider and tool work. The first request uses CAH-030's
  root-scope context snapshot. The follow-up uses either the atomically enriched snapshot after a
  successful read has complete requested/result-owner instruction coverage or that initial snapshot
  after a known tool error. Tool definitions
  remain byte-for-byte unchanged, and inclusion-report evidence is never sent.
- CAH-033 atomically returns the first accepted call. Only then does orchestration charge the one
  observed tool call and run, in order: exact registry lookup, duplicate-aware JSON-object decoding,
  CAH-032's exact model-facing required-key gate, native Pydantic input validation, synchronous
  dispatch, native result validation, CAH-031 instruction-scope extraction, and bounded rendering.
  CAH-034's decoder consumes preserved object pairs and rejects a repeated decoded member name at
  any nesting depth before constructing a dictionary. Equality is exact after JSON escape decoding,
  with no case folding or Unicode normalization. The key gate runs before Pydantic can apply a
  native default; a failed stage runs no later stage. Direct Python calls remain free to use the
  unchanged native request models and defaults outside this model-facing path.
- CAH-034 owns one reusable asynchronous `cooperate_then_guard(checkpoint)` scheduling seam. At
  every named synchronous boundary it unconditionally `await asyncio.sleep(0)` outside every lock,
  then invokes an optional injected deterministic test observer or gate, and only then applies the
  existing cancellation/deadline guard with its established precedence unchanged. Production code
  does not install a gate. The unconditional yield lets a queued cancel command run on the same
  event loop before the guard reads session state; calling a synchronous guard without yielding is
  not a cancellation checkpoint.
- M2 native tools are intentionally synchronous, bounded, and non-preemptive. Orchestration calls
  `cooperate_then_guard("before_dispatch")`, executes dispatch, then calls
  `cooperate_then_guard("after_dispatch")`. Cancellation cannot interrupt Python code already
  executing; a result that returns after cancellation or deadline selection remains a local
  candidate and is discarded, never replayed, published, or persisted. This is the post-dispatch
  cancellation/deadline check; the yield is what makes newly queued state observable to it.
- After an admitted call passes validation and its native tool succeeds, CAH-031 exposes an ordered,
  exact-deduplicated local `instruction_scopes` tuple. It starts with the validated request `path`
  and then contains the owner directory for every model-visible returned path in native result
  order. Only after the `after_dispatch` checkpoint passes does orchestration process each scope in
  order: ask CAH-025 to discover its bundle, call
  `cooperate_then_guard("after_discovery")`, fold the bundle through CAH-030 into a new local
  context candidate, then call `cooperate_then_guard("after_merge")`. Discovery and merge are
  synchronous and bounded but not preemptible; the seam runs after every scope's discovery and
  merge. A value produced before a losing checkpoint is discarded. A known tool error still passes
  through `after_dispatch`, carries no instruction scopes, skips discovery and merge, produces a
  local safe-result candidate, and retains the initial context candidate.
- Dispatch output, discovered instructions, merged context, result, replay history, and the complete
  bounded follow-up request remain local candidates. After request construction, orchestration
  calls `cooperate_then_guard("before_provider_start")`, performs the existing model-start
  admission, then atomically commits the selected history/context and invokes `Provider.start()`.
  The pre-start guard runs immediately before the follow-up admission/commit/start transition. No
  earlier checkpoint mutates session context, transcript evidence, or replay state. Thus a cancel
  command admitted at any named gate leaves no partial tool result or enriched context, including
  on the known-error path.
- Instruction discovery or context-merge failure is a safe session terminal: no follow-up provider
  operation starts and neither the pending result nor a partially enriched context is published or
  persisted. A successful `list_files` includes every returned directory itself and every returned
  file's parent in its local instruction scopes; `search_text` includes every matched file's parent.
  `stat_path` includes the canonical directory itself or the canonical file's parent, and `read_file`
  includes the canonical file parent.
  Thus every workspace path exposed in result JSON has applicable instructions admitted before that
  result is replayed. Existing CAH-025 source limits and CAH-030's 16-binding, 24-item, and 96-KiB
  bounds remain authoritative: broad evidence that cannot be completely covered fails closed rather
  than truncating scopes or replaying a partial result.
- A successful tool output is the exact compact canonical CAH-031 JSON envelope
  `{"result":<allowlisted-value>}`. Known failures are exact compact JSON envelopes
  `{"error":{"code":"<code>","message":"<fixed message>"}}` with no whitespace. The closed error
  set is CAH-031's `unknown_read_tool`,
  `invalid_read_tool_input`, and `invalid_read_tool_result`, plus CAH-026's twelve
  `RepositoryAccessError` code/message pairs. Malformed JSON, a non-object, or a duplicate decoded
  member name at any object depth maps to `invalid_read_tool_input`. For a known tool, duplicate
  arguments run no key gate, Pydantic validation, dispatch, discovery, or merge. When the final
  checkpoint, request bounds, and model admission pass, the charged call and fixed error must replay
  against unchanged context in the follow-up request. Unknown-name
  lookup still wins before decoding. Unknown exceptions and programmer defects are session failures,
  not model content. `invalid_read_tool_registration` is a pre-provider composition failure.
- The bounded result JSON is stored in `ProviderToolResult.output_json`; success/error meaning is
  inside that payload as well as the neutral domain status. It contains no arguments, absolute path, raw
  exception, OS text, secret, or unbounded content. Rendering or envelope overflow fails the session
  safely instead of truncating JSON.
- The follow-up request is a full immutable replay of original input plus the exact admitted call,
  its matching result, optional first-turn opaque continuation, the same definitions, and the
  atomically selected context snapshot. The single CAH-032 history tuple appends them exactly as
  `..., continuation? -> ProviderToolCall -> ProviderToolResult`; no separate continuation field or
  adapter side channel exists. It is reconstructed under CAH-032's 16-item and 512-KiB bounds before
  `Provider.start()`.
- The follow-up must be CAH-033's accepted non-empty final-text outcome. A second call is charged as
  another observed call, then fails through the existing fixed `tool_call_limit_exceeded` session
  path and starts no third turn. Invalid grammar, context overflow, provider failure, cancellation,
  or deadline follows its established bounded terminal path.
- Assistant text remains buffered until turn-two admission, then the exact staged chunks are emitted
  in order followed by the existing assistant/session completion events. A rejecting delta is never
  emitted or retained.
- Each accepted turn contributes zero or one optional `ProviderUsageReported`. Checked addition
  rejects integer overflow or aggregate values above the existing validated usage ceiling. Exactly
  one aggregate `ModelUsageObserved` is sent to the existing transcript-v3 session evidence path,
  and only after accepted final text wins. Missing usage stays missing; a rejected or cancelled
  round trip persists no partial usage. No transcript version, per-turn record, or per-call record is
  introduced.
- CAH-022 accounting admits exactly two model turns and one observed call for this teaching path.
  Model starts, provider deadline, assistant output, tool-call count, and request bytes remain
  cumulative; no boundary resets accounting.
- No protocol event is added. The TUI sees only the final assistant text and existing terminal.

## Reviewability budget

- **Estimated production-code churn:** 450-600 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- If exact envelope rendering or usage aggregation cannot fit beside the two-turn orchestration,
  split a focused prerequisite; do not add iteration or transcript migration here.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One first-turn accepted call causes exactly one charged observation, at most one native dispatch,
   and exactly one follow-up provider start when admission checks pass.
2. Validation runs in the locked order, and every known failure produces its exact bounded compact
   JSON envelope without executing a rejected later stage.
3. A successful dispatch refreshes instructions for the requested path plus every result-derived
   owner scope before replay; the follow-up replays the exact call/result only against the completely
   and atomically enriched context. A known tool error replays against the initial context.
   Definitions remain unchanged and history stays in the single provider-neutral order
   `continuation? -> call -> result`.
4. One accepted follow-up final answer publishes staged chunks through existing events and selects
   one completed session; a second call or invalid response starts no third turn.
5. Synchronous dispatch, discovery, and merge are never represented as preemptible:
   CAH-034's cooperative seam yields and then checks cancellation/deadline before and after
   dispatch, after each scope discovery, after each scope merge, and before the follow-up start;
   every late candidate is discarded and no result/context/history is committed before the final
   checkpoint and admission.
6. Optional per-turn usage is summed with checked arithmetic and exactly one existing aggregate is
   persisted only after accepted final text; partial/rejected usage is absent.
7. Instruction discovery/merge and all budgets span the two turns and one call without reset;
   discovery, merge, context, or request overflow prevents the follow-up start without publishing or
   persisting the pending result/context.
8. Existing transcript v3 and protocol v1 remain unchanged and content-safe; no per-call evidence
   record, argument, tool content, or provider continuation is persisted.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3-4 | One strict-fake/native-fixture integration starts with root instructions, dispatches a nested path, and asserts a second exact request with its newly applicable instruction—including `[user, opaque, call, result]` when continuation is present—one dispatch, full replay, unchanged definitions, ordered final events, one terminal, and zero third starts. Broad list/search cases return sibling paths and prove every first-occurrence owner bundle is present before result replay; a known-error case proves the second request retains the initial context. |
| 2 | Parameterized malformed/non-object JSON, same-value/conflicting/reversed duplicate names, escape-equivalent `path` names, nested duplicates, omitted defaulted keys, additional keys, unknown tool, invalid input/result, every CAH-026 access error, oversized rendering, and programmer defect asserts the exact envelope or safe session failure plus stage counters. Spies prove a duplicate fails before dictionary collapse/key gate/Pydantic/dispatch, missing/extra keys reach only the key gate, wrong types reach only Pydantic, and unknown lookup wins before decoding. A duplicate-specific two-turn case proves one charged observation, unchanged context, exact call/error history, one follow-up start when admission passes, and no native dispatch. |
| 5 | Named `asyncio.Event` gates at `before_dispatch`, `after_dispatch`, every `after_discovery`, every `after_merge`, and `before_provider_start` deterministically admit cancellation on the event loop; injected clocks prove the exact existing deadline/cancellation tie precedence without elapsed sleeps. Distinctive late tool/bundle/package/history/request sentinels remain local and are discarded, including cancellation on a later broad-result scope and the known-error path. A separate production-mode seam test installs no observer/gate, queues a ready cancellation task, and has the non-awaiting guard spy assert that task already ran before guard entry; deleting the unconditional outside-lock `asyncio.sleep(0)` must fail this test. A semantic documentation-policy assertion locks yield, optional hook, guard order, and CAH-035 reuse. |
| 6 | Two-turn tables cover no usage, usage on either/both turns, exact checked sums, aggregate overflow, rejected turn two, cancellation, and one transcript-v3 aggregate write. |
| 7 | Seeded boundary tests exhaust instruction/context item and byte budgets, model starts, deadline, assistant UTF-8 output, tool calls, native 500-entry/200-match scope derivation, and 512-KiB request projection without reset or late work. Broad list/search results prove exact owner ordering/deduplication and that one denied, invalid, changed, or over-budget returned scope prevents every result/context replay and provider start. |
| 8 | Transcript/replay and protocol fixture suites prove unchanged schemas and absence of call IDs, arguments, result/continuation content, and host paths. |

## Validation

- Use strict fake exchanges, bounded synchronous fake tools, injected clocks, and named
  `asyncio.Event` checkpoint gates; never use live requests, elapsed timing assertions, or
  wall-clock sleeps.
- Separately exercise `cooperate_then_guard` with no test hook: queue cancellation on the same event
  loop, let a synchronous guard spy assert it latched before guard entry, and mutation-test removal
  of `asyncio.sleep(0)`. The awaited Event gates do not count as evidence for the production yield.
- Assert exact request history and context snapshots, registry/discovery/merge stage counters, result
  bytes, provider starts/cleanup, aggregate usage, transcript projection, protocol events, and
  terminal count. Include every CAH-031 scope derivation shape and prove no successful output is
  replayed before all result-path owners have instruction coverage.
- Run focused round-trip, registry, limits, transcript-v3, runtime, and protocol tests followed by
  the canonical non-live repository gate.

## Documentation impact

Update agent-loop, provider-interface, context, safety, transcript/evaluation, glossary, backlog, and
story-index documentation. The concise lesson walks through one call/result feedback cycle and
contrasts local dispatch with a future MCP adapter. Do not create or update a presentation.

## Exclusions

- A general loop, repeated calls, multiple/parallel calls, retries, backoff, or planning framework.
- OpenAI SDK mapping, MCP/hosted tools, protocol/TUI tool events, transcript migration, or per-call
  transcript records.
- Asynchronous/preemptible tools, writes, subprocesses, network tools, approvals, or dynamic policy.

## Definition of done

- The two-turn path, closed error-envelope table, checked usage aggregation, and meaningful
  cancellation/deadline failures have deterministic automated tests.
- Late synchronous results, rejected provider data, arguments, and raw failures cannot enter replay,
  protocol, transcript, logs, or diagnostics.
- **Delivered production-code churn** records the measured result and is no more than 600 lines;
  generic iteration or schema migration is absent.
- Public APIs and the concise Markdown lesson are verified against implementation with a compact
  sequence diagram; presentations remain frozen.
- Focused validation and `./scripts/check` pass before the story is Done and published.

## Planned evidence

- One exact two-exchange fake script with root-only initial instructions, one nested native dispatch,
  atomic scoped-instruction enrichment, and immutable replay with unchanged definitions.
- Closed-table result-envelope, validation-order, discovery/merge, late-result, and budget failure
  suites, including duplicate-aware JSON decoding, unchanged-context known errors, and atomic
  requested-plus-result instruction coverage.
- Checked two-turn usage aggregation with exactly one existing transcript-v3 session record.

## Deferred work

- CAH-035 replaces the explicit two-turn branch with a bounded iterative state machine.
- CAH-036 maps OpenAI Responses items to the provider-neutral staged-turn contract.
- MCP adapters, parallel tool use, visible progress, and side-effecting policy remain later work.
