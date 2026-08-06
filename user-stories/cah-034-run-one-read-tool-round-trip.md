# CAH-034 - Run one read-tool round trip

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop (integrating E3 repository tools)
- **Dependencies:** CAH-030, CAH-031, CAH-032, CAH-033, CAH-039
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

- Accept one CAH-033 tool-call outcome, prepare it through CAH-039, dispatch an admitted invocation
  through CAH-031, and construct one matching provider-neutral result.
- After one successful read, discover instructions for every ordered CAH-031 instruction scope from
  the native operation's execution-time canonical request scope and model-visible result paths, then
  atomically enrich the CAH-030 context before starting exactly one follow-up provider turn.
- Start both requests with `catalog.definitions`, then start the follow-up with full immutable
  call/result replay and the resulting context snapshot.
- Publish only CAH-033-admitted final text through the existing protocol lifecycle.
- Aggregate optional usage from the two accepted turns with checked arithmetic and persist one
  existing session-level model-usage aggregate only after accepted final text.
- Reuse the existing transcript-v3 aggregate loop evidence; add no per-call record or migration.
- Prove the CAH-039 handoff, bounded synchronous execution, cancellation, and exact safe result JSON
  with deterministic fakes through one reusable cooperative scheduling seam.

## Locked contract

- `build_read_only_agent_services(boundary: WorkspaceBoundary) -> ReadOnlyAgentServices` is the sole
  M2 composition factory. It constructs, in order, one instruction discovery, read policy, metadata
  reader, text reader, searcher, context builder, registry, and catalog from that exact boundary.
  `ReadOnlyAgentServices` is a frozen runtime-scoped carrier exposing those nine exact read-only
  identities as `boundary`, `instructions`, `policy`, `metadata_reader`, `text_reader`, `searcher`,
  `context_builder`, `registry`, and `catalog`; callers cannot directly construct or cross-wire it.
  The factory validates every CAH-029/030/031/039 identity edge before publication and owns no session state.
  `ProviderSessionRunner(..., repository_instructions=(), read_only_services:
  ReadOnlyAgentServices | None = None, initial_context_request: ContextBuildRequest | None = None,
  limits: LoopLimits | None = None)`
  retains that exact object and passes it unchanged to each new `ProviderSession`. `None` preserves
  the shipped text-only path. Construction is fail-fast: `read_only_services is not None` requires
  legacy `repository_instructions == ()`; `read_only_services is None` requires
  `initial_context_request is None`; when services are present, `limits` must also be explicit rather
  than silently inheriting the shipped one-turn profile. Invalid combinations fail before runner/session publication,
  lifecycle events, filesystem I/O, or provider work rather than silently ignoring one carrier or
  producing a mixed CAH-032 request. The CAH-034 teaching path requires the bundle and exact standalone
  `LoopLimits(max_model_turns=2, provider_work_timeout_seconds=120,
  max_assistant_output_bytes=4096, max_observed_tool_calls=1)`. The runner creates one fresh
  `LoopLimitTracker` and one fresh context/history/operation state per session; equal-but-distinct
  dependency graphs are rejected at composition rather than rejoined inside a turn.
- After `session.started` makes the session lifecycle authoritative, the session builds its initial
  package with exact `ContextBuildRequest(scope=".", focus_paths=(), search_queries=())` and the
  CAH-030 checkpoint adapter, then calls CAH-032 `build_provider_context` and constructs the initial
  request with the bundle's one `catalog.definitions`. CAH-025 discovery failure preserves its exact
  code/message; CAH-030 and CAH-032 failures use the exact non-replayable table below. Each becomes one
  `session.failed` with zero provider starts and no partial session context/history. Failure is local
  to that session: the runtime may accept the next start with a fresh tracker and state. Catalog
  construction remains a runtime-composition prerequisite before the runner is published, so its
  failure creates no session ID or lifecycle event.
- Initial and follow-up context projection/request construction capture either one complete request or
  one exception as a local candidate. Orchestration always crosses the same
  `cooperate_then_guard("before_provider_start")` before unwrapping that candidate. Thus
  cancellation/deadline queued during bounded root context or request projection can win over a
  `ProviderToolContractError` or unexpected construction defect. If lifecycle does not win, the
  closed table below maps the error with zero model-turn charge/start; only a complete request enters
  the no-await start transaction.
- Inside the sole `build_read_only_agent_services(boundary)` call and before that carrier is
  published, composition calls CAH-039's `build_read_tool_catalog(registry)` exactly once. That
  registry-only factory invokes CAH-038's pure bridge internally, binds the returned exact
  four-definition tuple to the exact CAH-031 entries, exposes the one retained `catalog.definitions`
  to every CAH-032 request, and supplies that same catalog to argument admission. No caller rebuilds
  the catalog. Bridge/catalog failure performs zero runner publication, provider, or tool work. Independently built
  catalogs are legal when used consistently; mixing their definitions, prepared calls, or registry
  entries is not. The first request uses CAH-030's
  root-scope context snapshot. The follow-up uses either the atomically enriched snapshot after a
  successful read has complete canonical-request/result-owner instruction coverage or that initial snapshot
  after a known tool error. Tool definitions
  remain byte-for-byte unchanged, and inclusion-report evidence is never sent.
