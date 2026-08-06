# CAH-030 - Build budgeted repository context

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-025, CAH-027, CAH-028, and CAH-029
- **Lesson:** [Budgeted repository context](../docs/lessons/cah-030-budgeted-context.md)
- **Learning emphasis:** Core learning unit - deterministic context engineering and evidence
  provenance
- **Review focus:** Why the harness, rather than the provider, owns source priority, scoped
  instruction enrichment, inclusion reasons, deduplication, and content budgets

## User story

> As a user, I want the harness to assemble a bounded, provenance-rich repository context package so
> that model reasoning is grounded in selected evidence and omissions are visible rather than
> silently hidden.

## Single responsibility

CAH-030 owns deterministic selection and reporting for one provider-neutral repository context
package plus the pure, atomic merge of one newly discovered instruction bundle into that package. It
owns instruction discovery for evidence selected by that initial build, but does not decide when a
later tool result requires another scope, construct a provider request, count provider tokens,
register tools, handle LLM responses, dispatch tool calls, run multiple agent steps, or persist raw
repository content.

## Scope

- Add immutable Python context request, item, inclusion-report, and package contracts over CAH-025
  and CAH-027 through CAH-029.
- Accept one instruction scope, up to eight explicit focus files, and up to four optional literal
  search queries.
- Build the required instruction union for the request scope, every distinct explicit focus path, and
  every first-occurrence canonical owner directory of a search match. Then include bounded focus-file
  slices and bounded search excerpts in one exact priority order under reviewed binding, item, and
  UTF-8 content-byte budgets.
- Add one pure operation that atomically enriches an existing package from one expected canonical
  scope and one already-discovered CAH-025 instruction bundle without evicting or rewriting prior
  context.
- Record canonical provenance, inclusion reason, included bytes, source truncation, and aggregate
  omission reasons without storing denied labels or excluded content.
- Keep the package provider-neutral and local. Make no provider SDK, protocol, transcript, TUI,
  tool-registry, MCP, subprocess, network, or agent-loop change.

## Locked contract

### Exact service and cooperative API

- `RepositoryContextBuilder(instructions: RepositoryInstructionDiscovery, text_reader:
  RepositoryTextReader, searcher: RepositoryTextSearcher)` is the exact service. Construction
  requires `searcher.text_reader is text_reader`, `text_reader.policy is searcher.policy`, and
  `instructions.boundary is text_reader.policy.boundary`; it retains those exact read-only
  dependencies and rejects equal-but-distinct workspace/policy graphs before candidate I/O.
- Initial construction is exactly
  `async def build(request: ContextBuildRequest, checkpoint: ContextCheckpoint) -> ContextPackage`.
  `ContextCheckpoint` is a required injected async callable
  `Callable[[ContextBuildStage], Awaitable[None]]`; it has no no-op default. `ContextBuildStage` is the
  closed literal union `after_discovery | after_merge | after_focus_read | after_search`. CAH-030
  imports no CAH-034/session type. Final composition supplies a small adapter that forwards each stage
  to CAH-034's `cooperate_then_guard`; focused unit tests inject a recorder or a deterministic
  rejecting callback. The adapter lets CAH-034's private `_SessionLifecycleStop` propagate unchanged;
  the builder neither catches nor maps it.
- The builder captures either one value or one exception from every discovery, merge/budget check,
  focus read, and search attempt. It then awaits the callback outside locks, before inspecting or
  unwrapping that candidate and before beginning later I/O. Thus the callback runs after failed as
  well as successful synchronous stages. All candidates remain local until the complete build
  succeeds. A callback rejection propagates to the orchestration owner, returns no package, and starts
  no later discovery/read/search. A genuinely cancelled task propagates `CancelledError` only when
  `asyncio.current_task().cancelling() > 0`; an independently raised `CancelledError` is an unexpected
  stage exception, crosses the same callback, and becomes the fixed content-suppressed context failure
  if lifecycle does not win. Known repository/instruction failures retain their established mapping
  only after the callback. The exact repeated stage order is root
  `after_discovery -> after_merge`; for each focus `after_focus_read -> after_discovery ->
  after_merge`; for each search `after_search`; then for each first-occurrence match owner
  `after_discovery -> after_merge`.
