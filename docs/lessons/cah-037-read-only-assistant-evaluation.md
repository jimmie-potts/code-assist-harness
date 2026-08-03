# CAH-037 lesson: Prove the read-only assistant

- **Unit:** CAH-037
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; M2 is not yet composed or evaluated
- **Story:** [CAH-037](../../user-stories/cah-037-prove-read-only-assistant.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Composition-root ownership, exact root-only context defaults, scoped-instruction
  enrichment after path-targeted reads, and deterministic evidence for grounded explanation and
  planning
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Evaluation](../evaluation.md), [Architecture](../architecture.md), and
  [Context engineering](../context-engineering.md)

> This lesson defines planned deterministic evidence. Fixtures and pseudocode do not prove M2 yet.

## Quick summary

CAH-037 composes M2 and proves explain/plan outcomes with strict fakes. Ordinary runtime starts with
only root-scoped instructions and explicitly receives the M2 four-turn/three-call limit profile;
after `read_file(path="pkg/file.py")` succeeds, the next request includes `pkg/AGENTS.md`.
Evaluation alone may inject explicit focus/search context.

## Learning objectives

After this unit, you should be able to:

- locate dependency selection in the composition root;
- distinguish production defaults from test/evaluation injection;
- prove requested-path instruction enrichment and reject returned-path scope inference;
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
eval assembly:    explicit validated request injected for one named case
```

A common misconception is that the runtime should parse task text into hidden search queries. In M2,
the model explores explicitly through tools; only eval/test assembly gets the injection seam.

A tool result is also not authority to select scope. If `list_files` returns `pkg/file.py`, the loop
must make a successful specific path-targeting call before `pkg/AGENTS.md` can enter context.

## Key concepts

- **Composition root:** outer module that wires concrete implementations to domain ports.
- **Production default:** invariant used by ordinary interactive sessions.
- **Composition profile:** exact dependency values selected by the runtime instead of inherited
  constructor defaults.
- **Evaluation injection:** explicit controlled dependency used only by named cases/tests.
- **Grounding evidence:** exact admitted source/tool observations supporting an answer.
- **Scoped enrichment evidence:** exact before/after requests proving a successful requested path
  added only its applicable instruction chain.
- **Mutation:** deliberate test change proving a claimed check can fail.

## Architecture and design

```text
Ink TUI               Python runtime composition                 Provider
 task ----------> ContextBuildRequest(".", (), ()) -------> request 1: root instructions
                  + workspace/instructions/context
                  + registry + CAH-035 bounded loop ------> strict fake (default eval)
                    limits = (turns=4, seconds=120, bytes=4096, calls=3)
                  + CAH-036 OpenAI adapter                 \-> explicit live opt-in
                              |
          read_file("pkg/file.py") succeeds
                              v
             CAH-025 discover -> CAH-030 atomic merge ---> request 2: + pkg/AGENTS.md
                              |
fixture workspace <-----------+        Evaluation may inject explicit context request
                              |
final text <-------------------+        Existing protocol only

Evaluator: exact context + dispatch + relative citations/facts - forbidden evidence
```

The default has no hidden focus/search selection. Explain and plan remain ordinary task text, and a
plan performs no edit.

## Practical walkthrough

1. Compose only public CAH-025 through CAH-036 boundaries.
2. Construct the exact four-field M2 limit profile at the composition root.
3. Capture the exact empty-focus/search runtime request.
4. Build a minimal fixture with root, `pkg`, and sibling instructions, relevant source, and
   distractors.
5. Assert request one has only root instructions, then make the exact successful
   `read_file(path="pkg/file.py")` call and assert request two adds `pkg/AGENTS.md` plus `applies_to`.
6. Inject an explicit context request only in the named evaluation assembly.
7. Assert exact model history/tool dispatch before checking narrow answer facts.
8. Mutate scope, idempotence, sibling, safety, and evidence rules; run twice for identical results.

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
    task="Explain where completion is selected.",
    context_request=ContextBuildRequest(scope=".", focus_paths=(), search_queries=()),
    expected_calls=(("read_file", {"path": "pkg/file.py"}),),
)
assert evaluate(case, provider=strict_fake).passed
```

The explicit request is case evidence, not a protocol option or production fallback. The fake's
first request contains root instructions only; after the requested read succeeds, its second request
contains `pkg/AGENTS.md`. A broad list/search result naming the same path is insufficient.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| runtime derives search from task | composition test fails | captured exact default differs |
| composition uses bare loop defaults | composition test fails | exact `(4, 120, 4096, 3)` profile differs |
| distractor read | case fails | exact dispatch mismatch |
| forbidden source/claim | case fails | mutation rule triggers |
| list/search merely returns `pkg/file.py` | no instruction growth | specific path-targeting call required |
| repeated/canonical-alias scope grows context | idempotence check fails | byte-identical snapshot expected |
| sibling instruction overrides `pkg` | applicability check fails | both `applies_to` values retained |
| discovery/merge/budget failure | safe terminal | no next start or pending result/context evidence |
| invalid eval request | reject before provider | zero starts |
| cancellation/late tool/discovery/merge value | one bounded terminal | no late evidence |
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
5. Explain why a broad returned path cannot select its nested instructions.
6. Teach back what M2 proves and what MCP, editing, and secret scanning still require.

## Key takeaways

- Composition tests protect architectural ownership at the vertical seam.
- The composition root supplies the exact M2 limits; provider choice and constructor defaults do not.
- Ordinary context defaults are explicit and do not hide task-derived retrieval.
- Successful requested paths enrich instructions atomically; repeats/aliases are idempotent,
  siblings stay separately applicable, and returned paths do not select scope.
- Deterministic tool/source evidence is authoritative; optional live output is observational.

## Glossary

- **Vertical slice:** complete path through multiple architecture layers.
- **Fixture workspace:** small synthetic repository with stable expected evidence.
- **Deterministic evaluator:** offline runner that repeats the same result.
- **Observational evidence:** useful live result that does not gate correctness.
- **Path-targeting call:** a tool request whose validated `path`, not returned content, selects the
  local instruction scope after success.

## Further reading

- [CAH-037 delivery contract](../../user-stories/cah-037-prove-read-only-assistant.md)
- [pytest](https://docs.pytest.org/en/stable/)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)
