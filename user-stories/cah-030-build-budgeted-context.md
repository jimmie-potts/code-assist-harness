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
does not decide when to discover another scope, construct a provider request, count provider tokens,
register tools, handle LLM responses, dispatch tool calls, run multiple agent steps, or persist raw
repository content.

## Scope

- Add immutable Python context request, item, inclusion-report, and package contracts over CAH-025
  and CAH-027 through CAH-029.
- Accept one instruction scope, up to eight explicit focus files, and up to four optional literal
  search queries.
- Include applicable repository instructions, bounded focus-file slices, and bounded search excerpts
  in one exact priority order under reviewed item and UTF-8 content-byte budgets.
- Add one pure operation that atomically enriches an existing package with one already-discovered
  CAH-025 instruction bundle without evicting or rewriting prior context.
- Record canonical provenance, inclusion reason, included bytes, source truncation, and aggregate
  omission reasons without storing denied labels or excluded content.
- Keep the package provider-neutral and local. Make no provider SDK, protocol, transcript, TUI,
  tool-registry, MCP, subprocess, network, or agent-loop change.

## Locked contract

### Request and candidate construction

- `ContextBuildRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It
  contains `scope` (default `.`), `focus_paths` (ordered tuple, at most 8), and `search_queries`
  (ordered tuple, at most 4). Duplicate input paths or queries are retained for validation but
  deduplicated after canonical resolution or exact query comparison and counted in the report.
- The instruction scope must satisfy CAH-025. Every focus path is required and must satisfy
  CAH-028 as an admitted regular text file. A failed required source fails the build; the operation
  never emits a context package that quietly omits an explicit focus file.
- Each search query satisfies CAH-029's one-line, 256-byte contract. Search candidates are optional:
  normal no-match, skipped-file, and truncation outcomes are represented in report aggregates and do
  not fail otherwise valid required context.
- Candidate construction performs no repository-wide default scan. It discovers only scoped
  `AGENTS.md` files, explicitly named focus files, and literal-search excerpts requested by the
  caller.

### Selection order and immutable output

- Required instruction items are ordered root-to-nearest. Required focus-file items follow in input
  order after canonical deduplication. Optional search excerpts follow in query order and then each
  search result's canonical path/line/column order.
- A context item has `kind` (`instruction`, `focus_file`, or `search_excerpt`), canonical `path`,
  content, `content_bytes`, `truncated`, and kind-specific provenance: instruction precedence and
  canonical `applies_to` directory, focus line range, or search query rank plus line/column. An
  instruction's `applies_to` is the canonical workspace-relative POSIX parent of its `AGENTS.md`
  source, with `.` for the root source.
- Canonical duplicates use the highest-priority occurrence. Instruction content outranks the same
  path as a focus file. Search excerpts are deduplicated by canonical path, line, column, and exact
  excerpt; multiple distinct excerpts from one file may remain.
- `ContextPackage` contains an immutable ordered item tuple, `content_bytes`, and one immutable
  `InclusionReport`. Default representations suppress all content and search query text.
- The report has one record for each included item with canonical path, reason, included bytes, and
  truncation. Exclusions are aggregate counts by `duplicate`, `item_budget`, `byte_budget`,
  `search_limit`, `ignored_or_unavailable`, `non_text`, and `source_too_large`; it never reports an
  excluded/denied label, ignore rule, raw error, query text, or excluded content.

### Monotonic scoped-instruction enrichment

- The pure enrichment operation accepts exactly one existing `ContextPackage` and one validated,
  immutable CAH-025 bundle for a newly admitted scope. It performs no discovery, filesystem access,
  policy decision, tool dispatch, provider work, or mutation of either input.
- For each bundle source in CAH-025 root-to-nearest order, derive `applies_to` from the canonical
  source parent. A canonical source already present is idempotent only when its source, content,
  original byte count, and `applies_to` match exactly. Any mismatch fails the whole merge with
  `context_build_failed`; existing or candidate content is never exposed in the failure.
- Unseen instruction items are inserted in bundle order at topology-correct positions inside the
  instruction block. For each unseen source, insert immediately before the first instruction whose
  canonical `applies_to` is a strict path-segment descendant; if none exists, insert at the end of
  the instruction block. This handles an ancestor that appears after a descendant was admitted. All
  prior items and inclusion records retain their relative order, corresponding new records follow
  the new item positions, and no item is evicted, truncated, replaced, or reprioritized. The returned
  package and report are newly constructed immutable values.
- Precedence is path-local. Ancestor instructions precede narrower descendants on the same applicable
  path. Instructions for sibling `applies_to` scopes have no precedence over one another; their
  deterministic first-admission order is only serialization order and grants neither sibling wider
  authority.
- The resulting package may contain at most 16 distinct instruction sources, 24 total items, and
  96 KiB of content. Newly discovered instructions are required context: if the complete merged value
  crosses any bound, enrichment fails atomically with `required_context_exceeds_budget`. It never
  drops an old or new instruction to make room.

### Initial reviewed budgets

| Limit | Initial value | Boundary behavior |
| --- | ---: | --- |
| Distinct instruction sources | 16 | Initial construction or enrichment with a seventeenth source fails atomically. |
| Explicit focus files | 8 | A ninth fails request validation. |
| Literal search queries | 4 | A fifth fails request validation. |
| Context items | 24 | Required items must all fit; optional items beyond the limit are counted and omitted. |
| Aggregate item content | 96 KiB (98,304 UTF-8 bytes) | Required items must all fit; optional items use deterministic first-fit inclusion. |
| One instruction item | 32 KiB | Inherited from CAH-025; never truncated here. |
| One focus item | 32 KiB and 400 whole lines | Read from line 1 with CAH-028 and report source truncation. |
| One search item | 512 bytes | Exact CAH-029 excerpt; never expanded here. |

- Required instructions are all-or-nothing because silently dropping a narrower instruction can
  change meaning. If the initial or enriched instruction set exceeds 16 sources, or all instruction
  items and required focus items cannot fit the 24-item and 96-KiB package, the operation fails with
  `required_context_exceeds_budget`; it does not partially include required content.
- Optional search items use deterministic first-fit selection: consider them in defined order,
  include an item when both budgets permit it, otherwise increment the relevant aggregate and
  continue so a later smaller item may fit.
- `content_bytes` is the sum of `len(item.content.encode("utf-8"))`. Labels, report metadata, and
  future provider framing are outside this content budget but remain item-bounded. Bytes and items
  are deliberately reproducible proxies, not token counts or a claim that a provider request fits a
  particular model window.
- Package construction and enrichment are synchronous and bounded. Later orchestration checks
  cancellation between discovery, merge, reads, searches, and provider work; this unit introduces no
  event-loop state.

### Fixed, non-leaking failures

CAH-025 and CAH-026 fixed safe errors remain authoritative for source failures.
`ContextBuildError` adds only these package-level failures:

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_context_request` | `Repository context request exceeds the input limit.` | focus/query count or another package-level request shape is invalid |
| `required_context_exceeds_budget` | `Required repository context exceeds the item or byte budget.` | the 16-source limit or complete required instruction/focus set cannot fit |
| `context_build_failed` | `Repository context could not be built safely.` | a duplicate instruction conflicts or another bounded internal composition failure occurs |