- Pure enrichment remains synchronous and performs no scheduling:
  `merge_atomically(package: ContextPackage, expected_canonical_scope: str,
  discovered_instructions: RepositoryInstructions) -> ContextPackage`. It is the builder's exact
  public method. CAH-034/035 call it between their own `after_discovery` and `after_merge` cooperative
  seams; the method does not import, invoke, or fake those guards.

### Request and candidate construction

- `ContextBuildRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It
  contains `scope` (default `.`), `focus_paths` (ordered tuple, at most 8), and `search_queries`
  (ordered tuple, at most 4). Duplicate input paths and queries remain present until every derived
  request has passed its owning schema; focus paths are canonical-deduplicated after CAH-028
  admission and queries are exact-deduplicated after CAH-029 request validation. The first occurrence
  retains priority and each later duplicate increments the report's aggregate duplicate count. The
  builder materializes and schema-validates every user-derived focus and provisional search request
  before invoking any CAH-025/028/029 filesystem operation, so one invalid projection produces no
  candidate I/O.
- `scope` and every `focus_paths` member use CAH-024/026's inclusive 4,095-byte,
  256-normalized-component, and 255-byte-name path budget at `ContextBuildRequest` admission. Any
  invalid member produces `invalid_context_request` before projection construction, deduplication,
  instruction discovery, or filesystem work. Derived `ReadFileRequest` and `SearchTextRequest`
  validation repeats the same native invariant as defense in depth; it does not redefine the limit.
- `request.scope` is passed unchanged to the first CAH-025 `discover_for_path` call, which is the
  first filesystem operation. Fold that bundle and check required budgets before any focus read or
  search. Its immutable `canonical_scope` becomes the consistency snapshot for later search
  results. For each supplied focus path, first construct and validate exactly
  `ReadFileRequest(path=focus_path, start_line=1, max_lines=400, max_bytes=32768)` before any focus
  filesystem I/O. Every focus path is required and must then satisfy CAH-028 as an admitted regular
  text file; a failed source fails the whole build rather than quietly omitting an explicit focus.
- Canonical-deduplicate admitted focus results by their CAH-028 `path`, preserving input order. Build
  the initial instruction union by folding the already-admitted scope bundle first and then one
  CAH-025 bundle for every distinct canonical focus path in that order. Before each focus bundle is
  folded, require its `canonical_scope` to equal that focus result's captured `path`; replacing the
  canonical label with an internal alias to another allowed target fails atomically rather than
  changing instruction authority. Each fold uses the same topology-correct, no-eviction merge core
  defined below. Complete every required focus read, discovery, fold, and budget check before the
  first search executes.
- For each supplied query, construct and validate exactly
  `SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)` before any search
  filesystem I/O. Only after every projection validates, exact-deduplicate queries in input order.
  Run only those already-validated searches, with the supplied `request.scope` unchanged, in order
  after all focus work. Focus paths, admitted focus results, and search-result paths never become
  search roots. Immediately after each search returns and before inspecting its matches or starting
  the next search, require its `SearchTextResult.canonical_request_scope` to equal the root bundle's
  captured canonical scope exactly. A retargeted alias, stale scope, disappearance, or mismatch
  fails the build as `context_build_failed` without admitting match content, running a later search,
  returning a package, or falling back to or rediscovering through the alias.
- CAH-029 supplies each query's matches in canonical path/line/column order. Traverse matches in
  exact-deduplicated query order and that returned order, derive each canonical match file's canonical
  parent directory, and retain the first occurrence of each exact owner label. In that deterministic
  owner order, call CAH-025 `discover_for_path(owner)` once. Require the returned bundle's
  `canonical_scope` to equal the captured owner before folding it through the same idempotent topology
  merge. A changed canonical label cannot redirect discovery to another allowed subtree. The
  complete scope-plus-focus-plus-search-owner instruction union is committed before any focus item
  or search excerpt is appended.
- Every discovered search-owner bundle is required even if budget selection later omits all excerpts
  from that owner. Discovery failure, a conflicting owner snapshot, or overflow of the existing
  required-context budgets fails the whole build with no package; no search excerpt becomes visible
  before its owner's applicable instruction chain is present.
- Each validated query satisfies CAH-029's one-line, 256-byte contract. Search candidates are
  optional: normal no-match, skipped-file, and truncation outcomes are represented in report
  aggregates and do not fail otherwise valid required context.
- Candidate construction performs no unrequested content scan. It discovers instructions only for
  the supplied scope, distinct explicit focus paths, and canonical owner directories actually
  returned by a requested search; reads only explicit focus files; and runs only requested literal
  searches from the supplied scope. Search-owner discovery never launches another search.

### Selection order and immutable output

- Required instruction bindings from the complete scope-plus-focus-plus-search-owner union are
  ordered by the topology-correct merge core: an ancestor precedes a strict descendant while
  unrelated siblings retain first-admission order. Scope is admitted first, canonical-distinct focus
  paths follow in request order, and exact-deduplicated search owners follow in query/match order.
  Required focus-file items then follow in input order after canonical deduplication. Optional search
  excerpts follow in exact-deduplicated query order and then each search result's canonical
  path/line/column order.
- A context item has `kind` (`instruction`, `focus_file`, or `search_excerpt`), canonical `path`,
  content, `content_bytes`, `truncated`, and kind-specific provenance: instruction precedence and
  canonical `applies_to` directory, focus line range, or search query rank plus line/column. Search
  `query_rank` is the strict non-Boolean integer 1 through 4 equal to the query's one-based position
  in the exact-deduplicated query tuple, not its original request index and not an array position in a
  provider projection. For input `("todo", "todo", "fix")`, the retained queries have ranks 1 and 2
  and the aggregate duplicate count is 1; no rank gap is introduced. An
  instruction copies CAH-025's canonical target `source` into `path` and copies candidate-owner
  `applies_to` directly. It never derives applicability from the source path: for example,
  `pkg/AGENTS.md -> shared/rules.md` remains `source="shared/rules.md"` and `applies_to="pkg"`.
- Instruction identity is the candidate-owner `applies_to`. Two bindings with one canonical source
  and different owners are valid, remain distinct items, and each consumes instruction/item/content
  budget. Repeating one owner is idempotent only when its source, content, and original byte count
  match exactly; a changed target or snapshot is a conflict. For other canonical duplicates, the
  highest-priority occurrence wins. Instruction content outranks the same source as a focus file.
  Search excerpts are deduplicated by canonical path, line, column, and exact excerpt; multiple
  distinct excerpts from one file may remain.
- `ContextPackage` contains an immutable ordered item tuple, `content_bytes`, and one immutable
  `InclusionReport`. Default representations suppress all content and search query text.
- The report has one record for each included item with canonical path, reason, included bytes, and
  truncation; every instruction record also carries its copied `applies_to` so two bindings to one
  source remain distinguishable. Exclusions are aggregate counts by `duplicate`, `item_budget`,
  `byte_budget`, `search_limit`, `ignored_or_unavailable`, `non_text`, and `source_too_large`; it
  never reports an excluded/denied label, ignore rule, raw error, query text, or excluded content.

### Monotonic scoped-instruction enrichment

- `merge_atomically` accepts exactly one existing `ContextPackage`, one
  `expected_canonical_scope` captured by the successful native operation, and one validated,
  immutable CAH-025 bundle created by CAH-025's sole topology-validating result factory for that
  scope. Before inspecting or merging bindings, it requires exact
  equality with `bundle.canonical_scope`; mismatch is `context_build_failed` with no partial result
  and no alias fallback. It performs no discovery, filesystem access, policy decision, tool
  dispatch, provider work, or mutation of any input.
- For each CAH-025 binding in root-to-nearest owner order, copy `source` and `applies_to`; never derive
  the owner from the target. An `applies_to` already present is idempotent only when its source,
  content, and original byte count match exactly. Any mismatch fails the whole merge with
  `context_build_failed`; the existing or candidate snapshot is never exposed in the failure. The
  same source under a different `applies_to` is an unseen valid binding, not a duplicate.
- Unseen instruction items are inserted in bundle order at topology-correct positions inside the
  instruction block. For each unseen binding, insert immediately before the first instruction whose
  canonical `applies_to` is a strict path-segment descendant; if none exists, insert at the end of
  the instruction block. This handles an ancestor that appears after a descendant was admitted. All
  prior items and inclusion records retain their relative order, corresponding new records follow
  the new item positions, and no item is evicted, truncated, replaced, or reprioritized. Copy each
  CAH-025 canonical-owner-depth precedence rank unchanged: a late ancestor's smaller rank does not
  renumber a previously admitted descendant, legal gaps remain gaps, and equal sibling ranks do not
  imply cross-sibling precedence. The returned package and report are newly constructed immutable
  values.
- Precedence is path-local. Ancestor instructions precede narrower descendants on the same applicable
  path. Instructions for sibling `applies_to` scopes have no precedence over one another; their
  deterministic first-admission order is only serialization order and grants neither sibling wider
  authority.
- The resulting package may contain at most 16 distinct instruction bindings, 24 total items, and
  96 KiB of content. These are combined limits across the initial
  scope-plus-focus-plus-search-owner instruction union, required focus items, and optional search
  items, and the same limits govern later enrichment. Newly discovered instructions are required
  context: if the complete merged value crosses any bound, enrichment fails atomically with
  `required_context_exceeds_budget`. It never drops an old or new instruction to make room.

### Initial reviewed budgets

| Limit | Initial value | Boundary behavior |
| --- | ---: | --- |
| Distinct instruction bindings | 16 | Initial scope/focus/search-owner union or enrichment with a seventeenth owner binding fails atomically, even when two owners share one source. |
| Explicit focus files | 8 | A ninth fails request validation. |
| Literal search queries | 4 | A fifth fails request validation. |
| Context items | 24 | Required items must all fit; optional items beyond the limit are counted and omitted. |
| Aggregate item content | 96 KiB (98,304 UTF-8 bytes) | Required items must all fit; optional items use deterministic first-fit inclusion. |
| One instruction item | 32 KiB | Inherited from CAH-025; never truncated here. |
| One focus item | 32 KiB and 400 whole lines | Read from line 1 with CAH-028 and report source truncation. |
| One search item | 512 bytes | Exact CAH-029 excerpt; never expanded here. |

- Required instructions are all-or-nothing because silently dropping a narrower instruction can
  change meaning. If the initial or enriched instruction set exceeds 16 bindings, or the complete
  instruction union, including bundles derived from optional search candidates, and all required
  focus items cannot fit the combined 24-item and 96-KiB package, the operation fails with
  `required_context_exceeds_budget`; it does not partially include required content.
- Optional search items use deterministic first-fit selection: consider them in defined order,
  include an item when both budgets permit it, otherwise increment the relevant aggregate and
  continue so a later smaller item may fit.
- `content_bytes` is the sum of `len(item.content.encode("utf-8"))`. Labels, report metadata, and
  future provider framing are outside this content budget but remain item-bounded. Bytes and items
  are deliberately reproducible proxies, not token counts or a claim that a provider request fits a
  particular model window.
- Each dependency operation and pure merge is synchronous and bounded, while initial `build` is an
  async coordinator solely so its required callback can yield/guard between those stages. CAH-030
  creates no task, lock, cancellation state, clock, or provider work; pure enrichment remains
  synchronous.

### Fixed, non-leaking failures

CAH-025 and CAH-026 fixed safe errors remain authoritative for source failures.
`ContextBuildError` adds only these package-level failures:

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_context_request` | `Repository context request exceeds the input limit.` | focus/query count, an over-bound or invalid scope/focus path, or another package-level request shape is invalid |
| `required_context_exceeds_budget` | `Required repository context exceeds the item or byte budget.` | the 16-binding limit or complete required instruction/focus set cannot fit |
| `context_build_failed` | `Repository context could not be built safely.` | a duplicate instruction conflicts or another bounded internal composition failure occurs |

