# CAH-034 lesson: Run one read-tool round trip

- **Unit:** CAH-034
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; the harness still rejects tool requests
- **Story:** [CAH-034](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** One observe-validate-dispatch-enrich-result-follow-up sequence, duplicate-safe
  argument decoding, complete scoped instructions, non-preemptive cancellation boundaries, and one
  aggregate usage record
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Tool system](../tool-system.md), and
  [Context engineering](../context-engineering.md)

> This lesson describes planned behavior. Pseudocode is not evidence of an implemented round trip.

## Quick summary

CAH-034 takes one atomically admitted call, consumes CAH-039's prepared-or-error handoff, and executes
at most one native read tool. Before replay, it atomically covers the native operation's
execution-time canonical request scope and every model-visible result owner with applicable
instructions, then publishes only an admitted follow-up answer.

## Learning objectives

After this unit, you should be able to:

- trace ownership across model, registry, native tool, and follow-up request;
- explain why CAH-039 alone admits raw tool arguments and CAH-034 must consume only its prepared
  invocation or fixed error;
- derive ordered instruction scopes from a successful validated result without exposing that
  metadata to the provider;
- distinguish a tool's semantic error from a provider transport status;
- explain why cancellation around bounded synchronous work requires an event-loop yield before its
  state guard;
- build immutable stateless call/result replay; and
- aggregate usage without persisting partial turns.

## Why this unit matters

Function calling is a protocol: the model proposes, the application validates and executes, and the
result returns in another request. A two-turn slice exposes every trust boundary before a loop hides
the sequence inside iteration.

## Junior engineer foundation

Synchronous Python code cannot be cancelled halfway through an instruction. A cancel command also
cannot update session state while that code holds the event-loop thread. The harness therefore
yields once before each state guard, then discards a candidate if cancellation won while bounded
work ran.

```text
yield -> guard -> bounded sync tool -> yield -> guard -> admit or discard candidate
```

A common misconception is that returning an error result means the provider request failed. Tool
success/error is model-facing JSON; the provider transport completed normally in both cases.

CAH-032, CAH-033, and CAH-036/provider adapters preserve bounded argument JSON as raw text. CAH-039
owns the one lookup/preflight/pair-decode/duplicate/key/type admission path and returns either a
content-suppressed prepared invocation or one fixed safe error. CAH-034 calls that boundary once; it
does not rebuild a JSON parser inside orchestration. Review CAH-039 first if the exact 16-KiB,
64-level, signed-64-bit, non-finite-constant, or duplicate-name grammar is unfamiliar.

Repository instructions are scoped control-plane input. A validated successful result carries local,
content-suppressed `instruction_scopes`: the execution-time canonical request scope first, then
exact-deduplicated owners for every model-visible returned path. The harness discovers and folds all
of them before replaying the result. After discovery, the bundle must still report the captured
canonical scope before CAH-030 may merge it. The harness never re-resolves the original request alias
or accepts a captured label that retargeted to another allowed scope. These scopes are trusted only
because CAH-031 derives them from validated native values, not because the model named a path.

## Key concepts

- **Dispatch:** invoke the registered implementation after validation.
- **Safe envelope:** fixed compact JSON containing validated result or fixed error.
- **Full replay:** resend original history plus `continuation? -> call -> result` in exact order.
- **Instruction scopes:** ordered local paths whose complete instruction bundles must precede replay.
- **Prepared invocation:** CAH-039's typed, non-executed handoff after complete argument admission.
- **Atomic enrichment:** replace the whole immutable context snapshot or keep the prior one.
- **Late result:** work that returns after cancellation/deadline selected another outcome.
- **Aggregate usage:** an all-turns-present checked sum persisted once after successful final text;
  any missing turn means no aggregate.
- **Operation generation:** one operation, claimed iterator, pending read, and cleanup task that must
  settle and clear together before another turn owns those slots.
- **Continuation cleanup:** generation-only settlement that proves local provider work is reaped but
  deliberately leaves the session's single absolute-deadline watcher running.
- **Outcome adoption:** one guarded linearization point after CAH-033 returns and before call, output,
  or usage accounting and every side effect.

## Architecture and design

