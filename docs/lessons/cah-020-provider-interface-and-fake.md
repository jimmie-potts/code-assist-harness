# CAH-020 lesson: Provider interface and deterministic fake

- **Unit:** CAH-020
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no provider port or fake provider exists yet
- **Story:** [CAH-020](../../user-stories/cah-020-provider-interface-and-fake.md)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), and [Evaluation](../evaluation.md)

> This lesson explains an accepted provider boundary and its planned first implementation. It does
> not claim that provider types, a fake, or a model integration are currently shipped.

## Quick summary

This unit plans a harness-owned streaming provider port and a programmable, network-free fake. It
teaches how a narrow boundary protects the agent loop from SDK types while making timing, failure,
tool-call, usage, and cancellation behavior deterministic in tests.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a provider-neutral domain contract from a vendor SDK mapping;
- model a typed stream whose variants are explicit and exhaustively handled;
- script a strict fake that verifies requests as well as emitted responses; and
- compare an in-process fake with production provider gateways and contract-testing systems.

## Why this unit matters

CAH-021 cannot prove one model turn safely until the loop can be tested without HTTP or credentials.
If SDK objects enter core state, provider changes redefine the domain and make failure fixtures
fragile. If the fake merely returns canned text, it cannot expose cancellation races, malformed tool
arguments, unexpected requests, or unconsumed stream events.

## Key concepts

- **Port:** a harness-owned protocol describing what the loop needs from any model provider.
- **Adapter:** provider-specific code that translates between that port and an SDK or HTTP API.
- **Provider request:** model-facing conversation, instructions, and options represented only with
  harness types.
- **Stream event:** one typed provider-neutral observation such as text delta, tool-call request,
  usage, completion, or failure.
- **Strict fake:** a deterministic provider that checks the exact expected request and emits a
  scripted sequence, failing when either side of the script is left unmatched.
- **Normalization:** conversion of provider-specific status, error, and usage shapes into bounded
  domain values.

## Architecture and design

```text
agent loop --> Provider port --> deterministic fake (tests)
                         |
                         +----> future OpenAI adapter --> provider SDK
```

The Python harness owns provider request and stream types, interpretation, lifecycle, and terminal
session decisions. An adapter owns SDK construction and mapping. The fake implements the same port,
but it does not imitate a vendor SDK; it describes scenarios in domain terms.

The planned stream needs variants for text deltas, completed text, tool-call requests with serialized
arguments, usage, normal completion, and structured failure. Cancellation must be an operation-level
contract: callers know how to request it and what cleanup they may await.

Important invariants:

- core provider requests and events import no OpenAI, LangChain, or other provider classes;
- the fake rejects an unexpected request, omitted request, or unconsumed scripted event;
- only normalized, bounded failures may become domain events or transcripts;
- default provider tests require no network, API key, or provider SDK installation; and
- cancellation checkpoints are deterministic enough to exercise before-output and between-delta
  behavior.

## Practical walkthrough

1. Start with small immutable request types for conversation items, repository instructions, and
   provider options. Avoid copying an SDK's complete request schema into the port.
2. Define a discriminated stream-event union. Make event names express harness meaning and require
   explicit handling so a newly added variant cannot be silently ignored.
3. Specify an async provider operation that yields those events and supports cancellation. Document
   whether cleanup completes before iteration ends and how cancellation differs from provider
   failure.
4. Build fake scripts from ordered expected-request and emitted-event steps. Include deliberate
   checkpoints or an injected scheduler instead of real sleeps.
5. Produce an actionable structural diff when an actual request differs from its expectation. Do
   not dump credentials or an unbounded conversation into the failure message.
6. At test teardown, assert that every expected request and event was consumed. A passing partial
   script can hide a loop that stopped too early.
7. Exercise text, tool-call, usage, completion, provider error, malformed arguments, and cancellation
   variants entirely in memory.
8. Prove the domain modules import and tests pass with provider SDK and LangChain packages absent.

