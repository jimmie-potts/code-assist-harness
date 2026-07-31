# CAH-020 - Define the provider interface and fake provider

- **Status:** In progress
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-010, CAH-011
- **Lesson:** [Provider interface and fake](../docs/lessons/cah-020-provider-interface-and-fake.md)
- **Visual lesson:** Pending generation and validation at
  `docs/lessons/assets/cah-020-provider-interface-and-fake.pptx`; Windows-native artifact-tool
  execution permission is still required

## User story

> As an agent-loop developer, I want a provider-neutral streaming interface and deterministic fake
> so that loop behavior can be tested without OpenAI.

## Scope

- Define provider-neutral request, stream-event, usage, failure, and cancellation contracts.
- Represent text deltas, tool-call requests, completion, and usage without importing an SDK into the
  domain layer.
- Build a programmable fake that scripts expected requests, emitted events, delays, failures, and
  cancellation checkpoints.
- Keep this story entirely network-free.

## Acceptance criteria

1. Provider request and stream types contain no OpenAI SDK or LangChain classes.
2. A provider request carries the model-facing conversation and repository instructions needed for
   one turn using harness-owned types.
3. Provider stream events can represent text deltas, completed text, tool-call requests, usage,
   normal completion, and structured failure.
4. Cancellation is an explicit provider-operation contract and documents what cleanup/completion the
   caller may await.
5. The fake provider is configured from an ordered sequence of expected requests and emitted events.
6. The fake fails with an actionable mismatch when the harness makes an unexpected request, omits a
   request, or leaves scripted events unconsumed.
7. Tests can deterministically simulate delayed output, provider failure, malformed tool arguments,
   usage reporting, cancellation before output, and cancellation between deltas.
8. Provider failures are normalized without persisting raw provider payloads or credentials.
9. Unit tests make no network requests and require no API key.
10. Public provider protocols and fake scripting APIs have typed signatures, Google-style docstrings,
    and examples for non-obvious sequencing behavior.

## Validation

- Run provider contract and fake-provider tests under pytest.
- Exercise every supported stream-event variant and each required failure/cancellation scenario.
- Assert the domain/provider modules can import and tests can run without an OpenAI or LangChain
  package installed.
- Run transcript tests to verify normalized events are persisted while raw fake payload objects are
  not.
- Run the repository-wide non-live checks.

## Documentation impact

Update `docs/agent-loop.md` and the glossary with provider, request, model turn, stream event,
cancellation, and normalization boundaries. Document the fake script format for tests and evals.

## Out of scope

- The OpenAI adapter and any live call.
- Executing provider-requested tools or continuing through multiple model/tool turns.
- LangChain orchestration or adapter dependencies.

## Delivered evidence

- `src/code_assist_harness/provider/models.py` defines immutable, harness-owned conversation,
  repository-instruction, stream-event, usage, completion, and normalized-failure values without a
  provider or framework dependency.
- `src/code_assist_harness/provider/port.py` defines the structural `Provider` and
  `ProviderOperation` protocols. One operation exposes a single-consumer async event stream,
  idempotent awaited cancellation, and repeatable cleanup waiting.
- `src/code_assist_harness/provider/fake.py` verifies an ordered sequence of exact
  `ProviderRequest` values and executes explicit emit, logical-delay, and cancellation-checkpoint
  steps. Request diagnostics identify only bounded field paths, never request contents.
- Fake scripts reject ambiguous terminal placement, duplicate checkpoint names, and unsupported
  steps. `FakeProvider.assert_complete()` detects unfinished exchanges, omitted requests, and
  unconsumed output.
- Provider tests cover every stream variant, malformed serialized tool arguments, normalized
  failure bounds, ordered exchanges, request mismatches, omitted and extra requests, logical
  delays, cancellation before output and between deltas, consumer cancellation, and single-stream
  ownership.
- The provider package imports while common vendor and framework modules are unavailable, and the
  project metadata contains no OpenAI or LangChain dependency. Transcript regression coverage
  proves that only a normalized provider failure reaches persisted session evidence in the modeled
  handoff.
- The current `MockSession`, Python runtime, protocol, and TUI are intentionally unchanged.
  [CAH-021](cah-021-complete-one-model-turn.md) is the next unit and will connect this port to one
  model-free provider turn.

## Completion evidence

- The written lesson records the concrete provider types, fake script API, cancellation contract,
  failure paths, tests, and implementation code samples.
- **PENDING — visual validation:** record the final slide count, slide-by-slide rendered-image
  inspection, and presentation overflow-test result after the deck is generated.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passes: 263 Python tests, 30 Python
  protocol-fixture tests, 24 repository-policy tests, 208 TUI tests, 29 TypeScript
  protocol-fixture tests, and 4 real Node/Python boundary tests, plus Python lint/format and
  TypeScript typecheck/lint.
