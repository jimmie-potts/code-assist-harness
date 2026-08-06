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

CAH-033 owns only provider-neutral admission of one supervised model-turn observation sequence. It
returns one immutable accepted outcome or one bounded failure while the existing session owner retains
operation lifecycle. It does not dispatch a tool,
start another model turn, publish protocol events, or persist transcript evidence.

## Scope

- Replace optimistic text publication with a provider-neutral staged turn admission state machine
  driven by the existing session-owned operation supervisor.
- Add immutable accepted final-text and one-tool-call outcomes, and return the existing immutable
  normalized `ProviderFailure` value for a provider-declared failure.
- Admit one optional CAH-032 `ProviderOpaqueContinuation` and at most one usage value.
- Validate the entire observation grammar through its legal `ProviderCompleted` or `ProviderFailed`
  terminal before exposing an outcome.
- Keep cancellation, the absolute provider-work deadline, and provider resource cleanup under the
  existing session owner while making publication a later orchestration action.
- Extend the strict fake with exact successful and adversarial tool-aware turn scripts.

## Locked contract

- `provider/turn_admission.py` owns the synchronous, I/O-free `ToolAwareTurnAdmission` state machine.
  Its exact methods are `observe(event: ProviderStreamEvent) -> None` and
  `finish() -> AcceptedFinalText | AcceptedToolCall | ProviderFailure |
  AssistantOutputOverflow`. `observe` stages one already validated provider-domain event;
  `finish` is called exactly once after EOF. Neither method claims, awaits, cancels, closes, or reaps
  an operation.
- CAH-034's guarded start transaction synchronously claims and validates the operation's single-use
  iterator before committing any turn state. It passes that already-claimed iterator to
  `ProviderSession._collect_admitted_turn(operation: ProviderOperation, events:
  AsyncIterator[ProviderStreamEvent]) -> AcceptedFinalText | AcceptedToolCall | ProviderFailure |
  AssistantOutputOverflow | None`. The collector never calls `operation.events()` itself. It awaits
  the supplied iterator under the existing absolute deadline, cancellation/teardown selection, and
  decision locks, and feeds every observation to one fresh admission state machine.
- Seeing `ProviderCompleted` or `ProviderFailed` does not stop iteration. The driver continues through
  EOF under the same deadline; the first post-terminal observation invalidates the grammar, and EOF
  before a terminal is also invalid. Exhausting the pull-driven iterator before `finish()` both makes
  post-terminal rejection observable and prevents a natural-close barrier from waiting on unread
  events. Iterator `StopAsyncIteration` is the only successful end signal; iterator cancellation or
  exception returns the exact fixed invalid-response `ProviderFailure` after local pending-read work
  is reaped.
- The collector returns `None` only after cancellation, teardown, deadline, or another authoritative
  session terminal has already won and the current operation generation's local read task is reaped.
  Outer task cancellation propagates after reaping rather than returning `None`. An admitted
  provider-declared failure remains a returned `ProviderFailure`; CAH-034 maps it only after this
  method returns, so the return union is meaningful and no terminal is preselected inside pure
  response admission. Ordinary cleanup remains owned by the existing session finalizer after that
  candidate is selected.
- The accepted carriers are frozen and have no extra fields:
  `AcceptedFinalText(chunks: tuple[str, ...], usage: ProviderUsageReported | None)` and
  `AcceptedToolCall(call: ProviderToolCall, continuation: ProviderOpaqueContinuation | None,
  usage: ProviderUsageReported | None)`.
- `provider/models.py` owns the dependency-safe shared constant
  `MAX_PROVIDER_TEXT_BYTES = 8192`. Provider models, admission, the session, the strict fake, and later
  adapters import that identity rather than duplicating a literal or importing session code. The
  existing session-level `MAX_PROVIDER_TURN_OUTPUT_BYTES` name may remain only as a compatibility alias
  to this value while callers migrate; it is not the configurable 4,096-byte M2 session budget.
- CAH-033 adds frozen, content-free provider observation
  `ProviderTextOverflowObserved(required_bytes=8193)` with exact kind `text.overflow`; no other value
  is constructible. It belongs to `ProviderStreamEvent` and tells core admission that the first
  provider-specific producer saturated assistant text without forwarding the oversized content.
  `AssistantOutputOverflow(required_bytes: int)` remains the separate frozen internal outcome with
  the same sole legal value (`MAX_PROVIDER_TEXT_BYTES + 1`). On the marker, admission clears and
  retains no staged text, latches the outcome, and continues only grammar/cardinality tracking through
  terminal and EOF. The session owner passes the outcome once to the existing
  mutable `LoopLimitTracker` reservation path, which selects exact
  `assistant_output_limit_exceeded`; it is never relabeled `provider_invalid_response` and no partial
  output byte is charged.
