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
under exact item and UTF-8 byte budgets and explains every inclusion or aggregate omission. It also
defines a pure atomic merge for one newly discovered scoped-instruction bundle. The package remains
provider-neutral so later LLM and tool-loop work cannot silently take ownership of selection.

## Learning objectives

After completing this unit, you should be able to:

- explain required versus optional context and their different failure behavior;
- apply instruction, focus-file, and search priority deterministically;
- merge a newly discovered instruction chain without eviction or sibling-precedence mistakes;
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

Every instruction also carries `applies_to`, derived from the canonical parent of its `AGENTS.md`.
Ancestor and descendant instructions have precedence only along the same path. Two sibling scopes do
not override one another merely because one was discovered first. A later tool loop may discover one
new CAH-025 bundle, but this unit only defines the pure merge of that already-validated value.

A common misconception is that 96 KiB means the same number of model tokens for every provider.
Tokenization varies. This story counts UTF-8 content bytes because tests can reproduce them; a later
provider layer must fit its complete message to the selected model.

## Key concepts

- **Priority:** instructions root-to-nearest, focus files in request order, then search excerpts in
  query and match order.
- **Required all-or-nothing:** never silently drop a narrower instruction or explicit focus source.
- **Optional first-fit:** include a search item when both remaining budgets permit, then continue.
- **Canonical deduplication:** one source keeps its highest-priority reason despite aliases.
- **Monotonic enrichment:** add unseen required instructions at topology-correct positions inside the
  instruction block while preserving every prior item's relative order and evicting nothing.
- **Scoped precedence:** `applies_to` defines where guidance applies; sibling serialization order is
  not precedence.
- **Inclusion report:** included provenance plus bounded aggregate omission reasons, not a secret
  inventory.

## Architecture and design

```text
Ink TUI -- task/scope --> Python harness
                              |
        +---------------------+----------------------+
        |                     |                      |
  CAH-025 instructions   CAH-027/028 files    CAH-029 search excerpts
        |                     |                      |
        +---------------------v----------------------+
                    [CAH-030 context builder]
                       |                 |
             ContextPackage       InclusionReport
                       ^
 admitted tool scope -> CAH-025 bundle -> pure atomic instruction merge
                       |
            provider-neutral request mapping (later)
                       |
               Provider port / explicit agent loop (later)

Tool registry/MCP dispatch and transcript evidence are unchanged in CAH-030.
```

The package allows at most 16 distinct instruction sources, 24 total items, and 96 KiB of item
content. Up to eight focus files and four search queries enter the initial deterministic pipeline.
The provider receives no authority to reorder, bypass policy, or request hidden exclusions.

## Practical walkthrough

1. Validate one scope, no more than eight focus paths, and no more than four literal queries.
2. Discover all required instructions; read required focus files from line 1 within 32 KiB/400 lines.
3. Generate optional 512-byte search excerpts in deterministic query/match order.
4. Canonicalize and deduplicate, keeping the highest-priority reason.
5. Prove all required items fit 24 items and 96 KiB or fail without a partial package.
6. First-fit optional items and emit exact included records plus aggregate omissions.
7. Given one later CAH-025 bundle, derive each `applies_to`, skip only exact duplicate sources, insert
   unseen instructions before the first strict descendant or at the instruction-block end, and
   recheck 16/24/96-KiB atomically.

## Implementation code samples

No shipped code exists. Planned pseudocode:

```text
required = instructions(scope) + focus_files(request.focus_paths)
optional = search_excerpts(request.search_queries)
required = canonical_deduplicate(required)
require_fits(required, item_limit=24, byte_limit=96_KiB)
items = first_fit(required, optional)
return ContextPackage(items, InclusionReport.from_selection(items, optional))

def enrich(package, discovered_instructions):
    checked = require_exact_duplicates_or_unseen(discovered_instructions)
    merged = stable_topological_instruction_insert(package, checked.unseen)
    require_fits(merged, instruction_limit=16, item_limit=24, byte_limit=96_KiB)
    return immutable_package_and_report(merged)
```

