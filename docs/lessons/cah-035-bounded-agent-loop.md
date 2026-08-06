# CAH-035 lesson: Run the bounded agent loop

- **Unit:** CAH-035
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; only a one-call round trip is specified first
- **Story:** [CAH-035](../../user-stories/cah-035-run-bounded-agent-loop.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned state transitions, atomic scoped-instruction accumulation,
  cumulative accounting, reachable stop conditions, and defense-in-depth guards
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Architecture](../architecture.md), and
  [Safety model](../safety-model.md)

> This lesson describes planned loop behavior. Pseudocode is not shipped-code evidence.

## Quick summary

CAH-035 turns one proven call/result cycle into an explicit sequential state machine with at most
four model turns and three admitted calls. Each iteration reuses CAH-039's duplicate-safe argument
admission and CAH-034's guarded dispatch, then atomically covers every execution-time canonical
request and result-owner instruction scope before replay. The Python harness—not a provider or
tool—owns progress and context.

## Learning objectives

After this unit, you should be able to:

- locate agency in explicit states and transitions;
- prove termination from hard turn/call ceilings;
- distinguish reachable limit precedence from defense-in-depth checks;
- trace atomic context enrichment across nested, repeated, alias, and sibling instruction scopes;
- explain why every iteration reuses CAH-039's sole raw-argument admission path;
- carry history, usage, deadline, and output accounting cumulatively;
- explain why every synchronous guard first yields to the event loop; and
- explain where a future MCP adapter fits without owning the loop.

## Why this unit matters

An “agent” is not mysterious autonomy. Here it is a small state machine that repeatedly admits one
model outcome, optionally runs one tool, appends one result, and decides whether another turn is safe.

## Junior engineer foundation

A state machine names legal states and transitions. If code cannot name a transition, it must fail.

```text
MODEL -> FINAL
MODEL -> CALL -> VALIDATE -> YIELD/GUARD -> TOOL -> YIELD/GUARD
      -> DISCOVER -> YIELD/GUARD -> MERGE -> YIELD/GUARD
      -> STAGE REQUEST -> YIELD/GUARD -> ADMIT -> COMMIT/START MODEL
```

A common misconception is that every configured limit must be reachable normally. With three call
slots, a fourth call fails before it could request turn five; the fifth-turn guard still protects
against corrupted/seeded state.

Another misconception is that broad results may be replayed before their nested instructions are
known. CAH-031 derives content-suppressed `instruction_scopes` only after native result validation:
the execution-time canonical request scope first, then every exact-deduplicated returned-path owner.
The loop must discover and verify each returned bundle still names its captured scope before merge
or replay; it never re-resolves the original alias or accepts a canonical-label retarget.
Those local paths do not become provider fields or new search roots.

The reused CAH-031 derivation covers directory entries and file parents from `list_files`, the
canonical directory or file parent from `stat_path`, the canonical parent from `read_file`, and every
match-file parent from `search_text`, always in defined native result order.

Raw argument JSON also stays raw through CAH-032, CAH-033, and adapters. Every iteration calls
CAH-039's one structural/decode path after registry lookup: an iterative quote-aware preflight over
the complete 16-KiB value, at most 64 object/array levels with root object depth 1, then
pair-preserving decode with non-finite-constant rejection and an iterative every-depth duplicate
walk. The preflight also admits only signed-64-bit JSON integer tokens and rejects fractions or
exponents before Python conversion. Over-depth or mismatched structure, numeric overflow,
`NaN`/infinities, defensive decoder `RecursionError`/`ValueError`, and a duplicate decoded name all
produce `invalid_read_tool_input` before dictionary construction, key gating, or tool I/O. The loop
never resets the argument budget for a subtree or implements another parser on a later turn.

One more subtle misconception is that calling a synchronous cancellation guard is enough. While a
synchronous tool owns the event-loop thread, the cancel command cannot run and update session state.
CAH-034's reusable checkpoint must first `await asyncio.sleep(0)` outside locks, optionally cross a
deterministic test gate, and only then read cancellation/deadline state.
An awaited gate is useful for pausing a stage but cannot by itself prove the production yield exists;
the separate no-hook queued-cancel test observes state at guard entry and mutation-tests removal of
the yield.

## Key concepts

