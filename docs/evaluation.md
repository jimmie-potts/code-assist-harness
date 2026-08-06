# Evaluation

> Status: proposed evaluation-runner design. CAH-005 and CAH-006 provide deterministic
> streamed-completion and cancellation evidence in unit and real-boundary tests, and CAH-009 binds
> normalized teaching tapes to that evidence. CAH-007 runs all current deterministic layers through
> one offline repository gate and Linux workflow. CAH-010 adds equivalent pure lifecycle reducers
> and shared transition/replay fixtures. CAH-020 adds the provider-neutral port and programmable
> fake. CAH-021 proves one provider-backed turn, CAH-022 proves four hard limits, deadline races,
> bounded cleanup, and version-3 evidence around it, and CAH-023 adds SDK-fake adapter coverage plus
> an explicit optional live smoke. CAH-037 now refines the first filesystem-backed, deterministic
> read-only vertical-slice evaluation, but it is not implemented yet. The launched TUI still
> defaults to the deterministic mock.

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
| Provider exception | The injected turn translates a normalized provider failure into one structured session failure; unexpected start, iteration, or grammar failure becomes `provider_invalid_response`. |
| Invalid protocol line | The runtime survives when possible and reports a safe protocol error. |
| Unknown tool | Dispatch is rejected and the model receives a structured result. |
| Hard-limit exhaustion | CAH-022 unit and runtime integration tests stop before a disallowed operation or observation is accepted; a reusable filesystem scenario remains planned. |
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
`tests/provider/test_port_imports.py` proves the provider-neutral package surface imports while vendor
and framework modules are unavailable; the concrete adapter remains an isolated, non-reexported
module. A
transcript regression models the later failure handoff and verifies that only normalized failure
fields are persisted, never a raw adapter object.

CAH-021 adds deterministic orchestration evidence without adding the filesystem scenario runner.
`tests/test_provider_session.py` exercises exact request construction, one-operation ownership, the
successful text/completion/usage grammar, exact 8,192-byte acceptance and over-limit rejection,
normalized and invalid failures, tool rejection, cancellation before and between output, blocked
wire and transcript observers, terminal races, teardown, and cleanup-contract violations. Every
strict-fake path calls `assert_complete()`. `tests/test_runtime.py` injects the fake through
`run_runtime`, proves transcript-enabled and disabled modes have identical wire outcomes, restores
bounded usage evidence, and verifies that shutdown, EOF, and outer-task cancellation join provider
cleanup without fabricating a terminal. These tests use no SDK, credentials, model, or network.

CAH-022 adds deterministic safety-budget evidence without adding the filesystem scenario runner.
`tests/test_loop_limits.py` covers the four validated fields, defaults, ranges, and seeded tracker
boundaries. `tests/test_provider_session.py` uses injected clocks, deadline waiters, fake-provider
gates, and blocked sinks without wall-clock sleeps. It proves admission before provider start,
cumulative UTF-8 charging, tool observations before unavailable-tool handling, an exact
event/deadline tie, cancellation beginning while an admitted publication is blocked, one terminal
winner, and one shared cleanup task supervised by a fixed five-second grace. Grace regressions prove
the loop-owned barrier is cancelled and reaped before the required authoritative provider hook reaps
the nested cleanup owner on both cancellation and natural-completion paths. The ordered,
non-interleaved publication transaction finishes; an ordinary later failure does not roll back an
earlier accepted view, and the test does not claim to bound local sink latency.
`tests/test_runtime.py` proves the deadline is captured before transcript setup,
fresh counters across sequential provider sessions, transcript-mode wire parity, and version-3 loop
evidence. `tests/test_transcript.py` retains version-1 and version-2 replay and validates version-3
cardinality, order, ranges, prefixes, and mock omission.

CAH-023 adds deterministic adapter evidence without making the default suite networked.
`tests/provider/test_openai_config.py` and `tests/test_runtime_configuration.py` prove exact
provider/model parity, SDK-free rejection, credential privacy, mock independence from ambient keys,
and lazy composition. `tests/provider/test_openai_responses.py` uses SDK-shaped fakes to cover exact
request mapping, the accepted stream automaton, completed-usage reconciliation including exact 8,192
output-token acceptance and over-cap rejection, failure normalization, cancellation races, and every
stream/client cleanup outcome. It also proves force-reap while create, stream close, or client close
is blocked, ordinary joiner shielding, and the distinction between cleanup-owner cancellation and an
independently raised close-time `CancelledError`. TypeScript configuration, launcher, supervisor, and
real-boundary tests prove separate shell-free arguments and the explicit mock default. Check-script
regressions seed `SSLKEYLOGFILE` and prove the canonical gate clears it at every layer, while explicit
live opt-in rejects it without echoing its value. Repository policy permits the SDK and network surface
only in the concrete adapter.

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
terminal outcome, shutdown, stderr/stdout separation, and visible lifecycle state. Separate Python
integration tests exercise the CAH-020 fake through CAH-021's runtime seam and CAH-022's four hard
limits. CAH-023 activates that bounded path at the composition root only for explicit OpenAI/model
selection; the default process-boundary suite remains on the mock. A later unit may add a fake or
restricted executor.