```text
Ink TUI                Python harness                              Provider
 final text <--- publish accepted turn <---------------------- turn 2 final
                       ^                                      /
                       | enriched context + [opaque? -> call -> result]
                 CAH-034 two-turn owner
                       |
 CAH-031 registry -> CAH-039 catalog factory -> CAH-038 bridge
                        | catalog.definitions -----------------> tools
                        | same catalog
            CAH-039 admit raw call once
       (lookup/preflight/decode/duplicate/key/type)
                       |
     PreparedReadToolCall                     ProviderToolResult(error)
               |                                         |
       yield/guard -> dispatch                           |
               |                                         |
       ProviderToolResult + scopes                       |
               |                                         |
       after_dispatch guard ------------------------------+
               | success scopes                          | known error
               v                                         v
 for each scope: discover -> guard -> merge -> guard   unchanged context
               |                                         |
               +--------------- local replay candidate --+
                                      |
                  guard -> charge -> lazy start -> claim events -> build carrier
                                      |
                           final clock read -> one-pointer commit

Evidence: existing transcript-v3 session usage aggregate only; no per-call/content record
```

The first call is already atomic from CAH-033. CAH-039 preserves lookup and argument failure
precedence and gives this unit one prepared-or-error result. A rejection remains a charged
observation but causes zero dispatch, discovery, or context growth. If final checkpoint and
admission pass, its exact call/error pair replays in one follow-up against unchanged context. A
programmer defect or any scope discovery/merge failure fails the session. CAH-031's fixed
`read_tool_output_too_large` is instead a known, replayable tool error with no instruction scopes,
including when a valid native maximum read becomes too large only after JSON wrapping. No third turn
exists in this teaching slice.

The concrete orchestration entry remains `ProviderSession` created by `ProviderSessionRunner`. The
sole `build_read_only_agent_services(boundary)` factory creates and exposes the exact boundary,
instruction, policy, metadata-reader, text-reader, searcher, context-builder, registry, and catalog
identity graph. That frozen runtime-owned bundle enters both unchanged; this standalone lesson uses
exact limits of two turns, 120 seconds, 4,096 assistant bytes, and one observed call. Every session
still receives a fresh tracker and mutable state.

## Practical walkthrough

1. Call the sole boundary-only services factory once and configure `LoopLimits(2, 120, 4096, 1)`.
   Inside that factory, call CAH-039's registry-only catalog factory exactly once; it invokes CAH-038,
   binds the resulting definitions to the exact CAH-031 entries, and publishes the catalog as part of
   the one services carrier. The caller never rebuilds it.
2. After `session.started`, stage exact root-only context and initial request success/error. Cross
   `before_provider_start` before unwrapping that candidate and before charging/starting the initial
   turn. A setup failure starts no provider and does not poison the next session.
3. Admit the first response, then enter the outcome-adoption guard. Cancellation/deadline first means
   zero new charge or effect; adoption first charges its one call exactly once. Require the exact
   continuation cleanup helper to return `True`; `False` exits before argument admission. Then call
   CAH-039 exactly once. A fixed error skips dispatch; a prepared invocation remains local and unchanged.
4. For a prepared invocation, run the cooperative pre-dispatch checkpoint, call CAH-034's
   `dispatch_one(catalog, prepared)`, then cross `after_dispatch` exactly once. The helper verifies
   catalog/entry identity, calls CAH-031 `dispatch_bound(entry, request)`, and constructs the
   correlated CAH-032 result; a fixed CAH-039 error skips the first two actions but crosses the same
   single post-dispatch checkpoint.
5. On success, take CAH-031's local `instruction_scopes`, beginning with the native result's captured
   canonical request scope. For each scope in order, discover its instruction chain through CAH-025,
   checkpoint, require `bundle.canonical_scope == scope`, fold it through CAH-030 into the local
   context candidate, and checkpoint again. Never fall back to the original alias or a retargeted
   canonical label. On a known tool error—including `read_tool_output_too_large`—keep the initial
   context and replay only the fixed compact error envelope.
6. Stage the selected context, optional opaque state, call, result, history, and bounded follow-up
   request-or-error as local candidates. Yield and guard at `before_provider_start`, then unwrap the
   candidate. For a request, charge the model attempt through CAH-022, obtain one synchronous lazy
   operation, validate the complete runtime-checkable port, claim its iterator, and build one complete
   immutable installed-turn carrier. Perform the final clock read, then commit through one non-failing
   pointer assignment. A deadline after that assignment loses this transition. The earlier
   continuation settlement cleared turn one's generation without stopping the session-wide deadline
   watcher.
