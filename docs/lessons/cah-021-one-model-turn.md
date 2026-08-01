# CAH-021 lesson: Run one provider-neutral turn

- **Unit:** CAH-021
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; the provider-injected runtime seam is implemented and tested,
  while launched `main()` intentionally remains on `MockSession`
- **Story:** [CAH-021](../../user-stories/cah-021-complete-one-model-turn.md)
- **Visual companion:**
  [One turn, one owner](assets/cah-021-one-model-turn.pptx)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Protocol](../protocol.md)

> This lesson traces the implemented CAH-021 path in `ProviderSession`, the runtime composition
> seam, transcript version 2, and deterministic tests. It does not claim that the launched
> application uses a real model: `main()` still selects `MockSession`, and CAH-023 owns adapter
> configuration and activation.

## Quick summary

CAH-021 implements the smallest harness-owned model turn: one accepted task becomes one exact
`ProviderRequest`, one provider operation yields validated observations, and one shared finalizer
publishes the authoritative outcome after cleanup. The strict fake proves success, malformed
streams, usage, teardown, and cancellation races without HTTP, credentials, or provider SDK types.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a session, provider operation, and model turn;
- trace provider-neutral observations into ordered session events and transcript-only evidence;
- explain why reconciliation, a decision lock, and one finalizer make streaming trustworthy;
- read deterministic cancellation tests that use logical gates instead of elapsed-time guesses; and
- identify which limits, adapters, context, and tools remain separate units.

## Why this unit matters

CAH-020 proved that the provider port and fake work in isolation. CAH-021 proves the harder
integration boundary: the harness constructs the request, decides which stream observations are
legal, owns cancellation, awaits cleanup, and alone declares the session terminal. Keeping that
work provider-neutral lets CAH-022 add hard limits before CAH-023 introduces network and billable
provider work.

## Junior engineer foundation