- **Agent loop:** harness-owned repeated model/tool cycle.
- **Cumulative ledger:** limits that never reset between turns.
- **Reachable stop:** failure possible from a fresh legal session.
- **Defense in depth:** redundant guard tested through seeded internal state.
- **Sequentiality:** at most one active provider or tool operation.
- **Cooperative checkpoint:** CAH-034's yield, optional test hook, then established guard sequence.
- **Scoped accumulation:** atomically add newly applicable instruction items after successful reads.
- **Instruction scopes:** the execution-time canonical request path followed by ordered returned-owner
  paths, all derived from a validated native success and consumed only by the harness.
- **Idempotent scope:** a repeated candidate-owner binding adds nothing only when its source,
  content, and original byte count match; one source under another owner remains distinct.
- **Positional replay:** append each optional continuation immediately before its call and matching
  result in one immutable history tuple.
- **Operation generation:** the current operation, claimed iterator, pending read, and cleanup task
  settle and clear by identity before another turn can own those slots.
- **Session-wide watcher:** the one absolute-deadline task that survives every intermediate generation
  and is stopped only by the authoritative session finalizer.
- **All-or-none usage:** persist an aggregate only when every accepted turn reported usage.
- **Outcome adoption:** the guard-owned instant when one staged turn either loses to an existing
  terminal or becomes charged/admitted loop state.

## Architecture and design

```text
Ink TUI                 Python harness loop                     Provider
 final only <----- [publish accepted FINAL] <-------------- admitted text
                           ^        |
                           |        +---- next request -------> model
                           |             current context ^
         APPEND opaque? -> call -> result <---- bounded replay
                           ^
       CAH-039: LOOKUP -> STRUCTURAL + NUMERIC PREFLIGHT -> CONSTANT-REJECTING PAIR DECODE
                                                                  |
                                                   ITERATIVE DUPLICATE WALK
                                                                  |
                                             EXACT-KEY GATE -> PYDANTIC
                                                                  |
                                                     YIELD/GUARD -> DISPATCH
                                                                  |
                                                        native read registry
                                                                  |
                                                   local dispatch candidate
                                                                  v
                          YIELD/GUARD -> for each instruction_scope
                                           |
                          CAH-025 discover -> YIELD/GUARD
                                           |
                          CAH-030 merge -> YIELD/GUARD
                                           |
                          stage local result/context/history/request
                                           |
                              YIELD/GUARD -> admission -> lazy start candidate
                                           -> claim events -> build immutable carrier
                                           -> final clock -> one-pointer commit -> iterate to EOF

Ceilings: 4 provider starts / 3 within-budget calls / one rejecting fourth observation at most
Context: root-only start; every result fully covered; recheck context/request every turn
Evidence: one final transcript-v3 usage aggregate; no calls/results/opaque content
MCP: future registry/executor adapter below the loop, never the loop owner
```

The fourth admitted call is charged and rejected before dispatch. Starting turn five is therefore
unreachable normally and tested by seeding the turn ledger immediately before admission.
The loop uses CAH-034's exact runtime-owned `ReadOnlyAgentServices` bundle and a fresh per-session
`LoopLimits(4, 120, 4096, 3)` tracker. Each operation turn receives a distinct generation.

## Practical walkthrough

1. After `session.started`, use the exact shared services to stage root-only context and the initial
   request-or-error. Cross `before_provider_start` before unwrapping it; only a complete request can
   charge and start a model turn.
2. Collect one atomic CAH-033 outcome and enter the outcome-adoption guard. A terminal that already
   won discards it with no new call/output/usage charge; adoption first makes its accounting durable.
3. On final text, validate all-or-none usage and reserve the complete text once inside that guard;
   only then let the finalizer clean up, publish chunks, persist usage if complete, and finish.
4. Otherwise charge the call in that guard and reuse CAH-039's exact admission path: lookup first, 16-KiB/64-level
   quote-aware structural plus signed-64-bit numeric preflight, constant-rejecting pair decode and
   iterative duplicate check, and exact-key/Pydantic validation. Then reuse CAH-034's cooperative
   checkpoint, bounded dispatch, and post-dispatch checkpoint.
5. For success, iterate CAH-031's ordered `instruction_scopes`, beginning with captured canonical
   request scope. Discover one bundle, checkpoint, require its `canonical_scope` to equal the
   captured scope, merge it into the local context candidate, and checkpoint for every scope without
   falling back to the request alias or a retargeted canonical label. For a known error, retain the
   current context candidate; it carries no scopes.