### Live-provider smoke evaluations

CAH-023 includes one minimal live OpenAI smoke evaluation that is optional, explicitly selected,
credential-gated, and excluded from default validation and default CI even when credentials are
present. It runs only with `--run-live-provider`, `--live-provider-model gpt-5.6-luna`, and
`OPENAI_API_KEY`; ambient credentials alone never select it. After creating the ignored root
`dev.env` as documented in the README, run the one smoke explicitly through its strict reader:

```bash
./scripts/with-openai-dev-key \
  uv run --offline --frozen --no-sync --no-env-file \
  pytest -q -m live_provider tests/provider/test_openai_live.py \
  --run-live-provider --live-provider-model gpt-5.6-luna
```

This command may incur provider cost and is supplemental rather than completion evidence. Later live
evaluations may measure
retrieval quality, unnecessary reads, plan grounding, tool-call success, unsafe attempts, and
final-summary accuracy. Their variability must not weaken deterministic harness gates.

## Replay and diagnosis

An evaluation failure should retain a redacted event transcript, scenario name, deterministic seed
when used, expected/actual event diff, metrics, and fixture-state diff. Raw provider payloads and
environment values are never diagnostic artifacts.

Because visible state is input-derived, replaying trusted domain facts and a stored validated event
list reproduces the same terminal state. CAH-010 implements this fold in both languages and stops at
the first structured invariant failure. The transcript writer now emits version 3, while replay
accepts internally consistent versions 1, 2, and 3 and validates framing, schema, contiguous record
order, workspace/session identity, embedded protocol events, reducer invariants, usage placement, and
version-3 loop-limit cardinality, order, ranges, and counters. It returns lifecycle state plus a
separate evidence projection containing optional usage and loop limits. A version-3 mock tape may omit
limit evidence because it never enters the provider-backed loop. Replay does not re-execute tools or
provider calls, recover redacted or bounded values, resume work, treat usage as billing proof or limit
authority, or trust later lines after a failure.

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
`PYTHONPATH`, and is covered by the current production-source network policy instead. The gate also
checks local Markdown targets and anchors. These controls are defense in depth rather than an
operating-system sandbox for arbitrary native executables.
Focused tests remain useful for diagnosis, but a completed unit returns to the unified gate and
records its result.

## Implementation stories

### Planned CAH-037 — Prove the read-only assistant vertical slice

> As a repository user, I want fixture-backed explain and plan tasks to traverse the composed M2
> loop so that grounded behavior is proven without a live model.

The [implementation-ready story](../user-stories/cah-037-prove-read-only-assistant.md) introduces
`evals/` only with a small purpose-built runner, one synthetic workspace, deterministic strict-fake
explain/plan cases, and adversarial mutations. It checks structured retrieval/tool evidence before
small required or forbidden answer facts. Plain runtime composition defaults **initial** context
scope to `.` with empty focus and search inputs and supplies the exact M2 limits: four model turns, 120
provider-work seconds, 4,096 output bytes, and three observed tool calls. Fixture cases may inject
explicit context values through their test seam but may not alter that ordinary composition profile.
Tests assert a fresh exact profile for mock and OpenAI paths so bare `LoopLimits()` defaults cannot
silently narrow the loop. Optional live output remains observational and requires the same explicit
OpenAI selection and repository-content egress warning as the application path.

