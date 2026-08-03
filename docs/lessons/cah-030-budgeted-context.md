# CAH-030 lesson: Budgeted repository context

- **Unit:** CAH-030
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Build budgeted repository context](../../user-stories/cah-030-build-budgeted-context.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned priority, scoped provenance, atomic enrichment, and omission
  evidence
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Context engineering](../context-engineering.md),
  [Agent loop](../agent-loop.md), and [Harness architecture](../architecture.md)

> This lesson describes accepted planned behavior. No context-builder implementation or provider
> integration is claimed.

## Quick summary

CAH-030 is the M2 context-engineering checkpoint: the harness chooses ordered repository evidence
under exact instruction-binding, item, and UTF-8 byte budgets and explains every inclusion or
aggregate omission. Its initial instruction union covers both the supplied scope and every distinct
explicit focus path, plus every first-occurrence canonical owner directory returned by a requested
search. It also defines the same pure atomic merge for later scoped enrichment. The package remains
provider-neutral so later LLM and tool-loop work cannot silently take ownership of selection.

## Learning objectives

After completing this unit, you should be able to:

- explain required versus optional context and their different failure behavior;
- build a deterministic scope-plus-focus-plus-search-owner instruction union before appending
  model-visible content;
- project exact bounded focus and fixed-scope search requests without hidden fanout;
- explain why a search result adds an instruction scope but never a new search root;
- merge a newly discovered instruction chain without eviction or sibling-precedence mistakes;
- preserve target `source` separately from candidate-owner `applies_to`;
- design provenance and an inclusion report without leaking excluded sources; and
- distinguish a reproducible byte budget from a provider token-window guarantee.

## Why this unit matters

An LLM response can be only as grounded as its evidence. Sending the entire repository is unsafe and
usually impossible; sending a silent subset makes failures hard to diagnose. CAH-030 makes selection
a visible harness decision before provider-message or multi-step tool logic is introduced.

## Junior engineer foundation

Context is the information sent alongside a task. A candidate is a source that might be included; a
context item is a candidate that passed policy and selection. Required sources affect correctness:
applicable instructions and explicitly requested focus files must all appear or the build fails.
Search excerpts are optional hints and may be omitted with evidence.

Every CAH-025 instruction binding already carries two different labels. `source` is the canonical
file whose bytes were read. `applies_to` is the canonical directory that owned the `AGENTS.md`
candidate. CAH-030 copies both; it never derives one from the other. If `pkg/AGENTS.md` is a symlink
to `shared/rules.md`, the binding is `source="shared/rules.md"` and `applies_to="pkg"`. Deriving
`applies_to="shared"` would silently widen or move the rule's authority.

Binding identity is therefore the candidate owner. The same target shared by `pkg/AGENTS.md` and
`other/AGENTS.md` is two valid bindings, consumes budget twice, and appears as two distinguishable
inclusion records. Repeating one owner is idempotent only when source, content, and original byte
count match. A retargeted source or changed snapshot fails atomically.

The initial build starts with instructions for `request.scope`, then folds in instructions for every
canonical-distinct focus path in input order. Requested searches run only from `request.scope`.
Their canonical matches are traversed in query then path/line/column order; the first occurrence of
each exact match-file parent adds one CAH-025 bundle to the required instruction union. Ancestor and
descendant owners have precedence only along the same path; sibling owners do not override one
another merely because one was discovered first. A later tool loop may discover another CAH-025
bundle, but this unit only defines the pure merge of that already-validated value.

Validation must precede deduplication. Otherwise a duplicate-looking but malformed focus or query
could be hidden without passing its owning contract. All exact CAH-028 and CAH-029 projections are
schema-validated before candidate I/O. Focuses are canonical-deduplicated only after admission;
queries are exact-deduplicated after validation. Every search keeps the supplied scope as its root,
so a focus or match cannot silently widen search. A match owner does trigger instruction discovery:
guidance that governs returned evidence must be present before that evidence reaches a model.

A common misconception is that 96 KiB means the same number of model tokens for every provider.
Tokenization varies. This story counts UTF-8 content bytes because tests can reproduce them; a later
provider layer must fit its complete message to the selected model.

## Key concepts