- Before an explicit marker, core still incrementally charges deltas with a saturating 8,193-byte
  scan as defense against a defective provider port. It retains at most 8,192 bytes; if deltas cross
  that ceiling, it clears them and requires the later marker rather than accepting an oversized
  `ProviderTextCompleted`. A missing/misplaced marker is invalid response, so first-producer bounding
  remains enforceable rather than advisory.
- The normal neutral carriers are independently bounded before admission:
  `ProviderTextDelta.text` and `ProviderTextCompleted.text` must be exact built-in `str`, pass an O(1)
  8,192-character pre-gate, then pass terminal-safe Unicode-scalar and strict-UTF-8 checks with an
  inclusive 8,192-byte cap. Subclasses and over-bound values fail before hook-capable scanning or
  encoding; provider adapters and strict fakes represent over-bound text only with the fixed overflow
  observation. This prevents a future producer from hiding unbounded work inside a neutral event
  constructor before the state machine can saturate aggregate deltas.
- The overflow branch uses `text.delta* -> text.overflow`; it never contains neutral
  `text.completed`. Structural grammar has higher precedence: a mixed/duplicate call, a text event
  after the marker, wrong order, or post-terminal observation returns exact invalid response. A legal
  `ProviderFailed` at any allowed prefix retains its existing normalized failure and discards the
  overflow stage. Only an otherwise valid overflow marker through `ProviderCompleted` and EOF returns
  `AssistantOutputOverflow`; therefore overflow plus mixed call/post-terminal is invalid response,
  while overflow plus a legal provider failure is that provider failure. Provider-specific snapshot
  equality after saturation is deliberately waived by the producer because discarded oversized text
  cannot be compared without unbounded work; CAH-033 receives no discarded content to compare.
- The producer exposes opaque state only as CAH-032's
  `ProviderOpaqueContinuationObserved(continuation=...)` stream event with kind
  `opaque_continuation.observed`. The collector unwraps it into private staged state. An accepted tool
  call retains it for ordered replay; an accepted final text validates then discards it because that
  outcome ends the M2 loop and no later request can consume it. Bare continuations are not stream
  events, and neither accepted carrier contains an SDK object or raw observation.

- The admission state machine consumes one already-supervised event sequence and returns atomically. Its
  successful grammar is exactly one of:
  `opaque? -> text.delta+ -> text.completed -> usage? -> response.completed`,
  `opaque? -> text.delta* -> text.overflow -> usage? -> response.completed`, or
  `opaque? -> tool.call_requested -> usage? -> response.completed`.
  A normalized `response.failed` may be the first observation or may replace the remaining success
  suffix after any otherwise valid nonterminal prefix of either grammar. This preserves CAH-021's
  provider-neutral behavior and CAH-023's adapter behavior for failures after partial output.
  `response.failed` cannot launder an already-invalid prefix and is invalid after
  `response.completed`. End-of-stream before a required terminal observation is invalid.
- The legal failure cut points are exactly: before any staged observation; after the optional opaque
  continuation; after any valid text delta; after reconciled `text.completed`; after
  `text.overflow`; after post-text/overflow usage; after the one tool call; or after post-call usage.
  Each non-empty cut point may also include
  its legal first-position opaque continuation. No other prefix is admitted.
- On `response.failed`, the collector discards the complete staged prefix—including text, call,
  opaque continuation, and usage—and returns only the existing bounded `ProviderFailure` value. Its
  exact harness-owned `code`, safe `message`, and `retryable` classification are preserved; staged
  data and raw provider values are absent from the outcome, diagnostics, transcript, and protocol.
- On the normal text branch, `text.completed` must equal the byte-for-byte concatenation of the
  non-empty, terminal-safe text deltas. The accepted final text is non-empty. The overflow branch has
  only the content-free marker in place of completion. A tool-call turn contains no text observation and
  exactly one bounded `ProviderToolCall`; mixed text/call, duplicate calls, post-terminal values, and
  unsupported observations select exact
  `ProviderFailure(code="invalid_response", message="The provider returned an invalid response.",
  retryable=False)`. Existing session mapping emits
  `session.failed.code="provider_invalid_response"` with that same fixed message. A provider-declared
  `ProviderFailed` retains its normalized code/message/retryability and is not relabeled as a grammar
  failure.