7. In the final outcome-adoption guard, validate all-or-none usage and reserve the complete text once.
   If cancellation/deadline won first, discard the candidate without either charge. After both pass,
   settle cleanup, emit chunks, persist complete usage if present, then complete.

## Implementation code samples

### Planned pseudocode: reusable cooperative checkpoint

```python
async def cooperate_then_guard(checkpoint: ReadOnlyCheckpoint) -> None:
    await asyncio.sleep(0)  # no harness lock is held
    if checkpoint_observer is not None:  # deterministic tests only
        await checkpoint_observer(checkpoint)
    if not guard_allows_continuation():  # preserve established winner precedence
        raise _SessionLifecycleStop  # terminal is already selected
```

CAH-034 owns this one seam; CAH-035 calls it rather than wrapping or copying it. Normal return is the
only authorization for the next line. Private `_SessionLifecycleStop` is consumed only by the session
orchestration boundary and is never ignored or mapped into a stage/provider failure. An
`asyncio.Event`-backed observer can pause a named checkpoint while a test admits a cancel command,
without relying on elapsed time. Production installs no observer.

The critical yield regression does **not** install that awaited observer, because the observer could
hide a missing production yield. It queues a same-loop cancellation task, calls the production-mode
seam with `checkpoint_observer=None`, and lets a synchronous guard spy assert that cancellation ran
before guard entry. Removing `await asyncio.sleep(0)` makes that deterministic test fail. Injected
clocks separately lock the existing winner when cancellation and deadline coincide.

### Planned pseudocode: ordered dispatch

```python
services = build_read_only_agent_services(boundary)
catalog = services.catalog  # internally built once through CAH-039 -> CAH-038
admission = prepare_read_tool_call(call, catalog)  # PreparedReadToolCall | ProviderToolResult
context_candidate = context
dispatch_candidate = None
dispatch_error = None
if isinstance(admission, ProviderToolResult):
    result_candidate = admission
else:
    await cooperate_then_guard("before_dispatch")
    dispatch_candidate, dispatch_error = capture_sync(
        lambda: dispatch_one(catalog, admission)
    )
await cooperate_then_guard("after_dispatch")
if dispatch_error is not None:
    raise_mapped_stage_error(dispatch_error)
if dispatch_candidate is not None:
    result_candidate = dispatch_candidate.provider_result

if dispatch_candidate is not None and result_candidate.status == "success":
    # Only a CAH-031 success carries local instruction scopes.
    for scope in dispatch_candidate.instruction_scopes:
        discovered_candidate, discovery_error = capture_sync(
            lambda: discover_and_require_exact_scope(instructions, scope)
        )
        await cooperate_then_guard("after_discovery")
        if discovery_error is not None:
            raise_mapped_stage_error(discovery_error)
        merged_candidate, merge_error = capture_sync(
            lambda: context_builder.merge_atomically(
                package=context_candidate,
                expected_canonical_scope=scope,
                discovered_instructions=discovered_candidate,
            )
        )
        await cooperate_then_guard("after_merge")
        if merge_error is not None:
            raise_mapped_stage_error(merge_error)
        context_candidate = merged_candidate
```

`capture_sync` returns one local `(value, error)` pair. It re-raises `CancelledError` only when the
current task's cancelling count is positive; an independently raised instance is staged as an
unexpected error. The mandatory seam always runs before `raise_mapped_stage_error`, so lifecycle can
discard either a late value or error without claiming that synchronous work was preempted.

`dispatch_one` is the CAH-034-owned bridge rather than a CAH-031 dependency on later provider types:

```python
def dispatch_one(
    catalog: ReadToolCatalog,
    prepared: PreparedReadToolCall,
) -> DispatchCandidate:
    require_identity(prepared.catalog_identity is catalog.identity)
    try:
        native = catalog.registry.dispatch_bound(prepared.read_tool, prepared.request)
    except (RepositoryAccessError, ReadToolRegistryError) as known:
        require_replayable_code(known.code)  # closed CAH-026 + two CAH-031 result codes
        return DispatchCandidate(
            provider_result=fixed_error_result(prepared.call_id, known),
            instruction_scopes=(),
        )
    result = ProviderToolResult(
        call_id=prepared.call_id,
        status="success",
        output_json=native.output_json,
    )
    return DispatchCandidate(provider_result=result, instruction_scopes=native.instruction_scopes)
```

