# 2026-07-31 CAH-022 hard loop limits

## Outcome

CAH-022 wraps every provider-backed session in four harness-owned budgets: model-turn admission,
provider-work time, accepted assistant UTF-8 bytes, and observed tool calls. The provider-neutral
loop now owns the full safety path from pre-admission accounting through deadline races, provider
cleanup, one terminal outcome, and replayable evidence.

The launched `main()` path still uses `MockSessionRunner`. This unit adds no SDK, live provider,
credential, network request, tool execution, retry, or second model turn; CAH-023 remains the first
network-adapter unit.

## Locked decisions

- `LoopLimits` is immutable and exposes exactly four strict integer values. Defaults are one model
  turn, 120 seconds of provider work, 4,096 accepted output bytes, and one observed tool call;
  configured maxima are 16, 3,600, 8,192, and 64 respectively. Booleans, non-integers, zero,
  negative, and over-maximum values are rejected rather than coerced or clamped.
- The runner reuses immutable configuration but allocates a fresh `LoopLimitTracker` for every
  provider-backed session. Counters never cross session IDs. Seeded tracker state is a deterministic
  test seam and pre-exhausted trackers are rejected at session construction.
- The absolute provider-work deadline is captured when the session object is allocated, before
  transcript setup and provider admission. The clock and waiter are an injected pair, and invalid or
  non-finite clock values do not become false deadline evidence.
- Model turns are charged before synchronous lazy `Provider.start()`. Assistant deltas reserve their
  complete UTF-8 size before publication. Tool requests are counted before arguments are inspected
  or CAH-021's unavailable-tool result is selected.
- The watcher is independent of the event-publication lock. At an exact event/deadline tie the
  deadline wins and the ready event is reaped. A transaction admitted before expiry completes its
  ordered, non-interleaved wire/reducer/transcript-observer attempt while watcher-driven provider
  cancellation may begin; no rollback or local-sink latency bound is claimed.
- Provider cleanup has one loop-owned task. The deadline watcher may create it and the finalizer
  joins it. Cleanup completion wins an exact cleanup/grace tie; otherwise the five-second injected
  grace cancels and reaps the cancellation-responsive local barrier. The required provider
  `force_cancel_cleanup()` hook then cancels and awaits every provider-owned local task without
  shielding. Failure still leaves remote cleanup unconfirmed and emits only the stable payload-free
  diagnostic.
- Limit failures, provider completion/failure, user cancellation, and teardown retain CAH-021's
  single terminal-selection and finalization ownership. The four stable limit codes and bounded
  messages never include configured values or provider content.
- New transcripts use version 3 and provider-backed terminal preparation records at most one
  transcript-only `loop.limits_observed` record immediately before the terminal. Replay accepts
  versions 1, 2, and 3, validates record placement and counter invariants, and cross-checks exhaustion
  against the exact adjacent failure code. Version 3 also forbids a reserved limit-failure code
  without the record. The limit record may remain the final item of an incomplete replayable prefix.
  Mock version-3 sessions may omit it.

## Architecture position

- `src/code_assist_harness/loop_limits.py` owns configuration, first-exhaustion accounting, and the
  immutable session evidence snapshot.
- `src/code_assist_harness/provider_session.py` owns budget charge points, absolute-deadline
  arbitration, publication ordering, the shared provider-cleanup task, and terminal selection.
- `src/code_assist_harness/runtime.py` gives sessions fresh trackers and connects their evidence
  observer to persistence.
- `src/code_assist_harness/persistence/transcript.py` owns version-3 write, replay, validation, and
  summary projection for `loop.limits_observed`.
- The Ink TUI continues to render validated protocol events. No limit-policy decision or transcript
  evidence type crosses into the TUI reducer, and provider SDK types remain outside core APIs.

## Failure and concurrency discoveries

Provider start and iterator construction are synchronous but can still cross the captured deadline.
The admission guard therefore checks both before and after those calls. A provider exception at or
after expiry becomes the deadline result rather than a misleading invalid-response classification.

A silent provider requires an independent watcher; racing only the next stream event cannot wake.
That watcher must be reaped on every path, including failed `session.started` publication and
preselected teardown, or a completed session can leave local work behind.

Deadline cancellation and normal finalization must never call `operation.cancel()` concurrently.
Both paths obtain the same shared cleanup task. Cleanup uses its own grace because provider work has
already exceeded or completed its budget; the grace is not a fifth configurable work allowance. A
later contract correction added authoritative force-reap after grace expiry so the session cannot
return while a shielded adapter cleanup owner remains active locally.

Tool observations differ from admitted-work counters. Model-turn and output counts never exceed
their maxima. The rejecting tool request is itself evidence, so `tool_calls_observed` is exactly
maximum plus one only when `exhausted_limit` is `tool_calls`.

## Documentation and learning evidence

The written lesson was reconciled to shipped code and kept focused on system ownership, agent-loop
admission, deadline races, cleanup, and evidence flow. Its architecture diagram locates CAH-022 in
`ProviderSession` between the runtime, provider port, TUI, and transcript boundaries.

The 9-slide visual companion
[`docs/lessons/assets/cah-022-loop-limits.pptx`](../../docs/lessons/assets/cah-022-loop-limits.pptx)
includes the same architecture position and the distinct budget, race, cleanup, and evidence views.
It was rendered slide by slide; every rendered image was inspected, every slide contains a
repository-backed `[Sources]` speaker-notes block, and the presentation overflow test passed with
`No overflow detected.`

## Validation evidence

- Focused loop/session/runtime/transcript validation passed with 257 tests:
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_loop_limits.py tests/test_provider_session.py tests/test_runtime.py tests/test_transcript.py`.
- The 72 provider-session tests include pre-admission expiry, silent provider, exact event/deadline
  tie, blocked admitted sink, provider start crossing expiry, each configurable budget, user and
  completion races, cleanup exception, cleanup grace, and watcher-reaping regressions.
- Loop-limit tests cover every default, maximum, invalid type/range, first-exhaustion rule, seeded
  boundary, no-partial-output reservation, and rejecting tool observation.
- Runtime and transcript tests cover fresh per-session counters, allocation-time expiry, version-3
  writing and replay, version-1/version-2 compatibility, invalid evidence mutations, append rollback,
  replayable prefixes, and summary projection.
- The canonical non-live gate passed with
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check`: 463 Python tests, 30 Python protocol-
  fixture tests, 24 repository-policy tests, 208 TUI tests, 29 TypeScript protocol-fixture tests,
  and 4 real Node/Python boundary tests passed; Python lint/format and TUI typecheck/lint also passed.

## Deferred work

- CAH-023 adds the OpenAI Responses adapter and validated provider/model configuration. It must use
  this provider-neutral limits boundary rather than reimplement safety inside the adapter.
- Provider credentials, instruction discovery, context selection, tool execution, policy,
  approvals, retries, multiple turns, distributed quotas, local-sink timeouts, and process-level
  containment remain later work.