- The accepted call preserves CAH-032's bounded `arguments_json` byte-for-byte and does not parse it.
  Repeated JSON member names inside that one argument string are distinct from duplicate call
  observations: they do not invalidate CAH-033's response grammar and no first/last value is selected
  here. CAH-039 is the sole owner of pair-preserving decode and maps such input to
  `invalid_read_tool_input` before its exact-key gate, Pydantic validation, or dispatch.
- One optional `ProviderOpaqueContinuation` may appear only first. It contains one SDK-free,
  CAH-032-validated `payload` string whose strict UTF-8 encoding is at most 65,536 bytes. The provider
  adapter owns the payload's replay format; the core preserves the complete payload byte-for-byte and
  never parses or interprets it. CAH-032 owns construction, safe representation, ordered-history item
  counting, and canonical request projection. This collector only enforces first-position response
  grammar and keeps the value absent from protocol, transcripts, logs, and failure messages.
- At most one validated `ProviderUsageReported` may appear, after completed text, the overflow marker,
  or the call and
  before the legal `ProviderCompleted` or `ProviderFailed` terminal. Usage is non-authoritative
  evidence carried only by an accepted success outcome; the collector neither reports nor persists
  it. A duplicate, early, or late value invalidates the entire response. Field bounds are enforced by
  the CAH-020/032 value constructor before this collector; an out-of-range instance is not a reachable
  collector input.
- All assistant chunks and the candidate call remain private staging data through
  the legal terminal, iterator close, grammar reconciliation, and usage admission. The collector
  returns one immutable `AcceptedFinalText`, `AcceptedToolCall`, or normalized provider-failure
  outcome; it never yields a partly accepted result. A failure outcome contains no staged usage or
  continuation. No assistant event is emitted and no registry lookup, argument parsing, policy
  decision, or tool dispatch occurs inside collection.
- The 8,192-byte protocol-fit ceiling is checked at the first producer and defensively while staging,
  without publishing bytes or retaining byte 8,193. Text at or below that ceiling remains an
  `AcceptedFinalText`; CAH-022's
  configured cumulative session budget (4,096 in the M2 profiles) is reserved atomically by later
  orchestration against the complete accepted text. A prior used-byte count can therefore reject an
  otherwise valid turn without partial charge. Rejected text consumes no visible output and cannot
  survive in runtime state, evidence, or diagnostics.
- `ProviderSession._collect_admitted_turn` checks the absolute provider-work deadline while awaiting
  each observation and immediately before `finish`. Cancellation or teardown discards the private
  state, closes/reaps the provider operation, and returns no accepted outcome. A late observation
  cannot change the selected terminal.
- Provider cleanup remains mandatory under the existing session owner. Iterator cancellation or
  exception maps to exact `provider_invalid_response`; it is not a cleanup classification. After the
  caller selects the returned success/failure/limit candidate, the one-owner finalizer first uses
  `wait_closed()` for natural EOF or `cancel()` for cancellation, with the existing five-second
  supervised grace and `force_cancel_cleanup()` only after the ordinary barrier fails or expires.
  Cleanup failure emits the existing recoverable `runtime.error` diagnostic
  `provider_cleanup_failed` and never replaces the already selected terminal. Cleanup cannot turn
  invalid grammar into an accepted outcome or expose staged data.
- Strict-fake scripts compare complete CAH-032 requests and reproduce logical observation barriers.
  They emit the exact continuation, overflow, and call wrappers used by `ProviderStreamEvent`; tests use
  no bare continuation, live model, wall-clock sleep, SDK object, or network access.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: provider observation producer -> private staged
  response candidate -> admitted text/call outcome -> CAH-039/034 consumer spies.
- Split provider-specific event reconciliation into CAH-036 rather than importing SDK grammar here.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One fresh pure admission state machine returns exactly one immutable final-text, one-tool-call, or
   normalized-failure outcome only after the session-owned supervised driver has settled the complete
   provider operation.
2. Neither staged text nor a staged call causes protocol publication, dispatch, usage persistence,
   or another provider turn in this unit.
3. Exact final-text, text-overflow, and exactly-one-call grammars accept optional first-position
   opaque continuation and optional post-content usage; an accepted call preserves its bounded raw
   arguments without parsing, including duplicate-member syntax; normalized provider failure may
   terminate every otherwise valid nonterminal prefix of any grammar.
