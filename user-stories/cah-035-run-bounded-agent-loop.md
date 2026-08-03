# CAH-035 - Run the bounded agent loop

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop
- **Dependencies:** CAH-034
- **Lesson:** [Bounded agent loop](../docs/lessons/cah-035-bounded-agent-loop.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** The harness-owned state machine, its stop conditions, cumulative budgets, and
  defense-in-depth limit proofs across model turns and tool calls.

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
  call validation, synchronous dispatch, result append, and the next model admission.
- Admit at most four started model turns and three within-budget tool calls per session while retaining
  the single rejecting fourth observation required by CAH-022 when tool-call exhaustion wins.
- Reuse CAH-033 atomic turn outcomes and CAH-034 registry dispatch, safe result envelopes, immutable
  replay, checked usage aggregation, cancellation handling, and existing transcript-v3 evidence.
- Keep all CAH-022 limits and CAH-032 complete-request bytes cumulative.
- Prove legal progress, every reachable stop, and defense-in-depth guards with deterministic fakes
  and seeded ledger states.

## Locked contract

- The Python harness owns the state machine:
  `admit_model -> publish_final` or
  `admit_model -> admit_call -> validate -> dispatch -> append_result -> admit_model`.
  Provider adapters translate one operation; registry tools execute one validated input. Neither
  chooses whether another turn starts.
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
- Each accepted call follows CAH-034's exact lookup/parse/validate/dispatch/render order and compact
  JSON success/error envelopes. Synchronous tools remain bounded and non-preemptive; cancellation
  and deadline checks occur immediately before and after dispatch, and a late result is discarded.
- One immutable logical history contains initial input/context, every accepted opaque continuation,
  call, and matching result. Before each provider start, CAH-032 validates the full projection under
  512 KiB. No item is silently truncated, summarized, deduplicated, reset, or evicted.
- The absolute provider-work deadline is captured once. Model starts, observed calls, accepted
  assistant bytes, and complete request size remain cumulative. Limits are checked before costly
  work; the operation crossing a bound never starts or publishes.
- Optional usage values from accepted turns are added with checked arithmetic. One existing
  transcript-v3 aggregate is persisted only after an accepted final answer wins. Missing usage
  remains missing; rejected, failed, cancelled, or exhausted sessions persist no partial aggregate.
- Only the accepted final answer's staged chunks become `assistant.delta`, followed by existing
  completion events. Tool-only turns, result JSON, opaque continuation, and intermediate provider
  content are invisible to protocol/TUI and absent from transcript content.
- Bounded tool errors may become exact model-facing error results and continue while budget remains.
  Provider grammar errors, registry invariants, programmer defects, context/request overflow,
  deadline expiry, and cleanup failure follow established bounded terminal paths.
- Cancellation or teardown selects through the existing terminal guard, reaps the active provider
  operation, and prevents future transitions. A synchronous dispatch already running may return,
  but its post-dispatch guard discards the late result. Exactly one terminal winner remains.
- MCP may later supply registry descriptors and executor results, but it cannot own, continue, or
  bypass this state machine. M2 introduces no MCP client/server or remote trust boundary.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
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
5. All cumulative limits, full request replay (including opaque continuations), safe result
   envelopes, and request-size accounting survive every transition without reset.
6. Checked usage from all accepted turns produces exactly one existing transcript-v3 aggregate only
   on successful final text; every unsuccessful path persists no partial usage.
7. Bounded tool errors may continue, while invalid response grammar, internal invariants, and limit
   exhaustion terminate safely without raw or intermediate content.
8. Cancellation, teardown, provider failure, cleanup failure, and late synchronous results select
   one terminal and leave no owned provider work or actionable late result.
9. Protocol v1, TUI reducers, transcript v3 schema, provider adapters, and native tool contracts are
   unchanged by the loop generalization.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3 | Table-driven strict-fake cases complete with final text on turns one through four and assert exact states, immutable history, publication order, and one terminal. |
| 2 | Scripts exercise zero through three successful calls and instrument maximum provider/tool concurrency as one. |
| 4 | One fresh-session script returns a fourth admitted call and proves tool-limit precedence/no dispatch; a separate seeded model-turn ledger proves zero-start fifth-turn defense in depth. |
| 5 | Seeded boundaries exhaust deadline, UTF-8 output, calls, turns, and 524,287/524,288/524,289-byte requests; counters and replayed opaque/call/result items never reset. |
| 6 | Usage tables cover any subset of four turns, checked exact sums, overflow, missing usage, rejected final turn, cancellation, and exactly one aggregate persistence call. |
| 7 | Known tool errors continue once; grammar mutations, registry invariant faults, request overflow, and programmer defects assert exact safe terminal and no raw sentinel. |
| 8 | Logical barriers race cancellation/teardown against provider await, post-admission, pre/post-dispatch, append, next-start, final publication, and cleanup. |
| 9 | Transcript replay, protocol fixtures, reducer tests, adapter contract tests, and import-policy checks remain unchanged. |

## Validation

- Use deterministic fake exchanges, bounded fake tools, injected clocks, seeded ledgers, and explicit
  state traces; never use wall-clock sleeps or a live model.
- Assert exact provider starts, dispatches, maximum active work, request history, limits, aggregate
  usage, transcript projection, terminal count, cleanup, and protocol output.
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
- Writes, subprocesses, network tools, approvals, dynamic policy, context summarization, or
  unlimited/adaptive turns.

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

- Exact state traces for completion on each turn and zero through three calls.
- Fresh fourth-call precedence and seeded fifth-turn defense-in-depth tests.
- Cumulative request, deadline, output, usage, cancellation, and terminal-race suites.

## Deferred work

- CAH-036 maps OpenAI Responses items onto the proven provider-neutral turn contract.
- CAH-037 composes and evaluates the complete read-only assistant.
- MCP transport/discovery, parallel scheduling, durable continuation, and side-effecting tools remain
  later work.
