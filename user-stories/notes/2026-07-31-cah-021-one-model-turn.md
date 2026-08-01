# 2026-07-31 CAH-021 one provider-neutral model turn

## Outcome

CAH-021 connects the provider-neutral port to one harness-owned session turn. The implementation
constructs one exact request, starts and claims one operation, validates its stream grammar, admits
bounded text and optional usage evidence, and selects exactly one completion, failure, cancellation,
or teardown outcome before awaiting provider cleanup.

The runtime now has an injection seam for deterministic provider-backed tests and later composition,
but the launched `main()` path remains on `MockSessionRunner`. This unit makes no provider network
request and adds no provider SDK, credentials, model configuration, tool execution, retry, or second
turn.

## Locked decisions

- One accepted task becomes one `ProviderRequest` containing exactly one `user` message plus the
  ordered, already-resolved `RepositoryInstruction` tuple supplied at runtime composition. CAH-021
  does not discover, merge, or prioritize instruction files.
- A successful stream is one or more non-empty text deltas, one matching text-completed candidate,
  optional usage, and one provider-completed terminal in that order. Candidate completion is not a
  wire event until the full grammar is valid and loop-level cleanup has settled.
- Accepted assistant output has a fixed 8,192-byte cumulative UTF-8 ceiling. The delta that would
  cross the ceiling is rejected in full before wire publication; CAH-022 may configure a smaller
  limit but cannot enlarge this protocol-fit bound.
- Missing, duplicate, out-of-order, mismatched, or prematurely ended successful observations select
  the fixed `provider_invalid_response` failure. Rejected provider payload content is not copied into
  the diagnostic.
- A normalized `ProviderFailed` selects one `session.failed` outcome before the loop awaits
  `wait_closed()`. Partial accepted deltas stay visible, but a buffered text-completed candidate
  never becomes assistant completion inside the failed session.
- A tool request selects the fixed `tool_unavailable` failure, calls `cancel()`, and awaits cleanup.
  The loop does not parse the serialized arguments, look up a tool, execute work, or start another
  operation.
- Optional usage is local `ModelUsageObserved` evidence, bounded to non-negative IEEE-754-safe
  integers. It consumes no protocol sequence, enters neither lifecycle reducer, and is not billing
  or limit authority.
- Transcript writers now emit version 2 for every session. Replay accepts homogeneous version-1 and
  version-2 tapes, rejects mixed versions, validates the single version-2 usage window and session
  identity, and exposes usage through `TranscriptEvidence` rather than `SessionState`.
- One decision lock serializes lifecycle publication, reducer admission, lifecycle-observer work,
  usage-observer work, and terminal selection. An admitted transaction finishes before cancellation
  or teardown can win; a selected terminal suppresses later observations.
- Completion, provider failure, invalid response, tool rejection, user cancellation, and teardown
  all create or join one selected finalization task. Natural terminals use `wait_closed()`; paths
  that must stop active work use `cancel()`.
- Runtime shutdown, stdin EOF, and outer-task cancellation request teardown. Teardown-first cleans up
  without inventing `session.cancelled`; an already-selected user-visible outcome remains
  authoritative and finishes unchanged.
- A provider cleanup exception cannot replace the selected outcome. The loop emits at most one
  start-correlated runtime error with `code=provider_cleanup_failed`, message
  `Provider cleanup could not be confirmed.`, and `recoverable=true`; raw exception text is omitted.

## Implementation map

- `src/code_assist_harness/provider_session.py` owns request construction, stream consumption,
  grammar validation, bounded delta admission, the decision lock, outcome selection, provider
  cleanup, terminal publication, and runtime-local `ses_provider_N` allocation.
- `src/code_assist_harness/model_evidence.py` owns `ModelUsageObserved` and the shared maximum safe
  token count.
- `src/code_assist_harness/provider/models.py` applies that safe-integer bound to provider-reported
  usage before the loop can admit it.
- `src/code_assist_harness/runtime.py` selects `ProviderSessionRunner` only when a provider is
  injected, attaches lifecycle and usage transcript observers, closes completed transcript owners,
  and requests provider teardown on shutdown, EOF, and outer cancellation.