- No partial package is returned with a failure. Exceptions, reports, values, and their default
  representations contain no absolute paths, denied labels, raw OS/decoder text, or content outside
  admitted included items.
- Every filesystem source in an initial build is re-admitted through its owning CAH-025/028/029
  operation. Enrichment consumes one already-validated CAH-025 value and performs no access; later
  orchestration remains responsible for discovering that bundle for the newly admitted scope.

## Reviewability budget

- **Estimated production-code churn:** 475-600 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-025/027-029 admitted evidence -> immutable
  budgeted `ContextPackage`/`InclusionReport` plus pure scoped enrichment -> CAH-032 provider request
  and CAH-034/035 loop-enrichment consumers.
- **Split rule:** stop and refine another story before review if provider-message construction, token
  counting, adaptive ranking, post-build instruction-discovery triggering, tool dispatch, transcript
  persistence, or loop control enters this unit, or if production churn is likely to exceed roughly
  600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One request validates the exact CAH-028 focus and CAH-029 search projections before I/O, admits and
   folds root scope first, completes focus reads/discovery before search, builds the required
   instruction union for `request.scope`, every distinct focus path, and every first-occurrence
   canonical search-match owner, and produces immutable items in the exact reviewed priority order.
2. Required instructions and focus files are all-or-nothing; optional search excerpts use
   deterministic first-fit selection under combined 16-instruction-binding, 24-item, and 96-KiB
   limits.