- Every provider request obtains `repository_context` only through CAH-032's sole
  `build_provider_context(context_package)` integration bridge. CAH-034 never constructs provider
  context variants locally; bridge failure follows the exact non-replayable table below before a
  provider start.
- CAH-033 atomically returns the first accepted call. Only then does orchestration charge the one
  observed tool call and call CAH-039's sole synchronous admission path. CAH-039 owns exact lookup,
  quote-aware 16-KiB/64-level structural and signed-64-bit integer preflight, constant-rejecting
  pair decode, iterative every-depth duplicate rejection, dictionary construction, an exact-key gate
  against the catalog's CAH-038 definition, and strict native Pydantic validation. Its exact return
  type is `PreparedReadToolCall | ProviderToolResult`: either one content-suppressed invocation bound
  to that catalog's exact CAH-031 entry or the exact `unknown_read_tool`/`invalid_read_tool_input`
  result, with no wrapper carrier. CAH-034 must
  not wrap, copy, or partially reimplement those stages; integration spies assert that a rejected
  value causes zero dispatch and that a prepared value reaches same-catalog, same-entry dispatch
  unchanged.
- Every CAH-033 return crosses one guard-owned outcome-adoption transaction before accounting or side
  effects. Under the existing decision/deadline guard, orchestration first rechecks an authoritative
  selection and `_deadline_latched or _deadline_is_due()`. If cancellation/deadline already owns the
  guard, it discards the returned candidate with no new call charge, output reservation, usage
  candidate, dispatch, or publication. Otherwise a tool-call outcome calls the existing
  `LoopLimitTracker.observe_tool_call()` in that same transaction before cleanup/admission/dispatch;
  the admitted or rejecting observation is retained exactly as CAH-022 defines, and an admitted charge remains if
  cancellation wins later. A final-text outcome validates the complete usage candidate and reserves
  its whole text in the same guarded adoption before any cleanup or publication. A normalized
  provider failure is likewise selected there. The private helper's exact return is the unchanged
  `AcceptedToolCall | AcceptedFinalText | None`; `None` means the helper selected or observed an
  authoritative terminal. No test-only checkpoint sits inside the guard. A separate optional
  `outcome_adoption_observer` pauses immediately before it in deterministic tests; production passes
  `None`. This observer is not a `ReadOnlyCheckpoint` and does not add another cooperative scheduling
  seam. Its exact private session-constructor type is
  `Callable[[], Awaitable[None]] | None`; focused tests inject it directly, while
  `ProviderSessionRunner` always passes `None` and does not expose a production configuration option.
- CAH-034 owns reusable `dispatch_one(catalog: ReadToolCatalog, prepared: PreparedReadToolCall) ->
  DispatchCandidate`. `DispatchCandidate` contains exactly `provider_result: ProviderToolResult` and
  `instruction_scopes: tuple[str, ...]`. The helper requires
  `prepared.catalog_identity is catalog.identity` and the exact prepared `ReadTool` entry to belong
  to `catalog.registry`; a distinct catalog over the same registry and a second same-shaped registry
  both raise CAH-039's exact `ReadToolCatalogError` before handler I/O, result replay, or a provider
  follow-up. After the guard, the helper calls CAH-031's provider-independent
  `dispatch_bound(prepared.read_tool, prepared.request)`, then constructs the correlated CAH-032
  `ProviderToolResult` from `ReadToolSuccess.output_json` and keeps its local instruction scopes in
  one CAH-034 dispatch candidate. CAH-031 never imports a CAH-039 type, and a native success never
  invents a `provider_result` field. The helper also maps only CAH-026's closed access failures and
  CAH-031's `invalid_read_tool_result`/`read_tool_output_too_large` into correlated error results
  with an empty scope tuple. CAH-031 `invalid_read_tool_binding` maps without chaining to the same
  exact non-replayable `ReadToolCatalogError`; any impossible lookup/input/registration code or
  unknown exception is a content-suppressed session failure.
- CAH-034 owns one reusable asynchronous
  `cooperate_then_guard(checkpoint: ReadOnlyCheckpoint) -> None` scheduling seam. At
  every named synchronous boundary it unconditionally `await asyncio.sleep(0)` outside every lock,
  then invokes an optional injected deterministic test observer or gate, and only then applies the
  existing cancellation/deadline guard with its established precedence unchanged. Production code
  does not install a gate. The unconditional yield lets a queued cancel command run on the same
  event loop before the guard reads session state; calling a synchronous guard without yielding is
  not a cancellation checkpoint. Normal return is the sole authorization to execute the next line.
  When lifecycle has already selected a terminal, the seam raises private `_SessionLifecycleStop`
  after that selection; only the session orchestration boundary consumes it. Stage capture/mapping,
  CAH-030, provider adapters, and generic exception handlers must never convert it into another
  failure or ignore it.
