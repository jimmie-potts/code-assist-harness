# CAH-034 - Run one read-tool round trip

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop (integrating E3 repository tools)
- **Dependencies:** CAH-030, CAH-031, CAH-032, CAH-033
- **Lesson:** [One read-tool round trip](../docs/lessons/cah-034-one-read-tool-round-trip.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** One visible harness-owned observe-validate-dispatch-result-follow-up sequence,
  including exact safe result envelopes, cancellation boundaries, and aggregate usage evidence.

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
- Start exactly one follow-up provider turn with full immutable call/result replay, the original
  CAH-030 context, and the same CAH-032 definitions.
- Publish only CAH-033-admitted final text through the existing protocol lifecycle.
- Aggregate optional usage from the two accepted turns with checked arithmetic and persist one
  existing session-level model-usage aggregate only after accepted final text.
- Reuse the existing transcript-v3 aggregate loop evidence; add no per-call record or migration.
- Prove validation order, bounded synchronous execution, cancellation, and exact safe result JSON
  with deterministic fakes.

## Locked contract

- Before the first provider start, CAH-032's pure bridge produces the exact ordered four-tool
  catalog. Bridge failure performs zero provider and tool work. Both provider requests retain the
  same immutable context tuple and tool definitions; inclusion-report evidence is never sent.
- CAH-033 atomically returns the first accepted call. Only then does orchestration charge the one
  observed tool call and run, in order: exact registry lookup, JSON-object decoding, CAH-032's exact
  model-facing required-key gate, native Pydantic input validation, synchronous dispatch, native
  result validation, and bounded rendering. The key gate runs before Pydantic can apply a native
  default; a failed stage runs no later stage. Direct Python calls remain free to use the unchanged
  native request models and defaults outside this model-facing path.
- M2 native tools are intentionally synchronous, bounded, and non-preemptive. The harness checks
  cancellation and the captured absolute deadline immediately before dispatch and immediately after
  it returns. Cancellation cannot interrupt Python code already executing; a result that returns
  after cancellation or deadline selection is discarded, never replayed, published, or persisted.
- A successful tool output is the exact compact canonical CAH-031 JSON envelope
  `{"result":<allowlisted-value>}`. Known failures are exact compact JSON envelopes
  `{"error":{"code":"<code>","message":"<fixed message>"}}` with no whitespace. The closed error
  set is CAH-031's `unknown_read_tool`,
  `invalid_read_tool_input`, and `invalid_read_tool_result`, plus CAH-026's twelve
  `RepositoryAccessError` code/message pairs. Malformed JSON or a non-object maps to
  `invalid_read_tool_input`. Unknown exceptions and programmer defects are session failures, not
  model content. `invalid_read_tool_registration` is a pre-provider composition failure.
- The bounded result JSON is stored in `ProviderToolResult.output_json`; success/error meaning is
  inside that payload as well as the neutral domain status. It contains no arguments, absolute path, raw
  exception, OS text, secret, or unbounded content. Rendering or envelope overflow fails the session
  safely instead of truncating JSON.
- The follow-up request is a full immutable replay of original input plus the exact admitted call,
  its matching result, optional first-turn opaque continuation, and the same definitions/context. The
  single CAH-032 history tuple appends them exactly as
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
3. The follow-up request replays the original input, optional opaque continuation, exact call/result,
   unchanged context, and unchanged definitions in the single provider-neutral history order
   `continuation? -> call -> result`.
4. One accepted follow-up final answer publishes staged chunks through existing events and selects
   one completed session; a second call or invalid response starts no third turn.
5. Synchronous tools are never represented as preemptible: cancellation/deadline is checked before
   and after dispatch, and any late result is discarded.
6. Optional per-turn usage is summed with checked arithmetic and exactly one existing aggregate is
   persisted only after accepted final text; partial/rejected usage is absent.
7. All budgets span the two turns and one call without reset, and request overflow prevents the
   rejecting provider start.
8. Existing transcript v3 and protocol v1 remain unchanged and content-safe; no per-call evidence
   record, argument, tool content, or provider continuation is persisted.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 3-4 | One strict-fake/native-fixture integration asserts two exact requests—including `[user, opaque, call, result]` when continuation is present—one dispatch, full replay, ordered final events, one terminal, and zero third starts. |
| 2 | Parameterized malformed/non-object JSON, omitted defaulted keys, additional keys, unknown tool, invalid input/result, every CAH-026 access error, oversized rendering, and programmer defect asserts the exact envelope or safe session failure plus stage counters. A spy proves the raw-key gate rejects before native Pydantic validation/default application. |
| 5 | Logical checkpoints select cancellation/deadline immediately before dispatch and while a bounded synchronous fake runs; post-return checks discard distinctive late-result sentinels. |
| 6 | Two-turn tables cover no usage, usage on either/both turns, exact checked sums, aggregate overflow, rejected turn two, cancellation, and one transcript-v3 aggregate write. |
| 7 | Seeded boundary tests exhaust model starts, deadline, assistant UTF-8 output, tool calls, and 512-KiB request projection without reset or late work. |
| 8 | Transcript/replay and protocol fixture suites prove unchanged schemas and absence of call IDs, arguments, result/continuation content, and host paths. |

## Validation

- Use strict fake exchanges, bounded synchronous fake tools, injected clocks, and logical
  checkpoints; never use live requests or wall-clock sleeps.
- Assert exact request history, registry-stage counters, result bytes, provider starts/cleanup,
  aggregate usage, transcript projection, protocol events, and terminal count.
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

- One exact two-exchange fake script with one native dispatch and immutable replay.
- Closed-table result-envelope, validation-order, late-result, and budget failure suites.
- Checked two-turn usage aggregation with exactly one existing transcript-v3 session record.

## Deferred work

- CAH-035 replaces the explicit two-turn branch with a bounded iterative state machine.
- CAH-036 maps OpenAI Responses items to the provider-neutral staged-turn contract.
- MCP adapters, parallel tool use, visible progress, and side-effecting policy remain later work.