A catalog mismatch is the exact content-suppressed session invariant failure
`ReadToolCatalogError(code="invalid_read_tool_catalog", message="Read tool catalog is invalid.")`
with zero handler I/O, replay, or follow-up provider start. It is not converted into a
model-correctable tool error. CAH-031's `invalid_read_tool_binding` maps to that same unchained
non-replayable error. Likewise, an impossible CAH-031 lookup/input/registration code or an unknown
exception fails the session rather than passing `require_replayable_code`.

CAH-039 owns every raw-JSON/key/type detail and is tested independently. This unit proves the handoff:
one error crosses the outcome-adoption test gate with zero dispatch/context growth, while one prepared
value crosses the pre-dispatch checkpoint unchanged. Static imports prevent orchestration from growing
a second scanner, decoder, duplicate walk, key gate, or Pydantic-validation path.

Non-replayable failures are also closed rather than described as generic session errors:

| Boundary | Exact session result |
| --- | --- |
| catalog identity/binding | `invalid_read_tool_catalog` / `Read tool catalog is invalid.` |
| root or result-scope instruction discovery | the exact CAH-025 safe code/message |
| initial context build or later merge/budget | the exact CAH-030 safe code/message |
| initial context projection/request or follow-up request construction | `invalid_provider_tool_value` / `Provider tool value is invalid.` |
| provider start/shape, unexpected invariant, or usage aggregate overflow | `provider_invalid_response` / `The provider returned an invalid response.` |
| cleanup after a selected terminal outcome | keep that outcome; add only `provider_cleanup_failed` diagnostics |
| intermediate generation cannot be force-reaped | `provider_invalid_response` only if no terminal won; otherwise retain cancellation/deadline; cleanup diagnostic; no dispatch or next start |

Normalized provider failures and CAH-022 limits retain their existing exact mappings. Cancellation,
teardown, and an already-selected deadline retain existing winner precedence. None of these rows is
sent to the model as a tool result.

A late native result is discarded after the post-dispatch checkpoint. Every validated success path
starts with the execution-time canonical request scope, even for an empty listing or no-match search.
Then `list_files` covers each returned directory itself and each returned file's parent,
`search_text` covers match-file parents, `stat_path` covers a canonical directory itself or a
canonical file's parent, and `read_file` covers the canonical file parent.
Discovery and merge have a checkpoint for every scope. All scope candidates, the result, and the
complete context remain local; one failure or exhausted budget discards the entire transaction
instead of replaying partially covered content.

### Planned pseudocode: one follow-up

```python
turn_items = (
    (opaque, call, result_candidate)
    if opaque is not None
    else (call, result_candidate)
)
history_candidate = (*original_history, *turn_items)
request_candidate, request_error = capture_sync(
    lambda: build_bounded_request(
        conversation=history_candidate,
        repository_context=build_provider_context(context_candidate),
        tools=catalog.definitions,
    )
)
await cooperate_then_guard("before_provider_start")
if request_error is not None:
    raise_mapped_stage_error(request_error)  # no model charge/start
installed = await start_claim_and_commit_turn_atomically(
    request=request_candidate,
    context=context_candidate,
    history=history_candidate,
)  # charge -> start -> events() -> carrier -> final clock -> one pointer; no await
if installed is None:
    return  # selected terminal and any uninstalled cleanup already settled
final_turn = await self._collect_admitted_turn(
    installed.generation.operation, installed.generation.events
)
if final_turn is None:
    return  # an authoritative lifecycle terminal already won
if outcome_adoption_observer is not None:  # deterministic tests only
    await outcome_adoption_observer()
adopted = adopt_turn_outcome_under_guard(final_turn, all_turn_usage)
if adopted is None:
    return  # provider failure, limit, cancellation, or deadline selected
require_type(adopted, AcceptedFinalText)  # usage/text already admitted atomically
```