- `checkpoint` belongs to the closed `ReadOnlyCheckpoint` union `before_dispatch | after_dispatch |
  after_discovery | after_merge | before_provider_start | after_focus_read | after_search`. CAH-034's
  round trip uses the first five; the CAH-030 callback adapter passes the last two as well as every
  initial discovery/merge occurrence through this same seam. No second yield/guard implementation is
  introduced for initial context work.
- M2 native tools are intentionally synchronous, bounded, and non-preemptive. Orchestration calls
  `cooperate_then_guard("before_dispatch")`, executes dispatch, then calls
  `cooperate_then_guard("after_dispatch")`. Cancellation cannot interrupt Python code already
  executing; a result that returns after cancellation or deadline selection remains a local
  candidate and is discarded, never replayed, published, or persisted. This is the post-dispatch
  cancellation/deadline check; the yield is what makes newly queued state observable to it.
- A synchronous stage's exception is also only a local candidate until its mandatory following seam.
  Dispatch, each instruction discovery, and each context merge capture either one value or one
  exception without publishing or mapping it, always cross `after_dispatch`, `after_discovery`, or
  `after_merge`, and only then unwrap/map the candidate if no lifecycle terminal won. A queued
  cancellation/deadline therefore beats a dispatch exception, `RepositoryInstructionError`, or
  `ContextBuildError` that returned before its seam; the exception is discarded content-suppressed.
  If lifecycle does not win, the exact closed failure table applies. An `asyncio.CancelledError`
  propagates as task control flow only when `asyncio.current_task().cancelling() > 0`; one raised
  independently by dispatch, discovery, merge, context projection, or request construction is an
  unexpected local stage candidate, crosses the same mandatory seam, and maps to the fixed invalid
  response if lifecycle does not win.
- After an admitted call passes validation and its native tool succeeds, CAH-031 exposes an ordered,
  exact-deduplicated local `instruction_scopes` tuple. It starts with the execution-time canonical
  request scope captured by the validated native result and then contains the owner directory for
  every model-visible returned path in native result order. Orchestration never re-resolves or falls
  back to the original request alias. Only after the `after_dispatch` checkpoint passes does it
  process each scope in order: call CAH-025 `discover_for_path(scope)`, then call
  `cooperate_then_guard("after_discovery")`, require `bundle.canonical_scope == scope`, and pass both
  values to CAH-030's pure enrichment operation. Only then may the bundle fold into a new local
  context candidate, followed by `cooperate_then_guard("after_merge")`. Replacing the captured
  canonical label with an allowed symlink to another target therefore fails rather than redirecting
  instruction authority. Discovery and merge are synchronous and bounded but not preemptible; the
  seam runs after every scope's discovery and merge. A value produced before a losing checkpoint is
  discarded. A known tool error still passes through `after_dispatch`, carries no instruction
  scopes, skips discovery and merge, produces a local safe-result candidate, and retains the initial
  context candidate.
- Dispatch output, discovered instructions, merged context, result, replay history, and the complete
  bounded follow-up request-or-error remain local candidates. Orchestration calls
  `cooperate_then_guard("before_provider_start")` before unwrapping that final construction candidate.
  A complete request then calls exact private
  `async def _start_claim_and_commit_turn_atomically(...) -> _InstalledTurnState | None`. The helper
  may await existing decision/deadline-lock acquisition before entering its critical section and may
  await a transferred uninstalled-operation cleanup task after selecting a terminal. Inside the
  critical section, from model admission through a successful pointer commit, there is no await. It
  returns an installed carrier only after that commit; `None` means an authoritative terminal is
  selected and any uninstalled cleanup has joined, so the caller performs no iteration. Under the
  session guard its no-await section reuses CAH-022's mutable
  `LoopLimitTracker.admit_model_turn()` immediately before synchronous
  `Provider.start(request_candidate)`. The admitted attempt is charged even if the lazy factory
  raises, returns an invalid operation, or has an invalid single-use event stream; this deliberately
  preserves CAH-022 evidence semantics. With no intervening await, the same guarded transaction calls
  `Provider.start(request_candidate)`, requires the returned value to satisfy the complete
  runtime-checkable `ProviderOperation` port (`events`, `cancel`, `wait_closed`, and
  `force_cancel_cleanup`) before invoking any method, synchronously calls `operation.events()` exactly
  once, validates that result as the claimed async iterator, and constructs one complete immutable
  `_InstalledTurnState` candidate containing the new operation generation plus the selected
  history/context/result snapshots. Every allocation, validation, and test fault hook occurs before
  the final `_deadline_latched or _deadline_is_due()` read. If that read passes, one non-failing
  pointer assignment installs the complete carrier and commits all candidates atomically; there is no
  fallible multi-field install after the linearization point.
  `Provider.start` remains non-blocking, lazy, and I/O-free: provider I/O begins only when the claimed
  iterator is advanced.
