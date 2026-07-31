# CAH-021 - Run one provider-neutral turn

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-020
- **Lesson:** [One provider-neutral turn](../docs/lessons/cah-021-one-model-turn.md)

## User story

> As an agent-loop developer, I want one provider-neutral turn to run through the harness-owned
> session lifecycle so that orchestration can be proven deterministically before a network adapter
> is introduced.

## Scope

- Implement one explicit Python turn that builds a `ProviderRequest`, starts exactly one
  `ProviderOperation`, consumes its stream, and selects one authoritative session outcome.
- Add a runtime composition seam through which tests and later adapters can supply a `Provider`.
- Translate accepted provider text, completion, usage, failure, and tool-call observations into
  existing session events and trusted local evidence; propagate cancellation intent separately
  through the operation's cleanup contract.
- Keep the launched `main()` path on the current `MockSession` until CAH-023 supplies validated
  provider and model configuration.
- Keep the entire unit network-free and exercise it through CAH-020's strict fake.

## Locked turn contract

- The request contains one `user` message built from the accepted task and an ordered,
  already-resolved tuple of repository instructions. The planned CAH-021 runtime seam supplies an
  empty tuple; discovery and precedence remain E3 work.
- A successful text stream contains one or more non-empty `ProviderTextDelta` values, exactly one
  `ProviderTextCompleted`, optionally one `ProviderUsageReported`, and exactly one
  `ProviderCompleted`. Usage, when present, follows text completion and precedes provider completion.
- Completed text must equal the byte-for-byte concatenation of accepted deltas. A missing,
  duplicate, out-of-order, empty, or mismatched successful observation is
  `provider_invalid_response`.
- CAH-021 applies a fixed, non-configurable protocol-compatibility ceiling of `8192` cumulative
  accepted assistant UTF-8 bytes. A delta that would cross it is rejected in full as
  `provider_invalid_response` before emission. CAH-022 owns the configurable output budget and may
  only choose a value at or below this ceiling.
- `ProviderTextCompleted` is a candidate completion, not an immediately emitted session event. The
  loop buffers and reconciles it, then emits `assistant.completed` only after
  `ProviderCompleted` makes the whole successful grammar valid and the loop's `wait_closed()` attempt
  finishes. If that loop-level cleanup barrier raises, the already-selected completion remains and
  the runtime emits the separate `provider_cleanup_failed` diagnostic before the completed terminal.
  A later usage error, provider failure, or early close before `ProviderCompleted` therefore cannot
  leave a completed assistant inside a failed session.
- `ProviderFailed` may terminate the provider stream before or after partial text. Its normalized
  code and bounded safe message become the single `session.failed` outcome; raw provider values are
  never copied. Natural failure also awaits `wait_closed()` before the session task returns.
- `ProviderToolCallRequested` becomes `tool_unavailable`, requests provider cancellation, awaits the
  cleanup barrier, and never parses arguments, executes a tool, or starts another turn.
- Usage counters are an optional transcript-only `model.usage_observed` evidence record with
  `session_id`, `input_tokens`, and `output_tokens`, bounded to non-negative IEEE-754 safe integers.
  It is accepted after valid text completion and before the terminal provider observation and does
  not consume a protocol sequence number or change lifecycle state.
- Accepted usage has its own serialized, shielded evidence transaction under the session decision
  lock. If usage admission wins, its transcript write or disabled/failed-persistence attempt finishes
  before cancellation, teardown, or a deadline can select a terminal; if a terminal reservation or
  outcome wins first, that usage observation is discarded. The transaction never writes protocol or
  reducer input, and CAH-022's expiry latch has priority before usage admission.
- The CAH-021 writer always emits transcript version 2, whether or not usage is present. Replay
  accepts versions 1 and 2, validates version-2 usage order and session identity, exposes optional
  usage through a separate replay-evidence projection, and includes it in the human summary. The
  record is not a `SessionUpdate`, protocol-v1 event, Python/TypeScript lifecycle-reducer input,
  billing proof, or limit authority; CAH-010's shared lifecycle fixtures remain unchanged.
