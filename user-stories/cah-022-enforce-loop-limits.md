# CAH-022 - Enforce loop limits

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-021
- **Lesson:** [Loop limits](../docs/lessons/cah-022-loop-limits.md)

## User story

> As a user, I want the harness to stop predictably when limits are reached so that a faulty model or
> tool sequence cannot run indefinitely.

## Scope

- Introduce one typed limits configuration for model turns, tool calls, elapsed time, and bounded
  assistant output.
- Check applicable limits before each new costly operation and during streaming where needed.
- Emit distinct domain failure codes and understandable TUI messages.
- Exercise every limit deterministically with the fake provider, including scaffolding for tool-call
  limits before tool execution is implemented.
- Exercise model-turn exhaustion at the limit-tracker/preflight seam until a later story introduces
  multi-turn orchestration; this story must not expand CAH-021 beyond one model turn.

## Acceptance criteria

1. Configuration includes maximum model turns, maximum tool calls, a session deadline, and a bounded
   assistant-output limit with documented defaults and validation.
2. Invalid, zero, negative, or unreasonably large values follow a documented reject/clamp policy and
   cannot silently disable safety limits.
3. Before starting a provider or future tool operation, the loop checks every applicable limit
   and stops without making the costly call when exhausted.
4. The deadline uses a monotonic clock for elapsed-time enforcement and can be injected in tests.
5. Output limits are enforced during streaming without emitting unbounded content to the TUI or
   transcript.
6. Each limit emits a distinct structured failure code that identifies the exhausted limit without
   exposing sensitive content.
7. Exactly one terminal failure event is emitted when a limit wins a race with provider completion or
   user cancellation, according to documented terminal-transition semantics.
8. The transcript and human-readable summary identify the limit reached and bounded counters at the
   time of failure.
9. The TUI renders each limit failure in understandable language with a safe next step.
10. Deterministic fake-provider tests cover every limit at its boundary and prove an attempted
    admission after exhaustion does not start a provider call. Model-turn exhaustion may be seeded
    at the tracker/preflight seam until multi-turn orchestration exists.
11. Tool-call accounting can consume provider-requested calls even though execution remains out of
    scope, preventing calls beyond the configured budget from being admitted without implying tool
    execution or another provider turn.

## Validation

- Run parameterized fake-provider tests for one-below, exact-boundary, and over-limit cases.
- Use an injected fake monotonic clock for deadlines; tests must not depend on slow wall-clock sleeps.
- Assert provider request counts, emitted output size, terminal event count, reducer state,
  transcript fields, and TUI failure rendering for each limit.
- Run the repository-wide non-live checks.

## Documentation impact

Update `docs/agent-loop.md`, safety documentation, configuration guidance, protocol failure codes,
and the glossary with model turn, tool call, deadline, output accounting, and limit-race semantics.

## Out of scope

- Multi-turn orchestration, tool execution, command timeout implementation, retries, or adaptive
  budget increases.
- User interfaces that allow an active session to weaken its own limits.