3. Focus paths are canonical-deduplicated only after every exact read projection validates; search
   queries are exact-deduplicated only after every exact search projection validates, always search
   from the unchanged supplied scope, require each result's execution-time canonical scope to equal
   the root discovery snapshot before the next search starts, and never cause per-focus or per-match
   search-root fanout.
4. Canonical search-match owners are exact-deduplicated on first occurrence in query/match order and
   each triggers one CAH-025 discovery. Every focus/owner bundle must report the exact captured
   canonical scope before its required bindings join the instruction union. Any scope drift,
   discovery, conflict, or required-budget failure returns no package before focus content or an
   optional excerpt is visible.
5. Instruction items and report records copy CAH-025 target `source` into `path` and copy
   candidate-owner `applies_to`. The same source under different owners remains distinct and charged;
   one owner is idempotent only for an exact source/content/original-byte snapshot.
6. Other canonical duplicate sources are included once at their highest-priority reason, and every
   included item records exact UTF-8 content bytes and source truncation.
7. The inclusion report identifies included bindings/sources and aggregate omission reasons without
   exposing denied labels, excluded content, raw errors, or search query text.
8. Input counts, per-kind limits, aggregate binding/item/content budgets, and inherited strict text
   policy are tested exactly and do not use provider token estimates.
9. One expected canonical scope and validated CAH-025 bundle enrich an existing package atomically:
   scope mismatch and conflicting duplicates fail, exact owner snapshots are idempotent, and unseen
   instructions enter topology-correct positions without evicting or reordering prior items.