6. Stage optional continuation, call, result, context, history, and the complete bounded
   request-or-error locally. Checkpoint at `before_provider_start`, unwrap it, then charge the model
   attempt through CAH-022. Ask the provider for one lazy operation, validate its complete port, claim
   its events, construct one immutable installed-turn carrier, perform the final clock read, and commit
   by one non-failing pointer assignment. A start/claim/shape/carrier failure commits no context/history
   but retains the charge; an uninstalled operation uses one joined cancel-first cleanup task.
7. Settle and clear each tool-turn generation by identity before dispatch or the next start; force-reap
   after natural-cleanup failure/grace and continue only when reaping is confirmed. Leave the one
   session-wide deadline watcher alive. Late old callbacks cannot target the current generation.

## Implementation code samples

### Planned pseudocode: explicit loop

```python
services = build_read_only_agent_services(boundary)
catalog = services.catalog
initial_history = (task_item,)
initial_request, initial_request_error = capture_sync(
    lambda: build_initial_request(
        conversation=initial_history,
        repository_context=build_provider_context(initial_context),
        tools=catalog.definitions,
    )
)
await cooperate_then_guard("before_provider_start")
if initial_request_error is not None:
    raise_mapped_stage_error(initial_request_error)  # no model charge/start
installed = await start_claim_and_commit_turn_atomically(
    initial_request, initial_context, initial_history
)
if installed is None:
    return
outcome = await self._collect_admitted_turn(
    installed.generation.operation, installed.generation.events
)
while True:
    if outcome is None:
        return  # supervised terminal already selected and operation reaped
    if outcome_adoption_observer is not None:  # deterministic tests only
        await outcome_adoption_observer()
    adopted = adopt_turn_outcome_under_guard(outcome, all_turn_usage)
    if adopted is None:
        return  # failure/limit/cancellation/deadline already selected
    if isinstance(adopted, AcceptedFinalText):
        return await publish_admitted_final(adopted)  # usage/text already admitted
    require_type(adopted, AcceptedToolCall)
    all_turn_usage = (*all_turn_usage, adopted.usage)
    if not await settle_and_clear_current_generation_for_continuation():
        return  # no CAH-039 admission, dispatch, context work, or next start
    # This helper never stops the session-wide deadline watcher.
    admission = prepare_read_tool_call(adopted.call, catalog)  # prepared or ProviderToolResult
    context_candidate = installed.context
    dispatch_candidate = None
    dispatch_error = None
    if isinstance(admission, ProviderToolResult):
        result_candidate = admission
    else:
        await cooperate_then_guard("before_dispatch")
        dispatch_candidate, dispatch_error = capture_sync(
            lambda: dispatch_one(catalog, admission)  # CAH-034 helper
        )
    await cooperate_then_guard("after_dispatch")
    if dispatch_error is not None:
        raise_mapped_stage_error(dispatch_error)
    if dispatch_candidate is not None:
        result_candidate = dispatch_candidate.provider_result
    if dispatch_candidate is not None and result_candidate.status == "success":
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
    history_candidate = append_turn(installed.history, adopted, result_candidate)
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
        request_candidate, context_candidate, history_candidate
    )
    if installed is None:
        return
    outcome = await self._collect_admitted_turn(
        installed.generation.operation, installed.generation.events
    )
```

Every helper has a single admission or transition responsibility. In implementation the initial
start is admitted once before the loop and each continuation is admitted at its final guarded
transition. The opaque value remains in the same CAH-032 history tuple immediately before its call;
there is no adapter side channel. `admit_arguments_via_cah039` means reuse of the exact CAH-039
lookup/preflight/decode/duplicate/key/Pydantic stages, not a second loop-owned parser. Unknown lookup
wins before preflight/decoding; structural overflow, a non-finite constant, decoder recursion
failure, or a known duplicate remains a charged call but runs zero key gate, dispatch, or context
growth and follows the known-error path for exact replay against unchanged context. Context is
replaced only after every result-owner discovery/merge, the final cooperative
checkpoint, and model admission. Exact repeated/alias scopes are no-ops; changed owner snapshots
fail rather than silently replacing an earlier instruction, while the same source under another
owner remains a separately charged binding.
The registry's fixed `read_tool_output_too_large` follows that same known-error path after dispatch:
it carries no scopes, exposes no oversized content, and does not become an internal session failure.
Each bounded synchronous value/error and the complete next request remain local candidates until that
final checkpoint wins. `capture_sync` propagates `CancelledError` only for a genuinely cancelling
task; an independent instance is staged as an unexpected error, crosses the named seam, and is mapped
only if lifecycle does not win.

