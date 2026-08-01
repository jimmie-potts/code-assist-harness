# Agent Loop

> Status: incremental model-loop implementation. CAH-021 completes one provider-neutral turn through
> an injected runtime seam and the CAH-020 deterministic fake. The launched `main()` path and TUI
> remain on `MockSession`; CAH-022 is next and owns configurable hard limits.

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

The launched M0 path uses that same event loop without pretending that its fixed response is a model
turn. `run_runtime` keeps reading commands while one `MockSession` task streams. The session owns a
cooperative cancellation event and serializes delta writes, completion, and cancellation through one
state lock. The [walking-skeleton guide](walking-skeleton.md) traces this path from the Ink keypress
through its authoritative Python terminal event and back to rendering.

CAH-021 adds a parallel composition seam for tests and later adapters. When `run_runtime` receives an
injected `Provider`, `ProviderSessionRunner` creates one `ProviderSession` instead of a `MockSession`.
The session starts exactly one operation and claims its stream exactly once. Each accepted lifecycle
publication is one shielded transaction under the session decision lock: ordered protocol write,
Python reduction, and transcript-observer attempt all settle before cancellation or teardown may
select an outcome. This is a real provider-neutral orchestration slice, but `main()` deliberately
injects no provider, so it does not alter the visible mock or the TypeScript protocol-v1 projection.

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
contract tests run without vendor modules, framework packages, API keys, or network access. CAH-021
now consumes this port for one fake-backed turn. CAH-022 will enforce configurable hard limits, and
CAH-023 will then target the OpenAI Responses API at this boundary.

## Implemented one-turn grammar

`ProviderSession` builds one `ProviderRequest` containing the accepted task as its sole `user`
message plus an ordered tuple of already-resolved repository instructions. It does not discover
instructions, select repository context, import an SDK, start another turn, or execute tools.

A successful stream must contain one or more non-empty `ProviderTextDelta` observations, exactly one
`ProviderTextCompleted` equal to their byte-for-byte concatenation, optionally one
`ProviderUsageReported`, and exactly one `ProviderCompleted`, in that order. Completed text remains a
candidate until provider completion validates the entire grammar and `wait_closed()` has been
attempted. Only then does the session emit `assistant.completed` followed by `session.completed`.
A missing, duplicate, out-of-order, empty, mismatched, or early-ended success observation becomes the
safe `provider_invalid_response` failure.

The turn rejects a delta in full before emission when cumulative accepted assistant text would exceed
8,192 UTF-8 bytes. This fixed compatibility ceiling keeps protocol lines bounded; it is not the
configurable output budget, model-turn limit, tool-observation limit, or provider-work deadline owned
by CAH-022. A `ProviderFailed` observation becomes one normalized `session.failed` outcome, while a
tool request becomes `tool_unavailable`, triggers operation cancellation, and never exposes or parses
its arguments.

Optional usage is bounded to non-negative JavaScript-safe integers and recorded outside lifecycle
state as `model.usage_observed`. It consumes neither a protocol-v1 sequence number nor a reducer
transition. Transcript version 2 stores the observation before the terminal record and replay exposes
it through a separate evidence projection; version-1 tapes remain replayable. Usage admission shares
the decision lock, so an admitted evidence write settles before cancellation competes, while a
terminal outcome that wins first suppresses later usage.

Completion, normalized failure, user cancellation, invalid response, and runtime teardown select one
shared outcome before cleanup. User cancellation calls and awaits `ProviderOperation.cancel()`.
Shutdown, stdin EOF, or outer-task cancellation use teardown: they cancel and join active provider
work without fabricating `session.cancelled`, leaving an incomplete replayable transcript prefix when
teardown wins. A promised cleanup method that raises cannot rewrite an already-selected outcome; the
runtime emits at most one start-correlated, payload-free `provider_cleanup_failed` diagnostic before
any selected terminal.

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
for Python's event instead of treating a local request as acknowledgement. CAH-021 applies the rule
to provider completion, normalized failure, user cancellation, and runtime teardown through one
decision lock and shared finalizer. Deadlines and tool execution remain later extensions. It is not
safe to rely on every provider or executor stopping immediately after cancellation.

## Limits and failures

CAH-021 enforces only the fixed 8,192-byte protocol-compatibility ceiling described above.
Configuration will include maximum model turns, a provider-work deadline, assistant output bytes,
and observed provider tool calls. Model-turn admission is charged before provider work starts;
output and tool-call limits are checked before an observation is admitted for publication. An
independent deadline watcher can stop provider work while an already-admitted publication is
blocked, but that publication finishes atomically before the latched deadline selects the terminal
outcome. The deadline bounds provider work, not event-sink latency. Reaching a limit produces a
distinct stable failure code and an understandable TUI message; it is not reported as provider
failure.

Failures are converted at their ownership boundary:

- Provider adapters normalize expected failures before exposure; an unexpected start, iteration, or
  grammar failure in the implemented turn becomes the safe `provider_invalid_response` outcome.
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

### CAH-021 — Run one provider-neutral turn

> As an agent-loop developer, I want one provider-neutral turn to run through the harness-owned
> lifecycle so that orchestration is proven before network integration.

This story is complete. `provider_session.py` builds one request from a task and injected instruction
tuple, starts one fake-provider operation, enforces the strict text/completion grammar and fixed
8,192-byte ceiling, persists optional bounded usage as separate evidence, rejects tool requests as
unavailable, and preserves one terminal winner through cleanup. Focused session tests exercise valid
and invalid streams, failure and tool mapping, output bounds, usage ordering, cancellation races,
blocked publication and evidence transactions, teardown, and cleanup-contract violations. Runtime
tests prove the injected composition seam and transcript-mode parity without replacing the launched
`MockSession` or changing protocol v1.

### CAH-022 — Enforce loop limits

> As a user, I want provider work to stop predictably at configured limits so that faulty sequences
> cannot consume provider resources indefinitely.

Complete this story when provider-turn admission, an independent provider-work deadline, cumulative
accepted UTF-8 output, and observed tool calls are enforced before CAH-023 can activate network work.
The deadline may stop provider activity while an already-admitted local publication finishes; it is
not a sink-latency promise. Every limit must have deterministic fake-clock and fake-provider
evidence, awaited cleanup, one terminal winner, and bounded transcript evidence.

### CAH-023 — Add the OpenAI Responses adapter

> As an explicitly configured user, I want the bounded provider-neutral turn to use OpenAI Responses
> so that the first real model capability is available without leaking SDK types into the harness.

Complete this story when one text-only foreground Responses stream is explicitly configured with the
allowlisted `gpt-4.1-mini-2025-04-14` snapshot, `background=false`, and `store=false`; its request
omits tools and rejects reasoning/tool events; one exact assistant-text trace and SDK failures are
normalized behind the provider port; foreground cancellation suppresses pending observations and
joins operation-owned stream/client cleanup; default tests use SDK fakes with network denied; and a
separately selected credentialed smoke test remains outside the canonical gate and default CI.
