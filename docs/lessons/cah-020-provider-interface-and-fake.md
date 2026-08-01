# CAH-020 lesson: Provider interface and deterministic fake

- **Unit:** CAH-020
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; the provider-neutral port and strict fake are implemented and
  tested without a provider SDK, API key, or network request
- **Story:** [CAH-020](../../user-stories/cah-020-provider-interface-and-fake.md)
- **Visual companion:**
  [A stable socket for model streams](assets/cah-020-provider-interface-and-fake.pptx)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Evaluation](../evaluation.md)

> This lesson describes the shipped CAH-020 provider contract and fake. The code samples below are
> excerpts from the implementation and tests, not aspirational pseudocode. The current TUI still
> runs `MockSession`; CAH-021 now proves one injected provider-neutral turn without changing that
> launched path.

## Quick summary

CAH-020 adds a harness-owned vocabulary for one model request and its streamed response, plus a
strict in-memory fake that can pause, fail, and cancel at exact points. The central rule is simple:
the harness owns the meaning of a model turn, while a future adapter owns vendor syntax.

## Learning objectives

After completing this unit, you should be able to:

- explain a port, adapter, async iterator, and strict fake in plain language;
- identify which provider values may cross into the agent-loop domain;
- read a discriminated event union and follow one event through an async stream;
- script and verify exact request, delay, failure, and cancellation behavior;
- explain why cancellation is not represented as a provider failure; and
- compare this in-process fake with transport stubs and production provider gateways.

## Why this unit matters

The provider-neutral turn implemented in CAH-021 must react to partial text, tool requests, usage,
failures, and user cancellation. Testing those branches against a live API would be slow, variable,
credential-bound, and hard to force into rare races. Allowing SDK objects into the loop would make
vendor response shapes part of the project's domain.

CAH-020 creates a smaller, stable seam first. Later code can depend on `ProviderRequest`,
`ProviderStreamEvent`, and `ProviderOperation` without knowing whether the implementation is the
strict fake or a future OpenAI adapter.

## Junior engineer foundation

### 1. A port is a promise; an adapter is a translator

Imagine a wall outlet. The outlet shape is the **port**: it states what a device may rely on. A travel
plug is the **adapter**: it translates one country's physical plug into that stable shape.

In this project:

- `Provider` and `ProviderOperation` are the port;
- `FakeProvider` is one implementation used by tests; and
- the future OpenAI adapter will translate SDK values into the same harness-owned types.

The port should describe what the agent loop needs, not every feature a vendor offers.

### 2. A frozen dataclass is a small value object

Python's `@dataclass` generates an initializer and value-based equality. `frozen=True` prevents field
assignment after construction, and `slots=True` prevents arbitrary new attributes. That makes a
request safer to compare in a strict fake:

```python
message = ProviderMessage(role="user", content="Explain this repository.")
request = ProviderRequest(conversation=(message,))
```

The comma in `(message,)` matters: it creates a one-item tuple. `(message)` is just the original
object inside parentheses.

### 3. An async iterator produces values over time

A normal function returns one value. An async iterator can yield several values while other work,
such as terminal input or cancellation, continues:

```python
events = operation.events()
first = await anext(events)
second = await anext(events)
```

`await` pauses this task without blocking the entire event loop. `anext` asks for one more value.
An `async for` loop repeats that process until the iterator raises `StopAsyncIteration`.

### 4. Stream completion has two layers

`ProviderTextCompleted("hello")` means, “the provider says the final assistant text is `hello`.”
`ProviderCompleted()` means, “the entire provider operation ended normally.” They are deliberately
separate. A response may also report usage or tool calls before the operation closes.

CAH-021 compares completed text with accepted deltas and decides which session events to emit.
CAH-020 itself only defines the observations.

### 5. A fake is not merely a hard-coded answer

A useful fake is a tiny programmable implementation of the same interface as production code. This
fake verifies the request and controls the response. It can say:

1. expect this exact request;
2. emit one delta;
3. stop at a named checkpoint;
4. wait for cancellation; and
5. prove no later delta escaped.

