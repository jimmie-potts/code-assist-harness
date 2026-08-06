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
Broad list/search cases prove the execution-time canonical request scope and every returned owner are
covered before replay, while duplicate raw arguments prove zero dispatch and context growth.
Evaluation alone may inject explicit focus/search context and proves its exact projections, initial
I/O order, and scope-consistency guard. Named cancellation gates prove synchronous-stage candidates
never become partial session state.

## Learning objectives

After this unit, you should be able to:

- locate dependency selection in the composition root;
- distinguish production defaults from test/evaluation injection;
- prove all explicit-focus instruction chains precede focus content and search remains rooted at the
  supplied scope;
- distinguish a resolved instruction `source` from its candidate-owner `applies_to` scope;
- prove execution-time canonical request and result-owner instruction enrichment without turning
  results into search roots;
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
After native result validation, CAH-031 derives local `instruction_scopes`: the execution-time
canonical request scope first, then every exact-deduplicated returned-path owner. A `list_files`
result naming `pkg/file.py` therefore requires both its captured request scope and the `pkg`
instruction bundle before replay. Each bundle must still report the captured canonical scope before
merge. The original alias and a canonical label retargeted to another allowed scope are not
post-dispatch authority, the local tuple is not a provider field or a new search root, and one failed
scope discards the whole result/context transaction.

The injected focus path is different: it is explicit input to CAH-030, so its instruction chain is
required initial context. CAH-030 searches only from the supplied `scope`, then discovers every
first-occurrence search-match owner and adds its required instructions before any matching excerpt.
It validates all projections before I/O, discovers/folds/checks root first, completes focus work
before search, and requires every search result's execution-time canonical scope to match the root
discovery snapshot immediately before another search. Focus and match-owner discoveries must also
return the captured scope before merge. Focus and result paths never silently become additional
search roots.

Duplicate JSON is another composition boundary. CAH-032 construction and CAH-036 mapping reject a
malformed tool-name carrier or argument string above 16 KiB before CAH-033/039. CAH-032, CAH-033, and
CAH-036 preserve every admitted argument byte; CAH-039 therefore sees only a valid carrier at or below
the bound. It looks up the name first and preflights that complete value with an iterative
quote-aware delimiter stack capped at 64 object/array levels (root object is depth 1), rejects
non-signed-64-bit/fractional/exponent numeric tokens, non-finite constants, and defensive decoder
recursion/value failure, then pair-decodes and compares decoded names by exact code point without
normalization at every admitted object depth. A known structural, numeric, or duplicate error is
charged but becomes `invalid_read_tool_input` with zero key gate, Pydantic validation, dispatch, or
context growth. When final admission passes, its exact call/error pair is replayed in a follow-up
against unchanged context.

Result projection is a separate CAH-031 boundary. The evaluator also proves the outer `result` object
is depth 1 within a 64-level complete-envelope cap, a wide value stops at the 65,536-unit
pre-serialization work budget before sorting/encoding, and defensive serializer
`RecursionError`/`ValueError` becomes the fixed invalid-result failure. Byte overflow remains the
distinct `read_tool_output_too_large` known error.

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
- **Scoped enrichment evidence:** exact before/after requests proving every ordered execution-time
  canonical request and returned-owner scope was covered before result replay.
- **Structural-decoder evidence:** exact stage counters proving CAH-039 enforced the aggregate byte
  and depth bounds, rejected unsafe constants/recursion, saw preserved raw pairs, and checked
  duplicates before dictionary construction.
- **Mutation:** deliberate test change proving a claimed check can fail.
- **Candidate state:** a result, instruction bundle, context, replay history, or bounded request held
  locally until the final checkpoint and admission succeed.
- **One service graph:** a sole boundary-only factory constructs and exposes the exact instruction,
  policy, reader, search, context, registry, and catalog identities.
- **Provider-backed mock:** the default runtime now exercises the same session/context/limit path as
  OpenAI while emitting fixed local text with no network.

## Architecture and design

