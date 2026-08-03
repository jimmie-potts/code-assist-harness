# CAH-037 - Prove the read-only assistant

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E8 - Evaluation and observability
- **Dependencies:** CAH-025, CAH-026, CAH-027, CAH-028, CAH-029, CAH-030, CAH-031, CAH-032,
  CAH-033, CAH-034, CAH-035, CAH-036
- **Lesson:** [Proving the read-only assistant](../docs/lessons/cah-037-read-only-assistant-evaluation.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Composition-root ownership and deterministic end-to-end evidence for exact
  initial-context projections, scoped instruction ownership, and cooperative cancellation before
  retrieval produces a grounded explanation or plan, without permitting writes.

## User story

> As a repository user, I want the configured assistant to inspect bounded workspace evidence and
> return a grounded explanation or plan so that M2's read-only outcome is proven through the real
> harness composition rather than isolated components alone.

## Single responsibility

CAH-037 composes the already-proven M2 components and adds deterministic fixture evaluation for the
read-only outcome. It does not change a component contract, retrieval policy, tool, provider grammar,
protocol message, UI surface, or write capability.

## Scope

- Compose workspace boundary, instruction discovery, default context request, read registry,
  staged-response admission, bounded loop, existing evidence, and selected fake/OpenAI provider in
  the Python runtime root.
- Supply the exact M2 loop-limit profile at that composition root rather than inheriting the existing
  one-turn/one-call `LoopLimits` defaults.
- Lock the ordinary runtime to one explicit default CAH-030 request rather than inferring files or
  searches from task text.
- Prove that the exact root-only initial context is atomically enriched with every applicable nested
  instruction before a successful tool result exposing that path is replayed.
- Permit deterministic evaluation composition to inject an explicit context request through a test/
  eval-only seam.
- Evaluate one injected initial request with root scope, a nested explicit focus path, and a literal
  search query so the complete scope-plus-focus-plus-search-owner instruction union, focus content,
  and exact scope-rooted search projection are observable in order.
- Evaluate internal instruction symlink provenance/applicability and hard-denied symlink targets
  without weakening CAH-025/026 policy.
- Evaluate all five named cooperative checkpoints before dispatch, after synchronous dispatch,
  after discovery, after merge, and before provider start with deterministic gates and distinctive
  local candidates.
- Introduce `evals/` with one synthetic workspace and strict-fake explain/plan cases only when the
  runnable runner, assertions, documentation, and tests arrive together.
- Preserve mock as the credential-free default and OpenAI as explicit bounded-egress opt-in.
- Document exactly what M2 proves and what MCP, editing, secret scanning, and production retrieval
  still require.

## Locked contract

- The runtime composition root is the only place that selects concrete workspace, context, registry,
  loop, transcript, and provider implementations. Domain modules neither import the runtime nor
  select a provider.
- Every ordinary interactive task constructs exactly
  `ContextBuildRequest(scope=".", focus_paths=(), search_queries=())`. The runtime does not derive a
  focus path, search query, scope, or hidden retrieval hint from task text, provider output, current
  directory below the workspace root, environment variables, or TUI state. Initial context therefore
  contains only root-applicable CAH-025 instructions; repository exploration and any narrower
  instruction discovery occur through admitted read tools.
- The deterministic evaluator may inject one explicit validated `ContextBuildRequest` for a named
  case through the composition dependency. That seam is callable only by eval/test assembly, is not
  a protocol field or user-provider option, and records its exact request in structured test evidence.
  Evaluation injection never mutates the ordinary runtime default.
- The injected initial-context case supplies exactly `scope="."`,
  `focus_paths=("pkg/file.py",)`, and `search_queries=("completion",)`. Before any focus content is
  appended, its candidate package contains the CAH-025 bundle for `.` followed by the bundle for the
  canonical `pkg/file.py` focus path, folded through CAH-030's topology-correct merge. Its only search
  projection is exactly
  `SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`. The supplied scope
  remains the search root: neither a focus path, an admitted focus result, nor a returned search path
  creates another search root. Every first-occurrence search-match owner does trigger CAH-025
  discovery and joins the required instruction union before its excerpt enters context.
- Default mock behavior is deterministic, credential-free, and network-free. Strict M2 evaluations
  inject exact fake scripts. OpenAI remains an explicit selection with CAH-036's bounded repository-
  content egress consent and no-content-secret-scanning warning.
- One ordinary accepted task creates one immutable workspace boundary, discovers root instructions,
  builds one initial context package, and allocates fresh loop accounting before provider work. The
  injected evaluator uses the same atomic builder with its explicit request. Before a successful
  admitted `read_file` with `path="pkg/file.py"`,
  `cooperate_then_guard("before_dispatch")` can cancel with zero native dispatch. After dispatch,
  CAH-034's
  `cooperate_then_guard("after_dispatch")` observes the distinctive local result candidate, CAH-025
  discovers each distinctive instruction-bundle candidate from CAH-031's ordered local scopes, and
  `cooperate_then_guard("after_discovery")` runs after every one. CAH-030 folds each bundle into a
  local replacement and `cooperate_then_guard("after_merge")` runs after every fold. Candidate
  replay history and the bounded request are built locally before
  `cooperate_then_guard("before_provider_start")`. Named `asyncio.Event` gates deterministically
  cancel at each checkpoint, including a later broad-result scope. At every losing gate, all
  candidates produced so far are discarded; no result, instructions, context, history, or request is
  committed and no next fake/OpenAI operation starts. Known tool errors carry no scopes, keep the
  prior context candidate, and use the same final checkpoint; cancellation/deadline, discovery, or
  merge failure has the same no-partial-commit outcome.
  The composition root
  explicitly constructs `LoopLimits(max_model_turns=4, provider_work_timeout_seconds=120,
  max_assistant_output_bytes=4096, max_observed_tool_calls=3)` for every M2 session. These are CAH-035's
  four-turn/three-call ceilings with CAH-022's existing timeout/output profile made explicit; it never
  relies on `LoopLimits()` defaults, reuses a tracker, or lets provider selection alter the values.
  Available tools are exactly `list_files`, `stat_path`, `read_file`, and `search_text`, derived from
  the registry.
- Explain and plan are ordinary task text, not new commands or loop modes. A plan is advice only.
  Only an accepted non-empty final answer reaches existing `assistant.delta`,
  `assistant.completed`, and `session.completed` events.
- The synthetic fixture contains stable instructions, source, distractors, one allowed internal
  `pkg/AGENTS.md` symlink, one hard-denied-target mutation, and expected relative evidence but no
  copied secret, dependency tree, generated artifact, host-specific path, VCS data, or live
  credential. The allowed link proves the resolved canonical `source` can differ from the canonical
  candidate-owner `applies_to`; the denied-target mutation proves zero target reads and no partial
  initial context.
- At least two outcome cases execute: explain a known implementation fact and plan a bounded change.
  Contract cases additionally assert the exact root-only runtime request, the injected scope/focus/
  search projection, instruction-union-before-focus ordering, internal-symlink `source`/`applies_to`,
  the `read_file(path="pkg/file.py")` enrichment step, a broad search/list result whose returned
  owners add sibling instruction bindings before replay, the next request containing the binding
  `source="shared/rules.md"` with `applies_to="pkg"`, provider history, calls/results, accepted
  sources, final workspace-relative citations, and small required/forbidden answer facts.
- M2 enriches context from CAH-031's ordered `instruction_scopes` for every successful read. The
  validated requested path is first; local metadata then contains the exact-deduplicated owner of
  every model-visible result path. A broad `list_files` or `search_text` result is not replayed until
  every owner bundle is discovered, folded, budgeted, and guarded. Repeated and canonical-alias
  scopes must be idempotent; sibling scopes remain separately applicable rather than overriding one
  another. If any returned scope cannot be covered, the complete result/context transaction fails
  and the provider receives none of it.
- A provider call containing duplicate JSON object members is preserved raw through CAH-032/033/036
  but fails in CAH-034's duplicate-aware decoder as `invalid_read_tool_input`. The composed regression
  uses conflicting and escape-equivalent `path` names and proves zero key-gate, Pydantic, native read,
  instruction discovery, and context growth. When admission passes, it proves one charged observation
  and exact call/error replay in a follow-up against unchanged context.
- Structured retrieval and dispatch evidence is authoritative. Answer substrings are narrow outcome
  checks, not a claim of broad semantic quality. Mutations must prove each evaluator rule can fail.
- The default evaluator performs no network access, writes no target-repository or transcript content,
  prints no repository content/host path/opaque continuation, and exits nonzero on failure. Optional
  live evaluation reports separately and never gates Done.
- Existing transcript v3 records only its bounded aggregate session evidence. Tool arguments/results,
  intermediate provider content, opaque reasoning, and fixture content remain absent from transcript,
  protocol, visible TUI state, logs, and diagnostics.
- Completing CAH-037 establishes only bounded repository inspection, explanation, and planning.
  It does not claim editing, subprocess validation, MCP, content-level secret scanning, production
  retrieval quality, or general autonomous coding.

## Reviewability budget

- **Estimated production-code churn:** 250-400 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, evaluation fixtures and expected data, documentation, lockfiles,
  and generated artifacts.
- A missing domain abstraction or changed dependency contract becomes a focused prerequisite instead
  of an integration workaround. Keep the evaluator purpose-built; framework adoption is separate.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One composition path joins CAH-025 through CAH-036 through public boundaries without reverse
   imports or duplicated policy and supplies the exact four-field M2 loop-limit profile.
2. Ordinary runtime always uses exactly `scope="."`, empty focus paths, and empty search queries;
   no task/provider/environment inference changes initial context. A successful exact
   `read_file(path="pkg/file.py")` makes the `source="shared/rules.md"`, `applies_to="pkg"` binding
   appear in the next request, never the first.
3. Eval/test assembly alone can inject an explicit validated context request. The root-plus-nested-
   focus case proves every applicable instruction chain is unioned before focus content and that each
   query becomes exactly the supplied-scope-rooted `(depth=4, matches=100)` search request, with no
   focus/result fanout. Exact injection is observable without changing production defaults.
4. Mock/check remains credential-free and network-free; explicit OpenAI selection retains bounded
   egress behavior and the absent-secret-scan warning.
5. Exactly four native read operations remain contained in one workspace; no write, subprocess,
   network-tool, MCP, or hosted-tool path is reachable.
6. Fixture explain and plan cases complete through the bounded loop with exact root-to-enriched
   context/tool evidence, grounded relative citations/facts, one usage aggregate when present, and
   one existing terminal; broad result owners have complete scoped instructions before replay or the
   whole candidate transaction fails.
7. Distractor, forbidden source/claim, escape, limit, invalid response, late tool result,
   cancellation, tool failure, instruction discovery/merge failure, changed duplicate, hard-denied
   instruction target, and context budget cases fail reproducibly and safely. Allowed internal
   instruction links preserve resolved `source` separately from owner `applies_to`; repeated/alias
   and sibling-scope cases prove idempotence and non-overriding applicability. The before-dispatch
   cancellation gate proves zero native dispatch; gates after dispatch, every discovery/merge, and
   before provider start prove no candidate state is committed and no next provider begins. Duplicate
   argument members prove zero validation or dispatch stages after decoding.
8. The runner is deterministic, non-live by default, content-safe, and nonzero on failure; a live run
   is optional observational evidence only.
9. Protocol/TUI/transcript schemas remain unchanged, and documentation distinguishes proven M2
   behavior from deferred production capabilities.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 5 | Composition tests inject each boundary and assert one workspace, exact descriptors, and a fresh tracker configured with 4 turns, 120 seconds, 4,096 output bytes, and 3 observed calls for fake and OpenAI sessions. They also prove ownership/import rules, absence of side-effect transports, and that composition neither calls bare `LoopLimits()` nor inherits its one-turn/one-call defaults. |
| 2 | Runtime/launcher tests capture the exact root-only default `ContextBuildRequest` for varied task text, nested working paths, environment sentinels, mock/OpenAI selection, and repeated sessions. One strict fake then asserts request one has only root instructions, calls `read_file` with `path="pkg/file.py"`, and request two adds the exact `source="shared/rules.md"`, `applies_to="pkg"` binding while definitions stay unchanged. |
| 3 | Eval assembly injects exactly `ContextBuildRequest(scope=".", focus_paths=("pkg/file.py",), search_queries=("completion",))`. Spies prove root, every distinct focus path, and every first-occurrence search-match owner form the complete instruction union before their content; the only search call is exactly `SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`, with no focus/result search-root fanout. Invalid projection yields zero context I/O, and a later ordinary session proves defaults unchanged. |
| 4 | Provider-selection and socket-guard tests prove mock default, explicit OpenAI gating, bounded request fields, and warning behavior without live credentials. |
| 6 | Two fixture cases assert exact root-to-enriched fake requests, context items, call/result replay, dispatches, final citations/facts, aggregate evidence, ordered events, and one terminal. Broad list/search cases return paths under multiple sibling owners and prove all instruction bindings precede replay; removing one scope or binding fails the evaluator. |
| 7 | Mutations add duplicate JSON members, a distractor, forbidden path/claim, escape, exhausted limit, invalid grammar, late synchronous return, bounded tool error, discovery/merge failure on a later returned scope, changed duplicate, hard-denied instruction target, and context overflow. Duplicate-member cases include conflicting order, escape-equivalent names, and an unknown-tool precedence control with exact stage spies; the known duplicate case also proves one charged observation and exact unchanged-context call/error replay when admission passes. An allowed `pkg/AGENTS.md -> shared/rules.md` fixture proves `source="shared/rules.md"` with `applies_to="pkg"`; the denied target is never read and yields no partial package. Named `asyncio.Event` gates at `before_dispatch`, `after_dispatch`, each `after_discovery`, each `after_merge`, and `before_provider_start` prove zero dispatch at the first gate and use result/bundle/context/history/request sentinels to prove stage-local candidates are discarded and the next provider-start count remains zero. Repeat/canonical-alias scopes prove no growth; nested and sibling result owners prove root-to-nearest chain order and distinct sibling applicability. |
| 8 | Runner tests cover stable ordering/report bytes, zero/nonzero exits, repeated identical evidence, no content/path/opaque leaks, and explicit live-marker isolation. |
| 9 | Repository policy, documentation policy, transcript replay, protocol fixtures, reducer tests, and final diff review prove honest status and unchanged schemas. |

## Validation

- Run the fixture evaluator twice and compare its structured pass/fail evidence. Use no live provider
  for definition-of-done evidence.
- Run focused runtime/default-context/scoped-enrichment/eval-injection/composition tests, including
  exact search projection and result-owner instruction union, symlink source/owner, hard-denied
  target, duplicate argument decoding, and repeated named cooperative-gate cases; then run all M2
  native-tool suites, staged-turn/loop/adapter tests, transcript replay, protocol fixtures, and real
  process-boundary tests.
- Run `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` with provider credentials removed.
- If deliberately requested, run the separate live evaluation and report its bounded outcome without
  treating it as canonical evidence.

## Documentation impact

Update README, architecture, agent-loop, context, safety, evaluation, provider setup, protocol,
transcript/privacy, glossary, walking skeleton, backlog/timeline, story index, and the linked concise
lesson. Mark M2 complete only after deterministic cases and the canonical gate pass. Add or change no
presentation.

## Exclusions

- Writes, edits, diffs, subprocess checks, approvals, rollback, branches, commits, or PR automation.
- MCP client/server, remote/hosted tools, parallel calls, retries, subagents, framework-owned loops,
  adaptive/semantic retrieval, or task-derived context selection.
- New protocol/TUI displays, transcript tool content or reasoning, production telemetry, broad
  benchmark claims, content secret scanning, or live-provider CI requirements.

## Definition of done

- Explain/plan cases plus exact scope/focus/search projection, instruction symlink ownership,
  idempotence, sibling, hard-deny, cooperative-cancellation, safety, and failure mutations pass
  through composed runtime and existing process boundary twice with identical structured evidence.
- Exact ordinary default context and evaluation-only injection have direct tests, and all CAH-025
  through CAH-036 dependencies are Done without contract bypasses.
- **Delivered production-code churn** records the measured result and is no more than 600 lines;
  contract gaps become separate stories.
- Public composition APIs, cases, status documentation, and concise Markdown lesson are verified
  against implementation with a compact end-to-end diagram and no presentation changes.
- Focused validation, repeated evaluation, and `./scripts/check` pass before M2 and this story are
  Done and the review-ready PR is published.

## Planned evidence

- Composition tests proving exact root-only default/injected context requests, nested instruction
  enrichment after `read_file(path="pkg/file.py")`, complete direct/broad-result instruction unions,
  exact supplied-scope search projection, duplicate-argument zero-dispatch handling, internal-symlink
  `source`/`applies_to`, hard-denied target rejection, all five named cancellation checkpoint types
  including repeated per-scope gates and zero before-dispatch execution, idempotent repeat/alias scopes,
  non-overriding siblings, atomic failures, explicit M2
  `(4 turns, 120 seconds, 4096 output bytes, 3 observed calls)` limits, provider selection, and
  side-effect absence.
- Synthetic fixture, deterministic runner, explain/plan cases, and mutations with concise reports.
- Existing protocol/transcript evidence proving final text remains the only visible tool-assisted
  outcome.

## Deferred work

- M3 adds controlled edits, diff previews, approvals, subprocess validation, and write evidence.
- A future MCP unit requires remote trust, credentials, capability mapping, timeouts, cancellation,
  catalog change, and evidence decisions.
- Content secret scanning/redaction, production retrieval, larger evals, telemetry, parallel tools,
  retries, and reusable harness packaging remain later milestones.