- The deadline is checked before admission, in every start/claim/carrier-construction exception path,
  and once after a complete installed-state candidate exists. A deadline observed at that final read
  wins as exact `provider_work_deadline_exceeded`; a deadline becoming due only after the single
  pointer assignment loses this transition and is handled by the installed generation's normal
  watcher. Otherwise a start/claim/shape/carrier-construction failure is existing
  `provider_invalid_response` / `The provider returned an invalid response.`.
  Both retain the charged attempt and leave context/history/result candidates uncommitted. A value
  that fails the full operation-port check has no trusted cleanup API and is never installed or
  invoked. A valid real but uninstalled operation is settled outside the lock through the existing one-owner cleanup
  supervisor: call and await ordinary `cancel()` first under the fixed five-second grace, call
  `force_cancel_cleanup()` exactly once only if cancel fails or the grace expires, never run the two
  cleanup APIs concurrently, and retain the original selected terminal. The selected terminal is
  reserved but cannot be published until the one uninstalled-operation cleanup task has joined;
  cleanup trouble records the existing `provider_cleanup_failed` diagnostic before the terminal
  event. The terminal finalizer joins that same task instead of seeing an empty generation and racing
  ahead. Only an installed, claimed operation is iterated.
  The pre-start guard runs immediately before this no-await admission/start/claim/carrier/final-clock/
  pointer-commit
  transition and the one-pointer installed-state commit is its exact linearization point. No
  earlier checkpoint mutates session context, transcript evidence, or replay state. Thus a cancel
  command admitted at any named gate leaves no partial tool result or enriched context, including
  on the known-error path.
- Each provider turn owns one private `_ProviderOperationGeneration` containing exactly its monotonic
  generation number, operation, claimed iterator, pending-read task, cleanup task, and cleanup mode.
  The collector and deadline/cancellation paths address only the current generation by identity. One
  guard-owned cleanup task is created per generation with the mode of its first owner. A later
  cancellation, deadline, or finalizer joins that same task even when it would otherwise request a
  different mode; it never raises mode drift or invokes `cancel()` concurrently with an already-owned
  `wait_closed()` path. If cancellation owns cleanup first, its one task uses cancel mode.
- On a tool-call outcome, exact private
  `async def _settle_and_clear_current_generation_for_continuation() -> bool` settles the current
  generation without stopping the session-wide absolute-deadline watcher. `True` is returned only
  after confirmed local reaping, identity-checked clearing, and a guard proving no terminal owns the
  session; `False` means continuation is forbidden and the caller must return before CAH-039 admission,
  dispatch, or another provider start. It supervises natural `wait_closed()` under the
  existing five-second grace. If that barrier raises or expires, the helper cancels and reaps the local
  barrier task, invokes `force_cancel_cleanup()` exactly once, and may continue only after force returns
  and local reaping is therefore confirmed. Ordinary failure/grace may add the existing
  `provider_cleanup_failed` diagnostic after successful force-reap. If force raises or cannot confirm
  reaping and no terminal has already won, exact `provider_invalid_response` becomes the safe session
  failure; an already-selected cancellation/deadline instead remains authoritative. In either case no
  tool dispatch or next provider start occurs, and a non-returning force path makes no forward transition. Cancellation or
  deadline that wins while natural cleanup is pending joins the same cleanup task, selects the one
  terminal, and suppresses continuation. Only after successful settlement does the helper clear that
  exact generation under guard before dispatch or the next start. Every later start receives a fresh
  generation and cleanup task; a late callback from generation one cannot clear, cancel, publish, or
  otherwise mutate generation two. Ignoring the Boolean is a contract violation covered by mutation
  evidence.
- Final-text/failure selection leaves its generation to the authoritative session finalizer. Only that
  terminal finalizer stops and reaps the single deadline watcher; the intermediate generation helper
  must not reuse the shipped whole-session `_finish_provider_work()` path. `force_cancel_cleanup()`
  remains only the supervisor fallback, never an ordinary transition or direct install-loss call.
- Instruction discovery or context-merge failure is a safe session terminal: no follow-up provider
  operation starts and neither the pending result nor a partially enriched context is published or
  persisted. Every success begins with the native execution-time canonical request scope, including
  an empty `list_files` result or no-match `search_text` result. A successful `list_files` then
  includes every returned directory itself and every returned file's parent in its local instruction
  scopes; `search_text` includes every matched file's parent.
  `stat_path` includes the canonical directory itself or the canonical file's parent, and `read_file`
  includes the canonical file parent.
  Thus every workspace path exposed in result JSON has applicable instructions admitted before that
  result is replayed. Existing CAH-025 source limits and CAH-030's 16-binding, 24-item, and 96-KiB
  bounds remain authoritative: broad evidence that cannot be completely covered fails closed rather
  than truncating scopes or replaying a partial result.
