# CAH-035 - Run the bounded agent loop

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop
- **Dependencies:** CAH-034
- **Lesson:** [Bounded agent loop](../docs/lessons/cah-035-bounded-agent-loop.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** The harness-owned state machine, scoped-instruction accumulation, stop
  conditions, cumulative budgets, and defense-in-depth limit proofs across model turns and tool
  calls.

## User story

> As a learner building a coding agent, I want the harness to iterate explicitly between the model
> and read tools under small hard limits so that I can locate agency, reason about every transition,
> and prove that the process always stops.

## Single responsibility

CAH-035 generalizes CAH-034's explicit two-turn teaching path into one provider-neutral sequential
agent-loop state machine. It does not add provider SDK mapping, a tool capability, evidence schema,
TUI behavior, or parallel execution.

## Scope

- Define explicit loop states and legal transitions among model admission, final-answer publication,
  call validation, synchronous dispatch, scoped-instruction enrichment, result append, and the next
  model admission.
- Admit at most four started model turns and three within-budget tool calls per session while retaining
  the single rejecting fourth observation required by CAH-022 when tool-call exhaustion wins.
- Reuse CAH-033 atomic turn outcomes, CAH-039's registry-only catalog/argument admission, and
  CAH-034's catalog-identity-safe `dispatch_one` result bridge, immutable replay, checked usage
  aggregation, cooperative checkpoint seam,
  cancellation handling, and existing transcript-v3 evidence.
- Keep all CAH-022 counters cumulative while applying CAH-032's complete-request byte cap
  independently to each snapshot containing cumulative conversation/context.
- Accumulate applicable instruction items atomically across as many as three successful reads,
  covering the execution-time canonical request scope and every model-visible returned-path owner
  before each result replay.
- Prove legal progress, every reachable stop, and defense-in-depth guards with deterministic fakes
  and seeded ledger states.

## Locked contract

- The Python harness owns the state machine:
  `admit_model -> publish_final` or
  `admit_model -> admit_call -> CAH-039 argument admission
  -> prepared?(cooperate_before_dispatch -> CAH-034 dispatch_one(catalog, prepared)) | fixed_error
  -> cooperate_after_dispatch -> for_each_instruction_scope(discover -> cooperate_after_discovery
  -> enrich_context -> cooperate_after_merge) -> stage_result/history/request-or-error
  -> cooperate_before_provider_start -> unwrap_request
  -> admit_model_candidate -> lazy_start_candidate -> claim_events -> build_installed_turn
  -> final deadline check -> one-pointer commit -> iterate_to_EOF`. A CAH-039 fixed error skips native dispatch but still crosses
  `cooperate_after_dispatch`. A post-dispatch known tool error—including CAH-031's fixed
  `read_tool_output_too_large`—also crosses that seam, then skips
  discovery/enrichment and stages its safe result against the current context.
  Provider adapters translate one operation; registry tools execute one validated input. Neither
  chooses whether another turn starts.
- Composition builds one CAH-039 catalog from the CAH-031 registry before the first turn, advertises
  only `catalog.definitions`, passes that exact catalog to every argument admission and CAH-034
  dispatch helper, and never rebuilds it during the loop. Cross-catalog or foreign-entry input is the
  exact non-replayable CAH-039 `ReadToolCatalogError` with zero handler I/O, result replay, or next
  start.
- CAH-035 uses CAH-034's exact `ReadOnlyAgentServices` runner/session injection and initial setup
  transaction, but supplies exact
  `LoopLimits(max_model_turns=4, provider_work_timeout_seconds=120,
  max_assistant_output_bytes=4096, max_observed_tool_calls=3)`. The runtime-scoped service bundle is
  immutable; every session receives a fresh tracker, root context/history, and operation-generation
  counter. Initial CAH-025/030/032 failure occurs after `session.started`, uses CAH-034's exact closed
  mapping, starts no provider, and does not prevent the next session.
- The exact M2 ceilings are four started model turns and three within-budget tool calls. When the
  tool-call ceiling wins, CAH-022 accounting retains exactly one rejected fourth observation at
  maximum plus one. A final answer may complete on any admitted turn. There is at most one active
  provider operation or bounded synchronous tool invocation and never overlap between them.
- Every model operation first produces one atomic CAH-033 outcome. Only an accepted non-empty final
  text or exactly one call can advance the loop. Mixed/multiple/parallel calls, partial text,
  invalid usage, unsupported items, and malformed completion fail before publication or dispatch.
- Tool observation is charged after the call's whole provider grammar is admitted but before lookup
  or argument parsing. The fourth legal call is therefore rejected as
  `tool_call_limit_exceeded` and never dispatched. Starting a fifth turn is not reachable from a
  fresh legal M2 session: three calls lead to turn four, whose final text succeeds or whose fourth
  call fails first. The `model_turn_limit_exceeded` check before every `Provider.start()` remains
  defense in depth and is tested directly with a seeded admission ledger rather than an impossible
  five-turn response script.
- Each accepted call first follows CAH-039's exact lookup, iterative quote-aware structural preflight,
  pair-preserving JSON-object decode, model-facing key gate, and native Pydantic validation. It then
  follows CAH-034's guarded dispatch, result validation, instruction-scope extraction, context
  enrichment, and compact-envelope replay order. Every iteration inherits the one-value 16-KiB work
  bound and 64-level object/array ceiling with root
  object depth 1, and the iterative walker checks member-name uniqueness at every admitted object
  depth. Its numeric preflight admits only signed-64-bit JSON integer tokens and rejects
  fractions/exponents before Python conversion. Over-depth/mismatched structure, integer overflow,
  non-finite constants, defensive decoder `RecursionError`/`ValueError`, and any duplicate fail as
  `invalid_read_tool_input` before dictionary construction or any later stage; later loop iterations
  reuse this complete admission path and never implement a second argument path.
  Synchronous tools remain bounded and non-preemptive. CAH-035 reuses—not wraps or
  reimplements—CAH-034's `cooperate_then_guard(checkpoint)` before and after dispatch. Each call
  unconditionally yields with `await asyncio.sleep(0)` outside locks, invokes an optional injected
  deterministic test observer/gate, then applies the existing cancellation/deadline guard with its
  established precedence. Normal return authorizes the next line; a losing guard raises private
  `_SessionLifecycleStop`, which only the session orchestration boundary consumes and no stage mapper
  may catch, ignore, or relabel. A late result remains a local candidate and is discarded.
- CAH-035 also reuses CAH-034's value-or-exception staging for every synchronous dispatch, discovery,
  merge, provider-context projection, and request build. The mandatory following cooperative seam runs
  before an exception is unwrapped or mapped, so lifecycle can win and discard it. Independently
  raised `CancelledError` follows this unexpected-candidate path; only a task whose cancelling count is
  positive propagates it as control flow. No iteration adds a direct exception path around that seam.
- After each successful native dispatch and its post-dispatch guard, CAH-031 supplies ordered local
  `instruction_scopes`: the native result's execution-time canonical request scope first, then every
  exact-deduplicated owner of a model-visible returned path. The loop never re-resolves or falls back
  to the original request alias. For each scope, CAH-025 discovers the canonical ancestor chain; after
  the discovery guard, the loop requires `bundle.canonical_scope == scope` before CAH-030 may fold
  instruction items into a local candidate. A captured canonical label retargeted to another allowed
  target therefore fails without replacement instructions or fallback. Cancellation/deadline guards
  run after every discovery, after every merge before result/context append, and before the next
  provider start by reusing the same cooperative seam at `after_discovery`, `after_merge`, and
  `before_provider_start`. These bounded synchronous values are discarded when a checkpoint loses.
  Up to three successful calls may therefore accumulate instruction items from direct, list, stat,
  read, and search evidence. Known tool errors carry no scopes, keep the current context candidate
  unchanged, and still cross `before_provider_start` before continuation.
- A repeated candidate-owner `applies_to` binding is idempotent only when source, content, and
  original byte count are identical. A changed owner snapshot fails closed instead of replacing the
  prior item, while the same source under another owner remains a distinct charged binding. New
  nested or sibling chains merge without mutating the prior snapshot; precedence is
  root-to-nearest only within an ancestor chain, and sibling instructions retain distinct
  `applies_to` scopes rather than overriding one another. Any discovery, changed-duplicate,
  validation, item-budget, or byte-budget failure is atomic: the session terminates with no pending
  result/context publication or persistence and no next provider start.
- One immutable logical history contains initial input and appends every accepted call turn as
  `continuation? -> call -> matching result`; each admitted context is a new immutable snapshot. The
  continuation is CAH-032's positional item in that tuple, never a parallel field. Before every
  provider start, CAH-030 context item/byte bounds and CAH-032's 16-item and 512-KiB complete-request
  bounds are revalidated. No history or instruction item is silently truncated, summarized, reset,
  or evicted; only exact idempotent instruction duplicates are deduplicated.
- Every CAH-033 outcome reuses CAH-034's one guard-owned adoption transaction. Cancellation/deadline
  that owns the guard first discards the candidate with no new call/output/usage charge or effect;
  otherwise a call is charged exactly once before cleanup/dispatch and remains charged if a later
  terminal wins. Final usage validation and whole-text reservation linearize in that same guard before
  cleanup/publication. The separate optional `outcome_adoption_observer` sits immediately before,
  never inside, this transaction; it is test-only and not a `ReadOnlyCheckpoint`.
- Every initial or enriched CAH-030 snapshot crosses CAH-032's sole
  `build_provider_context(context_package)` bridge before request construction. The bridge/build pair
  produces one local request-or-error candidate; `before_provider_start` always runs before it is
  unwrapped, including on initial setup and known-error continuation. The loop owns no second context
  projector and never constructs a provider context variant directly.
- Dispatch output, discovery, merged context, provider result, history, and complete bounded
  request-or-error remain local candidates through `before_provider_start`. Only after that checkpoint,
  successful unwrapping, and model
  admission pass does the session guard reuse CAH-022's mutable
  `LoopLimitTracker.admit_model_turn()` immediately before calling synchronous, non-blocking, lazy
  `Provider.start(request_candidate)`. It reuses CAH-034's exact async helper: existing lock
  acquisition and a losing uninstalled-cleanup join may await, but its guarded critical section is the
  complete no-await transaction: charge,
  start, validate the complete runtime-checkable `ProviderOperation` port, call `events()` exactly
  once, validate the claimed async iterator, then build one immutable `_InstalledTurnState` containing
  the fresh generation and complete context/history/result snapshots. Every allocation, validation,
  and test fault hook precedes the final injected-clock read. If it passes, one non-failing pointer
  assignment commits the carrier. The attempt remains charged on every failure. A deadline observed at
  the final read wins; one becoming due only after the pointer assignment loses the transition and is
  handled by the installed generation's watcher. Other failure is existing
  `provider_invalid_response`; candidates remain unchanged. A real uninstalled operation uses one
  cancel-first/five-second/force-fallback task outside the lock, never a direct force call. The terminal
  finalizer joins that task and cannot publish before it settles; a cleanup diagnostic precedes the
  terminal. Only the installed claimed iterator is consumed through terminal to EOF.
  A losing
  cancellation/deadline checkpoint therefore leaves no partial tool
  result, transcript content, context, or next-turn request, including after a known tool error.
- Each successful one-pointer commit replaces the loop's current immutable turn-state carrier. The
  next iteration derives both `context` and `history` from that installed carrier; it never continues
  from pre-loop local names and therefore cannot drop a prior result, continuation, or enriched
  instruction snapshot.
- Every turn has a distinct operation generation containing its operation, claimed iterator,
  pending-read task, cleanup task, and mode. CAH-034's generation-only helper settles natural close
  without stopping the one session-wide deadline watcher and clears that exact generation under guard
  before dispatch or another start. Its exact Boolean must be checked: `False` returns from the loop
  before CAH-039 argument admission, dispatch, context work, or another start. Natural failure/grace
  forces once and may continue only after
  confirmed local reaping; a failed authoritative force selects exact invalid response only when no
  terminal already won, otherwise preserving cancellation/deadline, and performs no dispatch or later
  start. Cancellation/deadline target only the current generation and join its one
  already-owned cleanup task rather than changing mode or invoking another provider cleanup API. A late
  callback from a prior generation cannot clear, cancel, or mutate a newer one.
- The absolute provider-work deadline is captured once. Model starts, observed calls, and accepted
  assistant bytes remain cumulative. CAH-032 reapplies its 524,288-byte cap independently to every
  complete request; cumulative history/context are charged within each snapshot, while prior whole
  requests are not summed again. Limits are checked before costly work; the operation crossing a
  bound never starts or publishes.
- Usage is all-or-none across every accepted model turn. Checked addition produces one existing
  transcript-v3 aggregate only when every accepted turn reported usage; any missing turn means no
  aggregate. Before any final `assistant.delta`, the loop validates that aggregate candidate and
  reserves the complete staged text once through the tracker. Usage overflow selects exact invalid
  response before reservation; output rejection selects exact `assistant_output_limit_exceeded`.
  Either leaves zero chunks, zero usage, and no partial byte charge. After both pass, the finalizer
  settles the current generation, emits chunks, persists complete usage if present, then emits the
  existing completions. Tool-only turns, result JSON, opaque continuation, and intermediate provider
  content remain invisible to protocol/TUI and transcript content.
- Bounded tool errors may become exact model-facing error results and continue while budget remains.
  Every non-replayable failure reuses CAH-034's closed mapping table unchanged: catalog, instruction,
  context, request, provider/operation, usage-aggregate, normalized-provider, limit, and cleanup
  branches each have the exact code/message and precedence defined there. The loop adds no generic
  or iteration-specific terminal vocabulary.
- Cancellation or teardown selects through the existing terminal guard, reaps the active provider
  operation, and prevents future transitions. A synchronous dispatch, discovery, or merge already
  running may return, but its next cooperative yield lets a queued cancel command update session
  state before the guard discards the late result, bundle, or package. Exactly one terminal winner
  remains.
- MCP may later supply registry descriptors and executor results, but it cannot own, continue, or
  bypass this state machine. M2 introduces no MCP client/server or remote trust boundary.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: repeated CAH-033 outcomes -> CAH-039/034
  atomic tool round trips -> cumulative loop state -> one final harness-owned outcome.
- Split a newly discovered context, evidence, or tool contract into a prerequisite instead of hiding
  it in state-machine work. Do not count replacing CAH-034's branch as room for another capability.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One explicit provider-neutral state machine owns every model/tool transition and final outcome.
2. A fresh session starts at most four model turns and admits at most three within-budget tool calls;
   a rejecting fourth observation is retained only for tool-limit evidence, and all work is
   sequential with no overlapping operations.
3. A final answer can complete on turns one through four and only its fully admitted staged chunks
   reach existing assistant/session events.
4. A fourth legal call fails first as `tool_call_limit_exceeded`; the fifth-turn admission guard is
   proven separately from seeded state as `model_turn_limit_exceeded` with zero provider starts.
5. Every successful call's execution-time canonical request and result-derived instruction scopes accumulate applicable
   instructions atomically across up to three calls; exact owner snapshots are idempotent, changed
   owner snapshots fail closed, nested/sibling scopes retain their own applicability, and known tool
   errors do not change context.
6. Checked usage from all accepted turns produces exactly one existing transcript-v3 aggregate only
   when every turn reports it and final text succeeds; any missing or unsuccessful path persists no
   partial-looking usage. Complete usage and whole-text reservation precede all assistant publication.
7. Bounded tool errors may continue, while invalid response grammar, internal invariants, and limit
   exhaustion terminate safely without raw or intermediate content.
8. Cancellation, teardown, provider failure, cleanup failure, and late synchronous tool/discovery/
   merge/request values or errors select one terminal and leave no owned provider work, actionable
   late candidate, or partially committed result/context/history; all synchronous boundaries reuse
   CAH-034's yielding checkpoint seam, and terminal publication joins any uninstalled cleanup.
9. All cumulative CAH-022 limits, installed context and full request replay (including opaque continuations),
   safe result envelopes, and per-snapshot request-size accounting survive every transition. Protocol
   v1, TUI reducers, transcript v3 schema, provider adapters, and native tool contracts remain
   unchanged.
10. Exact 4/120/4096/3 runner injection plus per-operation generations keep initial setup and all four
    sequential starts independently implementable without reusing one-turn cleanup state.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3 | Table-driven strict-fake cases complete with final text on turns one through four and assert exact states, immutable context snapshots and positional continuation/call/result history, publication order, and one terminal. |
| 2, 5 | Scripts exercise zero through three successful calls and instrument maximum provider/tool concurrency as one. One catalog is built before the loop; every exact request uses `catalog.definitions`, and every admission/CAH-034 dispatch uses that same object. A distinct catalog over the same registry and a same-shaped registry with distinctive handlers both fail by identity before handler/replay/next-start. Exact requests prove root-only start, direct plus broad-result nested/sibling instruction accumulation before replay, unchanged definitions, first-occurrence scope ordering, repeat/alias idempotence, and distinct sibling `applies_to`. A later iteration retargets an empty-list/no-match request `alias -> A` to `B` at `after_dispatch` and proves only captured `A` drives discovery. Another replaces captured canonical `A` with an allowed symlink to `B`; returned-bundle scope mismatch (or removal of `A`) fails before merge with no replay or fallback. Later-turn 63/64/65-level, quoted-delimiter, signed-64-bit boundary/overflow/5,000-digit, fractional/exponent, array-nested-duplicate, non-finite-constant, and forced decoder-failure calls prove reuse of CAH-039's complete admission and zero dispatch. |
| 4 | One fresh-session script returns a fourth admitted call and proves tool-limit precedence/no dispatch; a separate seeded model-turn ledger proves zero-start fifth-turn defense in depth. |
| 5, 9 | Changed-duplicate, later-scope discovery, nested/sibling merge validation, and CAH-030 item/byte-budget failures leave the preceding snapshot intact, publish/persist no pending result/context, replay no successful output, and start no next turn. Seeded boundaries exhaust native 500-entry/200-match scope sets, deadline, UTF-8 output, calls, turns, and 524,287/524,288/524,289-byte complete requests; every request rechecks context and request bounds, and a two-start control proves request one is not added again to request two. |
| 6 | Usage tables cover all-present usage through four turns, every missing position/subset, checked exact sums, either-field overflow, rejected final turn, cancellation, and exactly one aggregate persistence call only for all-present success. Final-commit tables reserve complete text once at 4,095/4,096/4,097 bytes plus prior-used cases and CAH-033's 8,193 sentinel; every rejection proves zero deltas, zero usage, and unchanged prior byte count. |
| 7 | Known tool errors continue once; grammar mutations, registry invariant faults, request overflow, and programmer defects assert exact safe terminal and no raw sentinel. |
| 8 | The separate test-only `outcome_adoption_observer` proves both guard orders: terminal first means zero new call/output/usage charge or effect; adoption first calls `observe_tool_call()` or final admission once and later cancellation cannot roll it back. Named `asyncio.Event` gates race cancellation/teardown against provider await, `before_dispatch`, `after_dispatch`, `after_discovery`, `after_merge`, `before_provider_start`, final publication, and cleanup. Injected clocks prove exact existing deadline/cancellation tie precedence without elapsed sleeps. Distinctive late value or exception candidates never enter history, context, evidence, or another request, including known errors; dispatch, instruction-discovery, context-merge, initial/follow-up provider projection, and request-build exception races prove the following seam/lifecycle winner precedes mapping with zero charge/start for construction failures. Independent `CancelledError` at each synchronous stage maps as an unexpected candidate after its seam; true task cancellation propagates. CAH-034's separate no-hook queued-cancel test mutation-proves the unconditional yield rather than relying on an awaited Event hook. Semantic policy assertions prove CAH-035 calls that same outside-lock yield/test-hook/guard seam rather than duplicating it. |
| 8-10 | For initial and later starts, make the lazy factory raise, return a non-operation, or return every partial operation shape with one missing cleanup method; make a complete operation's `events()` raise/return a non-async iterator; fail installed-state carrier construction; and advance the injected clock before/after every path. Assert the full port check occurs before methods, retained turn charge, unchanged context/history, zero iteration, deadline precedence through the final precommit read, install-wins after the one non-failing pointer assignment, invalid response otherwise, no cleanup call on non-operations, and one cancel-first cleanup task for valid uninstalled operations. Block that task to prove terminal publication waits; force occurs only after ordinary failure/grace, no cleanup APIs overlap, and any diagnostic precedes the unchanged terminal. Across four turns assert distinct installed carrier/generation/iterator/pending-read/cleanup identities, clear each prior generation before dispatch/next start, and prove each committed carrier's context/history becomes the next iteration's sole base. A late old callback cannot mutate the current carrier. Fail natural cleanup and authoritative force on an intermediate turn and assert zero tool/next-start work; race cancellation/deadline into natural cleanup and assert one task/API path with no mode drift and one terminal. A generation-only cleanup spy proves the session-wide watcher survives turns one through three, and one injected absolute deadline can still win during a later turn. |
| 10 | Signature/composition tests lock CAH-034's exact dependency carrier and `LoopLimits(4, 120, 4096, 3)`, fresh trackers/session state, root setup failure after `session.started`, zero provider starts, and successful acceptance of the next session. |
| 9 | Transcript replay, protocol fixtures, reducer tests, adapter contract tests, and import-policy checks remain unchanged. |

## Validation

- Use deterministic fake exchanges, bounded fake tools, injected clocks, seeded ledgers, named
  `asyncio.Event` checkpoint gates, and explicit state traces; never use elapsed timing assertions,
  wall-clock sleeps, or a live model.
- Reuse CAH-034's no-observer queued-cancel regression; do not treat an awaited Event hook as proof
  that production's unconditional yield exists.
- Reuse CAH-039's structural/numeric tests rather than adding a loop parser: below/at/above 64
  levels, quote-and-escape-aware delimiters, arrays, deepest admitted duplicates, signed-64-bit
  endpoints/overflow, fraction/exponent and 5,000-digit integers, non-finite constants, and defensive
  decoder recursion/value failures all retain the single aggregate 16-KiB argument bound on later
  turns.
- Assert exact provider starts, dispatches, discovery/merge calls, immutable context snapshots,
  maximum active work, request history, limits, aggregate usage, transcript projection, terminal
  count, cleanup, and protocol output.
- Run focused loop/session/limits/context/registry/transcript tests, unchanged cross-language
  protocol tests, and the canonical non-live repository gate.

## Documentation impact

Update agent-loop, architecture, provider-interface, context, safety, evaluation, transcript,
glossary, backlog, and story-index documentation. The concise lesson centers on state ownership,
cumulative accounting, reachable versus defense-in-depth stops, and the future MCP seam. Add no
presentation.

## Exclusions

- Multiple/parallel calls per turn, concurrent tools, retries, backoff, planning frameworks,
  subagents, delegated loops, or provider-managed continuation.
- OpenAI SDK mapping, MCP clients/servers, remote/hosted tools, protocol/TUI tool events, new
  transcript records, or hidden-reasoning interpretation.
- Writes, subprocesses, network tools, approvals, dynamic policy, context summarization, semantic
  inference beyond explicit result paths, or unlimited/adaptive turns.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Retain session, turn, call, request-scope, access-time canonical target, instruction owner/source, context version, result, cumulative usage, and provider request as separate loop state. |
| End-to-end contract | Trace root context -> repeated CAH-033 outcome -> CAH-039 preparation -> CAH-034 guarded dispatch/context transaction -> next provider request until final text or one harness-owned terminal stop. |
| Failure and atomicity | Invalid response, rejected call, tool error, discovery/merge failure, cancellation, deadline, or any cumulative limit commits neither partial result nor partial context and cannot start another provider operation. |
| Reachable boundaries | Drive zero through three calls, completion on each legal turn, the rejecting fourth call, cumulative output/usage limits, each complete-request snapshot limit, lazy-start/install failure, late synchronous return, and queued cancellation through the real loop scheduler. |
| Closed grammar and cardinality | Lock one active provider/tool operation, one call per tool turn, four admitted turns, three observed calls, exact reachable stop precedence, and the fifth-turn guard as defense in depth. |
| Artifact parity | Story, lesson, state diagram, transition table, agent-loop/safety docs, and tests use the same outcome -> admit -> guard -> dispatch -> enrich -> admit-next-start transition. |
| Independent lenses | State-machine/atomicity review fixed terminal-to-EOF consumption, one cleanup owner per generation, force-reap before intermediate continuation, and no overlap; context/tool review fixed exact shared services, bridge use, immutable replay, and installed context/history as the next iteration's sole base; limits/scheduler review added the 4/120/4096/3 profile, final-clock/one-pointer start linearization, explicit stop-result consumption, joined uninstalled cleanup, a session-wide watcher that survives intermediate cleanup, cancellation/cleanup task joining without mode drift, all-or-none usage, and whole-text final commit. |

## Definition of done

- The transition table, every reachable stop, fifth-turn defense-in-depth guard, cumulative budget,
  usage aggregate, and meaningful cancellation/late-result path have deterministic tests.
- The loop remains provider-neutral, sequential, content-safe, and explicitly harness-owned.
- **Delivered production-code churn** records the measured result and is no more than 600 lines;
  adapter, tool, protocol, or evidence expansion is absent.
- Public APIs and the concise Markdown lesson are verified against implementation with a compact
  state/sequence diagram; presentations remain frozen.
- Focused checks and `./scripts/check` pass before the story is Done and published.

## Planned evidence

- Exact state traces for completion on each turn and zero through three calls, with atomic direct and
  broad-result nested/sibling instruction accumulation and idempotent repeated/alias scopes.
- Later-turn evidence that CAH-039's 16-KiB/64-level preflight, constant rejection, defensive
  recursion mapping, and iterative every-depth duplicate check are reused without another parser.
- Fresh fourth-call precedence and seeded fifth-turn defense-in-depth tests.
- Changed-duplicate/discovery/merge/budget atomicity plus cumulative context, per-snapshot request, deadline,
  output, usage, cancellation, and terminal-race suites.

## Deferred work

- CAH-036 maps OpenAI Responses items onto the proven provider-neutral turn contract.
- CAH-037 composes and evaluates the complete read-only assistant.
- MCP transport/discovery, parallel scheduling, durable continuation, and side-effecting tools remain
  later work.
