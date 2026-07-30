# Agent Loop

> Status: proposed model-loop design. CAH-006 verifies its session-cancellation and
> exactly-one-terminal precursor with the deterministic mock; no model-backed loop exists yet.

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

The provider adapter will own translation between provider-neutral types and a provider SDK. OpenAI
SDK objects must not escape its module. The TUI will display events and send commands; it does not
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
- Transcript writing consumes validated events without becoming the source of session truth.

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

Provider request and stream types represent harness concepts rather than OpenAI concepts. The
stream must be able to express:

- Text deltas.
- A completed assistant message.
- Tool-call requests with serialized arguments.
- Usage information.
- Provider completion and failure.
- Cooperative cancellation.

The deterministic fake provider is the first implementation. It receives a script of expected
requests and events and fails clearly when the loop deviates. It must simulate delays, provider
errors, malformed tool arguments, and cancellation without network access. The OpenAI adapter is a
later story and will target the Responses API at the provider boundary.

## State and terminal outcomes

The target state set is `idle`, `starting`, `running`, `awaiting_approval`, `cancelling`,
`completed`, `cancelled`, and `failed`. CAH-006 currently projects `idle`, `starting`, `running`,
`cancelling`, `completed`, and `cancelled` in the TUI, plus a local fail-closed
`protocol-failed` state. `awaiting_approval`, domain failure, and the equivalent reusable Python
reducer remain CAH-010 and later work.

Core invariants are:

- At most one provider request is active for a session.
- Every requested side effect passes through policy.
- Cancellation is checked before another costly operation begins.
- Terminal states never return to a running state.
- A session emits exactly one of `session.completed`, `session.cancelled`, or `session.failed`.
- Replaying the same validated event list produces the same visible state.

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

> As a harness developer, I want state derived from events so that runtime tests, the TUI, and
> replay share lifecycle semantics.

Complete this story when legal transitions and every terminal path are tested in Python and have
equivalent reducer semantics in TypeScript.

### CAH-020 — Define the provider interface and fake provider

> As an agent-loop developer, I want provider-neutral streaming types and a deterministic fake so
> that orchestration can be tested without OpenAI.

Complete this story without adding provider SDK types to the core or making network requests.

### CAH-021 — Complete one model turn

> As a user, I want one task answered through a provider so that the first conversational capability
> is available.

Complete this story when deltas, completion, provider failure, and cancellation all flow through
the fake-provider path and terminal event invariants hold.

### CAH-022 — Enforce loop limits

> As a user, I want the harness to stop predictably at configured limits so that faulty sequences
> cannot run indefinitely.

Complete this story when every limit is covered by deterministic tests and the transcript identifies
the exact limit reached.