- A successful tool output is the exact compact canonical CAH-031 JSON envelope
  `{"result":<allowlisted-value>}`. Known failures are exact compact JSON envelopes
  `{"error":{"code":"<code>","message":"<fixed message>"}}` with no whitespace. The closed error
  set is CAH-039's `unknown_read_tool` and `invalid_read_tool_input`, CAH-031's
  `invalid_read_tool_result` and `read_tool_output_too_large`, plus
  CAH-026's twelve
  `RepositoryAccessError` code/message pairs. CAH-039 has already mapped malformed, structurally or
  numerically invalid, duplicate, wrong-key, and wrong-type arguments without side effects. When the final
  checkpoint, request bounds, and model admission pass, the charged call and fixed error must replay
  against unchanged context in the follow-up request. Unknown-name
  lookup still wins before structural preflight or decoding. Unknown exceptions and programmer
  defects are session failures, not model content. `invalid_read_tool_registration` is a
  pre-provider composition failure.
- The bounded result JSON is stored in `ProviderToolResult.output_json`; success/error meaning is
  inside that payload as well as the neutral domain status. It contains no arguments, absolute path,
  raw exception, OS text, secret, or unbounded content. Rendering invariants fail the session safely;
  the expected envelope-size crossing becomes the fixed `read_tool_output_too_large` tool error
  rather than truncated JSON or an internal session terminal.
- Orchestration uses this closed non-replayable failure table; no branch says only "session failure":

  | Source | Session outcome |
  | --- | --- |
  | CAH-039 `ReadToolCatalogError`, including mapped CAH-031 foreign binding | exact `invalid_read_tool_catalog` / `Read tool catalog is invalid.` |
  | CAH-025 `RepositoryInstructionError` during root or result-scope discovery | its exact existing content-suppressed code/message |
  | CAH-030 `ContextBuildError` during initial build or enrichment | its exact `invalid_context_request`, `required_context_exceeds_budget`, or `context_build_failed` code/message |
  | CAH-032 `ProviderToolContractError` during initial context projection/request construction or follow-up construction | exact `invalid_provider_tool_value` / `Provider tool value is invalid.` |
  | provider start/operation shape, unexpected registry/programmer exception, or checked usage-aggregate overflow | exact `provider_invalid_response` / `The provider returned an invalid response.` |
  | normalized provider failure | existing `provider_<failure.code>` with its admitted safe message |
  | model-turn, deadline, assistant-output, or tool-call limit | existing CAH-022 exact limit code/message |
  | cleanup failure after another terminal outcome is selected | selected outcome is unchanged; emit only existing `provider_cleanup_failed` diagnostic |
  | intermediate natural cleanup cannot be force-reaped | exact `provider_invalid_response` / `The provider returned an invalid response.` only when no terminal already won; otherwise retain cancellation/deadline; emit the bounded cleanup diagnostic and perform no dispatch or next start |

  Cancellation/teardown and an already-selected deadline retain their existing precedence over a
  later candidate. None of these session outcomes is replayed as a `ProviderToolResult`.
- The follow-up request is a full immutable replay of original conversation plus the exact admitted call,
  its matching result, optional first-turn opaque continuation, the same definitions, and the
  atomically selected context snapshot. The single CAH-032 history tuple appends them exactly as
  `..., continuation? -> ProviderToolCall -> ProviderToolResult`; no separate continuation field or
  adapter side channel exists. It is reconstructed under CAH-032's 16-item and 512-KiB bounds before
  `Provider.start()`.
- The follow-up must be CAH-033's accepted non-empty final-text outcome. A second call is charged as
  another observed call, then fails through the existing fixed `tool_call_limit_exceeded` session
  path and starts no third turn. Invalid grammar, context overflow, provider failure, cancellation,
  or deadline follows its established bounded terminal path.
- Final-answer commit is one ordered transaction. Before any assistant delta is emitted, orchestration
  enters the outcome-adoption guard, builds and validates the complete two-turn usage aggregate
  candidate, then reserves the complete staged final-text UTF-8 size exactly once through CAH-022's
  mutable tracker. Checked usage overflow
  selects exact `provider_invalid_response` before output reservation; a rejected output reservation
  selects exact `assistant_output_limit_exceeded`. Either failure emits zero assistant chunks,
  persists zero usage, and leaves the prior output-byte count unchanged. An
  `AssistantOutputOverflow(8193)` from CAH-033 follows that same tracker path without retaining text.
- After both admissions succeed, the terminal finalizer settles the current operation generation,
  emits the exact staged chunks in order, persists the admitted usage aggregate when present, then
  emits the existing `assistant.completed` and `session.completed` events. Whole-text reservation—not
  per-chunk charging—prevents a late chunk from creating partial visible output. A rejecting delta is
  never emitted or retained.
- Each accepted turn contributes zero or one optional `ProviderUsageReported`. Evidence is
  all-or-none: exactly one aggregate `ModelUsageObserved` is persisted only when both accepted turns
  reported usage and checked addition admits each field; if either accepted turn omits usage, the
  session persists no model-usage aggregate rather than making a partial subset look complete. A
  rejected or cancelled round trip persists no usage. No transcript version, completeness flag,
  per-turn record, or per-call record is introduced.