- User cancellation calls and awaits `ProviderOperation.cancel()`. Cancellation, completion, and
  failure share the established terminal guard, so exactly one session terminal event wins.
- Session outcome authority is fixed before loop-initiated cleanup. Normal completion, failure, user
  cancellation, and teardown select the guard first. CAH-022's watcher is the one exception in form:
  it atomically latches an irrevocable deadline reservation before starting cancellation, and the
  session converts that reservation to the formal failed selection after any already-admitted event
  transaction releases the decision lock. Wire terminal emission is deferred until the loop cleanup
  attempt finishes; cleanup failure cannot rewrite the selected or reserved outcome, and a later
  competing path emits nothing.
- Provider-internal natural cleanup is a different phase: an adapter may close its own resources
  before exposing `ProviderCompleted` or `ProviderFailed`. It cannot select a session outcome. CAH-023
  maps adapter cleanup failure to `ProviderFailed` before exposure; after any provider terminal is
  observed, the loop still uses `wait_closed()` as its repeatable cleanup barrier.
- Every accepted lifecycle event uses one serialized, shielded publication transaction under the
  same session decision lock: admit the event, write it through `OrderedEventWriter`, accept it in
  the Python lifecycle reducer, and finish the attached transcript-observer attempt. Cancellation or
  teardown cannot select a terminal outcome between those steps. If the event transaction acquires
  the lock first, all three views finish before cancellation competes; if a terminal outcome wins
  first, no later delta transaction starts. Because `OrderedEventWriter` can commit a sink write and
  then propagate task cancellation, the session shields the whole transaction and observes its
  result before propagating outer cancellation into the terminal race.
- Explicit runtime shutdown, stdin EOF, and outer-task cancellation compete in the same guard. When
  teardown wins before any session outcome, it calls and awaits operation cancellation, emits no
  fabricated `session.cancelled`, and leaves a replayable incomplete transcript prefix with no
  summary. When completion, failure, or user cancellation was already selected, teardown cannot
  replace it; the runtime shields that selected path through cleanup, terminal wire emission, and
  summary completion before exiting.
- Every loop-detected invalid observation selects failure, then cancels and awaits an operation that
  is still active before emitting that failure. Invalid-stream fake scripts either end at the
  invalid terminal observation or provide a cancellation checkpoint so `assert_complete()` can
  prove the suffix was reaped.
- A provider implementation that raises from its promised cleanup barrier cannot replace the
  already-selected session outcome. The loop emits one payload-free, bounded
  `provider_cleanup_failed` runtime diagnostic, cancels and awaits any separate pending `anext`
  task, and never copies the exception text or claims that the non-conforming provider's own
  resources were reaped. The current port exposes no generic force-close operation beyond its
  promised cleanup methods.
- `provider_cleanup_failed` uses the existing protocol-v1 `runtime.error` surface with exactly the
  fields `code=provider_cleanup_failed`, `message=Provider cleanup could not be confirmed.`, and
  `recoverable=true`, plus the originating `session.start` command correlation. It is
  emitted at most once after the cleanup attempt and before an already-selected session terminal;
  teardown-first emits it without inventing a session terminal. It is not a `SessionUpdate`, does
  not enter either reducer or transcript, and cannot make the TUI reject the later authoritative
  terminal.

## Acceptance criteria

1. One accepted task and an injected instruction tuple produce one exact `ProviderRequest` without
   importing a provider SDK into the loop or session domain.
2. Exactly one provider operation is started and its event stream is claimed exactly once.
3. Accepted text deltas become ordered `assistant.delta` events with the start-command correlation.
4. The locked stream grammar and strict completion-reconciliation rule are enforced.
5. Only a fully valid stream ending in `ProviderCompleted` emits one `assistant.completed` followed
   by one `session.completed`; candidate completion remains buffered until then. The loop attempts
   `wait_closed()` before emission, but a cleanup-contract violation adds the locked diagnostic and
   does not rewrite the already-selected completion.
