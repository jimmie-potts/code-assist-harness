# CAH-037 lesson: Prove the read-only assistant

- **Unit:** CAH-037
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; M2 is not yet composed or evaluated
- **Story:** [CAH-037](../../user-stories/cah-037-prove-read-only-assistant.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Composition-root ownership, complete direct/broad-result instruction coverage,
  duplicate-safe dispatch evidence, and cooperative cancellation for grounded explanation and planning
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Evaluation](../evaluation.md), [Architecture](../architecture.md), and
  [Context engineering](../context-engineering.md)

> This lesson defines planned deterministic evidence. Fixtures and pseudocode do not prove M2 yet.

## Quick summary

CAH-037 composes M2 and proves explain/plan outcomes with strict fakes. Ordinary runtime starts with
only root-scoped instructions and explicitly receives the M2 four-turn/three-call limit profile;
after `read_file(path="pkg/file.py")` succeeds, the next request includes the `pkg` binding whose
resolved source is `shared/rules.md`.
Broad list/search cases prove every returned owner is covered before replay, while duplicate raw
arguments prove zero dispatch and context growth. Evaluation alone may inject explicit focus/search
context and proves its exact projections. Named cancellation gates prove synchronous-stage
candidates never become partial session state.

## Learning objectives

After this unit, you should be able to:

- locate dependency selection in the composition root;
- distinguish production defaults from test/evaluation injection;
- prove all explicit-focus instruction chains precede focus content and search remains rooted at the
  supplied scope;
- distinguish a resolved instruction `source` from its candidate-owner `applies_to` scope;
- prove requested and result-owner instruction enrichment without turning results into search roots;
- prove duplicate decoded argument names never reach key validation or native I/O;
- prove candidate state is discarded at cooperative cancellation checkpoints;
- design deterministic groundedness evidence around exact calls and sources;
- use mutations to prove an evaluator can detect failure; and
- state the boundary between an M2 learning result and production readiness.

## Why this unit matters

Correct components can still be wired incorrectly. A vertical evaluation catches wrong defaults,
duplicated policy, skipped instructions, incorrect tools, budget resets, and unsupported answer facts.

## Junior engineer foundation

A composition root chooses concrete implementations. It is allowed to know dependencies; domain
modules should not import back into it.

```text
ordinary runtime: ContextBuildRequest(scope=".", focus_paths=(), search_queries=())
eval assembly:    ContextBuildRequest(
                    scope=".",
                    focus_paths=("pkg/file.py",),
                    search_queries=("completion",),
                  )
```

A common misconception is that the runtime should parse task text into hidden search queries. In M2,
the model explores explicitly through tools; only eval/test assembly gets the injection seam.

A model-visible tool result cannot bypass policy, but its validated paths require policy coverage.
After native result validation, CAH-031 derives local `instruction_scopes`: the requested path first,
then every exact-deduplicated returned-path owner. A `list_files` result naming `pkg/file.py` therefore
requires the `pkg` instruction bundle before replay. The path is not a provider field or a new search
root, and one failed owner discards the whole result/context transaction.

The injected focus path is different: it is explicit input to CAH-030, so its instruction chain is
required initial context. CAH-030 searches only from the supplied `scope`, then discovers every
first-occurrence search-match owner and adds its required instructions before any matching excerpt.
Focus and result paths never silently become additional search roots.

Duplicate JSON is another composition boundary. CAH-032, CAH-033, and CAH-036 preserve bounded raw
arguments. CAH-034 looks up the name first, then pair-decodes recursively and compares decoded names
by exact code point without normalization. A known duplicate is charged but becomes
`invalid_read_tool_input` with zero key gate, Pydantic validation, dispatch, or context growth. When
final admission passes, its exact call/error pair is replayed in a follow-up against unchanged context.

An instruction link also has two locations. For `pkg/AGENTS.md -> shared/rules.md`, `source` records
the resolved file read (`shared/rules.md`), while `applies_to` records the candidate owner (`pkg`).
Treating the target directory as authority would move the rule to the wrong subtree.