The deterministic fixture also proves context evolution: the exact first request contains only root
instructions, and a successful `read_file` target under `pkg/` causes the binding with
`source="shared/rules.md"` and `applies_to="pkg"` to appear in the next request. An exact owner snapshot
repeats idempotently. Broad list/search results expose multiple nested and sibling owners; every
binding must appear before the result is replayed. After every discovery guard, the returned bundle's
`canonical_scope` must exactly equal the captured result scope; one mismatching or failing later owner
rejects the whole local transaction without alias fallback. Empty-list/no-match cases retarget a
supplied alias after dispatch and prove only the scope captured by the native operation's final
access-time admission drives discovery; removing that captured path fails without replay or alias
fallback. Stat/read cases likewise prove result `path` is final admitted provenance, including
`read_file`'s final pre-open path. A separate injected case validates every projection with zero I/O,
discovers/folds/checks root first, completes every focus read/discovery/fold before search, unions the
instruction chains for the supplied root scope, every canonical-distinct focus path, and every
first-occurrence search-match owner before its content, then proves each literal query uses only the
exact supplied-scope `SearchTextRequest` projection with depth four and 100 matches. Root failure has
zero focus/search calls and focus failure has zero search calls. A scope-alias retarget between root
discovery and search produces a canonical-result mismatch and no package. An internal instruction link records
its resolved source separately from candidate-owner applicability; a hard-denied target is never
read. Missing-ancestor and late-insertion snapshots prove CAH-025's canonical-depth precedence gaps
survive CAH-030 storage and CAH-032 projection unchanged; sibling serialization is never reinterpreted
as precedence. CAH-031 projection tables admit signed-64-bit integer endpoints, reject adjacent and
5,000-digit overflow values, cover 63/64/65-level complete result envelopes and wide/work-exhausting
values, and map injected serializer `RecursionError`/`ValueError` to the fixed
`invalid_read_tool_result`. CAH-032 construction and CAH-036 mapping tables cover malformed tool-name
carriers plus 16,383/16,384/16,385 argument bytes; rejected carriers invoke neither CAH-033 nor
CAH-039. CAH-033/036 text tables cover exact/subclassed 8,191/8,192/8,193-byte ASCII and multibyte
inputs, one bounded normal join, zero overflow-tail work, exact marker handoff, structural/failure
precedence, and zero publication/dispatch. Separate adapter cases pump 16,384 mapped-empty one-byte
argument deltas at constant stack depth and require raw terminal-to-EOF; an extra event or iterator
exception discards the staged terminal tuple. CAH-039's focused tables begin with admitted, at-or-below-limit carriers and cover an exact
16,384-byte argument; 63/64/65-level object-array shapes with root object depth 1; quoted/escaped
delimiters and mismatched containers; signed-64-bit endpoints and overflow; fractional/exponent
numeric tokens; all three
non-finite constant spellings; defensive decoder `RecursionError`/`ValueError`; and same-value,
conflicting, reversed, nested, array-contained, and escape-equivalent duplicate members through the
deepest admitted object depth. The composed CAH-037 fixture proves unknown-tool lookup wins first,
then structural and numeric preflight runs before Python conversion, the pair-preserving decode uses
rejecting `parse_constant` handling, and the iterative duplicate walk completes before
dictionary construction, the exact-key gate, Pydantic, or native dispatch. Every CAH-039-rejected input
becomes `invalid_read_tool_input`, followed by one charged observation and unchanged-context
call/error replay. Named
event gates before dispatch, after synchronous dispatch, after every discovery, after every merge, and before provider
start prove zero native execution at the first gate and that later result,
instruction, context, history, and request candidates remain uncommitted when cancellation wins.
Instruction-discovery or merge failures, changed owner snapshots, and
context/request overflow produce zero next provider starts; known bounded tool errors may continue
against unchanged context.

### Future story — Generalize the scenario format and runner

> As a harness developer, I want filesystem-based deterministic scenarios so that behavior can be
> reproduced from inputs, fake-provider events, decisions, and expected effects.

Complete this later story when CAH-037's focused read-only runner has a demonstrated second workflow
and can become a general isolated format without weakening its deterministic evidence.

### Future story — Evaluate lifecycle and stopping

> As a user, I want completion, cancellation, provider failure, and limit exhaustion evaluated so
> that the loop cannot hang or emit conflicting terminal outcomes.

### Future story — Evaluate tools and safety

> As a user, I want denial, approval, stale-edit, traversal, timeout, and cancellation scenarios so
> that side-effect defenses are continuously verified.

### Future story — Expand context-selection evaluation

> As a learner, I want a broader corpus of known relevant files, source ranges, budgets, and
> unnecessary reads so that context-engineering changes can be compared beyond CAH-037's two cases.

### CAH-023 (Implemented) — Add optional live-provider smoke evaluation

> As a maintainer, I want an explicit non-default provider smoke suite so that the real adapter can
> be checked without making ordinary development depend on credentials or network access.

The smoke executes one minimal request through `ProviderSession` and `LoopLimits`, then requires a
bounded completed result. Marker selection without the explicit run flag skips it; the canonical gate
also deselects `live_provider` and clears provider configuration. Broader live quality evaluation
remains future work.