6. A normalized provider failure emits one safe `session.failed`; an accepted partial prefix remains
   visible and persisted without being reclassified as success.
7. Invalid stream structure emits one `provider_invalid_response` failure without payload contents in
   diagnostics.
8. A provider tool request emits one `tool_unavailable` failure and the cleanup barrier is awaited
   before the session task returns. The conforming fake proves closure; a barrier exception follows
   the locked safe-diagnostic path without rewriting the failure.
9. Cancellation propagates to the operation and preserves the existing exactly-one-terminal race
   semantics before output, between deltas, during a blocked delta sink/observer transaction, and
   against completion. A committed delta is reduced and its transcript-observer attempt finishes
   before cancellation wins; cancellation-first writes no delta.
10. Optional usage is validated, bounded, persisted as `model.usage_observed` before the terminal
    record in transcript version 2, restored through a separate replay-evidence projection, and
    included in the summary without changing either lifecycle reducer or protocol v1.
    `--no-transcript` suppresses the record and summary without changing the session outcome. Usage
    admission races terminals under the same decision lock: usage-first finishes its evidence attempt,
    while terminal-first discards the observation.
11. The runtime exposes an injectable provider composition seam without changing the launched mock
    response/cancellation path or claiming that a real provider is configured; the shared transcript
    writer's explicit move to version 2 is the only launched-path schema change.
12. Fake-provider tests cover success, logical delay, failure before and after output, every invalid
    stream ordering, the fixed protocol ceiling, tool-call rejection, usage bounds, cancellation,
    and completion races without network access or credentials.
13. Runtime shutdown, stdin EOF, and outer-task cancellation cancel and await active provider work
    when teardown wins, while an already-selected session outcome finishes unchanged;
    cleanup-contract violations produce only the safe runtime diagnostic and no raw exception.
14. A cleanup-contract violation emits at most one recoverable, start-correlated
    `provider_cleanup_failed` runtime error with the locked payload and no transcript record; an
    already-selected session terminal follows it unchanged.

## Validation

- Run focused turn tests against `FakeProvider` and call `assert_complete()` in every scenario.
- Assert emitted session events, unchanged cross-language lifecycle state, version-1 and version-2
  replay evidence, transcript/summary metadata, and operation cleanup for success and every failure
  path.
- Exercise the provider-injected runtime seam with validated commands and an ordered event sink.
- Exercise runtime shutdown, stdin EOF, and outer-task cancellation while the fake is blocked at a
  logical checkpoint on both sides of terminal selection. Assert that teardown-first leaves an
  incomplete transcript without a summary and outcome-first finishes its one terminal record.
- Block the ordered sink during an `assistant.delta` publication and race both user cancellation and
  outer-task cancellation on either side of transaction admission. Assert that a committed wire
  delta is reduced and observed before cancellation, while cancellation-first produces no delta in
  wire, reducer, or transcript evidence.
- Block the usage-evidence sink and race cancellation, teardown, and a seeded CAH-022 expiry latch on
  either side of usage admission. Assert usage-first finishes its persistence attempt before the
  terminal path, while terminal-reservation-first writes no usage record.
- Run the existing real Node/Python boundary tests unchanged to prove the launched mock remains
  honest until CAH-023.
- Run the full repository-wide non-live gate without an API key.

## Documentation impact

Update the agent-loop, architecture, evaluation, glossary, and current-status documentation with
the one-turn stream grammar, injected-instruction boundary, usage evidence, failure mapping,
cancellation cleanup, and deliberate runtime-activation deferral. Complete the linked written lesson
and required visual lesson when the unit is implemented.

## Out of scope

- OpenAI or another provider adapter, SDK dependency, HTTP request, credentials, model selection, or
  live smoke test.
- Repository-instruction discovery, precedence, context selection, or workspace reads.
- Hard loop limits, retries, filesystem tools, edit proposals, approvals, or subprocesses.
- Tool execution, multiple provider operations, or another model turn.