## Key concepts

- **Composition root:** outer module that wires concrete implementations to domain ports.
- **Production default:** invariant used by ordinary interactive sessions.
- **Composition profile:** exact dependency values selected by the runtime instead of inherited
  constructor defaults.
- **Evaluation injection:** explicit controlled dependency used only by named cases/tests.
- **Exact projection:** one validated downstream request whose fields are fixed by the owning
  contract rather than inferred from results.
- **Grounding evidence:** exact admitted source/tool observations supporting an answer.
- **Scoped enrichment evidence:** exact before/after requests proving every ordered requested and
  returned-owner scope was covered before result replay.
- **Duplicate-decoder evidence:** exact stage counters proving CAH-034 saw preserved raw pairs and
  rejected a duplicate before dictionary construction.
- **Mutation:** deliberate test change proving a claimed check can fail.
- **Candidate state:** a result, instruction bundle, context, replay history, or bounded request held
  locally until the final checkpoint and admission succeed.

## Architecture and design

```text
Ink TUI               Python runtime composition                    Provider
 task ----------> ContextBuildRequest(".", (), ()) ----------> request 1: root instructions
                  + workspace/instructions/context
                  + registry + CAH-035 bounded loop ---------> strict fake (default eval)
                    limits = (turns=4, seconds=120, bytes=4096, calls=3)
                  + CAH-036 OpenAI adapter                    \-> explicit live opt-in
                              |
          read/stat/list/search succeeds
                              v
 lookup -> CAH-034 pair decode -> dispatch -> validated result + local instruction_scopes
before_dispatch after_dispatch after_discovery after_merge before_provider_start
                               |
       for each scope: CAH-025 discover -> CAH-030 merge ---> request 2: all owners covered
                              |
fixture workspace <-----------+        Evaluation injection:
  pkg/AGENTS -> shared/rules            fixed search root "."
  sibling/AGENTS                         root + focus + match-owner instructions
                                        before focus/search content
                              |
final text <-------------------+        Existing protocol only

Evaluator: exact context + dispatch + relative citations/facts - forbidden evidence
```

The default has no hidden focus/search selection. Explain and plan remain ordinary task text, and a
plan performs no edit. Every result, per-scope bundle/merge, history, and bounded request remains local
until all scopes and budgets pass, `before_provider_start` wins, and model admission succeeds. Any
failure discards the complete candidate transaction.

## Practical walkthrough

1. Compose only public CAH-025 through CAH-036 boundaries.
2. Construct the exact four-field M2 limit profile at the composition root.
3. Capture the exact empty-focus/search runtime request.
4. Build a minimal fixture with root, `pkg`, and sibling instructions; an allowed internal
   instruction symlink; a hard-denied-target mutation; relevant source; and distractors.
5. Assert request one has only root instructions, then make the exact successful
   `read_file(path="pkg/file.py")` call and assert request two adds
   `source="shared/rules.md"` plus `applies_to="pkg"`.
6. Return broad list/search paths under `pkg` and a sibling. Assert every first-occurrence owner
   bundle is present before replay; make a later owner fail and assert no result, partial context, or
   next provider start.
7. Inject the exact root/focus/search request only in named evaluation assembly. Assert the complete
   instruction union precedes focus content and the only search projection is
   `SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`.
8. Assert the instruction symlink reports resolved `source="shared/rules.md"` and owner
   `applies_to="pkg"`; mutate its target to a hard-denied path and assert no target read or package.
9. Send conflicting and escape-equivalent duplicate `path` names. Assert CAH-034 returns the fixed
   error with a charged call and zero key gate, Pydantic validation, dispatch, or context growth;
   assert exact unchanged-context call/error replay when admission passes and that unknown-name lookup
   still wins before decoding.