The code is intentionally not a `while` loop. `opaque` is the CAH-032 positional history item, not a
separate request field. The async helper may await existing decision/deadline locks before its
critical section and may join transferred uninstalled cleanup after a losing selection. Its no-await
critical section admits the turn immediately before `Provider.start`,
validates `events` plus all three cleanup methods before invocation, calls `events()` once, validates
the async iterator, and constructs the complete immutable carrier before the final injected-clock
read. One non-failing pointer assignment then commits it. A deadline observed by that read wins; one
becoming due only after assignment loses this transition. A start/claim/shape/carrier failure selects
exact invalid response unless the deadline is observed in its error path;
context/history remain unchanged and the attempt remains charged. A non-operation receives no method
or cleanup call; a valid uninstalled real operation goes
through one cancel-first cleanup task outside the lock; force cleanup is fallback only, and terminal
publication waits for that task and any cleanup diagnostic.
A successful factory/claim has no intervening await before install. Each request independently passes the
512-KiB gate:
the follow-up charges all cumulative conversation/context bytes inside its snapshot but does not add
the first request's whole size again.

Each installed operation, iterator, pending read, and cleanup task lives in one numbered generation.
Exactly one cleanup task owns that generation. Natural close is supervised under the five-second
grace; failure or expiry invokes force-reap once, and continuation is legal only after force returns.
If force cannot confirm reaping, the session fails as `provider_invalid_response` only when no
terminal already won; otherwise cancellation/deadline remains authoritative. It performs no dispatch
or later start. A cancellation/deadline arriving during natural cleanup joins the same task
rather than changing cleanup mode or starting `cancel()` concurrently. The generation-only helper
clears generation one by identity before dispatch/turn two but leaves the absolute-deadline watcher
alive; only the terminal session finalizer stops it. A late callback cannot touch a newer generation.
Before final publication, all usage is either present
on both accepted turns and checked as one candidate or omitted entirely. Usage admission runs before
the tracker's one complete-text reservation; only after both pass are chunks emitted, admitted usage
persisted, and completion events sent.

CAH-033 returns a staged value but does not own session accounting. An optional test-only
`outcome_adoption_observer` may pause immediately afterward; it is separate from
`ReadOnlyCheckpoint` and absent in production. Then one
guarded adoption transaction rechecks the selected terminal and absolute deadline. The winner is
linear: cancellation/deadline first discards the candidate with no new charge; adoption first charges
the call or validates usage and reserves whole text, and a later cancellation cannot roll that
accounting back. Tests pause immediately before this guard, never inside it.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| CAH-039 rejects name/JSON/duplicate/key/type | exact fixed error envelope | charged call; one admission call, zero dispatch/context growth, unchanged-context replay |
| production yield removed | queued cancellation is not latched | no-hook guard spy fails before dispatch |
| missing file | exact repository error envelope | no OS/path leak |
| 65,537-byte wrapped result or native-max read whose wrapper overflows | exact `read_tool_output_too_large` envelope | charged call crosses `after_dispatch`; zero discovery/context growth and no result content |
| cancellation during sync tool | `after_dispatch` yields before guarding | no turn two start |
| cancellation during discovery/merge | following checkpoint yields before guarding | no result/context commit |
| dispatch/discovery/merge/request raises, including independent `CancelledError` | following named checkpoint precedes mapping | lifecycle wins or fixed safe failure; true task cancellation alone propagates |
| instruction discovery/merge fails | safe session failure | no result/context publication or turn two |
| initial/follow-up projection or request build fails | checkpoint before mapping | no model charge/start; original context/history |
| provider start/event claim/shape/carrier build fails | deadline if observed by the final/error-path read, otherwise fixed `provider_invalid_response`; cancel-first supervised cleanup for an uninstalled operation | one charged model attempt; original context/history; zero operation iteration; force only after ordinary cleanup failure/grace |
| deadline becomes due after installed-state pointer commit | installed transition wins | watcher handles the deadline against the installed generation; no rollback |
| uninstalled-operation cleanup blocks or fails | terminal waits; failure adds diagnostic first | one cleanup task, no early terminal, no concurrent API |
| turn-one natural cleanup fails or expires | force-reap once; continue only after confirmed local reap | force failure selects fixed invalid response; zero dispatch or turn two |
| cancellation/deadline wins during natural cleanup | join the one generation cleanup task | no mode drift, concurrent cleanup API, tool side effect, or second terminal |
| intermediate cleanup stops the absolute watcher | forbidden composition | watcher identity survives turn one; injected deadline still wins on turn two |
| alias retargets after dispatch | discover only captured canonical scope | empty-list/no-match `alias -> A` changed to `B`; no replacement instructions or alias fallback |
| captured canonical label retargets to allowed `B` | exact scope mismatch | CAH-025 reports `B`; zero merge, replacement instruction, replay, fallback, or turn two |
| captured canonical scope disappears | safe session failure | no result replay, context commit, or turn two |
| broad list/search returns nested paths | cover every ordered result owner before replay | one failed scope discards result and all candidate context |
| turn two calls again | `tool_call_limit_exceeded` | zero third starts |
| either usage observation is missing | successful answer, no usage aggregate | partial evidence never looks complete |
| usage sum or whole-text reservation overflows | exact failure before publication | zero chunks, zero usage, no partial output-byte charge |