- The exact CAH-034 profile above admits two model turns and one observed call for this teaching path.
  Model starts, provider deadline, assistant output, and tool-call count remain cumulative. CAH-032's
  524,288-byte cap applies independently to each complete request snapshot; cumulative conversation
  and context are fully charged inside the follow-up snapshot, but the two whole-request sizes are
  not summed or double-charged.
- No protocol event is added. The TUI sees only the final assistant text and existing terminal.

## Reviewability budget

- **Estimated production-code churn:** 420-570 changed lines after a counted-path allocation.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-033/039 prepared call -> guarded CAH-031
  dispatch/result -> CAH-025/030 context transaction -> admitted second provider request.
- **Pre-implementation allocation:** services carrier/factory and runner guards 55-75 lines; initial
  context transaction 35-50; operation generation/start/claim/continuation cleanup 120-160;
  dispatch/result/enrichment 125-165; final output/usage commit 50-70; integration wiring 35-50.
  Re-estimate these counted paths against the implementation branch before coding.
- If result mapping or usage aggregation cannot fit beside the two-turn orchestration, split a
  focused prerequisite; do not pull CAH-039 parsing back in or add iteration/transcript migration.
- Split the services-composition or operation-generation prerequisite before implementation if the
  re-estimate exceeds 575 changed production lines or either area acquires another responsibility.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One first-turn accepted call causes exactly one charged observation, at most one native dispatch,
   and exactly one follow-up provider start when admission checks pass.
2. CAH-034 calls CAH-039 exactly once per admitted observation. A CAH-039 rejection produces its exact
   bounded compact JSON envelope with zero dispatch; a prepared invocation crosses the dispatch guard
   unchanged, and no parser/key/type stage is reimplemented here.
3. A successful dispatch refreshes instructions for its execution-time canonical request scope plus
   every result-derived owner scope before replay; the follow-up replays the exact call/result only
   against the completely and atomically enriched context. Every discovered bundle must report the
   exact captured scope before merge; neither the original request alias nor a retargeted canonical
   label is post-dispatch authority. A known tool error replays against the initial context.
   Definitions remain unchanged and history stays in the single provider-neutral order
   `continuation? -> call -> result`.
4. One accepted follow-up final answer publishes staged chunks through existing events and selects
   one completed session; a second call or invalid response starts no third turn.
5. Synchronous dispatch, discovery, merge, provider projection, and request construction are never
   represented as preemptible:
   CAH-034's cooperative seam yields and then checks cancellation/deadline before and after
   dispatch, after each scope discovery, after each scope merge, and before the follow-up start;
   every late candidate is discarded and no result/context/history is committed before the final
   checkpoint and admission. A synchronous provider-start/event-claim/shape failure or failed
   installed-state carrier construction commits no result/context/history candidate, retains the
   charged model-turn attempt, rechecks the deadline, and cleans any uninstalled operation
   cancel-first through the existing supervisor. A complete carrier commits through one non-failing
   pointer assignment after the final clock read; its finalization cannot publish a terminal before
   any uninstalled-operation cleanup task joins.
6. Usage is all-or-none across the two accepted turns. Checked arithmetic and whole-text reservation
   both complete before any assistant publication; only a complete admitted aggregate is persisted,
   while missing, overflowed, partial, or rejected usage is absent.
7. Instruction discovery/merge and cumulative loop budgets span the two turns and one call without
   reset; CAH-032 independently reapplies its complete-request cap to each cumulative snapshot.
   Discovery, merge, context, or request overflow prevents the follow-up start without publishing or
   persisting the pending result/context.
8. Existing transcript v3 and protocol v1 remain unchanged and content-safe; no per-call evidence
   record, argument, tool content, or provider continuation is persisted.
9. `ReadOnlyAgentServices`, the exact 2/120/4096/1 profile, and per-operation generations make this
   two-turn path independently runnable: initial setup fails safely after `session.started`, each
   model start owns a distinct claimed iterator/cleanup task, intermediate cleanup leaves the one
   absolute-deadline watcher active, and the next session is unaffected.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3-4 | One strict-fake/native-fixture integration calls the registry-only catalog factory once, passes `catalog.definitions` to both requests, dispatches a nested path through that same catalog entry, and asserts a second exact request with its newly applicable instruction—including `[user, opaque, call, result]` when continuation is present—one dispatch, full replay, unchanged definitions, ordered final events, one terminal, and zero third starts. Injected reordered bridge output fails before provider work. Catalog A and catalog B each work when internally consistent; mixing A's prepared call with B over the same registry, or with a same-shaped registry whose handler is distinctive, fails by `is` identity before either handler, result replay, or provider follow-up. At `after_dispatch`, empty-list/no-match cases retarget original `alias -> A` to `B`; discovery receives only captured `A`. A second seam replaces captured canonical label `A` with an internal symlink to allowed `B`; CAH-025 reports `B`, exact bundle-scope comparison fails before merge, and replacement instructions never enter the request. Removing `A` likewise fails without replay or fallback. Broad results prove this for every owner. Known-error cases include a native-maximum `read_file` whose wrapped success exceeds 65,536 bytes: the exact `read_tool_output_too_large` envelope crosses `after_dispatch`, carries no scopes, retains initial context, and replays without content. |
