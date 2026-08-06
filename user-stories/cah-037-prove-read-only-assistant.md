# CAH-037 - Prove the read-only assistant

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E8 - Evaluation and observability
- **Dependencies:** CAH-024, CAH-026, CAH-025, CAH-027, CAH-028, CAH-029, CAH-030, CAH-031,
  CAH-038, CAH-032, CAH-033, CAH-039, CAH-034, CAH-035, CAH-036
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
- Evaluate the complete seven-name cooperative checkpoint union: `after_focus_read` and
  `after_search` during initial CAH-030 construction plus `before_dispatch`, `after_dispatch`, every
  `after_discovery`, every `after_merge`, and `before_provider_start` during the loop, with
  deterministic gates and distinctive local candidates.
- Introduce `evals/` with one synthetic workspace and strict-fake explain/plan cases only when the
  runnable runner, assertions, documentation, and tests arrive together.
- Preserve mock as the credential-free default and OpenAI as explicit bounded-egress opt-in.
- Document exactly what M2 proves and what MCP, editing, secret scanning, and production retrieval
  still require.

## Locked contract

- The runtime composition root is the only place that selects concrete workspace, context, registry,
  loop, transcript, and provider implementations. Domain modules neither import the runtime nor
  select a provider.
- The root constructs one `WorkspaceBoundary`, then calls only
  `build_read_only_agent_services(boundary)`. That factory creates the exact graph in this order:
  `RepositoryInstructionDiscovery(boundary)`; `RepositoryReadPolicy(boundary)`;
  `RepositoryMetadataReader(policy)`; `RepositoryTextReader(policy)`;
  `RepositoryTextSearcher(policy, metadata_reader, text_reader)`;
  `RepositoryContextBuilder(instructions, text_reader, searcher)`;
  `build_read_tool_registry(metadata_reader, text_reader, searcher)`;
  `build_read_tool_catalog(registry)`; then the frozen nine-identity `ReadOnlyAgentServices`. No other
  runtime path constructs, copies, or rejoins a policy, service, registry, definition, or catalog.
- Every ordinary interactive task constructs exactly
  `ContextBuildRequest(scope=".", focus_paths=(), search_queries=())`. The runtime does not derive a
  focus path, search query, scope, or hidden retrieval hint from task text, provider output, current
  directory below the workspace root, environment variables, or TUI state. Initial context therefore
  contains only root-applicable CAH-025 instructions; repository exploration and any narrower
  instruction discovery occur through admitted read tools.
- The deterministic evaluator may inject one explicit validated `ContextBuildRequest` for a named
  case through exact `ProviderSessionRunner(..., initial_context_request: ContextBuildRequest | None
  = None)`. `None` causes the session to construct the exact ordinary default; the evaluator passes
  one immutable value copied unchanged into each named case's fresh session and records it. The seam
  is called only by eval/test assembly, is not
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
- M2 retires `MockSessionRunner` from the launched runtime path while retaining that historical class
  and its focused tests. `provider=None` now composes a provider-backed
  `DeterministicMockProvider` through the same `ProviderSessionRunner`, services, initial context, and
  4/120/4096/3 tracker as OpenAI. This mock accepts any already-admitted request, emits the existing
  fixed `MOCK_RESPONSE_DELTAS` as one text-only first turn, requests no tool, reports no usage/opaque
  state, performs no network, and has an injectable observation gate for cancellation tests; it never
  contains a fixture-specific or task-derived script. Strict M2 evaluations inject exact fake scripts.
  OpenAI remains an explicit selection with CAH-036's bounded repository-content egress consent and
  no-content-secret-scanning warning.
- Launched default-mock sessions now use `ProviderSessionRunner`'s opaque `ses_provider_<n>` IDs and
  transcript-v3 records include the exact 4/120/4096/3 loop-limit aggregate. The old `ses_mock_<n>`
  prefix and omission of provider-loop evidence remain historical `MockSessionRunner` test behavior,
  not compatibility promises; README/walking-skeleton/current architecture are updated when this
  story ships. Protocol consumers continue treating both ID spellings as opaque validated strings.