10. Gate cancellation at `before_dispatch`, `after_dispatch`, every `after_discovery` and
   `after_merge`, and `before_provider_start`; assert the first gate runs no native handler, later
   candidate sentinels never commit, and no next provider starts.
11. Assert exact model history/tool dispatch before checking narrow answer facts, then run all cases
   twice for identical results.

## Implementation code samples

### Planned pseudocode: ordinary runtime

```python
context_request = ContextBuildRequest(
    scope=".",
    focus_paths=(),
    search_queries=(),
)
m2_limits = LoopLimits(
    max_model_turns=4,
    provider_work_timeout_seconds=120,
    max_assistant_output_bytes=4096,
    max_observed_tool_calls=3,
)
runtime = compose(
    context_request_factory=lambda _task: context_request,
    loop_limits=m2_limits,
)
```

The task does not influence initial source selection. The composition root does not rely on the
existing one-turn/one-call constructor defaults, so a future default change cannot silently change
the M2 contract.

### Planned pseudocode: evaluation-only injection

```python
case = ReadOnlyCase(
    task="Explain completion selection from the explicit focus.",
    context_request=ContextBuildRequest(
        scope=".",
        focus_paths=("pkg/file.py",),
        search_queries=("completion",),
    ),
    expected_calls=(),
)
evidence = evaluate(case, provider=strict_fake)
assert evidence.all_required_instructions_precede_content
assert evidence.search_match_owners_are_covered
assert evidence.search_requests == (
    SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100),
)
assert evidence.passed
```

The explicit request is case evidence, not a protocol option or production fallback. Its root,
nested focus, and first-occurrence search-match-owner instruction bindings precede their content; the
focus and search matches do not fan out into extra search roots. A separate ordinary-runtime fake
starts with root instructions only. Its successful direct or broad read covers every local
`instruction_scope` before the result appears in a second request.

### Planned pseudocode: cooperative cancellation evidence

```python
for checkpoint, sentinel in (
    ("before_dispatch", no_candidate),
    ("after_dispatch", result_candidate),
    ("after_discovery", instruction_bundle_candidate),
    ("after_merge", context_candidate),
    ("before_provider_start", (history_candidate, request_candidate)),
):
    evidence = await cancel_at(checkpoint, sentinel=sentinel)
    if checkpoint == "before_dispatch":
        assert evidence.native_dispatches == 0
    assert evidence.committed_candidates == ()
    assert evidence.follow_up_provider_starts == 0
```

Each named `asyncio.Event` gate runs after CAH-034's unconditional cooperative yield and before its
cancellation/deadline guard. Distinctive sentinels show which synchronous stage completed, while the
empty committed snapshot proves completion of a stage is not permission to expose its value.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| runtime derives search from task | composition test fails | captured exact default differs |
| composition uses bare loop defaults | composition test fails | exact `(4, 120, 4096, 3)` profile differs |
| distractor read | case fails | exact dispatch mismatch |
| forbidden source/claim | case fails | mutation rule triggers |
| list/search returns `pkg` and sibling paths | complete ordered owner coverage | every binding precedes replay |
| one broad-result owner fails discovery/budget | safe terminal | no result, partial context, or next start |
| known arguments repeat `path` | exact `invalid_read_tool_input` | charged call; zero key gate/dispatch/context growth |
| repeated/canonical-alias scope grows context | idempotence check fails | byte-identical snapshot expected |
| sibling instruction overrides `pkg` | applicability check fails | both `applies_to` values retained |
| linked instruction derives scope from target | provenance check fails | `source="shared/rules.md"`, `applies_to="pkg"` expected |
| linked instruction targets hard-denied path | reject whole build | zero target reads and no partial context |
| focus/result becomes a search root | exact projection check fails | only `("completion", ".", 4, 100)` expected |
| discovery/merge/budget failure | safe terminal | no next start or pending result/context evidence |
| invalid eval request | reject before provider | zero starts |
| cancellation before dispatch | one bounded terminal | zero native dispatch and zero continuation |
| cancellation after sync stage | one bounded terminal | named gate, local sentinel discarded, zero next starts |
| live output varies | separate observation | never gates Done |