Inside `adopt_turn_outcome_under_guard`, normalized provider failure remains an explicit branch:

```python
case ProviderFailure(code=code, message=message, retryable=retryable):
    select_normalized_provider_failure(code, message, retryable)
    return None  # no call/output/usage charge, dispatch, or publication
```

The helper selects that exact safe terminal while holding the same decision/deadline guard; it does
not hide failure inside an accepted call/final carrier or expose the staged prefix.

Every non-replayable branch uses CAH-034's exact failure table unchanged. Iteration does not invent a
generic loop error: catalog, instruction, context, request, provider/operation, usage aggregate,
normalized-provider, limit, cancellation/deadline, and cleanup outcomes keep the same fixed mapping
and precedence on every turn.

`start_claim_and_commit_turn_atomically` may await existing lock acquisition before and joined
uninstalled cleanup after a losing selection. Its guarded critical section runs without an
intervening await from turn admission through lazy factory return, single `events()` claim,
async-iterator shape check, complete immutable carrier
construction, final injected-clock read, and one non-failing pointer assignment. A deadline observed
at that read wins; one becoming due after assignment loses this transition. Other failure is exact
invalid response. Original context/history remain while the charge stays. A real uninstalled
operation goes through one cancel-first cleanup task outside the lock, with force cleanup only after
failure/grace; terminal publication joins that task and records any cleanup diagnostic first. Every
installed operation has a
distinct generation and one cleanup task; a cancellation/deadline arriving during natural cleanup
joins that task without changing mode or invoking a concurrent provider API. The prior generation
must be provably reaped before continuation; failed force-reap selects exact invalid response only
when no terminal already won, otherwise retaining cancellation/deadline, and permits no tool or next
turn. Generation-only settlement never stops the session-wide deadline watcher. Each
complete request independently passes CAH-032's 512-KiB gate;
the cumulative conversation is inside the later snapshot, but earlier whole-request bytes are not
added a second time.

The continuation cleanup helper's exact result is Boolean. It returns `True` only after confirmed
reaping, identity-checked clearing, and a no-terminal guard; every other outcome returns `False`, and
the loop exits before CAH-039 argument admission. A mutation that ignores this result must fail.

The `installed` carrier is also the loop's sole committed context/history base. Each successful
pointer assignment replaces it, so the following iteration reads the just-committed snapshots instead
of stale pre-loop locals. This is what preserves every earlier continuation, call, result, and context
enrichment across three round trips.

### Planned pseudocode: fifth-turn defense

```python
ledger = seeded_ledger(model_turns=4)
assert start_next_turn(ledger, provider_spy).code == "model_turn_limit_exceeded"
assert provider_spy.starts == 0
```

This test does not invent an impossible fifth-turn provider transcript.

## Failure scenarios to study

| Scenario | First rejecting boundary | Safe result |
| --- | --- | --- |
| fourth call on turn four | call admission | no fourth dispatch |
| seeded fifth start | model admission | zero provider starts |
| request grows past 512 KiB | request construction | no next start |
| cancellation during sync tool | `after_dispatch` yields, then guards | late result discarded |
| cancellation during discovery/merge | following checkpoint yields, then guards | late bundle/package discarded |
| instruction source changes between scopes | atomic merge | prior context retained; terminal |
| nested/sibling merge exceeds context budget | atomic merge | no pending result/context publication |
| list/search exposes several owners | per-scope discovery/merge | all covered before replay or whole transaction discarded |
| captured canonical label retargets to allowed scope | bundle-scope check before merge | whole transaction discarded; no replacement instructions, fallback, or next start |
| later call repeats a decoded name | CAH-039 admission | charged call; zero key gate/dispatch/context growth |
| invalid mixed response | CAH-033 collector | no tool/publication |
| dispatch/discovery/merge/request raises, including independent `CancelledError` | following named checkpoint | lifecycle wins or fixed safe failure; true task cancellation propagates |
| provider request construction fails | `before_provider_start` before mapping | zero model charge/start; installed snapshots unchanged |
| deadline becomes due after installed-state pointer commit | installed transition | watcher handles it against that generation; no rollback |
| valid uninstalled operation requires cleanup | joined uninstalled-cleanup task | no terminal before cleanup; any diagnostic precedes terminal |
| any accepted turn omits usage | final evidence admission | answer may complete; no partial aggregate |
| usage sum or complete text reservation overflows | final commit admission | zero chunks and no transcript aggregate |

