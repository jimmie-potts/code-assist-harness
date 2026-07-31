# 2026-07-30 CAH-020 provider interface and fake provider

## Outcome

CAH-020 introduces the first model boundary owned by the harness: immutable provider-neutral request
and stream values, an async operation port with explicit cleanup, and a programmable fake that
proves request order, stream order, failure normalization, and cancellation without credentials or
network access.

The implemented package is not connected to the current `MockSession` runtime. CAH-021 follows this
unit and becomes dependency-ready after CAH-020's required visual lesson is generated and validated.

## Locked decisions

- `ProviderRequest` contains an ordered, non-empty tuple of `ProviderMessage` values and an ordered
  tuple of caller-supplied `RepositoryInstruction` values. CAH-020 does not discover instructions,
  select context, choose a provider model, or accept provider-specific options.
- The stream union is closed over six harness-owned observations: `ProviderTextDelta`,
  `ProviderTextCompleted`, `ProviderToolCallRequested`, `ProviderUsageReported`,
  `ProviderCompleted`, and `ProviderFailed`.
- Tool arguments remain serialized text at this boundary, including malformed JSON. Parsing,
  validation, tool lookup, policy, approval, and execution remain agent-loop responsibilities.
- A `ProviderOperation` has exactly one event consumer. Normal completion or failure appears as the
  final stream event; cancellation instead closes iteration because session cancellation intent is
  already owned above the provider boundary.
- Awaiting `cancel()` is the cleanup barrier. It returns `cancelled` only when it closes active work
  and `already_closed` after normal completion, failure, or an earlier cancellation. Once it
  returns, no later event may be emitted.
- `ProviderFailure` carries only a stable code, a bounded single-line safe message, and a retryable
  observation. It has no raw response, exception, header, request, environment, or credential
  field, and `retryable` does not authorize the loop to retry.
- The fake accepts ordered `FakeProviderExchange` values. Each exchange matches one exact request
  and executes explicit `FakeProviderEmit`, `FakeProviderDelay`, or
  `FakeProviderWaitForCancellation` steps.
- `FakeProviderDelay` is a named logical gate controlled by the test, not a wall-clock sleep.
  Cancellation checkpoints consume and suppress their scripted suffix when cancellation wins.
- A non-cancellation exchange ends in exactly one `ProviderCompleted` or `ProviderFailed` event.
  The fake rejects a terminal event before a cancellation checkpoint and control steps after it.
- Request-mismatch diagnostics report bounded field paths only. Conversation text, repository
  instructions, tool arguments, failure data, and credentials never enter an assertion message.
- `FakeProvider.assert_complete()` is part of the test contract. It detects omitted requests,
  active streams, consumer abandonment, and unconsumed script steps instead of letting a permissive
  stub hide loop drift.

## Implementation map

- `src/code_assist_harness/provider/models.py` owns the request and stream value types plus semantic
  validation.
- `src/code_assist_harness/provider/port.py` owns the structural `Provider` and
  `ProviderOperation` protocols and cancellation result.
- `src/code_assist_harness/provider/fake.py` owns the strict script, logical checkpoints,
  single-consumer operation, cancellation behavior, and content-safe mismatch diagnostics.
- `src/code_assist_harness/provider/__init__.py` is the intentional public package surface.
- `tests/provider/test_provider_models.py` covers value semantics, immutable ordering, every stream variant,
  malformed tool arguments, usage bounds, and normalized failures.
- `tests/provider/test_fake.py` covers ordered success, logical delays, terminal failure, mismatch
  privacy, extra and omitted requests, early consumer exit, cancellation at both required points,
  idempotent cancellation, operation ownership, multiple exchanges, and invalid scripts.
- `tests/provider/test_port_imports.py` proves structural protocol compatibility and importability
  without vendor or orchestration packages.
- `tests/test_transcript.py` models the future boundary handoff and proves raw adapter detail is
  absent when a normalized provider failure becomes a persisted session failure.

## Security and failure discoveries

Exact fake-request comparison is useful for catching orchestration drift, but echoing the compared
values would turn an assertion into a secret sink. The fake therefore computes only semantic field
paths and bounds the diagnostic to eight paths plus a remaining-count suffix.

Cancellation requires two separate ideas: a request to stop and an awaitable cleanup barrier.
Closing the iterator without awaiting provider cleanup could allow a late SDK callback or resource
release to race with the next step. The provider operation contract makes the barrier explicit even
though the fake has no network resources.

Deterministic asynchronous tests do not need short sleeps. Named logical checkpoints let a test
prove “before output” and “between deltas” directly, avoiding scheduler-sensitive timing. Consumer
task cancellation remains distinguishable from a scripted cancellation checkpoint: it closes the
operation but leaves unfinished script evidence for `assert_complete()`.

## Lesson evidence

The implementation-companion
[written lesson](../../docs/lessons/cah-020-provider-interface-and-fake.md) explains the
implemented port, strict fake, cancellation cleanup, safe mismatch behavior, production comparison,
and exact implementation excerpts.

The visual companion is pending generation and validation at
`docs/lessons/assets/cah-020-provider-interface-and-fake.pptx`. Its Windows-native artifact-tool
build currently awaits execution permission.

- **PENDING — rendered slides:** record the final slide count and confirm every image was inspected
  at full resolution.
- **PENDING — overflow validation:** record the presentation overflow-test result.

## Validation evidence

- Focused provider and transcript regression tests cover the delivered request, stream,
  cancellation, mismatch-privacy, dependency-isolation, and persistence-normalization contracts.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passes: 263 Python tests, 30 Python
  protocol-fixture tests, 24 repository-policy tests, 208 TUI tests, 29 TypeScript
  protocol-fixture tests, and 4 real Node/Python boundary tests, plus Python lint/format and
  TypeScript typecheck/lint.

## Deferred work

- CAH-021 will build one `ProviderRequest`, consume one operation, translate its events into the
  existing session lifecycle, and preserve the exactly-one-terminal invariant.
- CAH-022 will enforce turn, elapsed-time, and output limits before another costly operation begins.
- A real OpenAI Responses API adapter, instruction discovery, context selection, tool execution,
  policy, automatic retry, provider selection, and live evaluations remain later work.