## Production expansion

### Example enterprise scenario

A production registry may combine local and remote tools. It still needs application-owned input
validation, result envelopes, deadlines, idempotency, and audit policy for every executor.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  standardizes call/result exchange; schema/version maintenance costs remain local.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) can provide
  remote discovery/execution; authentication, network failure, and trust add cost.
- [Pydantic](https://docs.pydantic.dev/latest/) provides typed validation; schema discipline and
  upgrades require maintenance.
- [JSON Schema 2020-12](https://json-schema.org/draft/2020-12) improves portability; common-subset
  constraints reduce expressiveness.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Calls | exactly one | bounded repeated/parallel scheduling |
| Executor | local synchronous reads | local/remote async executors |
| Errors | closed fixed JSON | versioned capability error taxonomy |
| Evidence | one session aggregate | governed per-call traces |
| Cost | simple and reviewable | availability, auth, idempotency operations |

### Trade-offs and graduation signals

One call is artificial but makes ownership auditable. Generalize only after exact validation,
late-result handling, replay, and aggregate evidence pass adversarial tests.

## Practical exercises

1. Trace malformed arguments and name every stage that must not run.
2. Explain why a tool error still uses a completed function-output transport item.
3. Design the no-observer queued-cancel test that fails if production's unconditional yield is
   removed; explain why an awaited Event gate alone cannot prove this.
4. Design a fake synchronous tool and named `asyncio.Event` gate that proves its result is discarded
   after a queued cancel command without using elapsed sleeps.
5. Inject a CAH-039 fixed error and prepared invocation; identify which checkpoint and dispatch calls
   each path reaches and why CAH-034 must not import a JSON decoder.
6. Derive the ordered scopes for a list result containing a directory, two files in that directory,
   and a file in a sibling directory; explain why one failed scope prevents replay.
7. Retarget an empty-result alias at `after_dispatch`; identify why discovery must receive the
   captured canonical target rather than the replacement.
8. Teach back why usage is persisted only after accepted final text.

## Key takeaways

- The model proposes; the harness validates, dispatches, and decides continuation.
- CAH-039 alone admits raw argument JSON; CAH-034 consumes one prepared-or-error handoff and owns the
  guarded dispatch, context enrichment, replay, and follow-up transition.
- Every execution-time canonical request and result-derived owner scope receives applicable
  instructions atomically before a successful result can be replayed.
- Safe JSON errors let the model explain bounded failures without exposing internals.
- Cancellation around synchronous tools is cooperative: each named boundary must yield before it
  reads cancellation/deadline state.

## Glossary

- **Semantic status:** CAH-032's neutral success/error tag, validated to agree with the result payload;
  an adapter may send the payload without mapping that tag to a transport-status field.
- **Transport status:** provider lifecycle state for delivering that payload.
- **Non-preemptive:** cannot be interrupted mid-execution by task cancellation.
- **Cooperative checkpoint:** an unconditional event-loop yield, optional deterministic test hook,
  then the established cancellation/deadline guard.
- **Replay:** reconstructed ordered input sent in a stateless follow-up.
- **Context snapshot:** one immutable, fully validated context package used by a provider request.
- **Content-suppressed metadata:** local structural paths used for policy without copying tool content
  into protocol, transcript, or provider-facing schemas.

## Further reading

- [CAH-034 delivery contract](../../user-stories/cah-034-run-one-read-tool-round-trip.md)
- [CAH-039 argument-admission lesson](cah-039-provider-tool-argument-admission.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- [Pydantic](https://docs.pydantic.dev/latest/)
