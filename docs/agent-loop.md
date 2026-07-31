# Agent Loop

> Status: proposed model-loop design with the CAH-020 provider port and deterministic fake complete.
> CAH-010 verifies the pure session-state and replay precursor in Python and TypeScript; no
> provider-backed loop exists yet, and the current `MockSession` path is unchanged.

Code Assist Harness will own its agent loop directly. That choice makes orchestration, limits,
cancellation, tool policy, and event emission visible to a learner and testable independently of a
framework. LangChain may later be offered as an adapter, but no core domain type or lifecycle rule
will depend on it.

## Ownership boundaries

The Python harness owns:

- Building provider-neutral model requests.
- Deciding when another model turn is permitted.
- Interpreting provider text and tool-call stream events.
- Validating and authorizing tool requests.
- Waiting for approvals before side effects.
- Enforcing deadlines and count limits.
- Emitting one ordered, authoritative session event stream.
- Selecting exactly one terminal outcome.

A real provider adapter will own translation between the implemented provider-neutral types and its
SDK. OpenAI SDK objects must not escape that adapter. The deterministic fake implements the same
port without an SDK or network access. The TUI will display events and send commands; it does not
decide that a turn is complete or that an action is safe.

## Vocabulary

A **session** begins with one user task and ends in one terminal state. A **model turn** is one
provider request and its streamed response. A **tool call** is one model-requested operation. A
**step** is a bounded unit of loop progress, such as a model turn or tool execution. These terms
should remain distinct in code, documentation, transcripts, and metrics.

## Async runtime model

The Python runtime will use one `asyncio` event loop. The intended task structure is:

- A command-reader task validates NDJSON from stdin and dispatches domain commands.
- A single event-writer task validates and serializes events from an ordered queue to stdout.
- At most one active session task runs the agent loop in the MVP.
- Provider and tool operations are awaited child tasks so cancellation and deadlines can propagate.
- Transcript writing consumes trusted domain facts and validated events without becoming the source
  of session truth.

Small bounded filesystem reads may run synchronously. Work that can block the loop unpredictably
must be moved to a worker thread or a cancellable executor. Introducing threads should be a measured
response to observed blocking, not the default concurrency model.

The single event writer is an important invariant: multiple async producers may create domain
events, but only one task assigns final sequence numbers and writes protocol lines. This prevents
interleaving and makes transcript replay deterministic.

The current M0 precursor uses that same event loop without pretending to be an agent loop.
`run_runtime` keeps reading commands while one `MockSession` task streams. The session owns a
cooperative cancellation event and serializes delta writes, completion, and cancellation through
one state lock. This proves request routing and terminal selection before provider and tool child
tasks make propagation deeper. The [walking-skeleton guide](walking-skeleton.md) traces this
implemented precursor from the Ink keypress through its authoritative Python terminal event and
back to rendering; it does not describe the future provider loop as shipped.

## Bounded loop

Conceptually, one session follows this algorithm:

```text
accept task and emit session.started
while session is active:
    check cancellation, deadline, and limits
    build bounded context and provider-neutral request
    call provider and stream response into domain events
    if response is ordinary assistant text:
        emit assistant.completed and complete the session
    if response requests tools:
        validate each request
        evaluate policy and obtain approval when required
        execute permitted tools and append structured results
        check limits before beginning another model turn
emit exactly one terminal session event
```

The implementation should not hide the loop in callbacks. Each transition must be explicit enough
to unit test with a programmable fake provider.

## Provider port

`src/code_assist_harness/provider/` now defines the provider boundary using harness concepts rather
than OpenAI concepts. `ProviderRequest` contains a non-empty ordered conversation and ordered,
caller-supplied repository instructions. Instruction discovery and context selection remain later
work. The stream can express:

- Text deltas.
- A completed assistant message.
- Tool-call requests with serialized arguments.
- Usage information.
- Provider completion and failure.
- Cooperative cancellation through the operation contract rather than as a fabricated stream
  event.

`Provider.start()` returns one `ProviderOperation`. Its event stream may be claimed exactly once and
ends normally with `ProviderCompleted` or `ProviderFailed`. `cancel()` is idempotent and waits for
cleanup; after it returns, the operation cannot emit another event. Cancellation ends iteration
without inventing a provider failure because the session layer already owns the user's cancellation
intent. `wait_closed()` lets the caller await natural completion, failure, or cancellation cleanup
without requesting cancellation.

The deterministic `FakeProvider` is the first implementation. It consumes an ordered tuple of
`FakeProviderExchange` values. Each exchange pairs one exact `ProviderRequest` with explicit emit,
logical-delay, and cancellation-checkpoint steps:

```python
fake = FakeProvider(
    (
        FakeProviderExchange(
            expected_request=request,
            steps=(
                FakeProviderEmit(ProviderTextDelta("hello")),
                FakeProviderEmit(ProviderTextCompleted("hello")),
                FakeProviderEmit(ProviderCompleted()),
            ),
        ),
    )
)

operation = fake.start(request)
events = [event async for event in operation.events()]
fake.assert_complete()
```