- `src/code_assist_harness/persistence/transcript.py` owns transcript version 2, the
  `model.usage_observed` record, versioned replay validation, the separate evidence projection, and
  usage-aware summaries.
- `tests/test_provider_session.py` covers the provider-session contract with the strict fake and a
  small controlled operation for early EOF, delayed cleanup, and non-conforming cleanup barriers.
- `tests/test_runtime.py` covers the injected runtime seam, exact instruction handoff, enabled versus
  disabled transcript wire parity, persisted usage, EOF/shutdown teardown, and outer cancellation.
- `tests/test_transcript.py` covers version-1 compatibility, version-2 writing, mixed-version
  rejection, usage order and identity, duplicate handling, append rollback, replay evidence, and
  summary output.

## Concurrency and failure discoveries

Provider terminal selection and protocol terminal publication are separate phases. Selecting the
outcome before cleanup prevents cancellation or teardown from rewriting it, while delaying wire
publication until cleanup settles prevents a session task from returning with provider work still
active. A cleanup-contract violation is therefore reported beside, not instead of, the selected
session outcome.

Shielding only the ordered writer is insufficient. Cancellation can arrive after bytes commit but
before the reducer or transcript observer sees the event. `ProviderSession` shields the complete
wire-to-reducer-to-observer transaction under the decision lock so all trusted views either finish
that admission or all lose to the terminal selection.

Pending `anext()` is operation-owned work. Teardown and outer cancellation leave it alive long
enough for the operation's cancellation barrier to stop it, then join it before finalization. When a
non-conforming cleanup method raises, the loop reaps its separate pending iterator task where
possible and reports only the fixed runtime diagnostic; the port offers no broader force-close API
and the code does not claim remote resources were released.

Usage is deliberately separate from lifecycle. This preserves protocol-v1 and both lifecycle
reducers while still making model-cost evidence replayable. The evidence transaction uses the same
decision lock so a usage-first persistence attempt settles before cancellation, while a previously
selected terminal admits no later usage.

## Validation evidence

- Focused CAH-021 validation passed with 149 tests:
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest -q tests/test_provider_session.py tests/test_transcript.py tests/test_runtime.py tests/provider/test_provider_models.py`.
- The 47 provider-session tests cover exact request construction, one operation, normal completion,
  logical delay, invalid ordering, early EOF, the exact and crossing UTF-8 ceiling, provider failure
  before and after output, tool rejection, safe usage bounds, general-awaitable and malformed
  iterator boundaries, user cancellation before and between deltas, blocked sink and observer
  transactions, teardown, outer cancellation, completion races, and cleanup-contract failures.
- Runtime and transcript tests prove provider-enabled and transcript-disabled sessions emit the same
  protocol tape, usage stays transcript-only, replay remains compatible with version 1, and
  teardown-first leaves an incomplete replayable prefix without a summary.
- The 10-slide visual companion
  [`docs/lessons/assets/cah-021-one-model-turn.pptx`](../../docs/lessons/assets/cah-021-one-model-turn.pptx)
  was rendered slide by slide and inspected at full resolution. Every slide contains a `[Sources]`
  speaker-notes block, and the presentation overflow test passed with no overflow detected.
- The canonical non-live gate passed with
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check`: 336 Python tests, 30 Python protocol-
  fixture tests, 24 repository-policy tests, 208 TUI tests, 29 TypeScript protocol-fixture tests,
  and 4 real Node/Python boundary tests passed; Python lint/format and TUI typecheck/lint also passed.

## Deferred work

- CAH-022 adds model-turn admission, provider-work deadlines, configurable output and tool-call
  limits, deadline reservation, expiry races, and fixed cleanup grace. It is the next unit.
- CAH-023 adds the OpenAI Responses adapter and validated provider/model configuration. Until then,
  `main()` truthfully launches the deterministic `MockSession` path.
- Instruction discovery and precedence, context selection, network access, credentials, tool
  execution, policy, approvals, retries, multiple operations, and live evaluation remain later work.