10. Initial union and enrichment preserve path-local ancestor precedence, assign no precedence between
   sibling scopes, preserve CAH-025 canonical-depth ranks without renumbering, and enforce 16
   instruction bindings plus 24-item/96-KiB bounds all-or-nothing.
11. One exact service graph shares boundary/policy identity; every successful or failed initial stage
    crosses the required checkpoint in the closed repeated order before its value/error is unwrapped,
    and a rejecting callback stops all later work with no package, while pure `merge_atomically`
    performs no scheduling.
12. Public contracts are typed, documented, provider-neutral, and tested locally with no provider,
   subprocess, network, protocol, transcript, TUI, or agent-loop behavior.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Initial pipeline and instruction union | Use `scope="."` with ordered focus paths `pkg/a.py`, `other/b.py`, and an alias of `pkg/a.py`; return matches under nested sibling owners and inject projection/root/focus failures | Unit integration | All projections validate with zero I/O; scope discovery/fold/budget is the first I/O; every focus read/discovery/fold completes before search; root failure causes zero CAH-028/029 calls and focus failure causes zero CAH-029 calls; match owners follow in query/match order before every visible item |
| Exact focus projection | Spy on request construction for a regular focus, a symlink alias of it, an absolute path, and an empty path | Schema/boundary integration | Every `ReadFileRequest(path=focus_path, start_line=1, max_lines=400, max_bytes=32768)` validates before any CAH-025/028/029 I/O; no pre-validation dedup hides an error |
| Exact search projection | Use two equal valid queries and one query containing LF with non-default focus results present | Schema/boundary integration | Every `SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)` validates before any CAH-025/028/029 I/O; exact dedup follows validation and every admitted call retains the unchanged supplied scope |
| Fixed supplied search root and scope consistency | With two queries, discover through `scope_alias -> A`, retarget it to `B` before the first no-match result, and include a stable-alias control while spying on CAH-025/029 calls | Boundary integration | Search receives only `request.scope`; the stable result reports `A`, while `B` fails atomically before match inspection, a second search, or package return; focus and result paths never become search roots |
| Captured focus/owner consistency | Replace a captured canonical focus or match-owner label with an internal symlink to another allowed target between native admission and instruction discovery | Boundary integration | `bundle.canonical_scope` mismatch fails before merge/content; no replacement instructions, package, later search, or alias fallback |
| Search-owner order and aliases | Return repeated matches, distinct files with one parent, sibling parents, and stable symlink aliases across two queries | Boundary integration | Exact owner labels deduplicate at first occurrence in query then canonical match order; every discovered bundle exactly matches its captured owner before idempotent merge |
| Service identity and cooperative stages | Compose one real boundary/policy service graph, then try equal-but-distinct dependencies; record all stages and reject at each root/focus/search/owner occurrence; inject a distinctive value, each known error, an unexpected error, and independently raised `CancelledError` at discovery/merge/focus/search | Unit integration | Exact constructor/build/merge signatures; mismatched graph fails before I/O; each value/error crosses its named stage before inspection or mapping; callback rejection and lifecycle loss perform zero later calls and return no package; real task cancellation propagates, while independent `CancelledError` becomes the fixed context failure only after the callback |
| Priority and provenance | Combine scope/focus instruction bindings, ordered focus files, and two searches | Unit integration | Exact item kinds, canonical labels, copied `source`/`applies_to`/depth precedence, and order |
| Canonical deduplication | Reach one non-instruction file through aliases and multiple reasons | Boundary integration | One highest-priority item and exact duplicate aggregate |
| Binding identity and ownership | Point `pkg/AGENTS.md` and `other/AGENTS.md` at `shared/rules.md`, then repeat and retarget only `pkg` | Unit/boundary integration | Two distinct charged bindings report `source="shared/rules.md"` with owner-specific `applies_to`; exact owner replay is idempotent and owner snapshot mismatch fails atomically |
| Search-owner coverage is required | Make an optional match's owner discovery fail, conflict, or introduce the 17th binding, then repeat at all limits | Unit/boundary integration | No focus or excerpt is visible on failure; exact-limit union succeeds and every included excerpt follows its applicable instruction chain |
| Required all-or-nothing | Build required sources immediately below, at, and above 24 items/96 KiB | Unit | Full package at limits; fixed failure and no partial value above, including when optional excerpts would otherwise be omitted |
| Monotonic enrichment | Merge nested and sibling bundles into a package containing focus/search items | Unit | Unseen instructions enter topology-correct instruction-block positions; every prior item retains relative order and none is evicted |
| Duplicate instruction identity | Re-merge one exact owner, then change only its source, content, or original byte count | Unit | Exact owner snapshot is byte-for-byte idempotent; each mismatch fails `context_build_failed` with no partial package |
| Combined bounds | Build/merge the 16th/17th binding, including two owners of one source, and values at 24 items and 98,304/98,305 bytes | Unit | Success exactly at every combined bound; `required_context_exceeds_budget` above, with no eviction |
| Scoped precedence | Merge ancestor, descendant, and sibling bundles, including an ancestor created after its descendant was admitted and missing intermediate candidates | Unit | Late ancestors insert before descendants; copied depth ranks remain stable with legal gaps, and equal-ranked siblings retain order without a precedence claim |
| Optional first-fit | Place differently sized search excerpts around remaining capacity | Unit | Exact included items and item/byte omission aggregates |
| Input bounds | Exercise 8/9 focus paths, 4/5 queries, the inherited query limit, and each scope/focus path at 4,094/4,095/4,096 bytes, 254/255/256 name bytes, and 255/256/257 components; include an invalid duplicate before dedup | Schema/unit | Exact admission at endpoints; any above-bound member returns `invalid_context_request` with zero projections or I/O, and dedup never hides it |
| Inclusion hygiene | Use ignored, denied, invalid-text, oversized, no-match, and truncated search candidates | Policy integration | Safe aggregates, no excluded label/content/query leak |
| Determinism | Build the same fixture repeatedly with reversed filesystem creation order | Integration | Byte-for-byte equal provider-neutral packages and reports |

