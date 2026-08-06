# Agent Loop

> Status: incremental model-loop implementation. CAH-021 completes one provider-neutral turn,
> CAH-022 hard-bounds it, and CAH-023 activates it through an explicitly selected OpenAI Responses
> adapter. CAH-032 through CAH-039 now define the implementation-ready M2 tool-exchange and
> iterative-loop sequence in documented dependency order, but none is implemented. The launched
> `main()` path and TUI still
> default to `MockSession`.

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

A provider adapter owns translation between the implemented provider-neutral types and its SDK. The
OpenAI implementation also owns its SDK client, stream automaton, and resource cleanup; none escapes
the adapter. The deterministic fake implements the same port without an SDK or network access. The TUI
displays events and sends commands; it does not
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
- Provider operations are awaited child tasks so cancellation and deadlines can propagate.
- M2 native read tools execute synchronously under hard work bounds, with cancellation and deadline
  checks immediately before and after the call; if cancellation wins while a handler runs, its late
  result is discarded rather than represented as preemptively reaped.
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

CAH-021 adds a parallel provider composition seam. When `run_runtime` receives a `Provider`,
`ProviderSessionRunner` creates one `ProviderSession` instead of a `MockSession`.
CAH-022 gives each created session a fresh mutable limit tracker under one immutable limits value. The
session starts at most one operation and claims its stream exactly once when admission succeeds. Each
accepted lifecycle publication is a shielded, ordered, non-interleaved transaction under the session
decision lock: protocol write, Python reduction, and transcript-observer attempt settle before
cancellation or teardown may select an outcome. An ordinary later sink or observer failure does not
roll back an earlier accepted view. CAH-023 keeps the mock default but lets `main()` supply the
concrete adapter only after the TUI and Python composition roots validate `--provider openai --model
gpt-5.6-luna`. Provider selection does not alter the TypeScript protocol-v1 projection.

## Bounded loop

Conceptually, one session follows this algorithm:

