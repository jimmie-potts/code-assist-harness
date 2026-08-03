# CAH-033 - Stage and validate one tool-aware response

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E2 - Provider interface and explicit agent
  loop
- **Dependencies:** CAH-032
- **Lesson:** [Tool-aware response admission](../docs/lessons/cah-033-tool-aware-response-admission.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Atomic response admission: buffer an entire provider turn, accept one closed
  response grammar, and expose no text or tool call before terminal validation.

## User story

> As a learner building an agent loop, I want the harness to stage one complete tool-aware model
> response before acting on it so that malformed, mixed, or late provider output can never cause a
> partial answer or premature tool execution.

## Single responsibility

CAH-033 owns only provider-neutral admission of one model turn. It collects untrusted observations
and returns one immutable accepted outcome or one bounded failure. It does not dispatch a tool,
start another model turn, publish protocol events, or persist transcript evidence.

## Scope

- Replace optimistic text publication with a provider-neutral staged turn collector.
- Add immutable accepted final-text and one-tool-call outcomes, and return the existing immutable
  normalized `ProviderFailure` value for a provider-declared failure.
- Admit one optional CAH-032 `ProviderOpaqueContinuation` and at most one usage value.
- Validate the entire observation grammar through its legal `ProviderCompleted` or `ProviderFailed`
  terminal before exposing an outcome.
- Keep cancellation, the absolute provider-work deadline, and provider resource cleanup under the
  existing session owner while making publication a later orchestration action.
- Extend the strict fake with exact successful and adversarial tool-aware turn scripts.

## Locked contract

- The collector consumes exactly one provider operation and returns atomically. Its successful
  grammar is one of:
  `opaque? -> text.delta+ -> text.completed -> usage? -> response.completed` or
  `opaque? -> tool.call_requested -> usage? -> response.completed`.
  A normalized `response.failed` may be the first observation or may replace the remaining success
  suffix after any otherwise valid nonterminal prefix of either grammar. This preserves CAH-021's
  provider-neutral behavior and CAH-023's adapter behavior for failures after partial output.
  `response.failed` cannot launder an already-invalid prefix and is invalid after
  `response.completed`. End-of-stream before a required terminal observation is invalid.
- The legal failure cut points are exactly: before any staged observation; after the optional opaque
  continuation; after any valid text delta; after reconciled `text.completed`; after post-text
  usage; after the one tool call; or after post-call usage. Each non-empty cut point may also include
  its legal first-position opaque continuation. No other prefix is admitted.
- On `response.failed`, the collector discards the complete staged prefix—including text, call,
  opaque continuation, and usage—and returns only the existing bounded `ProviderFailure` value. Its
  exact harness-owned `code`, safe `message`, and `retryable` classification are preserved; staged
  data and raw provider values are absent from the outcome, diagnostics, transcript, and protocol.
- `text.completed` must equal the byte-for-byte concatenation of the non-empty, terminal-safe text
  deltas. The accepted final text is non-empty. A tool-call turn contains no text observation and
  exactly one bounded `ProviderToolCall`; mixed text/call, duplicate calls, post-terminal values, and
  unsupported observations select the fixed `provider_invalid_response` failure.
- The accepted call preserves CAH-032's bounded `arguments_json` byte-for-byte and does not parse it.
  Repeated JSON member names inside that one argument string are distinct from duplicate call
  observations: they do not invalidate CAH-033's response grammar and no first/last value is selected
  here. CAH-034 is the sole owner of pair-preserving decode and maps such input to
  `invalid_read_tool_input` before its exact-key gate, Pydantic validation, or dispatch.
- One optional `ProviderOpaqueContinuation` may appear only first. It contains one SDK-free,
  CAH-032-validated `payload` string whose strict UTF-8 encoding is at most 65,536 bytes. The provider
  adapter owns the payload's replay format; the core preserves the complete payload byte-for-byte and
  never parses or interprets it. CAH-032 owns construction, safe representation, ordered-history item
  counting, and canonical request projection. This collector only enforces first-position response
  grammar and keeps the value absent from protocol, transcripts, logs, and failure messages.
- At most one validated `ProviderUsageReported` may appear, after completed text or the call and
  before the legal `ProviderCompleted` or `ProviderFailed` terminal. Usage is non-authoritative
  evidence carried only by an accepted success outcome; the collector neither reports nor persists
  it. A duplicate, early, late, or out-of-range value invalidates the entire response.
- All assistant chunks and the candidate call remain private staging data through
  the legal terminal, iterator close, grammar reconciliation, and usage admission. The collector
  returns one immutable `AcceptedFinalText`, `AcceptedToolCall`, or normalized provider-failure
  outcome; it never yields a partly accepted result. A failure outcome contains no staged usage or
  continuation. No assistant event is emitted and no registry lookup, argument parsing, policy
  decision, or tool dispatch occurs inside collection.
- The existing per-turn UTF-8 output ceiling is checked while staging without publishing bytes.
  CAH-022's session output budget is reserved atomically by later orchestration only after an
  `AcceptedFinalText` exists. Rejected text consumes no visible output and cannot survive in runtime
  state, evidence, or diagnostics.
- The absolute provider-work deadline is still checked while awaiting each observation and during
  final admission. Cancellation or teardown discards the private stage, closes/reaps the provider
  operation, and returns no accepted outcome. A late observation cannot change the selected terminal.
- Provider cleanup remains mandatory. A cleanup failure cannot turn an invalid response into an
  accepted outcome or expose staged data; the existing safe cleanup-failure precedence remains
  authoritative.
- Strict-fake scripts compare complete CAH-032 requests and reproduce logical observation barriers.
  Tests use no live model, wall-clock sleep, SDK object, or network access.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- Split provider-specific event reconciliation into CAH-036 rather than importing SDK grammar here.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One collector returns exactly one immutable final-text, one-tool-call, or normalized-failure
   outcome only after the complete provider operation has been admitted.
2. Neither staged text nor a staged call causes protocol publication, dispatch, usage persistence,
   or another provider turn in this unit.
3. Exact final-text and exactly-one-call grammars accept optional first-position opaque continuation
   and optional post-content usage; an accepted call preserves its bounded raw arguments without
   parsing, including duplicate-member syntax; normalized provider failure may terminate every
   otherwise valid nonterminal prefix of either grammar.
4. Text completion reconciles exactly; mixed, duplicate, unsupported, premature EOF, post-terminal,
   invalid opaque, invalid usage, and provider failure after an already-invalid prefix select
   `provider_invalid_response` without leaks.
5. Provider failure discards the full valid staged prefix while preserving its exact bounded code,
   safe message, and retryability; cancellation, deadline, iterator-close, and cleanup races reap
   provider work and preserve one existing terminal winner.
6. The opaque continuation is provider-neutral, byte-bounded, replayable without interpretation,
   counted in request size, and structurally excluded from protocol, transcript, and diagnostics.
7. Existing text-only behavior is preserved semantically, except that accepted chunks are published
   only after complete-turn admission by later orchestration.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1-2 | Strict-fake success scripts assert the atomic returned value and zero writer, argument-parser, registry, usage-observer, transcript, and second-start calls. One accepted call carries same-value and conflicting duplicate `path` members byte-for-byte, proving CAH-033 neither rejects them as provider grammar nor chooses a winner. |
| 3 | Table tests cover both exact success grammars with/without opaque continuation and usage, then replace each remaining success suffix with `ProviderFailed` after the empty prefix, opaque-only prefix, one and multiple deltas, reconciled text completion, the call, and each post-content usage position. |
| 4 | Single-mutation scripts cover empty/mismatched text, mixed branches, duplicate call/usage/opaque, invalid order, early EOF, post-terminal data, controls, Unicode-byte bounds, unknown event classes, and an already-invalid prefix followed by `ProviderFailed`. |
| 5 | Failure tables preserve every bounded provider code, safe message, and retryability while distinctive text/call/opaque/usage sentinels are absent from the outcome and all side-effect spies. Logical barriers race failure, cancellation, deadline, iterator close, and cleanup failure after each staged observation. |
| 6 | Boundary tests exercise 65,535/65,536/65,537 bytes for the complete opaque replay payload, safe `repr`, canonical request-size accounting, and repository policy searches denying the value in protocol/transcript/log paths. |
| 7 | Existing final-text fake scenarios assert the same final outcome and failure codes while a spy proves no optimistic publication occurs. |

## Validation

- Use deterministic strict-fake observation scripts, injected clocks, and logical barriers; do not
  use timing sleeps or live provider calls.
- Assert exact atomic outcomes, observation consumption, cleanup, terminal selection, and absence of
  writer/registry/transcript side effects.
- Assert `ProviderFailed` at every legal prefix cut point preserves only the normalized bounded
  failure classification, while a failure after invalid grammar cannot override the fixed invalid
  response outcome.
- Run focused provider-model, staged-collector, provider-session, cancellation, and limit tests,
  followed by the canonical non-live repository gate.

## Documentation impact

Update provider-interface, agent-loop, safety, transcript/privacy, evaluation, glossary, backlog,
and story-index documentation. The concise lesson teaches staged admission as the boundary between
untrusted provider output and harness action. Do not create or revise a presentation.

## Exclusions

- Tool lookup, JSON parsing or duplicate-member detection, native dispatch, result construction, a
  second model turn, or a loop. CAH-034 owns duplicate-aware decoding after atomic call admission.
- OpenAI SDK event mapping, MCP clients/servers, remote or hosted tools, and provider continuation IDs.
- Protocol/TUI changes, transcript migration, usage persistence, repository writes, subprocesses,
  approvals, retries, parallelism, or content-level secret scanning.

## Definition of done

- Both accepted success grammars, every legal normalized-failure cut point, and every meaningful
  ordering/cardinality failure have deterministic tests.
- No staged value is externally observable before complete response admission, and cancellation or
  failure leaves no partial answer or actionable call.
- Provider-declared failure preserves the existing bounded `ProviderFailure` classification without
  retaining staged text, call, opaque continuation, or usage.
- Opaque continuation and usage bounds, request-size accounting, content-safe representations, and
  evidence exclusions have direct regression coverage.
- **Delivered production-code churn** records the measured result and is no more than 600 lines; any
  dispatch, iteration, or provider-specific behavior is split out.
- Public APIs and the concise Markdown lesson are verified against implementation with a compact
  staging-boundary diagram; presentations remain frozen.
- Focused checks and `./scripts/check` pass before the story is Done and published.

## Planned evidence

- Atomic final-text and tool-call collector outcomes from exact strict-fake scripts.
- Byte-exact admitted calls containing duplicate JSON argument members, with zero parser or dispatch
  work in this unit.
- A mutation matrix proving no partial publication or dispatch for rejected provider streams.
- A normalized-failure cut-point table proving bounded classification survives while the entire
  staged prefix disappears.
- Opaque-continuation boundary, replay-size, safe-representation, cancellation, and cleanup tests.

## Deferred work

- CAH-034 validates and dispatches one accepted call, then feeds one result into one follow-up turn.
- CAH-035 generalizes that teaching path into the bounded explicit agent loop.
- CAH-036 maps OpenAI Responses message, function-call, and complete canonical reasoning-item replay
  envelopes into this provider-neutral admission contract.
- MCP adapters, side-effecting tools, and visible tool-progress events remain later work.