## Validation

- Add focused context-builder tests using real CAH-024 through CAH-029 services over deterministic
  fixture workspaces; fake only a narrow race seam when needed.
- Record the exact checkpoint stage list, reject after every occurrence, and separately prove the pure
  `merge_atomically` method never invokes a callback or scheduling primitive.
- Assert the exact focus/search request snapshots and call order:
  validate all projections, discover/fold/check root, complete each focus read/discovery/fold, then
  run searches and discover match owners. Prove invalid projection means zero I/O, root failure means
  zero focus/search calls, focus failure means zero search calls, and a retargeted supplied scope
  yields a canonical-result mismatch before the next search and no package while a stable alias
  succeeds. Replace captured canonical focus and match-owner labels before discovery; require exact
  returned-bundle scope equality and no merge, replacement instruction, later work, or fallback.
  Assert the
  scope-plus-focus-plus-search-owner
  instruction union, absence of search-root fanout, deterministic
  first-occurrence owner discovery, alias idempotence, copied `source`/`applies_to`/depth precedence, deduplication,
  exact byte arithmetic, first-fit behavior, topology-correct atomic enrichment including a late
  ancestor, all-or-nothing required sources, safe representations, and full failure strings.
- Test instruction-binding/focus/query/item/content boundaries below, at, and above without a
  tokenizer, model, network, subprocess, or timing assertion.