A canned function that always returns `"hello"` cannot detect an extra request, early consumer stop,
or cancellation race.

### 6. Cancellation and failure answer different questions

- **Failure:** the provider operation tried to continue but ended unsuccessfully.
- **Cancellation:** the caller asked active work to stop.

The provider emits `ProviderFailed` for the first case. In the second case, `cancel()` closes the
stream and waits for cleanup without inventing a failure event. The session layer already knows why
it requested cancellation.

### Common beginner misconceptions

| Misconception | More accurate model |
| --- | --- |
| “A `Protocol` sends network protocol messages.” | Python `Protocol` describes a structural interface; this one performs no network I/O itself. |
| “A fake is less strict than production.” | This fake is intentionally stricter about test expectations so orchestration bugs fail quickly. |
| “If I received the last text delta, the operation is complete.” | Text, usage, tool requests, and terminal response state are distinct observations. |
| “Cancelling the consumer task is the same as provider cancellation.” | Consumer task cancellation aborts local iteration; `operation.cancel()` owns provider cleanup and the no-later-event guarantee. |
| “Malformed tool JSON should be rejected by the provider type.” | The provider boundary preserves serialized arguments; the later harness tool boundary validates them. |

## Key concepts

- **Provider request:** an immutable ordered conversation plus caller-supplied repository
  instructions. It contains no SDK value, credential, model-specific option, or file discovery.
- **Stream event:** one of six harness-owned observations: delta, completed text, requested tool
  call, usage, normal operation completion, or normalized failure.
- **Provider operation:** the single-consumer event stream plus `cancel()` and `wait_closed()`
  cleanup contracts.
- **Normalization:** mapping external provider details into a bounded stable code, safe message, and
  retryability observation.
- **Strict fake:** an ordered request/step script that fails for mismatches, omitted requests,
  unconsumed output, or unfinished operations.
- **Deterministic gate:** a named delay or cancellation checkpoint controlled by the test instead of
  a wall-clock sleep.

## Architecture and design

```text
                  harness-owned domain
                  ┌───────────────────────────────┐
agent loop (next) │ ProviderRequest               │
        ─────────>│ ProviderOperation.events()     │
                  │ ProviderStreamEvent union      │
                  │ cancel() / wait_closed()       │
                  └──────────────┬────────────────┘
                                 │ same port
                    ┌────────────┴────────────┐
                    v                         v
             FakeProvider               OpenAI adapter
             implemented                future CAH-023
             no network                 SDK stays here
```

Concrete ownership:

| Module | Responsibility |
| --- | --- |
| [`provider/models.py`](../../src/code_assist_harness/provider/models.py) | Immutable requests, messages, instructions, event variants, usage, and normalized failure |
| [`provider/port.py`](../../src/code_assist_harness/provider/port.py) | Structural provider and operation protocols, including cleanup semantics |
| [`provider/fake.py`](../../src/code_assist_harness/provider/fake.py) | Ordered exchanges, deterministic gates, single-consumer operations, safe mismatch paths, and exhaustion checks |
| [`provider/__init__.py`](../../src/code_assist_harness/provider/__init__.py) | Intentional package API |
| [`tests/provider/`](../../tests/provider) | Contract, import-isolation, script, failure, delay, mismatch, and cancellation evidence |

Important invariants:

- provider-domain modules import no OpenAI, LangChain, HTTP, or network package;
- every non-cancellation fake exchange ends with one `ProviderCompleted` or `ProviderFailed`;
- one operation event stream can be claimed only once;
- awaited cancellation closes the iterator and guarantees no later yield;
- cancellation checkpoints intentionally suppress their scripted suffix;
- ordinary early consumer stop leaves steps unconsumed and fails verification;
- mismatch diagnostics name only exchange ordinals and field paths, never request content; and
- raw provider payloads are not provider events or transcript inputs.

CAH-021 now supplies event-to-session mapping through an injected composition seam. Deliberately
deferred work includes CAH-022 hard limits, CAH-023 OpenAI adapter activation and model selection,
tool definitions, repository-instruction discovery, retries, and broader TUI integration.

## Practical walkthrough