- One ordinary accepted task creates one immutable workspace boundary, discovers root instructions,
  builds one initial context package, and allocates fresh loop accounting before provider work. The
  injected evaluator uses the same atomic builder with its explicit request. Before a successful
  admitted `read_file` with `path="pkg/file.py"`,
  the CAH-030 callback adapts every root/focus/search-owner discovery and merge plus each
  `after_focus_read` and `after_search` through CAH-034's same `cooperate_then_guard`; losing any gate
  returns no initial package and begins no later initial-context I/O. Before a successful admitted
  read, `cooperate_then_guard("before_dispatch")` can cancel with zero native dispatch. After dispatch,
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
  search projection, instruction-union-before-focus ordering, internal-symlink
  `source`/`applies_to`/depth precedence,
  the `read_file(path="pkg/file.py")` enrichment step, a broad search/list result whose returned
  owners add sibling instruction bindings before replay, the next request containing the binding
  `source="shared/rules.md"` with `applies_to="pkg"`, provider history, calls/results, accepted
  sources, final workspace-relative citations, and small required/forbidden answer facts.
- M2 enriches context from CAH-031's ordered `instruction_scopes` for every successful read. The
  native result's execution-time canonical request scope is first; local metadata then contains the
  exact-deduplicated owner of every model-visible result path. A broad `list_files` or `search_text`
  result is not replayed until every owner bundle is discovered, its `canonical_scope` exactly
  matches the captured scope, and it is folded, budgeted, and guarded. The original request alias
  and a retargeted canonical label are never post-dispatch authority. Repeated canonical scopes must be
  idempotent; sibling scopes remain separately applicable rather than overriding one another. If any
  returned scope cannot be covered, the complete result/context transaction fails and the provider
  receives none of it.
- CAH-032 construction and CAH-036 adapter mapping own the provider-call carrier bounds. A malformed
  tool-name carrier or argument string above 16 KiB fails there and never invokes CAH-033 or CAH-039.
  CAH-039 receives only a valid, bounded carrier; a valid-but-unknown name still wins at lookup before
  argument work. Structurally hostile or duplicate JSON remains raw through CAH-032/033/036 and fails
  in CAH-039 as `invalid_read_tool_input`. Composed CAH-039 regressions use reachable at-or-below-limit
  arguments and exercise object/array depth 63, 64, and 65 with root object depth 1; quoted and
  escaped delimiters; mismatched containers; `NaN`, `Infinity`, and `-Infinity`; a defensive decoder
  `RecursionError`; signed-64-bit endpoints/overflow, fractions/exponents, a 5,000-digit integer,
  numeric-looking strings, and defensive `ValueError`; and conflicting, escape-equivalent, nested,
  and array-contained duplicate names. They prove the quote-aware structural/numeric preflight and
  iterative every-depth duplicate walk run before
  dictionary construction/key-gate/Pydantic/native read/instruction discovery/context growth. When
  admission passes, one known-error case proves a charged observation and exact call/error replay in
  a follow-up against unchanged context. A separate native-maximum read proves wrapped overflow is
  the fixed `read_tool_output_too_large` known error with zero discovery/context growth rather than a
  session terminal; an unknown-tool control still wins before structural work. Result-projection
  regressions also cover 63/64/65-level complete envelopes with the outer `result` object at depth 1,
  one wide value exhausting the 65,536-unit pre-serialization work budget, and injected serializer
  `RecursionError`/`ValueError`. They preserve CAH-031's fixed oversize-versus-invalid-result mapping.
- Provider-text regressions use the real CAH-033 neutral constructors and CAH-036 SDK mapper at
  8,191/8,192/8,193 ASCII and multibyte bytes. They prove only exact bounded normal carriers or the
  content-free overflow marker reach admission, the tracker receives 8,193 once, and publication,
  usage persistence, and dispatch remain zero. A maximum-fragment function-call stream proves the SDK
  pump is iterative, while terminal-then-extra/exception cases prove raw EOF precedes neutral release.
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
- **Planning PR scope:** One contract neighborhood: existing TUI task carrier -> composed
  CAH-024-through-CAH-039 runtime -> validated protocol/transcript evidence -> deterministic evaluator.