- Keep provider requests, protocol, transcript, tool registry, agent loop, and TUI unchanged; use the
  existing repository gate as nearest parity evidence.
- Run focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update context-engineering, architecture, safety model, tool-system, glossary, story and lesson
indexes, E3 backlog sequence, and the Markdown lesson's compact architecture diagram. Document the
exact priority algorithm, inclusion report, and why byte budgets are not provider context-window
claims. Do not add or revise a presentation.

## Exclusions

- Provider system/user message construction, SDK request objects, tokenizers, adaptive token-window
  fitting, model-based relevance, embeddings, reranking, summarization, or caching.
- Tool schemas, registry, dispatch, MCP transport, LLM tool-call handling, multi-step loop control,
  protocol events, transcript persistence, and TUI rendering.
- Arbitrary repository scanning without a query, instruction prose interpretation, content secret
  classification, writes, subprocesses, network access, or policy override.
- Choosing when a tool target requires enrichment, extracting a scope from a tool input, or carrying
  context between model turns; later registry and loop units own those decisions.
- Multiple roots, descriptor-relative hardening, filesystem watching, concurrent context builds, and
  production-scale retrieval infrastructure.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish supplied scope/focus aliases, root canonical-scope snapshot, final canonical focus paths, canonical search result scope, first-occurrence match-owner scopes, instruction target `source`, semantic owner `applies_to`, item path/reason, and content-byte accounting. Provider-visible context never substitutes source for owner. |
