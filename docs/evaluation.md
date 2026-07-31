# Evaluation

> Status: proposed evaluation-runner design. CAH-005 and CAH-006 provide deterministic
> streamed-completion and cancellation evidence in unit and real-boundary tests, and CAH-009 binds
> normalized teaching tapes to that evidence. CAH-007 runs all current deterministic layers through
> one offline repository gate and Linux workflow. CAH-010 adds equivalent pure lifecycle reducers
> and shared transition/replay fixtures. CAH-020 adds the provider-neutral port and programmable
> fake used by later loop and evaluation scenarios. Filesystem-backed `evals/` scenarios and a
> provider-backed session turn are not implemented yet.

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

The implemented fake provider is programmable rather than a canned text stub. It verifies ordered
provider-neutral requests and executes explicit text/tool/usage/failure emits, logical delays, or
cancellation checkpoints at exact points. An unexpected request fails with bounded differing field
paths rather than a content-bearing diff; `assert_complete()` also catches omitted requests and
unconsumed stream steps. The later scenario runner still owns the on-disk serialization of this
Python script model.

## Initial scenarios

| Scenario | Expected behavior |
| --- | --- |
| Normal streamed response | Deltas remain ordered and the session completes once. |
| User cancellation | Active work stops and the session is cancelled once. Unit and boundary tests exist; a reusable evaluation scenario remains planned. |
| Provider exception | The fake can emit a normalized provider failure; CAH-021 must translate it into one structured session failure before transcript persistence. |
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

CAH-006 applies that layering before a scenario runner exists. `tests/test_runtime.py` controls mock
checkpoints to prove cancellation before output, between deltas, and against a blocked completion
write. TypeScript reducer, supervisor, and render tests prove the pending-versus-authoritative state
distinction and fail closed on conflicting terminal events. `tui/test/runtime-boundary.test.ts`
sends cancellation through the genuine Node-to-`uv`-to-Python process tree before the first delta
and between later deltas, rejects delayed post-terminal output, and verifies active shutdown reaps
the process tree. `tui/test/app.test.tsx` separately drives Escape through the Ink binding. These
are regression gates, not yet a serialized `evals/` scenario or metric report. CAH-009 adds
documentation fixtures rather than an evaluation runner: both language suites validate the guide's
NDJSON, while the real-boundary test compares the normalized session tapes without treating
timestamps as ordering evidence. See the [walking-skeleton guide](walking-skeleton.md).

CAH-010 adds domain-truth evaluation without introducing the later scenario runner. Fifty shared
cases construct every prior state from idle, validate each wire envelope through Pydantic or Zod,
and compare normalized Python and TypeScript state or invariant failures. The suite covers all 16
legal transitions, seven full replays, 27 failure cases, every terminal path, approval waiting,
completion winning a cancellation race, and payload-free failure diagnostics. Both suites replay
every case twice. Focused runtime, supervisor, conversation-reducer, and Ink tests prove that the
same core semantics participate in the implemented mock path.

CAH-020 adds deterministic provider-boundary evidence without introducing the agent loop or scenario
runner. `tests/provider/test_provider_models.py` exercises every harness-owned stream variant, immutable
request ordering, malformed serialized tool arguments, usage validation, and safe failure bounds.
`tests/provider/test_fake.py` exercises exact request order, logical delays without wall-clock sleep,
normalized failure, content-safe mismatch diagnostics, omitted and extra calls, abandoned streams,
single-consumer ownership, and cancellation before output and between deltas.
`tests/provider/test_port_imports.py` proves the package imports while common vendor and framework
modules are unavailable and that the project declares no OpenAI or LangChain dependency. A
transcript regression models the later failure handoff and verifies that only normalized failure
fields are persisted, never a raw adapter object.

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

Pure reducers, validators, provider contracts, budgeting, path policy, command policy, redaction,
and loop branches use fakes and temporary directories. They never invoke a live provider or depend
on network access. The CAH-020 fake uses named logical gates rather than short sleeps for
asynchronous ordering evidence.

### Contract tests

Shared golden JSON fixtures are parsed by Pydantic v2 in Python and Zod in TypeScript. Invalid
fixtures test unsupported versions, bad discriminators, missing fields, and malformed payloads.

### Integration tests

The walking-skeleton tests start the real Node parent and Python child with mocked runtime behavior.
They assert ordered streamed completion, authoritative cancellation, another session after a
terminal outcome, shutdown, stderr/stdout separation, and visible lifecycle state. Later
integrations begin with the CAH-020 fake provider in CAH-021 and may later add a fake or restricted
executor. The current `MockSession` integration does not consume the provider port.

### Live-provider smoke evaluations

Live OpenAI evaluations are optional, explicitly selected, credential-gated, and excluded from
default validation and CI. They may measure retrieval quality, unnecessary reads, plan grounding,
tool-call success, unsafe attempts, and final-summary accuracy. Their variability must not weaken
deterministic harness gates.

## Replay and diagnosis

An evaluation failure should retain a redacted event transcript, scenario name, deterministic seed
when used, expected/actual event diff, metrics, and fixture-state diff. Raw provider payloads and
environment values are never diagnostic artifacts.

Because visible state is input-derived, replaying trusted domain facts and a stored validated event
list reproduces the same terminal state. CAH-010 implements this fold in both languages and stops at
the first structured invariant failure. CAH-011 now validates transcript-v1 JSONL framing, schema,
contiguous record order, workspace/session identity, embedded protocol events, and reducer
invariants before returning a terminal or explicitly incomplete projection. Replay does not
re-execute tools or provider calls, recover redacted or bounded values, resume work, or trust later
lines after a failure.

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

CAH-007 makes `./scripts/check` the canonical local and CI entry point for this evidence. It removes
common provider credentials, forces dependency tools offline after setup, and preloads guards into
the top-level Python and Node checks that reject common socket/network client entry points. The real
Python integration child preserves its runtime-selector sanitization, including removal of
`PYTHONPATH`, and is covered by the current M0 production-source denylist instead. The gate also
checks local Markdown targets and anchors. These controls are defense in depth rather than an
operating-system sandbox for arbitrary native executables.
Focused tests remain useful for diagnosis, but a completed unit returns to the unified gate and
records its result.

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