4. Normal text completion reconciles exactly; the content-free overflow marker replaces completion
   only on its branch. Mixed, duplicate, unsupported, premature EOF, post-terminal,
   misplaced opaque, misplaced/duplicate usage, and provider failure after an already-invalid prefix
   return exact `ProviderFailure(code="invalid_response", message="The provider returned an invalid
   response.", retryable=False)` and emit `provider_invalid_response` without leaks.
5. Provider failure discards the full valid staged prefix while preserving its exact bounded code,
   safe message, and retryability; terminal observations are consumed through EOF; cancellation,
   deadline, iterator error, and cleanup races reap local work and preserve one existing terminal
   winner.
6. The opaque continuation is provider-neutral, byte-bounded, replayable without interpretation,
   counted in request size, enters the stream only through its exact wrapper, and is structurally
   excluded from protocol, transcript, and diagnostics.
7. Existing text-only behavior is preserved semantically, except that accepted chunks are published
   only after complete-turn admission by later orchestration.
8. Text above 8,192 bytes is saturated by the first provider producer into the exact bounded overflow
   observation, which core converts to one sentinel; the existing tracker selects exact
   `assistant_output_limit_exceeded` with zero publication and zero partial byte charge. Core's
   defensive delta bound cannot be bypassed by a producer that omits or misplaces the marker.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1-2 | Signature/field tests lock `ToolAwareTurnAdmission.observe`/`finish`, the exact collector signature with an already-claimed async iterator, its four-outcome-plus-`None` return, both frozen success carriers, the exact 8,193-only `ProviderTextOverflowObserved` union member/kind, and the separate overflow outcome. Neutral text constructor tests require exact built-in strings, O(1) 8,192-character pre-gates, terminal-safe scalars, and 8,192-byte UTF-8 caps before admission; huge/subclass spies prove no unbounded hooks. Strict-fake success scripts assert the atomic returned value only after terminal then EOF and zero writer, argument-parser, registry, usage-observer, transcript, and second-start calls. One accepted call carries same-value and conflicting duplicate `path` members byte-for-byte, proving CAH-033 neither rejects them as provider grammar nor chooses a winner. |
| 3 | Table tests cover all three exact success grammars with/without opaque continuation and usage, then replace each remaining success suffix with `ProviderFailed` after the empty prefix, opaque-only prefix, one and multiple deltas, reconciled text completion, the overflow marker, the call, and each post-content usage position. |
| 4 | Single-mutation scripts cover empty/mismatched normal text, mixed branches, duplicate/misplaced overflow/call/usage/opaque, delta/completion/call after overflow, aggregate deltas crossing without a marker, invalid order, early EOF, post-completed and post-failed observations, text controls, unknown event classes, and an already-invalid prefix followed by `ProviderFailed`. Every grammar failure or iterator exception produces exact internal `ProviderFailure(code="invalid_response", message="The provider returned an invalid response.", retryable=False)` and exact emitted `provider_invalid_response`; a legal provider-declared failure retains its own normalized fields only after EOF. Overflow precedence cases prove mixed call/post-terminal remains invalid response, legal `ProviderFailed` retains its normalized failure, and an otherwise valid marker branch returns the bounded outcome without content. Opaque/usage/overflow values are valid producer outputs; this unit mutates only their reachable ordering/cardinality. |
| 5 | Failure tables preserve every bounded provider code, safe message, and retryability while distinctive text/call/opaque/usage sentinels are absent from the outcome and all side-effect spies. Logical barriers race failure, cancellation, deadline, iterator error, natural close, and cleanup failure after each staged observation through the session-owned async driver; `None` occurs only after an authoritative lifecycle terminal and current-generation read-task reaping, outer task cancellation propagates after cleanup, iterator error is invalid response, and cleanup failure is diagnostic-only after the returned candidate is selected. |
| 6 | CAH-032 dependency tests exercise 65,535/65,536/65,537 bytes for opaque construction, safe `repr`, exact stream-wrapper membership, and canonical request-size accounting. Collector tests use only admitted wrapped 65,535/65,536-byte endpoints, reject bare values, vary first-position/cardinality, retain opaque state only on accepted calls, and keep admitted payloads out of protocol/transcript/log paths. |
| 7 | Existing final-text fake scenarios assert the same final outcome and failure codes while a spy proves no optimistic publication occurs. |
| 8 | Stage 4,095/4,096/4,097-byte text against the M2 profile and 8,191/8,192 bytes plus the exact 8,193 overflow marker against the compatibility ceiling, including prior used bytes. A defective direct-neutral producer also crosses the aggregate delta ceiling with and without the required marker. The tracker is called once with the complete size or 8,193 sentinel; rejection selects `assistant_output_limit_exceeded`, publishes no chunk, persists no usage, and leaves the prior byte count unchanged. Deleting first-producer marker handling, defensive incremental ceiling logic, or whole-value reservation fails a mutation test. |