| End-to-end contract | Validate every derived request -> discover/fold root -> read/discover/fold each focus -> run search/check root scope -> discover/fold each first-occurrence match owner -> commit instruction union -> select focus/search items -> immutable package/report; CAH-032 consumes the package and CAH-034/035 later call pure enrichment. CAH-037 owns evaluation wiring. |
| Failure and atomicity | Invalid projection performs zero I/O; root failure runs zero focus/search work; focus failure runs zero search; scope mismatch or a rejecting cooperative callback stops later discovery/search; conflicts or required-budget overflow return no package. Optional omissions only update aggregates, and enrichment constructs a new all-or-nothing value. Final orchestration supplies cancellation/deadline behavior through the required callback without a reverse import. |
| Reachable boundaries | Real CAH-025/028/029 producers exercise 8/9 focuses, 4/5 queries, 16/17 instruction owners, 24/25 items, and 98,304/98,305 content bytes, including two owners sharing a source, late-ancestor enrichment, scope retargets, and smaller optional items after an oversized candidate. |
| Closed grammar and cardinality | The request has exactly one scope, at most eight ordered focus paths, and at most four ordered literal queries; item kinds, inclusion reasons, omission aggregates, priority, canonical deduplication, owner-idempotence, topology insertion, and first-fit selection are closed and deterministic. Required items are never truncated or dropped. |
| Artifact parity | Story, lesson, diagram, context/architecture/safety docs, pseudocode, and tests name the same validate-all -> root -> focuses -> searches -> match owners -> complete instruction union -> item selection order and the same repeated cooperative stages, with exact bundle-scope equality, failure precedence, owner/source identity, and atomic enrichment. |
| Independent lenses | Security/identity review covers aliases, captured scopes, owner/source provenance, and leak-free reports; handoff/composition review covers every CAH-025/027-029 producer and CAH-032/034/035 consumer; limits/scheduler review covers reachable budgets and records provider/token fitting plus scheduler behavior as deferred. |

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Instruction-binding/focus/query/item/content and per-kind limits pass below/at/above evidence.
3. Exact derived request projection, scope-plus-focus-plus-search-owner instruction union,
   search-scope containment without search-root fanout, deterministic owner discovery, owner-scoped
   provenance, canonical deduplication, topology-correct atomic enrichment including a late ancestor,
   all-or-nothing required sources, optional first-fit selection, byte arithmetic, and safe reporting
   are proved without leaks.
4. Public request, item, report, and package contracts are immutable, typed, documented, and reject
   unsupported fields.
5. Focused tests and the canonical offline `./scripts/check` pass with no model, subprocess, or
   network.
6. Existing provider, protocol, transcript, tool, loop, and TUI boundaries remain unchanged and pass
   their existing tests.
7. The Markdown lesson uses exact implementation and failure-test excerpts after code exists and
   includes no presentation work.
8. Story, lesson, conceptual docs, indexes, backlog, planning note, and statuses agree.
9. Delivered production-source churn is recorded and remains near the planned range or is split
   before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- A provider-neutral context-builder module and fixture-workspace tests prove exact scope/focus/search
  projections, search-match owner coverage, initial instruction-union selection, monotonic
  scoped-instruction enrichment, and reporting.
- Integration evidence uses the real instruction, listing, read, and search contracts and compares
  repeated packages for deterministic equality.
- The lesson locates context construction between native repository evidence and the later explicit
  agent loop; its primary teach-back question is: what decisions must remain in the harness before
  any context reaches an LLM?

## Deferred work

- The next core learning unit maps a validated context package into provider-neutral request content
  without importing SDK types into the harness domain.
- E4 identifies the ordered instruction scopes of a successful read; later loop units decide when to
  discover and fold those CAH-025 bundles between model turns.
- A later evaluation unit measures known-file retrieval and context usefulness before adding ranking,
  embeddings, summarization, or provider-specific token fitting.