Success means the same loop-facing test can swap fake implementations without changing domain
types, and every deviation from a scripted interaction points to the exact mismatched step.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Loop sends an extra request | Fake reaches the end of expected requests | Test fails with request number and bounded structural difference |
| Loop stops before script ends | Expected events remain unconsumed | Teardown fails instead of reporting a false pass |
| Tool arguments are malformed | Stream carries an invalid serialized argument value | Domain receives the planned malformed case without executing a tool |
| Provider raises an SDK exception | Adapter boundary catches provider detail | Normalized failure omits raw response, credential, and SDK object |
| Cancellation occurs between deltas | Fake pauses at a controlled checkpoint | Operation observes cancellation and emits no later scripted delta |

## Production expansion

### Example enterprise scenario

Consider a company with separate product teams using several approved model endpoints across regions.
Platform engineers need a stable internal contract, provider conformance tests, controlled rollout,
cost and latency telemetry, and the ability to route around a regional outage. That exceeds a
single-process port and fake, but the same ownership boundary remains useful.

### Typical production capabilities and tools

These official references illustrate capabilities rather than required or endorsed products:

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses) illustrates the
  first adapter's concrete streaming, usage, and tool-call surface. OpenAI's
  [background-mode limits](https://developers.openai.com/api/docs/guides/background#limits)
  distinguish foreground cancellation by terminating the active connection from cancellation of a
  durable background response; the adapter must map the mode it actually uses.
- [Pact](https://docs.pact.io/) illustrates consumer-driven contract tests between independently
  deployed clients and provider-facing services.
- [WireMock stubbing](https://wiremock.org/docs/stubbing/) illustrates controlled HTTP behavior for
  adapter tests that need transport-level responses without a live model service.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate interoperable telemetry fields for model operations while requiring deliberate
  content and privacy controls.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Providers | One planned real adapter plus a domain fake | Multiple endpoints, regions, versions, and routing policy |
| Contract | In-process Python protocols and types | Versioned service contract and compatibility governance |
| Testing | Strict deterministic fake | Fake plus transport stubs, conformance suites, and staged canaries |
| Reliability | Caller receives normalized failure | Health-aware routing, isolation, retry budgets, and failover |
| Observability | Assertions and bounded usage events | Central latency, error, cost, and saturation telemetry |
| Cost | Small explicit interface | Gateway infrastructure, platform ownership, and integration upkeep |

### Trade-offs and graduation signals

A gateway can centralize credentials, routing, quotas, and telemetry, but it adds another network hop,
failure domain, compatibility surface, and owning team. Graduate when two or more production
providers must satisfy the same application contract, several teams duplicate adapter controls, a
regional availability objective requires routing, or provider changes repeatedly break consumers.
Do not widen the local port speculatively to every feature offered by every provider.

## Practical exercises

1. Sketch the smallest request and stream-event union needed by CAH-020, then identify fields that
   belong only in a future adapter.
2. Script three deltas followed by completion and deliberately add an unexpected second request;
   design the error a learner should see.
3. Add a cancellation checkpoint before the first event and another between two events without using
   wall-clock sleeps.
4. Seed a provider exception with a fake token and prove normalization and transcript paths exclude
   both the token and raw exception object.
5. Compare a strict domain fake with an HTTP stub: list which bugs each can detect and which it
   cannot.

## Key takeaways

- The harness owns provider meaning; adapters own provider syntax.
- A useful fake verifies the loop's requests and stopping behavior, not only its happy-path text.
- Production gateways become worthwhile for demonstrated multi-team, multi-provider, or availability
  requirements, not as a prerequisite for a clean local port.

## Glossary

- **Adapter:** translation code between a harness port and one provider's API or SDK.
- **Conformance test:** evidence that an implementation obeys a shared behavioral contract.
- **Normalization:** mapping external values and failures into stable, bounded domain types.
- **Port:** a domain-owned interface required by core logic.
- **Scripted fake:** an in-memory implementation driven by ordered expectations and events.
- **Stream event:** one typed unit emitted during a provider operation.

See the shared [project glossary](../glossary.md) for provider, model turn, tool call, and cancellation.

## Further reading

- [CAH-020 user story](../../user-stories/cah-020-provider-interface-and-fake.md)
- [ADR 0001: Own the agent loop](../adr/0001-own-the-agent-loop.md)
- [Agent loop: provider port](../agent-loop.md#provider-port)
- [Evaluation: scenario model](../evaluation.md#scenario-model)
- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Pact documentation](https://docs.pact.io/)
- [WireMock stubbing](https://wiremock.org/docs/stubbing/)
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