| 2 | Handoff integration injects one CAH-039 unknown-name result, one representative duplicate/key/type rejection, and one distinctive prepared invocation. A spy proves exactly one admission call, zero dispatch for every error, unchanged-context call/error replay after the outcome-adoption test gate, and exact catalog/entry/request identity at `dispatch_one`. The helper calls CAH-031 `dispatch_bound(entry, request)` once, converts `ReadToolSuccess.output_json` into the correlated CAH-032 result once, and preserves local scopes; static/import tests forbid CAH-031 from importing prepared/provider types and forbid scanner, decoder, key, or Pydantic logic in CAH-034. |
| 5 | A separate optional `outcome_adoption_observer` races cancellation/deadline immediately before the guard: terminal-first proves zero new call/output/usage charge or side effect; adoption-first calls `observe_tool_call()` or final admission once and proves a later cancellation cannot roll it back. It is absent in production and is not part of `ReadOnlyCheckpoint`. Named `asyncio.Event` gates at `before_dispatch`, `after_dispatch`, every `after_discovery`, every `after_merge`, and `before_provider_start` deterministically admit cancellation on the event loop; injected clocks prove the exact existing deadline/cancellation tie precedence without elapsed sleeps. Distinctive late value and exception candidates remain local and are discarded, including dispatch, `RepositoryInstructionError`, `ContextBuildError`, initial/follow-up `ProviderToolContractError`, unexpected request-construction defects, and cancellation on a later broad-result scope. Independently raised `CancelledError` at dispatch/discovery/merge/request construction follows the unexpected-candidate path; only a truly cancelling task propagates it. With no lifecycle winner, each exception maps only after its mandatory following seam through the closed table, and construction failures cause zero model charge/start. A separate production-mode seam test installs no observer/gate, queues a ready cancellation task, and has the non-awaiting guard spy assert that task already ran before guard entry; deleting the unconditional outside-lock `asyncio.sleep(0)` must fail this test. A semantic documentation-policy assertion locks yield, optional hook, guard order, and CAH-035 reuse. |
| 5 | A start-order table makes `Provider.start` raise, return a non-operation, or return partial shapes with `events()` but one missing cleanup method; makes a complete operation's `events()` raise/return a non-async iterator; makes immutable installed-state carrier construction fail; and advances an injected clock before/after each path. It asserts the full runtime port check precedes method calls, retained turn charge, unchanged context/history, zero iteration, deadline precedence through the final precommit read, exact invalid-response otherwise, and install-wins when the clock becomes due only after the non-failing pointer assignment. A non-operation receives no cleanup call; every valid uninstalled operation goes through one cancel-first cleanup task: no force after clean cancel, exactly one force after cancel failure/grace, no concurrent cleanup APIs, original terminal unchanged, and diagnostic-only cleanup failure. A blocked-cancel case proves no terminal event precedes cleanup completion and any cleanup diagnostic precedes that terminal. Successful start claims once, builds the carrier before the last clock read, and commits it with one pointer assignment and no intervening await or fallible hook. Services-present/limits-absent and every other invalid runner combination fail before publication or work. |
| 5, 9 | Two-turn lifecycle tests prove distinct generation/iterator/pending-read/cleanup identities, settle and clear generation one before dispatch/turn two, and route cancellation/deadline only to the current generation. Natural cleanup failure/grace invokes force once and continues only after confirmed reap; force failure selects exact invalid response when no terminal won, but retains an already-selected cancellation/deadline, with zero dispatch/turn two in both branches. Race cancellation/deadline into an already-owned natural cleanup task and assert one task/API path, no cleanup-mode drift, no tool side effect, and one terminal. Inject a late generation-one completion during generation two and assert it cannot clear, cancel, publish, or mutate the newer generation. A generation-only finalizer spy proves turn-one cleanup does not stop the session deadline watcher; one injected absolute clock then wins during turn two. |
| 6 | Two-turn tables cover usage on both turns, each missing position, exact checked sums, either-field aggregate overflow, rejected turn two, cancellation, and one transcript-v3 aggregate write only for both-present usage. A final-commit table reserves complete 4,095/4,096/4,097-byte text plus prior-used cases and CAH-033's 8,193 sentinel; overflow yields zero chunks, zero usage, and no partial byte charge. Whole-text reservation and usage-first ordering are mutation-tested. |
| 7 | Seeded boundary tests exhaust instruction/context item and byte budgets, model starts, deadline, assistant UTF-8 output, tool calls, native 500-entry/200-match scope derivation, and each 512-KiB request projection without late work. A control proves cumulative history is charged inside request two while whole request one is not added again. Broad list/search results prove exact owner ordering/deduplication and that one denied, invalid, changed, or over-budget returned scope prevents every result/context replay and provider start. |
| 3, 7 | Registry-backed projection tests admit complete success envelopes at 65,536 bytes, convert 65,537 bytes and a native 65,536-byte file whose wrapper overflows into the fixed small `read_tool_output_too_large` error, and prove one charged call, `after_dispatch`, zero discovery/merge, unchanged-context replay, no content/path leak, and no session-terminal shortcut. |
| 8 | Transcript/replay and protocol fixture suites prove unchanged schemas and absence of call IDs, arguments, result/continuation content, and host paths. |
| 9 | Signature/composition tests lock the sole boundary-only service factory, all nine exposed identities, and every graph edge: instruction boundary; policy boundary; metadata/text policy; search policy/metadata/text; context instruction/text/search; registry-bound metadata/text/search; and catalog registry/entry/definition identities. Equal-but-distinct/cross-wired graphs fail before I/O. Runner/session injection, exact `LoopLimits(2, 120, 4096, 1)`, and a fresh tracker per session are also locked. The real tracker admits starts one/two and rejects three and admits call one/rejects two. Root discovery/context projection/request failure occurs after `session.started`, emits one exact `session.failed`, starts no provider, and does not prevent a second session from succeeding. |

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
- For the request scope and a later broad-result owner, replace the captured canonical label itself
  with an allowed internal symlink before CAH-025 discovery. Assert returned-bundle scope mismatch
  prevents CAH-030 merge, replay, fallback, and the next provider start; keep a stable-label control.