The first two lines separate correctness-critical and optional evidence. Canonical deduplication
prevents aliases from spending budget twice. `require_fits` is all-or-nothing; `first_fit` may skip
optional items but must report why. Enrichment performs no discovery or tool work, and a conflicting
duplicate fails rather than silently replacing the session's earlier instruction snapshot. Stable
topological insertion places a newly appearing ancestor before an existing descendant without
changing the relative order of any prior items.

## Failure scenarios to study

- **Instruction overflow:** required instructions exceed 96 KiB. The build fails; it never drops the
  nearest rule.
- **Seventeenth instruction:** enrichment fails `required_context_exceeds_budget`; no old or new item
  is evicted.
- **Changed duplicate:** the same canonical source arrives with different content, bytes, or
  `applies_to`; the merge fails `context_build_failed` without revealing either value.
- **Sibling scopes:** both remain in first-admission order, but neither receives precedence over the
  other.
- **Late ancestor:** a root or intermediate instruction appears after a descendant was admitted. It
  inserts before that descendant while every previously admitted pair keeps its relative order.
- **Missing focus file:** an explicitly requested source becomes unavailable. The source's fixed safe
  error ends the build instead of producing falsely complete context.
- **Optional pressure:** one large search excerpt cannot fit but a later smaller one can. First-fit
  omits the former and includes the latter with exact counters.
- **Credential probe:** a search encounters a denied file. The report increments a generic aggregate
  and never includes its label or existence detail.
- **Alias duplication:** instruction, focus, and search paths resolve to the same source; only the
  highest-priority representation spends package budget.

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
| Scope | Explicit local instructions, monotonic scoped enrichment, files, and literal matches | Multi-source indexed retrieval and ranking |
| Reliability | Deterministic fresh build | Cache/index freshness, fallback, and replayable ranking |
| Operations | Fixture tests and inclusion report | Traces, retrieval metrics, alerts, and governance |
| Cost | Low services and cognitive load | Indexing, storage, model calls, telemetry, and ownership |

### Trade-offs and graduation signals

The local algorithm is predictable but cannot rank a huge candidate set or guarantee provider token
fit. Add ranking when known-file retrieval evaluations show measurable misses; add provider-specific
token fitting only at the adapter/request boundary; add remote retrieval only with explicit access,
latency, and provenance tests.

## Practical exercises

1. Given three instructions, two focus files, and search excerpts, write the exact inclusion order.
2. Calculate whether required content at 98,303, 98,304, and 98,305 bytes succeeds.
3. Construct an optional first-fit example where a later item fits after an earlier omission.
4. Inspect an inclusion report and identify what it intentionally does not reveal.
5. Admit a package instruction before a root instruction appears, then merge root/package and
   root/other chains; place the late ancestor and explain why siblings have no precedence.
6. Change one exact duplicate's content and predict the atomic failure.
7. Teach back: which context decisions must remain in the harness before any evidence reaches an
   LLM?

## Key takeaways

- The Python harness owns context selection, priority, provenance, and omissions.
- Required all-or-nothing and deterministic optional first-fit are the central invariants.
- Scoped enrichment is pure, monotonic, and atomic: late ancestors enter before descendants, exact
  duplicates are idempotent, and conflicts or budget overflow produce no partial package.
- Production retrieval can improve recall and scale but demands evaluation, observability, access
  control, and operational ownership.

## Glossary

- **Candidate:** Admitted source considered for a context package.
- **Required context:** Evidence whose omission makes the package invalid.
- **First-fit:** Consider candidates in order and include each only when remaining budgets permit.
- **Inclusion report:** Bounded evidence of what was selected and why other classes were omitted.
- **Provenance:** Canonical source identity and the reason a context item exists.
- **`applies_to`:** Canonical directory subtree governed by one instruction source.
- **Monotonic enrichment:** Adding required instructions without removing or reordering prior items
  relative to one another.

## Further reading

- [CAH-030 delivery contract](../../user-stories/cah-030-build-budgeted-context.md)
- [Context engineering](../context-engineering.md)
- [ADR 0001: Own the agent loop](../adr/0001-own-the-agent-loop.md)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