- **Priority:** the complete topology-ordered scope-plus-focus-plus-search-owner instruction union,
  focus files in request order, then search excerpts in query and match order.
- **Required all-or-nothing:** never silently drop a narrower instruction or explicit focus source.
- **Optional first-fit:** include a search item when both remaining budgets permit, then continue.
- **Validation before deduplication:** every supplied focus/query projection must satisfy its owner
  before canonical or exact duplicate removal.
- **Binding identity:** `applies_to` identifies an instruction binding; one source can legitimately
  back multiple separately charged owners.
- **Canonical deduplication:** a non-instruction source keeps its highest-priority reason despite
  aliases.
- **Monotonic enrichment:** add unseen required instructions at topology-correct positions inside the
  instruction block while preserving every prior item's relative order and evicting nothing.
- **Scoped precedence:** `applies_to` defines where guidance applies; sibling serialization order is
  not precedence.
- **Result coverage without search fanout:** a canonical match owner adds required instructions, but
  the match path never becomes another search root.
- **Inclusion report:** included provenance plus bounded aggregate omission reasons, not a secret
  inventory.

## Architecture and design

```text
Ink TUI -- task/scope --> Python harness
                              |
            [CAH-030 request projection]
                 |
 request.scope -> CAH-025(scope first) ----------------------\
 focus paths -> CAH-028 -> canonical focuses -> CAH-025(each) +-> required instruction union
                                                               (topology/no eviction)
                         \--------------------------------------> focus items
 queries -> CAH-029(path=request.scope) -> canonical matches --+-> search excerpts
                                           |
                 first-occurrence parent owners -> CAH-025(each)
                                             \         |         /
                              [CAH-030 bounded selection]
                                             |
                            16 bindings / 24 items / 96 KiB
                                             |
                               ContextPackage + InclusionReport
                                             ^
 admitted tool scope -> CAH-025 bundle -> same topology/no-eviction merge
                                             |
                              provider mapping / agent loop (later)

Tool registry/MCP dispatch and transcript evidence are unchanged in CAH-030.
```

The package allows at most 16 distinct instruction bindings, 24 total items, and 96 KiB of item
content across the whole initial build or enriched value. Two owners of one instruction source use
two binding slots, two item slots, and both copies' content bytes. Up to eight focus files and four
search queries enter the initial deterministic pipeline. The provider receives no authority to
reorder, bypass policy, or request hidden exclusions.

## Practical walkthrough

1. Validate one scope, no more than eight focus paths, and no more than four literal queries.
2. Materialize every exact focus projection as
   `ReadFileRequest(path=focus_path, start_line=1, max_lines=400, max_bytes=32768)` and every exact
   search projection as
   `SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)`. Validate all of
   them before candidate I/O.
3. Read every required focus, then canonical-deduplicate admitted results in input order. Exact-dedup
   validated queries in input order and run each search from the unchanged supplied scope.
4. Discover the required CAH-025 bundle for `request.scope` first, then one bundle per distinct focus
   path. Traverse canonical matches in query/path/line/column order, exact-deduplicate their parent
   owners on first occurrence, and discover one bundle for each owner. Fold every bundle through the
   topology merge and finish the union before any focus item or search excerpt.
5. Append required focus items, then generate optional 512-byte search excerpts. Focus and match paths
   cause no extra searches. Search-owner bundles remain required even when first-fit later omits every
   excerpt for that owner.
6. Prove the complete required set fits 16 bindings, 24 items, and 96 KiB or fail with no partial
   package. First-fit optional items and emit owner-aware inclusion records plus aggregate omissions.
7. Given one later CAH-025 bundle, copy each `source` and `applies_to`, skip only exact owner
   snapshots, insert unseen bindings before the first strict descendant or at the instruction-block
   end, and recheck the same 16/24/96-KiB limits atomically.

## Implementation code samples

No shipped code exists. Planned pseudocode:

```text
focus_requests = tuple(
    ReadFileRequest(path=path, start_line=1, max_lines=400, max_bytes=32768)
    for path in request.focus_paths
)
search_requests = tuple(
    SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)
    for query in request.search_queries
)
# Constructing both tuples validates every projection before source I/O.

focuses = canonical_unique(read(focus_request) for focus_request in focus_requests)
queries = exact_query_unique(search_requests)
search_results = tuple(search(search_request) for search_request in queries)
match_owners = exact_unique_first(
    parent(match.path)
    for result in search_results
    for match in result.matches  # canonical path/line/column order
)

package = merge(empty_package(), discover_for_path(request.scope))
for focus in focuses:
    package = merge(package, discover_for_path(focus.path))
for owner in match_owners:
    package = merge(package, discover_for_path(owner))
# Every required instruction now exists before any focus item or excerpt is appended.

required = append_focus_items(package, focuses)
require_fits(required, binding_limit=16, item_limit=24, byte_limit=96_KiB)
optional = ordered_excerpts(search_results)
items = first_fit(required, optional)
return ContextPackage(items, owner_aware_report(items, optional))

def enrich(package, discovered_instructions):
    checked = require_exact_owner_snapshots_or_unseen(discovered_instructions)
    merged = stable_topological_instruction_insert(package, checked.unseen)
    require_fits(merged, binding_limit=16, item_limit=24, byte_limit=96_KiB)
    return immutable_package_and_report(merged)
```

The two projection tuples lock the exact downstream request shapes before any candidate operation can
touch the filesystem. Canonical focus deduplication happens only after CAH-028 admission; query dedup
uses exact validated query equality. Notice that every search request keeps `request.scope` rather
than substituting a focus or a result path. Canonical result owners affect only instruction coverage;
they never launch another search.

The scope bundle is folded first, then one bundle per distinct focus, then one per first-occurrence
canonical match owner in deterministic query/match order. CAH-025 canonicalization and the same
idempotent merge core prevent aliases from creating extra logical bindings. `require_fits` treats
all those instructions as required; `first_fit` may skip optional search items but must report why.
A discovery error, conflicting owner snapshot, or required-budget overflow returns no partial
package. Stable topological insertion places a newly appearing ancestor before an existing
descendant without changing the relative order of prior items.

## Failure scenarios to study

- **Required overflow:** required content crosses 96 KiB or a seventeenth instruction binding appears.
  The build fails without dropping or evicting any rule, even when owners share one physical source.
- **Binding identity:** two owners targeting `shared/rules.md` remain separately charged. Repeating one
  owner with a changed source, content, or original byte count instead fails `context_build_failed`.
- **Missed nested rule:** `scope="."` plus focus `pkg/file.py` must include `pkg/AGENTS.md`; discovering
  only the scope bundle would produce falsely incomplete required context.
- **Uncovered search evidence:** a match under `other/` would be model-visible without
  `other/AGENTS.md`. The owner bundle is required before any excerpt, even if selection later omits
  that optional excerpt.
- **Invalid duplicate projection:** a duplicate-looking focus or query is malformed. Validation fails
  before source I/O rather than deduplication hiding the error.
- **Search-root drift:** a focus or match sits under `pkg/`. Search still uses the unchanged supplied
  scope. The match parent triggers instruction discovery but never an extra search.
- **Owner discovery failure:** a returned match owner cannot be admitted, conflicts with an earlier
  owner snapshot, or pushes the union over a required bound. The build returns no package or excerpt.
- **Topology:** sibling scopes retain first-admission order without precedence; a late ancestor
  inserts before a descendant while every previously admitted pair keeps its relative order.
- **Missing focus file:** an explicitly requested source becomes unavailable. The source's fixed safe
  error ends the build instead of producing falsely complete context.
- **Optional pressure:** one large search excerpt cannot fit but a later smaller one can. First-fit
  omits the former and includes the latter with exact counters.
- **Credential probe:** a search encounters a denied file. The report increments a generic aggregate
  and never includes its label or existence detail.
- **Alias duplication:** non-instruction focus and search paths resolve to one source; only the
  highest-priority representation spends package budget. Instruction owner bindings remain distinct
  even when they share that target.

## Production expansion

### Example enterprise scenario

A large organization may retrieve from code indexes, issue trackers, documentation, and runtime
telemetry across many repositories. Production selection may use ranking, embeddings, summaries,
provider-specific token fitting, caching, and access-control-aware provenance. Each heuristic must
remain observable and evaluated against grounded tasks.

### Typical production capabilities and tools