```text
Ink TUI               Python runtime composition                    Provider
 task ----------> ContextBuildRequest(".", (), ()) ----------> request 1: root instructions
                  + build_read_only_agent_services(boundary)
                    -> instructions -> policy -> metadata/text/search
                    -> context builder -> registry -> catalog
                  + CAH-035 bounded loop --------------------> deterministic mock (default)
                                                            \-> strict fake (eval)
                    limits = (turns=4, seconds=120, bytes=4096, calls=3)
                  + CAH-036 OpenAI adapter                    \-> explicit live opt-in
                              |
          read/stat/list/search succeeds
                              v
 CAH-031 registry -> CAH-039 factory -> internal CAH-038 bridge -> catalog.definitions
 CAH-032/036 admitted carrier (valid name shape; arguments <= 16 KiB)
        -> same CAH-039 catalog: lookup -> structural preflight -> pair decode
        -> iterative duplicate walk -> exact-key gate -> Pydantic -> prepared invocation
        -> before_dispatch -> CAH-034 identity guard
        -> CAH-031 dispatch_bound(entry, request) -> after_dispatch
        -> CAH-034 correlated result + CAH-031 local instruction_scopes
        -> per scope: after_discovery -> after_merge -> before_provider_start
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

The launched mock now uses `ProviderSessionRunner`, so its opaque IDs intentionally become
`ses_provider_<n>` and transcript-v3 gains the exact loop-limit aggregate. Model usage remains absent.
Historical `MockSessionRunner` keeps `ses_mock_<n>`, partial-delta cancellation, and its older evidence
shape only in focused tests and frozen lessons; those are not current runtime guarantees.

## Practical walkthrough

1. Construct one boundary and call the sole services factory; assert all nine exposed identities and
   every edge before provider or repository I/O.
2. Construct the exact four-field M2 limit profile at the composition root.
3. Capture the exact empty-focus/search runtime request.
4. Build a minimal fixture with root, `pkg`, and sibling instructions; an allowed internal
   instruction symlink; a hard-denied-target mutation; relevant source; and distractors.
5. Assert request one has only root instructions, then make the exact successful
   `read_file(path="pkg/file.py")` call and assert request two adds
   `source="shared/rules.md"`, `applies_to="pkg"`, and its copied canonical-depth `precedence`.
6. Return broad list/search paths under `pkg` and a sibling. Assert the captured canonical request
   scope and every first-occurrence owner bundle are present before replay. Retarget an empty-result
   `alias -> A` to `B` after dispatch and prove only `A` drives discovery; make `A` unavailable and
   assert no result, partial context, fallback, or next provider start. Then replace captured `A`
   itself with an allowed symlink to `B`; CAH-025 reports `B` and exact comparison must fail before
   merge.
7. Inject the exact root/focus/search request only through the runner's immutable
   `initial_context_request` argument in named evaluation assembly. Assert projections
   validate before I/O, root discovery/fold/budget is first, focus work completes before search, the
   complete instruction union precedes focus content, and the only search projection is
   `SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`. Retarget a
   supplied scope alias between root discovery and a no-match search; canonical-scope mismatch must
   return no package and execute zero later searches. Retarget one captured focus/owner canonical
   label and require the discovered bundle mismatch to fail before merge.
8. Assert the instruction symlink reports resolved `source="shared/rules.md"` and owner
   `applies_to="pkg"`; mutate its target to a hard-denied path and assert no target read or package.
   At separate seams before probe/read, replace captured owner `pkg` with an allowed symlink to
   `other`; exact owner re-admission must fail before resolving or reading `other/AGENTS.md`.
9. First send malformed tool-name carriers and 16,383/16,384/16,385-byte argument carriers through
   CAH-032/036; assert rejected carriers never invoke CAH-033 or CAH-039. Then use only admitted,
   at-or-below-limit carriers for CAH-039: send 63/64/65-level object/array shapes, quoted and escaped
   delimiters, mismatched containers,
   signed-64-bit endpoints/overflow, fractions/exponents, a 5,000-digit integer, numeric-looking
   strings, `NaN`/infinities, forced decoder `RecursionError`/`ValueError`, and conflicting/escape-equivalent/nested/
   array-contained duplicate names. Assert CAH-039 returns the fixed error for each rejected shape
   with a charged call and zero key gate, Pydantic validation, dispatch, or context growth; assert
   exact unchanged-context call/error replay when admission passes and that unknown-name lookup still
   wins before structural work.
   Then run complete result-envelope depths 63/64/65, a wide 65,536-unit-work-budget exhaustion,
   forced serializer `RecursionError`/`ValueError`, success envelopes at 65,536/65,537 bytes, and a
   native 65,536-byte file whose metadata/wrapper overflows. Assert the deep/serializer failures use
   the fixed invalid-result error while work/byte overflow uses
   `read_tool_output_too_large` result, cross `after_dispatch`, carry no scopes/content, and replay
   against unchanged context rather than terminating the session.
10. Drive 8,191/8,192/8,193-byte ASCII/multibyte text through real neutral and OpenAI producers.
    Require bounded normal carriers or the content-free overflow marker, one 8,193 tracker
    reservation, zero publication/usage/dispatch, and no overflow-tail work. Pump the maximum legal
    one-byte function-call fragments at constant stack depth, then prove a raw terminal releases no
    neutral tuple before EOF and discards it on an extra event or iterator exception.
11. Gate cancellation at initial `after_focus_read`/`after_search`, every initial root/focus/search-
    owner `after_discovery`/`after_merge`, and loop `before_dispatch`/`after_dispatch`/each result-scope
    discovery/merge/`before_provider_start`; assert no initial package or later I/O after an initial
    loss, no native handler at the pre-dispatch loss, no committed candidate, and no next start.
12. Assert exact model history/tool dispatch before checking narrow answer facts, then run all cases
   twice for identical results.

## Implementation code samples

### Planned pseudocode: ordinary runtime

```python
boundary = WorkspaceBoundary.from_path(workspace_root)
services = build_read_only_agent_services(boundary)
m2_limits = LoopLimits(
    max_model_turns=4,
    provider_work_timeout_seconds=120,
    max_assistant_output_bytes=4096,
    max_observed_tool_calls=3,
)
runtime = ProviderSessionRunner(
    writer=writer,
    provider=DeterministicMockProvider(MOCK_RESPONSE_DELTAS),
    read_only_services=services,
    limits=m2_limits,
    initial_context_request=None,  # exact root-only production default
)
```

The task does not influence initial source selection. The deterministic mock is task-independent,
credential-free, and network-free but now exercises the same provider-backed session path. The root
does not rely on the
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
evidence = evaluate(
    case,
    runner=ProviderSessionRunner(
        writer=writer,
        provider=strict_fake,
        read_only_services=services,
        limits=m2_limits,
        initial_context_request=case.context_request,
    ),
)
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
    ("after_focus_read", focus_candidate),
    ("after_search", search_candidate),
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

Every initial and loop gate runs after CAH-034's same unconditional cooperative yield and before its
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
| tool request alias retargets after dispatch | captured canonical scope only | no replacement instruction or alias fallback |
| captured canonical label retargets to allowed scope | exact bundle-scope check | no merge, replacement instruction, replay, fallback, or next start |
| initial scope alias retargets before search | `context_build_failed` | result scope differs from root snapshot; no package |
| root/focus setup fails | fail before later I/O | root failure has zero focus/search calls; focus failure has zero search calls |
| one broad-result owner fails discovery/budget | safe terminal | no result, partial context, or next start |
| malformed name or arguments above 16 KiB | CAH-032 construction/CAH-036 mapping rejects | zero CAH-033/039 calls |
| known arguments exceed 64 levels or mismatch containers | exact `invalid_read_tool_input` | preflight rejects before decode/key gate/dispatch |
| known arguments use `NaN`/infinity or decoder recurses | exact `invalid_read_tool_input` | no parser detail; zero key gate/dispatch/context growth |
| known arguments overflow signed 64-bit, use fraction/exponent, or hit decoder `ValueError` | exact `invalid_read_tool_input` | numeric preflight prevents interpreter-limit failure; zero later stages |
| known arguments repeat a decoded name through depth 64 | exact `invalid_read_tool_input` | charged call; zero key gate/dispatch/context growth |
| result envelope reaches depth 65 or serializer raises | exact `invalid_read_tool_result` | no interpreter text or partial output |
| wide result exhausts the 65,536-unit work budget | exact `read_tool_output_too_large` | stop before sorting/serialization or sentinel sibling |
| wrapped result exceeds 65,536 bytes | exact `read_tool_output_too_large` | charged call; no scopes/content, unchanged-context replay, not a session-terminal shortcut |
| repeated/canonical-alias scope grows context | idempotence check fails | byte-identical snapshot expected |
| sibling instruction overrides `pkg` | applicability check fails | both `applies_to` values retained |
| OpenAI mapping renumbers a missing-ancestor gap | exact request mismatch | CAH-025 depth rank is copied, not derived from array position |
| linked instruction derives scope from target | provenance check fails | `source="shared/rules.md"`, `applies_to="pkg"` expected |
| linked instruction targets hard-denied path | reject whole build | zero target reads and no partial context |
| captured instruction owner retargets `A -> B` before probe/read | reject whole build | no `B/AGENTS.md` resolution/read and no false `applies_to=A` binding |
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
6. Retarget aliases during initial context search and after tool dispatch; distinguish the expected
   atomic mismatch from the captured-scope success.
7. Retarget the captured canonical label itself and explain why CAH-025's returned bundle must be
   rejected before merge.
8. Test signed-64-bit endpoints, overflow, fractions/exponents, a 5,000-digit integer, and
   numeric-looking strings through the full composed path.
9. Explain why `{"path":"a","pa\u0074h":"b"}` is preserved through CAH-036 yet fails in CAH-039.
10. For `pkg/AGENTS.md -> shared/rules.md`, explain why `source` and `applies_to` must differ.
11. Map all five checkpoint types, including repeated per-scope gates, to the newest local candidate.
12. Teach back what M2 proves and what MCP, editing, and secret scanning still require.

## Key takeaways

- Composition tests protect architectural ownership at the vertical seam.
- The composition root supplies the exact M2 limits; provider choice and constructor defaults do not.
- Ordinary context defaults are explicit and do not hide task-derived retrieval.
- Injected focus chains are required before focus content; search projection stays rooted at the
  supplied scope, while search-match owners receive instructions before excerpts.
- Instruction provenance and applicability are separate; hard-denied linked targets and retargeted
  candidate owners produce neither replacement reads nor partial context.
- Successful direct and broad reads cover every execution-time canonical request/result owner
  atomically; every discovered bundle must still name its captured scope, the original alias is never
  post-dispatch authority, repeats are idempotent, siblings stay separately applicable, and any
  failed owner discards the transaction.
- Raw arguments remain untouched through provider boundaries; CAH-039's lookup-first, 16-KiB/
  64-level structural plus signed-64-bit numeric preflight, constant-safe pair decoder, and iterative
  every-depth duplicate walk reject unsafe JSON before interpreter conversion, dictionary collapse,
  or native work.
- Producer-bound carrier failures never reach CAH-039; its composed cases begin with an admitted
  name shape and at-or-below-limit raw arguments.
- CAH-031 separately bounds result depth, width/work, bytes, and serializer failure before replay.
- The before-dispatch gate proves cancellation runs no handler; later cooperative gates prove
  synchronous results remain local candidates until final admission.
- Deterministic tool/source evidence is authoritative; optional live output is observational.

## Glossary

- **Vertical slice:** complete path through multiple architecture layers.
- **Fixture workspace:** small synthetic repository with stable expected evidence.
- **Deterministic evaluator:** offline runner that repeats the same result.
- **Observational evidence:** useful live result that does not gate correctness.
- **Instruction scope:** an execution-time canonical request path or validated result owner whose
  applicable bundle must be present before replay; it is local metadata, not provider-visible
  content.
- **Candidate owner:** canonical directory containing the probed instruction leaf; it defines
  `applies_to` even when the leaf resolves to a different internal target.
- **Cooperative gate:** deterministic test hook between an unconditional event-loop yield and the
  cancellation/deadline guard at one named synchronous-stage boundary.

## Further reading

- [CAH-039 argument-admission lesson](cah-039-provider-tool-argument-admission.md)
- [CAH-037 delivery contract](../../user-stories/cah-037-prove-read-only-assistant.md)
- [pytest](https://docs.pytest.org/en/stable/)
- [OpenAI evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices)
- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/)