- A missing domain abstraction or changed dependency contract becomes a focused prerequisite instead
  of an integration workaround. Keep the evaluator purpose-built; framework adoption is separate.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. The sole boundary-only services factory joins every CAH-024-through-CAH-039 M2 component in
   documented dependency order, exposes the exact nine-identity graph without reverse imports or
   duplicated policy, and supplies the exact four-field M2 loop-limit profile.
2. Ordinary runtime always uses exactly `scope="."`, empty focus paths, and empty search queries;
   no task/provider/environment inference changes initial context. A successful exact
   `read_file(path="pkg/file.py")` makes the `source="shared/rules.md"`, `applies_to="pkg"` binding
   appear in the next request, never the first.
3. Eval/test assembly alone can inject an explicit validated context request. The root-plus-nested-
   focus case proves every applicable instruction chain is unioned before focus content and that each
   query becomes exactly the supplied-scope-rooted `(depth=4, matches=100)` search request, with no
   focus/result fanout. Exact injection is observable without changing production defaults.
4. The launched mock path is provider-backed through the same runner/services/profile, remains
   credential-free and network-free, and preserves intentional visible lifecycle/cancellation
   semantics; explicit OpenAI selection retains bounded egress and the absent-secret-scan warning.
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
   cancellation gate proves zero native dispatch; initial `after_focus_read`/`after_search` plus every
   root/focus/search-owner discovery/merge gate prove no package and no later context I/O; gates after
   dispatch, every result-scope discovery/merge, and before provider start prove no candidate state is
   committed and no next provider begins. Duplicate
   structurally invalid, non-finite, recursive-failure, and duplicate argument cases prove zero key
   validation or dispatch stages after CAH-039 rejects them. Malformed tool-name and above-16-KiB
   carriers fail at CAH-032 construction or CAH-036 mapping and invoke neither CAH-033 nor CAH-039.
   Over-bound provider text becomes only the content-free overflow observation and exact assistant
   output limit with no publication, usage, or dispatch.
8. The runner is deterministic, non-live by default, content-safe, and nonzero on failure; a live run
   is optional observational evidence only.
9. Protocol/TUI/transcript schemas remain unchanged, and documentation distinguishes proven M2
   behavior from deferred production capabilities.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1, 5 | Composition tests call only `build_read_only_agent_services(boundary)` and assert all nine exact identities plus every edge: instruction/policy boundary, metadata/text policy, search policy/metadata/text, context instruction/text/search, registry-bound metadata/text/search, and catalog registry/entry/definition. Equal-but-distinct/cross-wired mutations fail before descriptor construction or I/O. Tests assert one catalog factory call, `catalog.definitions` in every request, that same catalog at every handoff, and a fresh 4/120/4096/3 tracker for deterministic mock, strict fake, and OpenAI sessions. They also prove ownership/import rules, absence of side-effect transports, and no bare `LoopLimits()` default. |