- [LlamaIndex](https://docs.llamaindex.ai/) provides ingestion, indexes, retrievers, and response
  synthesis, improving breadth at the cost of framework and storage complexity.
- [LangChain retrieval](https://docs.langchain.com/oss/python/langchain/retrieval) offers composable
  loaders and retrievers, adding abstraction and evaluation/upgrade work.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) standardizes remote
  resources and tools, adding client/server trust, authorization, and transport operations.
- [OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/) can trace retrieval decisions and
  latency, adding telemetry schemas, storage, sampling, and redaction responsibilities.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | Initial scope/focus/search-owner instructions, monotonic scoped enrichment, files, and fixed-root literal matches | Multi-source indexed retrieval and ranking |
| Reliability | Deterministic fresh build | Cache/index freshness, fallback, and replayable ranking |
| Operations | Fixture tests and inclusion report | Traces, retrieval metrics, alerts, and governance |
| Cost | Low services and cognitive load | Indexing, storage, model calls, telemetry, and ownership |

### Trade-offs and graduation signals

The local algorithm is predictable but cannot rank a huge candidate set or guarantee provider token
fit. Add ranking when known-file retrieval evaluations show measurable misses; add provider-specific
token fitting only at the adapter/request boundary; add remote retrieval only with explicit access,
latency, and provenance tests.

## Practical exercises

1. With `scope="."` and focuses `pkg/a.py`, `other/b.py`, and an alias of `pkg/a.py`, list the CAH-025
   calls and the final instruction/focus ordering.
2. Write the exact CAH-028 and CAH-029 projections for one focus and query. Explain why all projections
   validate before I/O and why search keeps the supplied scope.
3. Return matches under `pkg/`, `other/`, then `pkg/` again across two queries. List CAH-025 calls and
   explain why their owner scopes do not become search roots.
4. Let `pkg/AGENTS.md` and `other/AGENTS.md` target `shared/rules.md`. Write both item and report
   identities, then calculate their binding/item/content budget charge.
5. Calculate whether required content at 98,303, 98,304, and 98,305 bytes succeeds.
6. Construct an optional first-fit example where a later item fits after an earlier omission.
7. Admit a package instruction before a root instruction appears, then merge root/package and
   root/other chains; place the late ancestor and explain why siblings have no precedence.
8. Retarget one repeated owner while keeping its content equal. Predict the atomic failure and explain
   why source identity is part of the snapshot.
9. Teach back: which context, instruction-scope, and search-root decisions must remain in the harness
   before any evidence reaches an LLM?

## Key takeaways

- The Python harness owns context selection, priority, provenance, and omissions.
- Required all-or-nothing includes instructions for the request scope, every distinct focus path, and
  every first-occurrence canonical search-match owner; optional excerpts remain deterministic
  first-fit from one unchanged search scope.
- CAH-030 copies `source` and owner `applies_to`: shared targets remain separately scoped and charged.
- Initial assembly and later enrichment use one pure, monotonic, atomic merge: late ancestors enter
  before descendants, exact owner snapshots are idempotent, and conflicts or budget overflow produce
  no partial package.
- Production retrieval can improve recall and scale but demands evaluation, observability, access
  control, and operational ownership.

## Glossary

- **Candidate:** Admitted source considered for a context package.
- **Required context:** Evidence whose omission makes the package invalid.
- **First-fit:** Consider candidates in order and include each only when remaining budgets permit.
- **Inclusion report:** Bounded evidence of what was selected and why other classes were omitted.
- **Provenance:** Canonical source identity and the reason a context item exists.
- **Instruction binding:** One candidate owner paired with its validated instruction target snapshot.
- **`source`:** Canonical instruction target whose content was read.
- **`applies_to`:** Canonical candidate-owner directory subtree governed by one instruction binding;
  it is copied from CAH-025, not inferred from `source`.
- **Projection:** Exact downstream request constructed from one higher-level context request.
- **Search-match owner:** Canonical parent directory of a returned match file; it contributes required
  instruction coverage but never becomes a search root.
- **Monotonic enrichment:** Adding required instructions without removing or reordering prior items
  relative to one another.

## Further reading

- [CAH-030 delivery contract](../../user-stories/cah-030-build-budgeted-context.md)
- [Context engineering](../context-engineering.md)
- [ADR 0001: Own the agent loop](../adr/0001-own-the-agent-loop.md)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
