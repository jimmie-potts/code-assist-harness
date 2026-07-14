# CAH-020 - Define the provider interface and fake provider

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-010, CAH-011
- **Lesson:** [Provider interface and fake](../docs/lessons/cah-020-provider-interface-and-fake.md)

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