- No partial package is returned with a failure. Exceptions, reports, values, and their default
  representations contain no absolute paths, denied labels, raw OS/decoder text, or content outside
  admitted included items.
- Every filesystem source in an initial build is re-admitted through its owning CAH-025/028/029
  operation. Enrichment consumes one already-validated CAH-025 value and performs no access; later
  orchestration remains responsible for discovering that bundle for the newly admitted scope.

## Reviewability budget

- **Estimated production-code churn:** 400-550 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if provider-message construction, token
  counting, adaptive ranking, instruction-discovery triggering, tool dispatch, transcript
  persistence, or loop control enters this unit, or if production churn is likely to exceed roughly
  600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One request produces immutable instruction, focus, and optional search items in the exact reviewed
   priority order with canonical provenance, including instruction `applies_to` scope.
2. Required instructions and focus files are all-or-nothing; optional search excerpts use
   deterministic first-fit selection under 24-item and 96-KiB limits.
3. Canonical duplicate sources are included once at their highest-priority reason and every included
   item records exact UTF-8 content bytes and source truncation.
4. The inclusion report identifies included sources and aggregate omission reasons without exposing
   denied labels, excluded content, raw errors, or search query text.
5. Input counts, per-kind limits, aggregate item/content budgets, and inherited strict text policy are
   tested exactly and do not use provider token estimates.