1. Construct ordered `ProviderMessage` and `RepositoryInstruction` values, then place them in a
   frozen `ProviderRequest`.
2. Choose explicit stream observations. Tool arguments remain serialized—even malformed JSON is a
   valid provider observation—because parsing belongs to the harness tool boundary.
3. Start a `ProviderOperation`, claim `events()` once, and consume until `ProviderCompleted` or
   `ProviderFailed`.
4. For a deterministic delay, add `FakeProviderDelay("name")`, await
   `operation.wait_for_checkpoint("name")`, and call `release_checkpoint("name")`.
5. For a cancellation race, add `FakeProviderWaitForCancellation("name")`, wait until it is reached,
   then await `operation.cancel()`. The scripted suffix must not appear.
6. Call `fake.assert_complete()` at test teardown. A missing request or partial stream turns the
   test red instead of silently passing.
7. Keep `MockSession` in the launched runtime. CAH-021 now adds an injected turn seam and maps this
   stream into authoritative session events; CAH-023 will activate it with explicit provider and
   model configuration after hard limits exist.

## Implementation code samples

These excerpts are copied from the implemented repository rather than invented pseudocode.

### Sample 1: the request is small, ordered, and immutable

From [`provider/models.py`](../../src/code_assist_harness/provider/models.py):

```python
@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """Immutable harness-owned input for exactly one model turn.

    Conversation and repository-instruction order are significant. The request deliberately omits
    SDK response objects, provider credentials, model-specific options, and instruction discovery.

    Args:
        conversation: Non-empty ordered model-facing history.
        repository_instructions: Ordered caller-supplied repository guidance.
    """

    conversation: tuple[ProviderMessage, ...]
    repository_instructions: tuple[RepositoryInstruction, ...] = ()
```

`frozen=True` prevents mutation after creation. Both fields use tuples so order is preserved and the
fake can compare exact values. The default `()` means a repository with no supplied instruction is
still legal. Discovery is absent on purpose: the caller must supply already-selected instructions.

### Sample 2: the union lists every legal stream observation

From [`provider/models.py`](../../src/code_assist_harness/provider/models.py):

```python
type ProviderStreamEvent = (
    ProviderTextDelta
    | ProviderTextCompleted
    | ProviderToolCallRequested
    | ProviderUsageReported
    | ProviderCompleted
    | ProviderFailed
)
"""One provider-neutral observation emitted while a model turn is active."""
```

The `|` operator forms a union type: an event must be one of those six classes. A later loop can use
`isinstance` to handle each variant explicitly. Adding a seventh variant is visible code review
work rather than an unstructured dictionary key appearing at runtime.

The tool-call class deliberately stops before parsing:

```python
class ProviderToolCallRequested:
    """One provider-requested tool call with deliberately unparsed arguments.

    ``arguments_json`` may be malformed. Parsing, tool lookup, validation, policy, and execution
    remain harness-loop responsibilities rather than provider-boundary behavior.
    """

    kind: ClassVar[Literal["tool.call_requested"]] = "tool.call_requested"
    call_id: str
    name: str
    arguments_json: str
```

That separation lets tests deliver `{"path":"README.md"` with a missing brace. The later tool
validator—not the adapter—must decide that the call is invalid and prevent execution.

### Sample 3: cancellation is an awaited cleanup contract

From [`provider/port.py`](../../src/code_assist_harness/provider/port.py):

```python
async def cancel(self) -> ProviderCancellationResult:
    """Request cancellation and wait until provider cleanup finishes.

    Returns:
        ``cancelled`` when this call stopped active work, or ``already_closed`` when normal
        completion, failure, or an earlier cancellation had already closed the operation.

    Note:
        Once this awaitable returns, the iterator is closed and cannot yield another event.
        Implementations must release provider-specific stream resources before returning.
    """
    ...

async def wait_closed(self) -> None:
    """Wait for natural completion, failure, or cancellation cleanup.

    After this method returns, no later provider event may be yielded. Waiting does not request
    cancellation and is safe to repeat.
    """
    ...
```

`async def` means cleanup can itself take time without blocking the event loop. The return value
makes repeated or late cancellation explicit. `wait_closed()` observes closure but does not request
it, which keeps “stop” separate from “wait.”

