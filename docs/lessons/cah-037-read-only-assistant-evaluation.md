# CAH-037 lesson: Prove the read-only assistant

- **Unit:** CAH-037
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; M2 is not yet composed or evaluated
- **Story:** [CAH-037](../../user-stories/cah-037-prove-read-only-assistant.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Composition-root ownership, exact runtime context defaults, and deterministic
  evidence for grounded explanation and planning
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Evaluation](../evaluation.md), [Architecture](../architecture.md), and
  [Context engineering](../context-engineering.md)

> This lesson defines planned deterministic evidence. Fixtures and pseudocode do not prove M2 yet.

## Quick summary

CAH-037 composes M2 and proves explain/plan outcomes with strict fakes. Ordinary runtime starts with
only root-scoped instructions; evaluation alone may inject explicit focus/search context.

## Learning objectives

After this unit, you should be able to:

- locate dependency selection in the composition root;
- distinguish production defaults from test/evaluation injection;
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

## Key concepts

- **Composition root:** outer module that wires concrete implementations to domain ports.
- **Production default:** invariant used by ordinary interactive sessions.
- **Evaluation injection:** explicit controlled dependency used only by named cases/tests.
- **Grounding evidence:** exact admitted source/tool observations supporting an answer.
- **Mutation:** deliberate test change proving a claimed check can fail.

## Architecture and design

```text
Ink TUI               Python runtime composition                 Provider
 task ----------> ContextBuildRequest(".", (), ())
                  + workspace/instructions/context
                  + registry + CAH-035 bounded loop ------> strict fake (default eval)
                  + CAH-036 OpenAI adapter                 \-> explicit live opt-in
                              |
                    four native read tools
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
2. Capture the exact empty-focus/search runtime request.
3. Build a minimal fixture with instructions, relevant source, and distractors.
4. Inject an explicit context request only in the named evaluation assembly.
5. Assert exact model history/tool dispatch before checking narrow answer facts.
6. Mutate every safety/evidence rule and run twice for identical results.

## Implementation code samples

### Planned pseudocode: ordinary runtime

```python
context_request = ContextBuildRequest(
    scope=".",
    focus_paths=(),
    search_queries=(),
)
runtime = compose(context_request_factory=lambda _task: context_request)
```

The task does not influence initial source selection.

### Planned pseudocode: evaluation-only injection

```python
case = ReadOnlyCase(
    task="Explain where completion is selected.",
    context_request=ContextBuildRequest(scope=".", focus_paths=("src/session.py",)),
    expected_calls=("read_file",),
)
assert evaluate(case, provider=strict_fake).passed
```

The explicit request is case evidence, not a protocol option or production fallback.

## Failure scenarios to study

| Scenario | Safe result | Evidence |
| --- | --- | --- |
| runtime derives search from task | composition test fails | captured exact default differs |
| distractor read | case fails | exact dispatch mismatch |
| forbidden source/claim | case fails | mutation rule triggers |
| invalid eval request | reject before provider | zero starts |
| cancellation/late tool result | one bounded terminal | no late evidence |
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
4. Teach back what M2 proves and what MCP, editing, and secret scanning still require.

## Key takeaways

- Composition tests protect architectural ownership at the vertical seam.
- Ordinary context defaults are explicit and do not hide task-derived retrieval.
- Deterministic tool/source evidence is authoritative; optional live output is observational.

## Glossary

- **Vertical slice:** complete path through multiple architecture layers.
- **Fixture workspace:** small synthetic repository with stable expected evidence.
- **Deterministic evaluator:** offline runner that repeats the same result.
- **Observational evidence:** useful live result that does not gate correctness.

## Further reading

- [CAH-037 delivery contract](../../user-stories/cah-037-prove-read-only-assistant.md)
- [pytest](https://docs.pytest.org/en/stable/)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)
