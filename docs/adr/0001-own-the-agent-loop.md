# ADR 0001: Own the agent loop

- **Status:** Accepted
- **Date:** 2026-07-13
- **Decision scope:** Harness orchestration and framework dependencies

## Context

The initial repository scaffold describes Code Assist Harness as a Python foundation built with
LangChain and OpenAI, and its initial dependency list reflects that description. The scaffold does
not yet implement an agent, so this wording expresses an architectural intention rather than an
existing compatibility requirement.

The project's primary purpose is to learn agent-loop mechanics, context engineering, tool design,
safety, and evaluation. Delegating orchestration to a framework-owned executor would hide several
of those mechanisms and couple the domain model to framework types. At the same time, model access
must be replaceable and testable without a network connection.

## Decision

Code Assist Harness will implement and own an explicit, bounded agent loop in Python.

The loop will directly:

1. assemble provider-neutral input from session state and selected context;
2. invoke a provider through a harness-defined interface;
3. translate provider streaming output into domain events;
4. validate requested tool names and arguments;
5. apply policy and request approval where required;
6. execute authorized tools and add bounded results to session state; and
7. continue, complete, cancel, or fail according to explicit lifecycle rules and limits.

The loop's public types will express harness concepts rather than classes from OpenAI, LangChain,
or another orchestration framework. OpenAI will be the first real provider adapter, targeting the
Responses API when that story is implemented. Provider SDK objects and raw payloads remain inside
the adapter. A programmable fake provider supports deterministic unit tests and model-free
vertical slices.

LangChain is not an MVP orchestrator or core dependency. A future LangChain adapter may translate
between LangChain and stable harness ports if a concrete use case justifies it, but it may not
change core domain types or take ownership of session lifecycle and policy.

This decision explicitly supersedes the architectural intent in the initial README and package
metadata that characterizes LangChain as the project's foundation. Those references and unused
dependencies are migration work under CAH-001; their presence in an intermediate revision does
not override this ADR.

## Invariants

- At most one provider request is active for a session.
- Every model-requested side effect passes through harness validation and policy.
- Limits are checked before another costly operation begins.
- A session emits exactly one terminal event.
- Cancellation is checked and propagated explicitly.
- Provider failures become structured harness failures rather than leaked SDK exceptions.
- Default tests and evaluations make no live provider or network request.

## Consequences

### Benefits

- The mechanisms the project is intended to teach remain visible and testable.
- Provider and framework changes do not redefine the session, event, tool, or policy model.
- Failure, cancellation, and stopping behavior can be exercised deterministically with a fake.
- The Python core can later serve a TUI, another interface, or a library caller.

### Costs and risks

- The project must implement loop control, streaming translation, tool-result continuation, and
  error handling that a framework could otherwise provide.
- New provider features require deliberate translation into the provider-neutral contract.
- The loop could accumulate framework-like complexity if responsibilities are not kept in focused
  modules.

These costs are accepted because they are central to the learning goals. Focused modules, hard
limits, deterministic scenarios, and documented invariants will control the risk.

## Alternatives considered

### Use LangChain's agent executor

Rejected for the MVP because it would move orchestration and some tool semantics outside the
project's control and obscure the primary learning surface.

### Call OpenAI directly throughout the core

Rejected because SDK types would spread through domain code, make deterministic tests harder, and
make a later provider or fake implementation unnecessarily expensive.

### Build a generic multi-provider framework immediately

Rejected because only one real provider is in scope. The provider port should be narrow and
provider-neutral, but abstraction beyond demonstrated needs is deferred.

## Implementation status

This is an accepted target decision. At acceptance time, the repository contained only the Python
scaffold and no agent loop or provider adapter. Stories CAH-020 through CAH-022 introduce the
provider interface, one-turn loop, and hard limits after the model-free walking skeleton exists.