| 2 | Signature/static tests lock `initial_context_request: ContextBuildRequest | None = None`, production callers always pass/retain `None`, and eval assembly alone supplies an exact immutable request without task inspection. Runtime tests capture the exact root-only default for varied task text, nested working paths, environment sentinels, mock/OpenAI selection, and repeated sessions. One strict fake then asserts request one has only root instructions, calls `read_file` with `path="pkg/file.py"`, and request two adds the exact `source="shared/rules.md"`, `applies_to="pkg"`, canonical-depth `precedence` binding while definitions stay unchanged. |
| 3 | Eval assembly injects exactly `ContextBuildRequest(scope=".", focus_paths=("pkg/file.py",), search_queries=("completion",))`. Spies prove all projections validate before I/O, root discovery/fold/budget is first, every focus read/discovery/fold finishes before search, and every first-occurrence search-match owner joins the complete instruction union before content. Invalid projection yields zero context I/O, root failure yields zero focus/search calls, and focus failure yields zero search calls. Two queries prove first-result scope mismatch causes zero second-search calls. The only stable search projection is exactly `SearchTextRequest(query="completion", path=".", max_depth=4, max_matches=100)`, with no focus/result search-root fanout. Separate request-alias and captured-focus/owner-label retargets prove result/bundle scope mismatch returns no package; stable controls prove success. |
| 4 | Provider-selection and socket-guard tests prove `provider=None` no longer constructs `MockSessionRunner`, but instead injects one task-independent `DeterministicMockProvider` into `ProviderSessionRunner` with the exact services/profile. Successful migration tests preserve the existing fixed final text and ordered start/delta/completion lifecycle. Cancellation before or among provider observations now follows CAH-033 atomic staging and emits `session.started -> session.cancelled` with zero assistant deltas; the legacy partial-delta cancellation behavior remains only in focused historical `MockSession` tests and is explicitly not a launched-runtime invariant. Tests lock the deliberate opaque ID migration from launched `ses_mock_*` to `ses_provider_*`, add exact loop-limit aggregate evidence, retain absent model usage, and preserve teardown, repeated-session isolation, and zero network. Protocol consumers accept both opaque spellings. Explicit OpenAI gating, bounded request fields, and warning behavior remain covered without live credentials. |
| 6 | Two fixture cases assert exact root-to-enriched fake requests, context items, call/result replay, dispatches, final citations/facts, aggregate evidence, ordered events, and one terminal. Broad list/search cases return paths under multiple sibling owners and prove all instruction bindings precede replay. Native-producer seams retarget allowed request `alias -> A` to `B` immediately before list/stat/read/search access and prove each validated result reports the target actually inspected, including empty/no-match outcomes. Separate `after_dispatch` retargets prove only captured `A` drives discovery. Replacing captured canonical `A` itself with an allowed symlink to `B` makes CAH-025 report `B` and fails before merge/replay/fallback; removal and stable controls cover the other outcomes. |
| 7 | Mutations add structurally hostile and duplicate JSON, a distractor, forbidden path/claim, escape, exhausted limit, invalid grammar, late synchronous return, bounded tool error, discovery/merge failure on a later returned scope, changed instruction duplicate, hard-denied instruction target, context overflow, initial/post-dispatch alias retargets, and captured instruction-owner `A -> B` retargets immediately before probe/read. Initial-context gate tables cancel after each root/focus/search-owner discovery and merge plus `after_focus_read` and `after_search`; each asserts no returned package and zero later I/O. Carrier cases cover 16,383/16,384/16,385 argument bytes and malformed names, proving only producer-admitted carriers reach CAH-033/039. Provider-text cases use real neutral/SDK producers at 8,191/8,192/8,193 ASCII/multibyte bytes, maximum mapped-empty fragments, and raw terminal-then-extra/exception; they prove bounded normal carriers or one content-free marker, constant stack depth, raw EOF authorization, one 8,193 tracker reservation, and zero publication/usage/dispatch. Reachable CAH-039 cases use at-or-below-limit arguments and cover 63/64/65 object-array levels, quoted/escaped delimiters, mismatched containers, signed-64-bit endpoints/overflow, fractions/exponents, a 5,000-digit integer, numeric-looking strings, all non-finite constants, forced decoder `RecursionError`/`ValueError`, conflicting/reversed/escape-equivalent duplicates, nested/array duplicates at the deepest admitted level, and a valid unknown-tool precedence control. Exact spies prove no later stage. A known rejected-input case proves one charged observation and exact unchanged-context replay. Result cases cover complete-envelope depths 63/64/65, a wide 65,536-unit-work-budget exhaustion, injected serializer `RecursionError`/`ValueError`, exact envelope bytes 65,536/65,537, and a native 65,536-byte file; they preserve fixed invalid-result versus `read_tool_output_too_large` mapping, cross `after_dispatch` only for a known error, carry no scopes/content, and replay known errors against unchanged context. Instruction-link and owner-retarget mutations prove no replacement instruction read; loop checkpoint mutations prove no partial context or next provider start; repeated/nested/sibling scopes prove stable applicability. |
| 8 | Runner tests cover stable ordering/report bytes, zero/nonzero exits, repeated identical evidence, no content/path/opaque leaks, and explicit live-marker isolation. |
| 9 | Repository policy, documentation policy, transcript replay, protocol fixtures, reducer tests, and final diff review prove honest status and unchanged schemas. OpenAI mapping snapshots preserve a missing-ancestor precedence gap and reject index-based renumbering. |