Non-cancellation exchanges end in exactly one completion or normalized failure event. A
`FakeProviderDelay` names a logical gate that the test releases explicitly, so asynchronous
ordering tests need no timing-sensitive sleep. `FakeProviderWaitForCancellation` lets a test pause
before output or between deltas; cancellation consumes and suppresses the remaining scripted emits.
Every started exchange must finish before the next begins, and `assert_complete()` detects omitted
requests, active streams, abandoned consumers, and unconsumed steps. Unexpected requests report
only bounded differing field paths rather than conversation or instruction contents.

`ProviderFailure` normalizes provider errors into a stable code, bounded single-line safe message,
and retryable observation. It has no raw exception, response, header, environment, or credential
field; retryability does not authorize the loop to retry. Malformed tool arguments remain serialized
text at this boundary so later tool validation can return a structured harness result. Provider
contract tests run without vendor modules, framework packages, API keys, or network access. The
OpenAI adapter is a later story and will target the Responses API at this boundary.

## State and terminal outcomes

The implemented one-session state set is `idle`, `starting`, `running`, `awaiting_approval`,
`cancelling`, `completed`, `cancelled`, and `failed`. `session_state.py` and
`session-lifecycle.ts` are pure native reducers governed by the same transition fixtures. The
TypeScript conversation adapter preserves terminal turns and retains a separate local
`protocol-failed` projection for an invalid trusted tape; a later task starts a fresh core.

The reducers consume two kinds of trusted input. Pydantic- or Zod-validated protocol-v1 session
events establish authoritative Python facts. Command-originated `task.submitted` and
`cancel.requested` facts establish local intent. Domain-only `approval.requested` and
`approval.resolved` exercise the waiting state without adding premature approval messages to
protocol v1. A later approval story must define the action and decision wire identities before a
live producer uses those facts.

Core invariants are:

- At most one provider request is active for a session.
- Every requested side effect passes through policy.
- Cancellation is checked before another costly operation begins.
- Terminal states never return to a running state.
- A session emits exactly one of `session.completed`, `session.cancelled`, or `session.failed`.
- Replaying the same trusted lifecycle input list produces the same visible state.

Before a wire event can alter state, the cores check its legal edge, command correlation, session
identity, contiguous sequence, and payload-specific assistant completion rule. A rejection returns
the exact prior state plus only a stable code, prior status, and input type. Task text, assistant
text, IDs, payloads, and validator details are excluded. Every later input to `completed`,
`cancelled`, or `failed` returns `terminal_state_absorbing`; duplicate terminals never create a
second outcome.

CAH-006 proves the first cancellation/completion race rule: a `MockSession` lock lets the first
valid terminal selection win, repeated or recent-terminal requests become no-ops, and the TUI waits
for Python's event instead of treating a local request as acknowledgement. Provider completion,
deadlines, tool cleanup, and child exit will reuse or extend that rule. It is not safe to rely on
every provider or executor stopping immediately after cancellation.

## Limits and failures

Configuration will include maximum model turns, tool calls, output size, and elapsed time. Each
limit is checked before starting the next operation that could incur work. Reaching a limit produces
a distinct stable failure code and an understandable TUI message; it is not reported as provider
failure.

Failures are converted at their ownership boundary:

- Provider exceptions become provider failure domain events.
- Invalid tool arguments become structured tool results the model can reason about.
- Policy denials and rejected approvals become explicit results without side effects.
- Harness invariant violations fail the session and preserve diagnostic detail on stderr.
- Transcript failure is surfaced separately and must not silently rewrite agent state.

Raw provider responses are not session events and are not persisted by default.

## Implementation stories

### CAH-010 — Implement session state as a reducer

> As a harness developer, I want state derived from trusted lifecycle inputs so that runtime tests,
> the TUI, and replay share lifecycle semantics.

This story is complete. Sixteen legal transitions, seven full replays, and twenty-seven invariant
failures are shared across both reducers. The mock runtime and TypeScript supervisor route their
current tapes through the cores, including successful completion, cancellation, completion winning
the cancellation race, and an authoritative `session.failed` terminal.

### CAH-020 — Define the provider interface and fake provider

> As an agent-loop developer, I want provider-neutral streaming types and a deterministic fake so
> that orchestration can be tested without OpenAI.

This story is complete. Harness-owned immutable request and stream values live in
`provider/models.py`, the structural async port lives in `provider/port.py`, and the strict scripted
implementation lives in `provider/fake.py`. Focused tests exercise every event variant, ordering,
logical delays, normalized failures, mismatch privacy, malformed tool arguments, omitted work, and
cancellation before output and between deltas without a provider dependency or network request.

### CAH-021 — Complete one model turn

> As a user, I want one task answered through a provider so that the first conversational capability
> is available.

This is the next dependency-ready unit. Finish it when deltas, completion, provider failure, and
cancellation all flow through the fake-provider path and terminal event invariants hold.

### CAH-022 — Enforce loop limits

> As a user, I want the harness to stop predictably at configured limits so that faulty sequences
> cannot run indefinitely.

Complete this story when every limit is covered by deterministic tests and the transcript identifies
the exact limit reached.