## Validation

- Use deterministic strict-fake observation scripts, pure admission sequences, injected clocks, and
  logical barriers around the session-owned driver; do not use timing sleeps or live provider calls.
- Assert exact atomic outcomes, observation consumption, cleanup, terminal selection, and absence of
  writer/registry/transcript side effects.
- Assert terminal-then-EOF success, EOF-before-terminal failure, both terminal-plus-extra-event
  failures, and iterator exception -> invalid-response separately from diagnostic-only cleanup failure.
- Assert `ProviderFailed` at every legal prefix cut point preserves only the normalized bounded
  failure classification, while a failure after invalid grammar cannot override the fixed invalid
  response outcome.
- Run focused provider-model, turn-admission, provider-session, cancellation, and limit tests,
  followed by the canonical non-live repository gate.

## Documentation impact

Update provider-interface, agent-loop, safety, transcript/privacy, evaluation, glossary, backlog,
and story-index documentation. The concise lesson teaches staged admission as the boundary between
untrusted provider output and harness action. Do not create or revise a presentation.

## Exclusions

- Tool lookup, JSON parsing or duplicate-member detection, native dispatch, result construction, a
  second model turn, or a loop. CAH-039 owns duplicate-aware admission before CAH-034 dispatches a
  prepared invocation.
- OpenAI SDK event mapping, MCP clients/servers, remote or hosted tools, and provider continuation IDs.
- Protocol/TUI changes, transcript migration, usage persistence, repository writes, subprocesses,
  approvals, retries, parallelism, or content-level secret scanning.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Preserve the provider operation, call ID, exact raw argument string, opaque continuation, and aggregate usage as distinct staged values. Filesystem identity is N/A because this unit performs no tool lookup or I/O. |
| End-to-end contract | Trace provider operation -> bounded observations -> private staged candidate -> one admitted text or tool-call outcome -> CAH-039 preparation/CAH-034 consumption, with publication and dispatch spies at the boundary. |
| Failure and atomicity | Provider failure, invalid grammar, EOF, cancellation, deadline, and limit exhaustion discard every candidate; assistant publication, actionable-call publication, lookup, and dispatch each execute zero times. |
| Reachable boundaries | Construct carrier limits through CAH-032 and drive legal and illegal observation sequences through the real collector/session seam; keep malformed name and over-bound argument construction in CAH-032 tests rather than inventing unreachable CAH-033 states. |
| Closed grammar and cardinality | Lock the two complete success grammars, optional continuation/usage positions, one-call maximum, failure cut points, ordering, and duplicate-observation policy before any outcome is admitted. |
| Artifact parity | Story, lesson, diagram, pseudocode, provider models, session composition, and test matrix use the same observe -> stage -> complete-grammar validation -> admit stage order. |
| Independent lenses | Provider/protocol review fixed terminal-to-EOF consumption and the closed outcome union; atomicity review added the bounded overflow sentinel and zero-publication/zero-dispatch staging; limit/scheduler/handoff review separated iterator failure from cleanup diagnostics and locked the already-claimed iterator contract consumed by CAH-034. |

## Definition of done

- Both accepted success grammars, every legal normalized-failure cut point, and every meaningful
  ordering/cardinality failure have deterministic tests.
- No staged value is externally observable before complete response admission, and cancellation or
  failure leaves no partial answer or actionable call.
- Provider-declared failure preserves the existing bounded `ProviderFailure` classification without
  retaining staged text, call, opaque continuation, or usage.
- Opaque continuation and usage producer bounds, request-size accounting, content-safe
  representations, and evidence exclusions have direct dependency regression coverage; this unit
  directly covers only reachable placement/cardinality.
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

- CAH-039 validates one accepted call; CAH-034 dispatches the prepared invocation and feeds one result
  into one follow-up turn.
- CAH-035 generalizes that teaching path into the bounded explicit agent loop.
- CAH-036 maps OpenAI Responses message, function-call, and complete canonical reasoning-item replay
  envelopes into this provider-neutral admission contract.
- MCP adapters, side-effecting tools, and visible tool-progress events remain later work.