### Sample 4: strict verification detects work that quietly stopped

From [`provider/fake.py`](../../src/code_assist_harness/provider/fake.py):

```python
def assert_complete(self) -> None:
    """Assert that every expected request and stream step was consumed exactly once.

    Raises:
        FakeProviderMismatch: If a started operation is unfinished, a consumer stopped early,
            or one or more expected requests were omitted.
    """
    for operation in self._operations:
        failure = operation.verification_failure()
        if failure is not None:
            raise FakeProviderMismatch(failure)
    if self._next_exchange_index < len(self._exchanges):
        remaining = len(self._exchanges) - self._next_exchange_index
        raise FakeProviderMismatch(
            f"fake provider expected request {self._next_exchange_index + 1}, "
            f"but {remaining} exchange(s) were never started"
        )
```

The first loop checks every stream already started. The final comparison catches an expected
request that never happened. Without this teardown assertion, a loop that exits too early might
look successful because no exception occurred during the consumed prefix.

### Sample 5: a cancellation race with no sleep

From [`tests/provider/test_fake.py`](../../tests/provider/test_fake.py):

```python
assert await anext(events) == ProviderTextDelta("first")
pending_event = asyncio.create_task(anext(events))
await operation.wait_for_checkpoint("between-deltas")
assert await operation.cancel() == "cancelled"
with pytest.raises(StopAsyncIteration):
    await pending_event
with pytest.raises(StopAsyncIteration):
    await anext(events)
fake.assert_complete()
```

The test accepts the first delta, starts waiting for the next event in a separate task, and then
waits for the fake's named checkpoint. No millisecond guess is involved. After cancellation, both
the already-pending read and a later read must observe the closed iterator. The final assertion
proves the cancellation checkpoint consumed its intended script branch.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Actual request differs | `start()` raises `FakeProviderMismatch` | Diagnostic identifies the exchange and field path but excludes both request contents |
| Extra request | Script has no next exchange | Immediate bounded mismatch names the unexpected request ordinal |
| Omitted request | Test body ends before `start()` | `assert_complete()` names the first unstarted exchange |
| Consumer stops after one delta | Operation remains at its next scripted step | `assert_complete()` reports the exact step kind without dumping event data |
| Malformed tool arguments | `arguments_json` is invalid JSON | Event preserves the string unchanged; no tool is parsed or executed in this unit |
| Normalized provider failure | Terminal event is `ProviderFailed` | Only stable code, bounded safe message, and retryability cross the boundary |
| Cancellation before output | Cancellation checkpoint is first | `cancel()` closes cleanly and the iterator yields nothing |
| Cancellation between deltas | First delta is accepted, checkpoint blocks the next read | Awaited cancellation closes the pending read and suppresses the suffix |
| Consumer task is cancelled | Local `anext` task receives `CancelledError` | Operation closes, but unconsumed script still fails strict verification |

Transcript tests preserve the CAH-011 boundary: they store reducer-approved lifecycle inputs, not
provider events. A regression maps an already-normalized failure into a validated `session.failed`
test event and proves that a local raw adapter object, fake token, and body marker never enter the
transcript. CAH-021 now implements the actual provider-to-session mapping; this CAH-020 regression
remains intentionally limited to the provider-boundary handoff.

## Production expansion

### Example enterprise scenario

Consider several teams using approved model endpoints in multiple regions. Platform engineers may
need a stable internal contract, adapter conformance suites, credential isolation, cost and latency
telemetry, compatibility rollout, and outage routing. Those needs exceed this single-process port
and fake, but the ownership rule still applies.

### Typical production capabilities and tools

These are capability comparisons, not project dependencies:

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) is the intended
  first concrete adapter surface. It adds credential rotation, quota/spend monitoring, API
  compatibility work, content-retention decisions, and stream cleanup.