## Validation

- Run the fixture evaluator twice and compare its structured pass/fail evidence. Use no live provider
  for definition-of-done evidence.
- Run focused runtime/default-context/scoped-enrichment/eval-injection/composition tests, including
  exact initial I/O order, search projection and canonical-scope consistency, execution-time
  request/result-owner instruction union, symlink source/owner, hard-denied
  target, producer-side name/argument carrier bounds, reachable at-limit CAH-039 structural/numeric
  preflight, non-finite/recursion rejection, every-depth duplicate decoding, result-envelope
  depth/width/work and serializer-failure cases, and repeated named cooperative-gate cases; then run all M2
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

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Evidence distinguishes task/session/call IDs, lexical request scope, access-time canonical target, instruction owner/source, context provenance/precedence, provider-visible relative label, and evaluator citation target. |
| End-to-end contract | Trace existing TUI command -> Python composition -> CAH-024-through-CAH-039 read-only loop -> fake or explicit OpenAI provider -> validated final protocol events/transcript evidence -> evaluator assertions. |
| Failure and atomicity | Every invalid carrier/grammar, hard deny, retarget, tool error, discovery/merge failure, limit, cancellation, and deadline case proves zero forbidden effect, no partial context/replay, and one bounded terminal outcome. |
| Reachable boundaries | Run below/at/above limits through the composed runtime with real fixture producers, same-loop cancellation, access-time mutations, huge-string/shape cases, and repeated deterministic evaluation rather than relying only on isolated helper states. |
| Closed grammar and cardinality | Fix the evaluation case schema, ordinary context defaults, evaluation-only injection seam, exact expected facts/citations/tool traces, allowed failures, four-turn/three-call ceilings, and deterministic evidence projection. |
| Artifact parity | Story, lesson, end-to-end diagram, README/roadmap, conceptual docs, fixture cases, and policy tests agree on dependency order, ownership, status, checkpoints, and M2 exit evidence. |
| Independent lenses | Filesystem security/identity review fixed one factory-built service graph and retarget/hard-deny evidence; composition/learning review added the exact eval injection API and provider-backed default-mock migration; provider/scheduler/evaluation review added fresh 4/120/4096/3 trackers, operation generations, all seven checkpoint names including initial focus/search stages, and deterministic mutation-validity evidence. |

## Definition of done

- Explain/plan cases plus exact scope/focus/search projection, instruction symlink ownership,
  idempotence, sibling, hard-deny, cooperative-cancellation, safety, and failure mutations pass
  through composed runtime and existing process boundary twice with identical structured evidence.
- Exact ordinary default context and evaluation-only injection have direct tests, and every
  CAH-024-through-CAH-039 M2 dependency is Done in documented dependency order without contract
  bypasses.
- **Delivered production-code churn** records the measured result and is no more than 600 lines;
  contract gaps become separate stories.
- Public composition APIs, cases, status documentation, and concise Markdown lesson are verified
  against implementation with a compact end-to-end diagram and no presentation changes.
- Focused validation, repeated evaluation, and `./scripts/check` pass before M2 and this story are
  Done and the review-ready PR is published.

## Planned evidence

- Composition tests proving exact root-only default/injected context requests, nested instruction
  enrichment after `read_file(path="pkg/file.py")`, complete direct/broad-result instruction unions,
  exact supplied-scope search projection and canonical-result comparison, projection/root/focus
  failure precedence, post-dispatch canonical-scope preservation, structural/non-finite/recursive/
  duplicate-argument zero-dispatch handling, internal-symlink
  `source`/`applies_to`/depth precedence, hard-denied target rejection, all seven named cancellation checkpoint types
  including initial focus/search and repeated per-scope gates plus zero before-dispatch execution, idempotent repeat/alias scopes,
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