6. One validated CAH-025 bundle enriches an existing package atomically: exact duplicates are
   idempotent, conflicting duplicates fail, and unseen instructions enter topology-correct positions
   without evicting or reordering prior items.
7. Enrichment preserves path-local ancestor precedence, assigns no precedence between sibling
   scopes, and enforces 16 instruction sources plus the existing 24-item/96-KiB bounds all-or-nothing.
8. Public contracts are typed, documented, provider-neutral, and tested locally with no provider,
   subprocess, network, protocol, transcript, TUI, or agent-loop behavior.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Priority and provenance | Combine nested instructions, ordered focus files, and two searches | Unit integration | Exact item kinds, canonical labels, provenance, and order |
| Canonical deduplication | Reach one file through aliases and multiple reasons | Boundary integration | One highest-priority item and exact duplicate aggregate |
| Required all-or-nothing | Build required sources immediately below, at, and above 24 items/96 KiB | Unit | Full package at limits; fixed failure and no partial value above |
| Monotonic enrichment | Merge nested and sibling bundles into a package containing focus/search items | Unit | Unseen instructions enter topology-correct instruction-block positions; every prior item retains relative order and none is evicted |
| Duplicate instruction identity | Re-merge one exact source, then change only content, bytes, or `applies_to` | Unit | Exact duplicate is byte-for-byte idempotent; each mismatch fails `context_build_failed` with no partial package |
| Enrichment bounds | Merge the 16th/17th distinct instruction and values at 24 items and 98,304/98,305 bytes | Unit | Success exactly at every bound; `required_context_exceeds_budget` above, with no eviction |
| Scoped precedence | Merge ancestor, descendant, and sibling bundles, including an ancestor created after its descendant was admitted | Unit | Late ancestors insert before existing descendants; prior sibling order remains stable without a precedence claim |
| Optional first-fit | Place differently sized search excerpts around remaining capacity | Unit | Exact included items and item/byte omission aggregates |
| Input bounds | Exercise 8/9 focus paths and 4/5 queries plus inherited query limit | Schema/unit | Exact admission at bounds and fixed request failure above |
| Inclusion hygiene | Use ignored, denied, invalid-text, oversized, no-match, and truncated search candidates | Policy integration | Safe aggregates, no excluded label/content/query leak |
| Determinism | Build the same fixture repeatedly with reversed filesystem creation order | Integration | Byte-for-byte equal provider-neutral packages and reports |

## Validation

- Add focused context-builder tests using real CAH-024 through CAH-029 services over deterministic
  fixture workspaces; fake only a narrow race seam when needed.
- Assert item priority, `applies_to` provenance, deduplication, exact byte arithmetic, first-fit
  behavior, topology-correct atomic enrichment including a late ancestor, all-or-nothing required
  sources, safe representations, and full failure strings.
- Test instruction-source/focus/query/item/content boundaries below, at, and above without a
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

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Instruction-source/focus/query/item/content and per-kind limits pass below/at/above evidence.
3. Priority, scoped provenance, canonical deduplication, topology-correct atomic enrichment including
   a late ancestor, all-or-nothing required sources, optional first-fit selection, byte arithmetic,
   and safe reporting are proved without leaks.
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

- A provider-neutral context-builder module and fixture-workspace tests prove exact selection,
  monotonic scoped-instruction enrichment, and reporting.
- Integration evidence uses the real instruction, listing, read, and search contracts and compares
  repeated packages for deterministic equality.
- The lesson locates context construction between native repository evidence and the later explicit
  agent loop; its primary teach-back question is: what decisions must remain in the harness before
  any context reaches an LLM?

## Deferred work

- The next core learning unit maps a validated context package into provider-neutral request content
  without importing SDK types into the harness domain.
- E4 identifies the typed target scope of a successful read; later loop units decide when to discover
  one CAH-025 bundle and invoke this pure merge between model turns.
- A later evaluation unit measures known-file retrieval and context usefulness before adding ranking,
  embeddings, summarization, or provider-specific token fitting.
