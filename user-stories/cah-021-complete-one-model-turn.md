# CAH-021 - Complete one model turn

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-020
- **Lesson:** [One model turn](../docs/lessons/cah-021-one-model-turn.md)

## User story

> As a user, I want the harness to answer one task through a model provider so that the first real
> conversational capability is available.

## Scope

- Implement the smallest explicit agent loop for one provider request and terminal response.
- Convert provider-neutral deltas, completion, usage, failure, and cancellation into session events.
- Add the first OpenAI adapter behind the provider port while keeping the fake as the default test
  path.
- Target OpenAI's Responses API without exposing SDK objects outside the adapter.

## Acceptance criteria

1. The loop accepts one user task plus applicable repository-level instructions and constructs a
   provider-neutral request.
2. Exactly one provider operation is active for a session.
3. Provider text deltas become ordered `assistant.delta` session events as they arrive.
4. Normal provider completion becomes one `assistant.completed` event followed by exactly one
   successful terminal event.
5. The final assistant text equals the ordered accumulation of accepted text deltas or follows one
   documented provider-completion reconciliation rule.
6. A normalized provider failure produces one actionable structured session failure without raw
   provider payloads, credentials, or full sensitive response content.
7. Session cancellation propagates to the provider operation and follows the established exactly-one
   terminal-event race semantics.
8. Usage data, when supplied, is represented by harness-owned types and recorded as bounded,
   validated event data.
9. The OpenAI adapter targets the Responses API, maps SDK types at its boundary, and is replaceable by
   the fake without changing loop or session domain types.
10. Fake-provider tests cover success, delayed streaming, provider failure, malformed provider data,
    cancellation, and completion races without network access.
11. Live-provider smoke tests are opt-in, require explicit credentials, and are excluded from the
    unified default validation.
12. Real-provider use supports the transcript opt-out and redaction behavior delivered by CAH-011.

## Validation

- Run the full one-turn suite against the fake provider and assert emitted events, transcript, final
  reducer state, and provider cancellation.
- Run boundary-mapping tests for the OpenAI adapter using SDK fakes/mocks, not HTTP.
- Run default repository checks without an API key and assert the live marker/suite is not selected.
- Optionally run a separately documented, minimal live-provider smoke test; it is supplemental and
  never required for unit-test completion.

## Documentation impact

Update the agent-loop and provider documentation with the one-turn sequence, repository instruction
input, stream normalization, failure mapping, usage, cancellation, transcript privacy, and live-test
boundary. Document provider setup without placing real keys in examples.

## Out of scope

- Filesystem tools, edit proposals, approvals, or subprocesses.
- Multiple provider/tool iterations.
- Other providers or a LangChain adapter.