```text
accept task and emit session.started
while session is active:
    check cancellation, deadline, and limits
    build bounded context and provider-neutral request
    call provider and stage the complete response privately
    validate one closed final-text-or-single-call grammar
    if the admitted outcome is ordinary assistant text:
        atomically reserve output, publish its staged chunks, and complete the session
    if the admitted outcome is one tool call:
        charge the observation, then validate the request
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
without requesting cancellation. `force_cancel_cleanup()` is a required session-only fallback after
the five-second cleanup grace: it cancels and reaps all operation-owned local work without shielding,
closes the stream logically, and prevents later events. It confirms local task termination, not remote
resource release.

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
consumes this port for one turn, CAH-022 enforces its four configurable hard limits, and CAH-023 maps
the same port to OpenAI Responses without changing its types.

## OpenAI Responses adapter

`openai_config.py` validates provider, exact model ID, environment names, and
`OPENAI_API_KEY` without importing the SDK. The mock ignores ambient provider credentials. OpenAI is
constructed only after explicit selection; every other `OPENAI_*` variable is rejected with a fixed
message rather than being inherited as hidden SDK routing. `SSLKEYLOGFILE` is stripped by the normal
supervisor and rejected again at the provider boundary; Python starts with `-E` so remaining ambient
`PYTHON*` settings cannot alter the child interpreter.

`openai_responses.py` maps the ordered conversation and caller-supplied instructions into one
foreground text request with `background=false`, `store=false`, reasoning effort `none`,
current-turn reasoning context, a generated-token cap, no tools, and no tool choice.
`Provider.start()` remains synchronous, lazy, and I/O-free. Consuming the operation creates one async
client and one stream, validates the exact lifecycle/item/text/completion sequence, and exposes only
provider-neutral text, usage, completion, or fixed failure values. One optional opaque empty
reasoning envelope before the message is validated and suppressed. Tool, reasoning text/summary,
multimodal, duplicate, missing, or inconsistent observations fail closed without retaining raw values.
Assistant text preserves TAB/LF layout and rejects every other C0/C1 terminal control before the
fragment is retained or emitted; both wire validators enforce the same invariant before rendering.
Message items must move from `in_progress` to `completed`, and the completed response must echo the
reviewed reasoning effort `none` and context `current_turn` before completion is trusted.
An SDK create or read awaitable that independently raises `CancelledError` becomes a bounded provider
failure; only cancellation selected by the operation remains cancellation control flow.

Natural termination and cancellation converge on one operation-owned, shielded cleanup task that
attempts both stream and client close. A cleanup failure becomes one safe adapter exception consumed
by the existing `ProviderSession` cleanup boundary; it never changes the already selected session
failure. A close coroutine that independently raises `CancelledError` is treated as a bounded cleanup
failure so the other resource is still attempted; only cancellation of the cleanup owner remains task
control flow and stops the remaining sequential closes. Ordinary `cancel()` and `wait_closed()`
joiners shield the owner. Only `ProviderSession`, after its cleanup grace expires, calls the
provider-neutral force-reap hook to cancel and await the owner directly. SDK objects, exceptions,
request IDs, headers, and raw response bodies remain inside the adapter. The credential is confined
to the provider-specific validation, composition, and adapter boundary and never enters a
provider-neutral or protocol value. Deterministic SDK fakes cover this path by default; the separately
selected live smoke remains outside the canonical gate and default CI.

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
safe `provider_invalid_response` failure. TAB and LF are the only admitted C0 layout characters;
another C0 or any C1 control makes the provider observation invalid before publication.

Empty completed text has one deliberately narrow non-success use: the session may retain it as a
candidate until a following tool request arrives. That request still becomes `tool_unavailable` and
triggers cancellation. Empty text cannot authorize usage or provider completion, so it never emits
an empty `assistant.completed` event.

The turn rejects a delta in full before emission when cumulative accepted assistant text would exceed
the configured UTF-8 output budget. This check runs before the fixed 8,192-byte
protocol-compatibility ceiling, so `assistant_output_limit_exceeded` wins when both would reject the
same delta. A `ProviderFailed` observation becomes one normalized `session.failed` outcome. A tool
request is counted before any handling; the first admitted request still becomes `tool_unavailable`,
triggers operation cancellation, and never exposes or parses its arguments.

Optional usage is bounded to non-negative JavaScript-safe integers and recorded outside lifecycle
state as `model.usage_observed`. For a completed OpenAI response, input plus output must equal total,
reasoning tokens cannot exceed output tokens, and output tokens cannot exceed the same fixed 8,192
generation cap sent in the request. A violation becomes `invalid_response` before usage or completion
evidence is admitted. Valid usage consumes neither a protocol-v1 sequence number nor a reducer
transition. The version-3 writer stores the observation before the terminal record, and replay of
versions 1, 2, and 3 exposes it through a separate evidence projection. Usage admission shares the
decision lock, so an admitted evidence write settles before cancellation competes, while a terminal
outcome that wins first suppresses later usage.

Completion, normalized failure, user cancellation, invalid response, limit exhaustion, and runtime
teardown select one shared outcome before cleanup. User cancellation calls and awaits
`ProviderOperation.cancel()`. Shutdown, stdin EOF, or outer-task cancellation use teardown: they
cancel and join active provider work without fabricating `session.cancelled`, leaving an incomplete
replayable transcript prefix when teardown wins.

Provider cleanup uses exactly one loop-owned task per session. The deadline watcher may start that
task in cancellation mode, and the finalizer joins the same task instead of invoking cleanup again.
Every `cancel()` or `wait_closed()` await is supervised by a fixed five-second local grace. A cleanup
task already complete when the grace wakes wins the tie. Otherwise the loop cancels and reaps its
local barrier task, then invokes required `force_cancel_cleanup()` to cancel and await the actual
provider-owned cleanup and SDK tasks without shielding. The loop also cancels and awaits any pending
local read. A cleanup failure or grace expiry emits at most one start-correlated, payload-free
`provider_cleanup_failed` diagnostic before any selected terminal and cannot rewrite that outcome.
Force-reap guarantees no provider-owned local task remains; remote release remains unconfirmed. These
bounds require cancellation-responsive provider awaitables; an implementation that suppresses task
cancellation requires stronger process isolation.

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
decision lock and shared finalizer. CAH-022 adds limit exhaustion and a separately latched provider
deadline to that competition. Tool execution remains a later extension. It is not safe to rely on
every provider or executor stopping immediately after cancellation.

## Limits and failures

CAH-022 implements an immutable four-field `LoopLimits` configuration for provider-backed
sessions. It rejects booleans and out-of-range values rather than clamping or disabling a budget:

| Field | Default | Allowed range | Accounting point |
| --- | ---: | ---: | --- |
| `max_model_turns` | `1` | `1..16` | Immediately before `Provider.start()` |
| `provider_work_timeout_seconds` | `120` | `1..3600` | Absolute deadline captured at session allocation |
| `max_assistant_output_bytes` | `4096` | `1..8192` | Cumulative UTF-8 bytes before delta publication |
| `max_observed_tool_calls` | `1` | `1..64` | Each tool request before parsing or handling |

`ProviderSessionRunner` shares the immutable configuration but creates a fresh mutable tracker for
every session ID, so counts never leak across sequential sessions. Model-turn denial starts and
cancels nothing. An over-budget output delta is rejected in full. A tool-call attempt is counted
before its decision, so the rejecting observation is retained as the configured maximum plus one.
Provider-reported usage remains observational metadata and cannot replace these counters.

The provider-work deadline is `monotonic_now() + provider_work_timeout_seconds`, captured when the
accepted command allocates the session before transcript setup or observer attachment. A separate
watcher races each provider-stream wait and checks the clock again after it wakes. At an exact
event/deadline tie, `monotonic_now() >= deadline` makes expiry win and the event is not admitted.
Admission and deadline latching share a small guard: latch-first starts no operation; admission-first
installs exactly one lazy operation for the watcher to cancel.

The watcher does not acquire the publication lock before latching expiry and starting the shared
cleanup task. It can therefore request provider cancellation while an already-admitted wire or
transcript sink is blocked. That ordered, non-interleaved publication transaction still completes its
wire write, reducer acceptance, and transcript-observer attempt before terminal selection sees the
latch. An ordinary later failure does not roll back an earlier accepted view. The deadline is not a
terminal-latency timeout: it bounds provider work, not local sink latency.

Each limit produces one safe `session.failed` payload with a distinct stable code:

- `model_turn_limit_exceeded`
- `provider_work_deadline_exceeded`
- `assistant_output_limit_exceeded`
- `tool_call_limit_exceeded`

With healthy persistence through terminal publication, the version-3 transcript writes one
`loop.limits_observed` record immediately before the terminal session event. It includes the four
configured values, admitted model turns and assistant bytes, observed tool calls, and the exhausted
limit if any. Writer and replay require an exhausted limit to match the exact adjacent
`session.failed` code and forbid a loop-limit failure code when no limit was exhausted. Replay accepts
versions 1, 2, and 3; version 3 also forbids a reserved limit-failure code without the evidence
record. A version-3 mock tape may omit this evidence because the launched `MockSession` does not use
the provider loop.

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

This story is complete. `loop_limits.py` owns the immutable configuration, validation, per-session
tracker, bounded observation, and stable exhausted-limit vocabulary. `provider_session.py` enforces
all four accounting points, exact deadline ties, blocked-publication cancellation, one supervised
cleanup task with a fixed five-second grace, and one terminal winner. `transcript.py` writes version 3
and restores `loop.limits_observed` evidence while retaining version-1 and version-2 replay. Runtime
tests prove fresh trackers and deadline capture before transcript setup. See the
[story](../user-stories/cah-022-enforce-loop-limits.md),
[implementation-backed lesson](lessons/cah-022-loop-limits.md), and
[visual companion](lessons/assets/cah-022-loop-limits.pptx).

### CAH-023 — Add the OpenAI Responses adapter

> As an explicitly configured user, I want the bounded provider-neutral turn to use OpenAI Responses
> so that the first real model capability is available without leaking SDK types into the harness.

This story is complete. The TUI and Python composition roots default to mock and require the explicit
OpenAI provider/model pair. SDK-free configuration rejects unsupported models, credentials, and
ambient OpenAI routing before lazy adapter construction. The adapter implements the reviewed
text-only stream automaton, fixed failure normalization, cancellation, and shared stream/client
cleanup behind the provider port. Deterministic SDK-fake tests run with network denied; the minimal
credentialed smoke requires separate explicit selection and remains outside the canonical gate and
default CI.

### CAH-032 — Define the provider-neutral tool contract

> As an agent-loop developer, I want selected context, prebuilt tool definitions, calls, and
> correlated results carried in one bounded harness request so that no provider owns loop semantics.

This [planned story](../user-stories/cah-032-define-provider-tool-contract.md) adds immutable,
SDK-free selected context, a bounded positional opaque-continuation item type, calls, results, and
ordered history to the provider port and strict fake. It consumes CAH-038's already-admitted
function-tool definitions unchanged; it neither defines nor rebuilds their schema. Each continuation is
one content-suppressed history item immediately before its call or assistant item, not a separate
request field. The full canonical request projection is capped at 512 KiB. It preserves raw arguments
and performs no argument interpretation, dispatch, or second turn. Exact-string and O(1)
character/cardinality gates run before UTF-8, tuple iteration, projection, or JSON encoding, so the
incremental request encoder never receives an unbounded caller string.
An MCP adapter may later translate into these values, but MCP transport and remote trust are separate
work.

### CAH-038 and CAH-039 — Bound definitions and admit arguments

CAH-038's [planned definition story](../user-stories/cah-038-canonicalize-provider-tool-definitions.md)
owns the strict portable schema subset and bounded registry-to-provider definition bridge. It invokes
schema generation only for the exact four native model identities and charges/omits expected
`title`/`default` annotations inside the same shape-directed pass, never a recursive pre-pass. CAH-039's
[planned argument story](../user-stories/cah-039-admit-provider-tool-arguments.md) owns unknown-name
lookup followed by the complete 16-KiB/64-level structural and signed-64-bit numeric preflight,
constant-rejecting pair decode, every-depth duplicate rejection, exact-key gate, and native Pydantic
validation. Its sole public catalog factory accepts one CAH-031 registry and invokes CAH-038's
definition bridge internally; callers cannot inject a separate definition tuple. CAH-032
construction and provider mapping reject malformed names or arguments above 16
KiB before this path; CAH-039 covers reachable at-limit carriers. Its immutable catalog owns the
exact CAH-031 registry identity, re-exposes the exact CAH-038 definitions used by requests, and binds
each prepared invocation to the same registry entry. It returns one prepared invocation or fixed
error and performs no dispatch.

### CAH-033 — Stage and validate one tool-aware response

> As a learner, I want the harness to admit a complete tool-aware response atomically so that an
> invalid provider grammar cannot publish partial text or authorize work.

This [planned story](../user-stories/cah-033-stage-and-validate-tool-aware-response.md) stages every
observation until the whole response is known to be final text, one content-free text-overflow
marker, or exactly one tool call. Normal neutral text carriers are exact built-in strings bounded to
8,192 characters/UTF-8 bytes; provider producers represent larger text only with the shared 8,193
marker. Only an accepted final-text branch may publish text, and only an accepted tool-call branch may be
returned for later dispatch. A normalized provider failure may terminate any otherwise valid
nonterminal prefix: the full prefix is discarded, its bounded failure classification is preserved,
and publication and dispatch remain zero. Premature EOF, mixed text/call output, a second call, or
invalid terminal ordering also produces zero publication and zero dispatch. Optional provider usage
remains candidate evidence until accepted final text completes the session.

### CAH-034 — Run one read-tool round trip

> As a learner, I want one explicit request, call, dispatch, result, and final response so that each
> ownership handoff is visible before general iteration.

This [planned story](../user-stories/cah-034-run-one-read-tool-round-trip.md) implements exactly two
fake-backed model turns around one native read dispatch. It calls CAH-039's registry-only catalog
factory, which invokes CAH-038 internally, advertises `catalog.definitions`, and admits calls through
that same object. Only after CAH-033 accepts the complete response does CAH-034's `dispatch_one`
identity-check the prepared value, call CAH-031 `dispatch_bound(entry, request)`, and construct the
correlated provider result. Cross-catalog input is a session failure before handler/replay/follow-up. A
CAH-039 fixed error causes zero dispatch and may replay against unchanged
context after the guarded handoff. After a successful dispatch, orchestration processes CAH-031's
ordered local `instruction_scopes`—the canonical request scope captured by the native operation's final
access-time admission, including an empty-list or no-match success, plus every model-visible result
owner. It never re-resolves the original alias. Context is atomically enriched before one canonical
correlated result envelope is replayed and `continuation? -> call -> result` is appended to the
single ordered history. CAH-031 admits only signed 64-bit integers and at most 64 complete-envelope
object/list levels in that canonical result projection, with the outer `result` object at depth 1. A
65,536-unit pre-serialization work budget bounds width before sorting/encoding, and a defensive
serializer `RecursionError`/`ValueError` maps to `invalid_read_tool_result`.
Synchronous native reads, instruction discovery, and context merge are bounded and non-preemptive;
one shared scheduling seam runs before dispatch, after dispatch, after every discovery, after every
merge, and before the follow-up start. After each discovery and its guard, the returned bundle's
`canonical_scope` must exactly equal the captured scope before merge; mismatch fails the transaction
without alias fallback. CAH-030 retains each binding's CAH-025 depth rank and CAH-032 copies that exact
precedence into provider context; neither layer derives it from list position or renumbers gaps. The
seam unconditionally yields once to the event loop outside locks, then applies the existing
cancellation/deadline guard. Tool results, instruction bundles, merged context, history, and the next
request stay local until the final guard passes, so another terminal commits none of
those candidates. A production-mode regression installs no awaited checkpoint hook, queues
cancellation on the same loop, and asserts at guard entry that the unconditional yield alone let it
latch; Event gates separately pause named stages. This does not claim that an in-flight synchronous
handler was reaped.

### CAH-035 — Run the bounded agent loop

> As a learner, I want the harness to iterate explicitly under small hard limits so that I can prove
> where agency lives and why the session stops.

This [planned story](../user-stories/cah-035-run-bounded-agent-loop.md) replaces the teaching branch
with a sequential state machine capped at four model turns and three within-budget tool calls. It
permits one call per turn, accumulates instructions for all direct and result-derived owner scopes
without removing prior context, reuses CAH-039's complete lookup-first bounded argument-admission
pipeline and CAH-034's guarded dispatch/enrichment path, keeps session limits cumulative while
reapplying the complete-request cap independently to each cumulative snapshot, and retains
exactly one rejecting fourth
observation when that limit wins, matching CAH-022 evidence semantics. It fails closed on mixed,
multiple, or parallel call shapes. Per-turn provider usage is staged and admitted privately; only
the complete optional session aggregate is persisted alongside accepted final assistant text, never
as a per-tool-turn lifecycle fact.
Planned CAH-037's composition root supplies the complete M2 profile explicitly as four turns, 120
seconds, 4,096 output bytes, and three observed calls instead of inheriting one-turn/one-call defaults.

### CAH-036 — Map OpenAI Responses tool calls

> As an explicitly configured OpenAI user, I want the provider-neutral loop translated to Responses
> function calling without giving the SDK orchestration authority.

This [planned story](../user-stories/cah-036-map-openai-tool-calls.md) maps exact local function
definitions, scoped instructions, untrusted repository evidence, streamed calls, and full stateless
call/result replay behind the existing adapter. Each opaque history item maps back to a reasoning item
at the same position. With `store=false`, replay includes each bounded
canonical full reasoning-item envelope from accepted prior turns—even while reasoning context remains
`current_turn`—so required IDs and item fields are not reduced to encrypted content alone. Optional
`content` and `status` use canonical null markers and are omitted on input replay only when null. The
core harness never interprets those envelopes. To ensure every accepted reasoning item has the payload
needed for later replay, every request—including turn one—sets exactly
`include=["reasoning.encrypted_content"]`. The adapter sets `parallel_tool_calls=false`, omits
`previous_response_id`, and rejects hosted or remote-MCP tools. Explicit OpenAI selection authorizes
bounded admitted repository-content egress for that session and must warn that allowed files are not
content-secret-scanned. Reasoning `id` and `encrypted_content` must be exact strings and pass O(1)
character plus strict UTF-8 byte ceilings before canonical replay serialization. Default evidence
remains SDK-fake and network-free. The OpenAI mapper saturates text at the first producer, joins only
bounded normal text once, and emits the content-free overflow observation only after raw terminal
structure is valid. Its mapped-empty event pump is iterative, and it drains raw terminal-to-EOF before
releasing the neutral terminal tuple; extra events or iterator failure discard that tuple.