- Reuse CAH-039's exhaustive admission suite. Here, use handoff spies and import checks to prove one
  admission call, no parser/key/type implementation, zero dispatch for rejected calls, and unchanged
  typed input at dispatch for a prepared call.
- Run focused round-trip, registry, limits, transcript-v3, runtime, and protocol tests followed by
  the canonical non-live repository gate.

## Documentation impact

Update agent-loop, provider-interface, context, safety, transcript/evaluation, glossary, backlog, and
story-index documentation. The concise lesson walks through one call/result feedback cycle and
contrasts local dispatch with a future MCP adapter. Do not create or update a presentation.

## Exclusions

- Argument parser/key/type admission (CAH-039), a general loop, repeated calls, multiple/parallel
  calls, retries, backoff, or planning framework.
- OpenAI SDK mapping, MCP/hosted tools, protocol/TUI tool events, transcript migration, or per-call
  transcript records.
- Asynchronous/preemptible tools, writes, subprocesses, network tools, approvals, or dynamic policy.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Track catalog/registry/entry object identities, definitions, session/call ID, prepared typed request, native `ReadToolSuccess`, correlated provider result, request alias/canonical target, instruction owner/source, context candidate, and visible label without collapsing them. |
| End-to-end contract | Trace registry-only catalog factory -> advertised definitions -> initial CAH-032 request -> CAH-033/039 prepared call -> cooperative guard -> CAH-034 `dispatch_one` -> CAH-031 `dispatch_bound(entry, request)` -> CAH-032 result construction/scopes -> CAH-025/030 merge -> admitted second request -> final text. |
| Failure and atomicity | Every admission, catalog/entry identity, dispatch, result, discovery, merge, cancellation, deadline, and next-start failure leaves candidates uncommitted; cross-catalog input is a session failure with zero handler/replay/follow-up, rejected calls dispatch zero times, and late synchronous results are discarded. |
| Reachable boundaries | Exercise producer-admitted calls, exact result/context/request limits, access-time retargets, late returns, and queued cancellation through the real two-turn composition and its five cooperative seams. |
| Closed grammar and cardinality | Admit exactly one call and one matching result before exactly one second provider start; preserve the closed fixed-error table, aggregate usage rules, and one non-preemptive native handler at a time. |
| Artifact parity | Story, lesson, sequence diagram, pseudocode, agent-loop docs, and tests use the same stage names and exact checkpoint order from dispatch preparation through model admission. |
| Independent lenses | Path identity/TOCTOU review fixed execution-time scopes and exact identity guards; end-to-end review added a concrete dependency carrier, explicit limits, initial setup transaction, context bridge, and real two-turn profile; lifecycle/accounting review added one claimed iterator, immutable installed state, final-clock/one-pointer linearization, joined uninstalled cleanup, explicit checkpoint/continuation stop contracts, one cleanup task per generation, watcher-preserving force-reap before continuation, whole-text final commit, and all-or-none usage. |

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
  suites, including 16-KiB/64-level structural admission, quote-aware delimiter cases,
  constant/recursion rejection, duplicate-aware JSON decoding, unchanged-context known errors, and
  atomic canonical-request-plus-result instruction coverage.
- Checked two-turn usage aggregation with exactly one existing transcript-v3 session record.

## Deferred work

- CAH-035 replaces the explicit two-turn branch with a bounded iterative state machine.
- CAH-036 maps OpenAI Responses items to the provider-neutral staged-turn contract.
- MCP adapters, parallel tool use, visible progress, and side-effecting policy remain later work.