- [Pact](https://docs.pact.io/) illustrates consumer-driven contract testing when the provider
  boundary becomes an independently deployed service. It adds broker operations, contract
  versioning, provider verification, and coordinated release gates.
- [WireMock](https://wiremock.org/docs/stubbing/) illustrates transport-level HTTP stubbing for
  adapter tests. It catches serialization and status-mapping bugs that an in-process domain fake
  cannot, but representative stubs must be maintained.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate shared model-operation telemetry. Adoption adds collector pipelines, cardinality and
  storage cost, semantic-convention upgrades, and privacy review.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Provider scope | One narrow port, strict fake, future OpenAI adapter | Multiple endpoints, regions, versions, and routing rules |
| Contract | In-process frozen dataclasses and Python protocols | Versioned service/API contract and compatibility governance |
| Testing | Exact domain request/event scripts | Domain fake plus adapter stubs, conformance tests, and staged canaries |
| Timing | Named zero-clock gates | Real transport deadlines, retry budgets, backpressure, and failover |
| Failure data | Bounded normalized values | Central classification, redaction policy, telemetry, and incident evidence |
| Operations | No service and no network in default tests | Gateway availability, ownership, credentials, observability, and on-call load |
| Cost | Small code and cognitive surface | Infrastructure, latency, governance, and integration maintenance |

### Trade-offs and graduation signals

The strict fake is fast and makes orchestration timing exact, but it cannot prove HTTP headers, SDK
stream framing, real quota behavior, or vendor compatibility. Transport stubs cover more adapter
syntax but are slower and can drift from the provider. A gateway centralizes credentials, routing,
quotas, and telemetry, but creates another network hop and failure domain.

Graduate when two or more production providers must satisfy the same application contract, several
teams duplicate adapter controls, a regional availability objective requires routing, or provider
changes repeatedly break consumers. Do not widen the local port speculatively to every vendor
feature.

## Practical exercises

1. Add a second repository instruction and intentionally reverse its order. Predict and then inspect
   the fake's content-safe mismatch path.
2. Replace `ProviderCompleted()` with `ProviderFailed(...)` in a script and trace why cancellation is
   still a separate outcome.
3. Remove the final `fake.assert_complete()` from an early-stop test. Explain the false-positive
   behavior it would permit.
4. Add `FakeProviderDelay("usage-ready")` before a usage event and prove the test blocks and resumes
   without `asyncio.sleep`.
5. Pass malformed tool JSON through the fake, then sketch the later validation boundary that must
   reject it before execution.
6. Draw a mapping table from a vendor SDK's stream items to the six provider-domain variants. Mark
   every vendor-only field that should stay inside the adapter.

## Key takeaways

- The harness owns model-turn meaning; adapters own vendor syntax.
- A strict fake verifies requests and stopping behavior, not only returned text.
- Async cancellation is a cleanup contract: after it returns, no event may arrive.
- Completed text and completed operation are distinct observations.
- Beginner-friendly boundaries are also production-friendly boundaries: each responsibility has one
  clear owner.
- Add transport or gateway machinery only when measured integration or operational needs justify it.

## Glossary

- **Adapter:** code that translates provider SDK or HTTP values into the harness port.
- **Async iterator:** an object that produces ordered values over time through awaited `anext`
  calls.
- **Cancellation checkpoint:** a named scripted point where the fake waits for cancellation and
  suppresses later output.
- **Deterministic delay:** a named test-controlled gate that requires no wall-clock sleep.
- **Normalization:** conversion of external failures into bounded stable domain values.
- **Port:** the harness-owned interface required by core logic.
- **Strict fake:** an in-memory provider implementation that checks exact requests and complete
  script consumption.
- **Stream event:** one typed provider-neutral observation during an operation.

See the shared [project glossary](../glossary.md) for provider, model turn, tool call, cancellation,
and transcript terminology.

## Further reading

- [CAH-020 user story](../../user-stories/cah-020-provider-interface-and-fake.md)
- [ADR 0001: Own the agent loop](../adr/0001-own-the-agent-loop.md)
- [Agent loop: provider port](../agent-loop.md#provider-port)
- [Evaluation: scenario model](../evaluation.md#scenario-model)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Pact documentation](https://docs.pact.io/)
- [WireMock stubbing](https://wiremock.org/docs/stubbing/)
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