An asynchronous iterator is like a sequence whose next item may arrive later. Calling `anext()`
returns an awaitable for one item; putting that awaitable in a task lets another coroutine request
cancellation while the provider is waiting. The implemented consumer in
[`provider_session.py`](../../src/code_assist_harness/provider_session.py#L351) does exactly that:

```python
while self._selection is None:
    pending = asyncio.create_task(anext(events))
    self._pending_event_task = pending
    try:
        observation = await asyncio.shield(pending)
```

- The `while` condition stops requesting observations after an outcome owns the session.
- `create_task()` gives the pending provider read an identity that cleanup can join.
- `self._pending_event_task` records ownership; teardown must not simply forget this task.
- `shield()` keeps cancellation of the session waiter from silently cancelling provider-owned work
  before the operation's explicit cleanup path runs.

A lock protects a decision, not just a data structure. `ProviderSession` uses one
`asyncio.Lock` so an admitted delta can finish its wire write, reducer update, and observer attempt
before cancellation selects a competing outcome.

A common beginner misconception is “the stream ended, so the turn succeeded.” End-of-iteration is
not success here. The stream must contain a matching text-completed candidate and an explicit
`ProviderCompleted`; otherwise the harness selects `provider_invalid_response`.

## Key concepts

- **Provider-neutral request:** immutable conversation and already-resolved repository instructions
  expressed only with harness-owned types.
- **Provider operation:** one claimed async stream plus explicit `cancel()` and `wait_closed()`
  cleanup barriers.
- **Stream grammar:** the accepted order and cardinality of delta, text completion, usage, provider
  failure, tool request, and provider completion observations.
- **Completion reconciliation:** exact comparison of completed text with the concatenation of
  accepted deltas.
- **Decision lock:** the serialization boundary for observation admission, evidence observers, and
  outcome selection.
- **Selected finalizer:** the one shared task that awaits cleanup, reports bounded cleanup failure,
  and emits at most one session terminal.
- **Trusted usage evidence:** optional bounded counters persisted as
  `model.usage_observed`; they are neither protocol-v1 lifecycle state nor billing proof.

## Architecture and design

```text
validated session task
        |
        v
ProviderSession ---- builds ----> ProviderRequest
        |                               |
        |                        Provider.start()
        |                               |
        +<----- ProviderOperation ------+
        |
        +--> assistant/session events --> OrderedEventWriter --> Python/TUI reducers
        +--> ModelUsageObserved --------> transcript v2 --> replay evidence / summary
        +--> selected outcome ----------> cleanup barrier --> one terminal publication
```

The harness owns request construction, observation acceptance, reconciliation, cancellation, and
session truth. A provider owns only the provider-specific operation behind the neutral port. The
ordered writer owns protocol sequence numbers. Transcript persistence observes accepted facts but
does not become lifecycle authority.

The implemented success grammar is deliberately narrow:

1. one or more non-empty `ProviderTextDelta` values;
2. exactly one `ProviderTextCompleted` equal to their concatenation;
3. optionally one bounded `ProviderUsageReported`;
4. exactly one `ProviderCompleted`.

`ProviderFailed` may terminate before or after a partial prefix. A tool request selects the fixed
`tool_unavailable` failure, calls the operation's cancellation barrier, and starts no tool or second
turn. Missing, duplicate, out-of-order, empty, mismatched, unencodable, or prematurely ended success
observations select `provider_invalid_response` without copying rejected content into diagnostics.
The session may retain `ProviderTextCompleted("")` as a candidate only so a following tool request is
recognized as `tool_unavailable`. Empty text cannot admit usage or complete successfully.

Accepted deltas share a fixed 8,192-byte cumulative UTF-8 compatibility ceiling. The delta that
would cross it is rejected in full before emission. This protects the current protocol shape; it is
not CAH-022's configurable output budget. CAH-022 may choose a smaller value, never a larger one.

`ProviderTextCompleted` is only a candidate. The session stores it after reconciliation, but does
not emit `assistant.completed` until `ProviderCompleted` selects success and `wait_closed()`
settles. A later provider failure or early EOF therefore cannot leave a completed assistant inside
a failed session.

Usage is also separate from lifecycle. One valid report becomes `ModelUsageObserved`, passes through
the usage observer under the decision lock, and may become one transcript-version-2 record. It does
not consume a protocol sequence or enter either lifecycle reducer. Replay accepts homogeneous
version-1 and version-2 tapes, rejects mixed versions and invalid placement, and exposes usage in
`TranscriptEvidence` and the human summary. CAH-022's expiry reservation is still deferred.

Outcome selection and terminal publication are two phases. Completion, provider failure, invalid
response, tool rejection, user cancellation, and teardown can each propose an outcome, but
`_select_locked()` stores only the first and creates one finalization task. That task attempts
`wait_closed()` for natural provider terminals or `cancel()` when active work must stop. A cleanup
or local read-reaping exception adds the fixed `provider_cleanup_failed` runtime diagnostic. After
the cleanup attempt, the loop cancels and awaits any pending local read. For a cancellation-
responsive iterator, that join prevents local task scheduling from hanging finalization. A
successful barrier return is trusted and does not create a warning merely because the wrapper task
was pending; a warning never rewrites the selected outcome or exposes provider content. An iterator
that suppresses cancellation requires stronger process isolation beyond this unit.

Runtime shutdown, stdin EOF, and outer-task cancellation use teardown rather than fabricating a
user cancellation. Teardown-first cancels and joins provider work, emits no session terminal, and
leaves an incomplete replayable transcript prefix. If a user-visible outcome already won, teardown
joins the same finalizer and lets that outcome finish unchanged.

The composition seam is intentionally narrower than product activation. Tests can pass a
`Provider` and an already-resolved instruction tuple to `run_runtime()`. Its default `provider=None`
selects `MockSessionRunner`, which is also what launched `main()` uses. Instruction discovery and
precedence remain context-engineering work; a real OpenAI adapter and model selection remain
CAH-023 work.

## Practical walkthrough

1. `ProviderSession.__init__()` snapshots one user message and the injected instruction tuple into
   one immutable request.
2. `run()` publishes `session.started`, calls `Provider.start()` once, and claims `events()` once
   while holding the decision lock.
3. Each delta is UTF-8 measured before it can enter the existing `assistant.delta` protocol path.
4. The session writes an admitted delta, reduces it, and finishes the lifecycle observer before
   appending it to the internal reconciliation buffer.
5. Text completion must match that buffer. An empty match is held only for a possible following tool
   request; it cannot admit usage or successful provider completion.
6. `ProviderCompleted` after a non-empty text candidate selects completion but does not immediately
   emit it. The shared finalizer awaits `wait_closed()` first, then publishes
   `assistant.completed` and `session.completed`.
7. Provider failure preserves a partial accepted prefix. Invalid grammar and tool requests select
   fixed safe failures; active work is cancelled and joined before `session.failed` is emitted.
8. Cancellation and teardown compete under the same decision lock. Every caller joins the selected
   finalizer rather than creating another cleanup owner.
9. The runtime attaches transcript lifecycle and usage observers only around the injected session;
   disabled persistence leaves the protocol tape unchanged.
10. Each deterministic fake scenario ends with `FakeProvider.assert_complete()`, proving the one
    request and its scripted stream were not abandoned.

## Implementation code samples

### 1. Construct one provider-neutral request

The constructor excerpt is from
[`ProviderSession.__init__()`](../../src/code_assist_harness/provider_session.py#L147):

```python
self._writer = writer
self._provider = provider
self._command = command
self._session_id = session_id
self._request = ProviderRequest(
    conversation=(ProviderMessage(role="user", content=command.payload.task),),
    repository_instructions=repository_instructions,
)
self._decision_lock = asyncio.Lock()
```

The first four assignments retain harness-owned collaborators and identities. `ProviderRequest`
contains exactly one user message for this unit; the trailing comma makes `conversation` a tuple,
not a single value in parentheses. The already-resolved instruction tuple is passed through without
filesystem discovery. Finally, the decision lock establishes the shared admission boundary before
provider work can start.

### 2. Start and claim exactly one operation

The operation claim is from
[`_start_provider_operation()`](../../src/code_assist_harness/provider_session.py#L329):

```python
async with self._decision_lock:
    if self._selection is not None:
        return
    try:
        operation = self._provider.start(self._request)
        self._operation = operation
        events = operation.events()
    except (asyncio.CancelledError, Exception):
        self._select_locked(
            _SelectedOutcome(
                kind="failed",
                cleanup_mode="cancel",
                failure_code=PROVIDER_INVALID_RESPONSE_CODE,
                failure_message=PROVIDER_INVALID_RESPONSE_MESSAGE,
                correlation_id=self._command.command_id,
            )
        )
        return
    self._events = events
```

The lock first checks whether cancellation or teardown already selected an outcome. The provider is
started once, and the operation is stored before `events()` is claimed so even a broken claim can be
cleaned up. A start or claim exception becomes the fixed invalid-response outcome; raw exception
text never becomes a protocol payload. Only the successfully claimed iterator enters `_events`.

### 3. Admit a bounded delta and reconcile completion

The important success checks are in
[`_accept_observation()`](../../src/code_assist_harness/provider_session.py#L379):

```python
if isinstance(observation, ProviderTextDelta):
    if self._completed_text is not None or self._usage_observed:
        self._select_invalid_response_locked()
        return
    try:
        encoded_length = len(observation.text.encode("utf-8"))
    except UnicodeEncodeError:
        self._select_invalid_response_locked()
        return
    if self._accepted_text_bytes + encoded_length > MAX_PROVIDER_TURN_OUTPUT_BYTES:
        self._select_invalid_response_locked()
        return
    delta = await self._writer.emit_session(
        "assistant.delta",
        self._session_id,
        {"text": observation.text},
        correlation_id=self._command.command_id,
    )
    await self._accept_lifecycle_locked(delta)
    self._accepted_text.append(observation.text)
    self._accepted_text_bytes += encoded_length
    return
```

The first guard rejects a delta after text completion or usage. Encoding determines bytes, not
Python characters, which matters for emoji and other multibyte text. Both encoding failure and a
ceiling crossing select the same payload-free safe failure. The writer and lifecycle reducer settle
before the fragment enters the reconciliation buffer, so internal state cannot get ahead of
published evidence.

The same method keeps completion as a candidate and selects success only on the provider terminal:

```python
if isinstance(observation, ProviderTextCompleted):
    if (
        self._completed_text is not None
        or self._usage_observed
        or observation.text != "".join(self._accepted_text)
    ):
        self._select_invalid_response_locked()
        return
    self._completed_text = observation.text
    return

if isinstance(observation, ProviderCompleted):
    if self._completed_text is None or not self._accepted_text:
        self._select_invalid_response_locked()
        return
    self._select_locked(
        _SelectedOutcome(
            kind="completed",
            cleanup_mode="wait_closed",
            correlation_id=self._command.command_id,
        )
    )
    return
```

The joined delta text must match exactly. Setting `_completed_text` changes no wire state, which lets
an empty tool-only prefix wait for its actual tool observation. The provider-completion guard still
requires at least one accepted delta, so that empty candidate can never emit assistant completion.
Only `ProviderCompleted` after non-empty text selects success, and its cleanup mode records that the
operation ended naturally rather than needing cancellation.

### 4. Finish cleanup before publishing the selected terminal

The selected finalizer is implemented in
[`_select_locked()` and `_finalize()`](../../src/code_assist_harness/provider_session.py#L525):

```python
def _select_locked(self, selection: _SelectedOutcome) -> None:
    if self._selection is not None:
        return
    self._selection = selection
    self._finalization_task = asyncio.create_task(self._finalize(selection))

async def _join_finalization(self) -> None:
    task = self._finalization_task
    if task is not None:
        await _join_shared(task)

async def _finalize(self, selection: _SelectedOutcome) -> None:
    if selection.kind != "teardown":
        await self._session_start_settled.wait()
        if not self._session_started_successfully:
            return
    cleanup_failed = await self._finish_provider_work(selection.cleanup_mode)
    if cleanup_failed:
        await self._report_cleanup_failure_once()
    if selection.kind == "teardown":
        return
    await self._emit_selected_terminal(selection)
```

The early return makes the first selection authoritative. Every competing caller joins the stored
task through `_join_shared()` instead of cancelling or replacing it. The finalizer waits for the
start publication to settle, attempts provider cleanup, reports a bounded cleanup problem once, and
emits no terminal for teardown. Other selected outcomes proceed to exactly one terminal publication.

### 5. Keep the launched path honest

The runtime seam is in
[`run_runtime()`](../../src/code_assist_harness/runtime.py#L166):

```python
session_runner: MockSessionRunner | ProviderSessionRunner
if provider is None:
    session_runner = MockSessionRunner(writer)
else:
    session_runner = ProviderSessionRunner(writer, provider, repository_instructions)
```

Tests and later composition can inject a provider, but omission is an explicit branch, not an
implicit global. Because `main()` supplies no provider, ordinary launch still produces the familiar
mock stream. CAH-023 must add validated configuration before changing that truth.

### 6. Prove a blocked delta transaction wins admission before cancellation

The meaningful race excerpt comes from
[`test_delta_transaction_finishes_before_user_cancellation()`](../../tests/test_provider_session.py#L1069):

```python
async def sink(line: bytes) -> None:
    if blocked_boundary == "sink" and b'"type":"assistant.delta"' in line:
        transaction_started.set()
        await release_transaction.wait()
    lines.append(line)

async def observe(update: SessionUpdate, _state: SessionState) -> None:
    if isinstance(update, AssistantDeltaEvent):
        if blocked_boundary == "observer":
            transaction_started.set()
            await release_transaction.wait()
        observer_finished.set()

session = ProviderSession(
    OrderedEventWriter(sink, timestamp_factory=lambda: TIMESTAMP),
    fake,
    _session_start(),
    "ses_blocked_delta",
)
await session.attach_lifecycle_observer(observe)
running = asyncio.create_task(session.run())
await asyncio.wait_for(transaction_started.wait(), timeout=1)

cancelling = asyncio.create_task(session.request_cancellation("cmd_cancel"))
await asyncio.sleep(0)
cancellation_waited = not cancelling.done()
release_transaction.set()
```

The same test is parameterized over a blocked wire sink and a blocked lifecycle observer. Each uses
an event as a logical gate. Cancellation is started only after the chosen boundary is definitely
blocked; `sleep(0)` yields one scheduler turn rather than waiting for elapsed time. If the decision
lock protects the full transaction, cancellation cannot finish until `release_transaction` opens.

The assertions prove all three consequences:

```python
assert cancellation_waited is True
assert _event_types(lines) == [
    "session.started",
    "assistant.delta",
    "session.cancelled",
]
assert session.lifecycle_state.assistant_text == "committed"
assert session.lifecycle_state.status == "cancelled"
```

The committed delta stays in the wire tape and authoritative reducer, then cancellation becomes the
one terminal outcome. A cancellation-first companion test proves the opposite ordering emits no
delta.

### 7. Prove cleanup failure is bounded and cannot rewrite completion

The cleanup-failure test records a secret-looking exception inside its controlled operation, then
asserts the safe observable order in
[`test_completion_cleanup_failure_emits_one_safe_diagnostic_then_completion()`](../../tests/test_provider_session.py#L1514):

```python
assert _event_types(lines) == [
    "session.started",
    "assistant.delta",
    "runtime.error",
    "assistant.completed",
    "session.completed",
]
assert "sk-secret-cleanup-exception" not in b"".join(lines).decode()
assert session.lifecycle_state.status == "completed"
```

The diagnostic precedes the already-selected terminal, but the session still completes. The raw
exception text never reaches protocol output. This test separates “the session outcome is known”
from “provider resource release was confirmed.”

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and repository evidence |
| --- | --- | --- |
| Provider fails before output | No assistant delta | One normalized `session.failed`; `test_normalized_provider_failure_before_or_after_output_is_authoritative` |
| Provider fails after output | Partial prefix remains visible | Prefix stays in lifecycle evidence; no assistant completion |
| Completed text differs | Reconciliation rejects the stream | Fixed `provider_invalid_response`; invalid-grammar parameter cases |
| Output crosses 8,192 bytes | Candidate delta would exceed the ceiling | Whole delta rejected by `test_delta_crossing_utf8_output_ceiling_is_rejected_in_full` |
| Tool request arrives | Provider asks for unsupported work | Fixed `tool_unavailable`, cancellation, and no arguments in output |
| Empty text precedes a tool request | Provider represents a tool-only response | Empty candidate stays non-terminal; the tool still selects `tool_unavailable` |
| Stream closes early | No provider terminal observation | Invalid response plus cancellation of the operation |
| Cancellation arrives during delta admission | Sink or observer is blocked | Admitted transaction finishes, then one `session.cancelled` |
| Cancellation races selected completion | Cleanup is still pending | Cancellation returns `terminal` and joins the winning completion finalizer |
| Usage competes with cancellation or teardown | Usage observer is blocked | Usage-first observer settles; terminal-first companion suppresses usage |
| Runtime pipe closes | No correlated user cancel exists | Teardown cleanup, incomplete transcript prefix, no invented terminal |
| Cancellation-responsive local read is pending after cleanup returns | Provider says cleanup succeeded before the wrapper task settles | Local read is cancelled and joined without inventing a warning |
| Provider cleanup or read reaping raises | Resource cleanup is unconfirmed | One bounded diagnostic preserves the selected outcome |

## Production expansion

### Example enterprise scenario

A multi-tenant coding assistant may run thousands of concurrent streams across regions and provider
versions. It needs deadlines, admission control, retry budgets, telemetry, privacy policy, and
provider conformance testing while preserving the same rule: adapters report observations and the
harness owns session truth.

### Typical production capabilities and tools

These are capability comparisons, not repository dependencies:

- [OpenAI Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
  illustrates typed remote events that CAH-023 can normalize behind the provider port. Its benefit
  is a real model stream; its costs include credentials, usage, remote failure, and adapter upkeep.
- [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking)
  illustrates connection, request, and pending-work bounds. It adds proxy operation and policy
  ownership that a one-process local harness does not need.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate interoperable model telemetry. They also introduce privacy review, sampling,
  retention, and observability cost.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html) document the task,
  shielding, lock, and cancellation primitives used locally; these primitives still require the
  application to define ownership correctly.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Traffic | One local active operation | Concurrent tenants, regions, and provider versions |
| Reliability | Deterministic fake and one selected finalizer | Deadlines, retry budgets, circuit breakers, and failover |
| Evidence | Local redacted transcript metadata | Traces, metrics, cost allocation, and retention governance |
| Testing | Scripted fake with logical checkpoints | Conformance, canary, load, and fault-injection suites |
| Operations | No provider network in this unit | Credential rotation, quota monitoring, and on-call ownership |
| Cost | No API usage and small local state | Provider spend plus telemetry and resilience infrastructure |

### Trade-offs and graduation signals

The narrow grammar is easy to teach and test. Tool-only output cannot succeed in this unit, but its
tool request is still recognized and rejected through `tool_unavailable`; multimodal and multi-turn
responses remain invalid. The single-process finalizer makes ownership visible, but it does not
provide durable distributed recovery. Expand the grammar only when a story names the new outcome and
adds fixtures for every observation. Add production routing, resilience, or central telemetry when
measured concurrency, latency, availability, cost-allocation, or on-call needs justify their
operational burden.

## Practical exercises

1. Run the candidate-completion delay test and identify the exact moment
   `assistant.completed` becomes legal.
2. Change one character in `ProviderTextCompleted` inside an invalid-grammar fake and predict which
   prefix remains accepted.
3. Add a multibyte delta at exactly the 8,192-byte boundary, then one byte beyond it, and compare the
   tapes.
4. Follow the blocked-observer race and explain why writer shielding by itself would be insufficient.
5. Emit a tool request with secret-looking arguments and verify neither its name nor arguments enter
   protocol output.
6. Trace `run_runtime(provider=None)` and explain why it is honest for `main()` to stay mocked after
   the provider-session implementation ships.

## Key takeaways

- The Python harness, not the provider or TUI, owns request meaning, observation admission, cleanup,
  and session truth.
- Strict grammar, reconciliation, one decision lock, and one selected finalizer preserve exactly one
  terminal outcome even under cancellation.
- CAH-021 proves orchestration without network access; CAH-022 adds hard limits, and CAH-023 adds and
  activates the real adapter only after validated configuration exists.

## Glossary

- **Model turn:** one provider request and all observations from its operation.
- **Provider operation:** the single-use stream plus cancellation and natural-cleanup barriers.
- **Reconciliation:** validation that completed text exactly matches accepted incremental text.
- **Stream grammar:** legal provider-observation order and cardinality.
- **Decision lock:** the lock that serializes evidence admission with outcome selection.
- **Selected finalizer:** the single shared task that cleans up and publishes the winning outcome.
- **Trusted usage evidence:** bounded non-authoritative counters restored from a transcript-only
  record, outside lifecycle state.

See the shared [project glossary](../glossary.md) for session, provider, assistant delta, and usage.

## Further reading

- [CAH-021 user story](../../user-stories/cah-021-complete-one-model-turn.md)
- Project design: [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [agent loop](../agent-loop.md), [protocol](../protocol.md), and
  [context engineering](../context-engineering.md)
- Provider-port precursor: [CAH-020 lesson](cah-020-provider-interface-and-fake.md)
- Next hard-limit unit: [CAH-022 story](../../user-stories/cah-022-enforce-loop-limits.md)
- Later network boundary: [CAH-023 lesson](cah-023-openai-responses-adapter.md)
- Production references: [OpenAI Responses streaming](https://developers.openai.com/api/docs/guides/streaming-responses),
  [Envoy circuit breaking](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/circuit_breaking),
  [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
  and [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
