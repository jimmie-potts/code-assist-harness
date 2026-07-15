# Evaluation

> Status: proposed design. The evaluation runner and scenarios are not yet implemented.

Evaluation starts with the walking skeleton and measures the harness before it attempts to measure
model intelligence. Deterministic scenarios should make lifecycle, protocol, policy, context, edit,
and cancellation regressions reproducible without an API key or network access.

## Scenario model

Each filesystem-based scenario supplies:

- A small workspace fixture.
- A user task.
- A scripted fake-provider interaction.
- Scripted approval decisions.
- Expected ordered events or event predicates.
- An expected terminal state.
- Expected final files and explicit unchanged files.
- Optional expected metrics and transcript assertions.

Scenario data, workspaces, and expected results will live under `evals/`. The exact serialization
format should be chosen in the runner story; readability, stable diffs, and precise byte content are
more important than adopting a framework. Scenario inputs are immutable during a run. Each run uses
a fresh temporary copy so tests cannot influence one another.

The fake provider is programmable rather than a canned text stub. It verifies expected
provider-neutral requests and emits text deltas, tool calls, delays, usage, failure, or cancellation
at exact points. An unexpected request fails the scenario with a useful diff.

## Initial scenarios

| Scenario | Expected behavior |
| --- | --- |
| Normal streamed response | Deltas remain ordered and the session completes once. |
| User cancellation | Active work stops and the session is cancelled once. |
| Provider exception | A structured provider failure is emitted and persisted. |
| Invalid protocol line | The runtime survives when possible and reports a safe protocol error. |
| Unknown tool | Dispatch is rejected and the model receives a structured result. |
| Step-limit exhaustion | The loop stops before another provider call. |
| Rejected approval | No side effect occurs and the loop receives the rejection. |
| Workspace escape | The tool is denied before filesystem access. |
| Stale edit | The file remains unchanged and a conflict is reported. |
| Command timeout | The process tree is terminated and bounded output is returned. |

Additional scenarios should be added with the story that introduces a behavior. A regression test
belongs at the lowest useful layer as well as in an end-to-end scenario when the process boundary or
event sequence is part of the contract.

## Assertion layers

Evaluation separates several kinds of truth:

1. **Domain truth:** reducer state, policy decisions, limits, and structured tool results.
2. **Protocol truth:** valid envelopes, sequence order, correlation, and cross-language fixtures.
3. **Effect truth:** actual file bytes, absent changes, terminated processes, and sanitized
   environments.
4. **Projection truth:** the TUI reducer and important rendered states.
5. **Evidence truth:** transcripts contain validated redacted decisions and match actual effects.

Tests should prefer stable machine fields over prose snapshots. User-visible errors and important
screen layouts still need focused assertions so an actionable failure cannot degrade into an opaque
code.

## Metrics

Scenario results will collect:

- Terminal outcome and stable failure code.
- Model turns, loop steps, and tool-call counts.
- Context item count and measured context size.
- File reads, repeated reads, and selected source ranges.
- Requested, approved, rejected, denied, and executed actions.
- Duration and deadline/timeout outcomes.
- Provider token or usage data when supplied.
- Output truncation and transcript status.

Metrics explain behavior and enable comparisons; they are not pass criteria unless a scenario sets
an expected bound. Duration assertions should use a controllable clock where possible to avoid
flaky wall-clock tests.

## Test tiers

### Unit tests

Pure reducers, validators, budgeting, path policy, command policy, redaction, and loop branches use
fakes and temporary directories. They never invoke a live provider or depend on network access.

### Contract tests

Shared golden JSON fixtures are parsed by Pydantic v2 in Python and Zod in TypeScript. Invalid
fixtures test unsupported versions, bad discriminators, missing fields, and malformed payloads.

### Integration tests

The walking-skeleton test starts the real Node parent and Python child with mocked runtime behavior.
Later integrations may use a fake provider and fake or restricted executor. They assert ordered
events, shutdown, stderr/stdout separation, and visible lifecycle state.

### Live-provider smoke evaluations

Live OpenAI evaluations are optional, explicitly selected, credential-gated, and excluded from
default validation and CI. They may measure retrieval quality, unnecessary reads, plan grounding,
tool-call success, unsafe attempts, and final-summary accuracy. Their variability must not weaken
deterministic harness gates.

## Replay and diagnosis

An evaluation failure should retain a redacted event transcript, scenario name, deterministic seed
when used, expected/actual event diff, metrics, and fixture-state diff. Raw provider payloads and
environment values are never diagnostic artifacts.

Because visible state is event-derived, replaying a stored validated event list should reproduce the
same terminal state. Replay does not re-execute tools or provider calls. A transcript that cannot be
validated fails explicitly rather than being partially trusted.

## Definition of done for behavioral work

A behavioral story adds or updates:

- A happy-path test and at least one meaningful failure test.
- Protocol documentation and fixtures for new messages.
- Transcript assertions for side effects and approvals.
- Redaction checks when new data is emitted.
- Python and TypeScript checks relevant to the changed boundary.
- A rendering or reducer test for visible TUI behavior.
- The conceptual documentation that explains the design rationale.
- The unit lesson with concrete implementation paths, observed trade-offs, and evidence links.

Default validation must remain model-free and network-free.

## Implementation stories

### Future story — Define the scenario format and runner

> As a harness developer, I want filesystem-based deterministic scenarios so that behavior can be
> reproduced from inputs, fake-provider events, decisions, and expected effects.

Complete this story when an isolated runner reports event and file-state differences clearly.

### Future story — Evaluate lifecycle and stopping

> As a user, I want completion, cancellation, provider failure, and limit exhaustion evaluated so
> that the loop cannot hang or emit conflicting terminal outcomes.

### Future story — Evaluate tools and safety

> As a user, I want denial, approval, stale-edit, traversal, timeout, and cancellation scenarios so
> that side-effect defenses are continuously verified.

### Future story — Evaluate context selection

> As a learner, I want known relevant files, source ranges, budgets, and unnecessary reads measured
> so that context-engineering changes can be compared.

### Future story — Add optional live-provider smoke evaluation

> As a maintainer, I want an explicit non-default provider smoke suite so that the real adapter can
> be checked without making ordinary development depend on credentials or network access.