## Production expansion

### Example enterprise scenario

A production evaluation program covers many repositories/models with human labels, privacy review,
cost/latency metrics, and regression monitoring. It needs dataset governance and statistical care.

### Typical production capabilities and tools

- [pytest](https://docs.pytest.org/en/stable/) runs deterministic fixtures/mutations cheaply; teams
  maintain cases and failure diagnostics.
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
  guides task-specific evals; representative data and ongoing curation cost remain.
- [OpenAI Evals](https://github.com/openai/evals) offers reusable runners/scorers; framework and
  dataset operations may exceed this small project's needs.
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) correlate steps;
  redaction, sampling, storage, and access control add operational cost.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Dataset | two synthetic cases + mutations | governed representative corpus |
| Provider | strict fake default | model matrix + human labels |
| Score | exact evidence + narrow facts | calibrated quality/grounding metrics |
| Context | fixed runtime default | measured retrieval policy |
| Cost | fast, offline | inference, labeling, telemetry operations |

### Trade-offs and graduation signals

Small fixtures are reproducible but do not predict broad quality. Add cases for observed failure
classes; adopt model-graded or live scoring only after labeled calibration can quantify errors/cost.

## Practical exercises

1. Explain why exact dispatch evidence is stronger than one answer substring.
2. Add a keyword-sharing distractor and predict the expected calls.
3. Prove evaluation injection cannot change a later ordinary session.
4. Explain why explicit composition is safer than relying on the current `LoopLimits()` defaults.
5. Derive the ordered scopes for a broad list/search result and explain why they add instructions but
   never search roots.
6. Explain why `{"path":"a","pa\u0074h":"b"}` is preserved through CAH-036 yet fails in CAH-034.
7. For `pkg/AGENTS.md -> shared/rules.md`, explain why `source` and `applies_to` must differ.
8. Map all five checkpoint types, including repeated per-scope gates, to the newest local candidate.
9. Teach back what M2 proves and what MCP, editing, and secret scanning still require.

## Key takeaways

- Composition tests protect architectural ownership at the vertical seam.
- The composition root supplies the exact M2 limits; provider choice and constructor defaults do not.
- Ordinary context defaults are explicit and do not hide task-derived retrieval.
- Injected focus chains are required before focus content; search projection stays rooted at the
  supplied scope, while search-match owners receive instructions before excerpts.
- Instruction provenance and applicability are separate, and a hard-denied linked target produces
  neither a read nor partial context.
- Successful direct and broad reads cover every requested/result owner atomically; repeats/aliases
  are idempotent, siblings stay separately applicable, and any failed owner discards the transaction.
- Raw arguments remain untouched through provider boundaries; CAH-034's lookup-first recursive pair
  decoder rejects duplicate decoded names before dictionary collapse or native work.
- The before-dispatch gate proves cancellation runs no handler; later cooperative gates prove
  synchronous results remain local candidates until final admission.
- Deterministic tool/source evidence is authoritative; optional live output is observational.

## Glossary

- **Vertical slice:** complete path through multiple architecture layers.
- **Fixture workspace:** small synthetic repository with stable expected evidence.
- **Deterministic evaluator:** offline runner that repeats the same result.
- **Observational evidence:** useful live result that does not gate correctness.
- **Instruction scope:** a requested path or validated result owner whose applicable bundle must be
  present before replay; it is local metadata, not provider-visible content.
- **Candidate owner:** canonical directory containing the probed instruction leaf; it defines
  `applies_to` even when the leaf resolves to a different internal target.
- **Cooperative gate:** deterministic test hook between an unconditional event-loop yield and the
  cancellation/deadline guard at one named synchronous-stage boundary.

## Further reading

- [CAH-037 delivery contract](../../user-stories/cah-037-prove-read-only-assistant.md)
- [pytest](https://docs.pytest.org/en/stable/)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)