## Production expansion

### Example enterprise scenario

A production agent may schedule remote tools, retries, and subagents. Each feature multiplies states,
so transition tracing, idempotency, quotas, and recovery become operational requirements.

### Typical production capabilities and tools

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  provides call turns; application loop control and budgets remain local work.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) standardizes remote
  capability boundaries; authentication and availability add cost.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html) provide cancellation;
  task ownership and race tests add complexity.
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) expose transitions;
  privacy, sampling, and storage governance add cost.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Turns/calls | 4 / 3 | policy/model-specific quotas |
| Context | complete canonical-request/result-owner accumulation | indexed retrieval and versioned context policy |
| Scheduling | one sequential operation | bounded concurrency and idempotency |
| Recovery | foreground fail closed | durable checkpoints/resumption |
| Evidence | aggregate only | redacted transition traces |
| Cost | simple, deterministic | orchestration and telemetry operations |

### Trade-offs and graduation signals

Small fixed ceilings may stop useful work, but make safety and cost testable. Increase or specialize
them only with eval evidence; add parallelism only after ordering, cancellation, and evidence rules
are designed.

## Practical exercises

1. Trace three calls followed by final text and count every turn.
2. Explain why a fourth call wins before a fifth-turn limit.
3. Trace nested then sibling reads; explain why precedence applies within each chain but one sibling
   does not override the other.
4. Derive all scopes from a broad list result and show why cancellation on the last scope discards
   the result and every candidate merge.
5. Explain why `"path"` and `"pa\u0074h"` fail in CAH-039 on both the first and third iteration.
6. On the third iteration, test structure at depths 63, 64, and 65, quoted delimiters, an object
   nested in an array with a duplicate, all three non-finite constant spellings, and a forced decoder
   `RecursionError`. Add signed-64-bit endpoints/overflow, fractions/exponents, a 5,000-digit integer,
   numeric-looking strings, and forced `ValueError`; explain why none warrants a loop-owned parser.
7. Design a request-growth test crossing 512 KiB without truncation.
8. Design named `asyncio.Event` gates for each synchronous checkpoint and explain why elapsed sleeps
   would make the cancellation test nondeterministic.
9. Explain why the no-hook guard-spy test, not an awaited Event hook, proves the unconditional yield.
10. Retarget an empty-result alias on the third iteration and show why discovery still receives only
   the native result's captured canonical scope.
11. Then retarget that captured canonical label itself to another allowed scope; explain why the
    discovered bundle must be rejected before merge.
12. Teach back why an MCP server cannot decide the next model turn or select instruction scope.

## Key takeaways

- The explicit Python state machine is the agent's control plane.
- Every iteration reuses CAH-039's lookup-first, bounded structural and signed-64-bit numeric
  preflight, constant-safe pair-preserving decode, and iterative duplicate check; no adapter or loop
  parser may inspect or collapse raw arguments first.
- Context growth is a guarded transition: every execution-time canonical request and result-owner
  discovery/merge succeeds atomically or the loop stops without replay or a next provider start.
- The guard observes queued cancellation only after CAH-034's reusable checkpoint yields to the
  event loop; staged candidates prevent partial state when it loses.
- Cumulative limits and exact precedence make termination provable.
- Defense-in-depth tests should seed the guarded state instead of inventing illegal histories.

## Glossary

- **Control plane:** component that decides transitions and policy.
- **Limit precedence:** which guard wins when more than one could reject work.
- **Seeded state:** deliberate test setup at an internal boundary.
- **Terminal winner:** the single completion/failure/cancellation selected for a session.
- **Sibling scope:** a different ancestor chain whose instructions retain separate applicability.
- **Result owner:** directory whose model-visible returned path requires applicable instructions
  before that result can be replayed.

## Further reading

- [CAH-035 delivery contract](../../user-stories/cah-035-run-bounded-agent-loop.md)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
