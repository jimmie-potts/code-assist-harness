# CAH-030 - Build budgeted repository context

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-025, CAH-027, CAH-028, and CAH-029
- **Lesson:** [Budgeted repository context](../docs/lessons/cah-030-budgeted-context.md)
- **Learning emphasis:** Core learning unit - deterministic context engineering and evidence
  provenance
- **Review focus:** Why the harness, rather than the provider, owns source priority, inclusion
  reasons, deduplication, and content budgets

## User story

> As a user, I want the harness to assemble a bounded, provenance-rich repository context package so
> that model reasoning is grounded in selected evidence and omissions are visible rather than
> silently hidden.

## Single responsibility

CAH-030 owns deterministic selection and reporting for one provider-neutral repository context
package. It does not construct a provider request, count provider tokens, register tools, handle LLM
responses, dispatch tool calls, run multiple agent steps, or persist raw repository content.

## Scope

- Add immutable Python context request, item, inclusion-report, and package contracts over CAH-025
  and CAH-027 through CAH-029.
- Accept one instruction scope, up to eight explicit focus files, and up to four optional literal
  search queries.
- Include applicable repository instructions, bounded focus-file slices, and bounded search excerpts
  in one exact priority order under reviewed item and UTF-8 content-byte budgets.
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
  content, `content_bytes`, `truncated`, and kind-specific provenance: instruction precedence,
  focus line range, or search query rank plus line/column.
- Canonical duplicates use the highest-priority occurrence. Instruction content outranks the same
  path as a focus file. Search excerpts are deduplicated by canonical path, line, column, and exact
  excerpt; multiple distinct excerpts from one file may remain.
- `ContextPackage` contains an immutable ordered item tuple, `content_bytes`, and one immutable
  `InclusionReport`. Default representations suppress all content and search query text.
- The report has one record for each included item with canonical path, reason, included bytes, and
  truncation. Exclusions are aggregate counts by `duplicate`, `item_budget`, `byte_budget`,
  `search_limit`, `ignored_or_unavailable`, `non_text`, and `source_too_large`; it never reports an
  excluded/denied label, ignore rule, raw error, query text, or excluded content.

### Initial reviewed budgets

| Limit | Initial value | Boundary behavior |
| --- | ---: | --- |
| Explicit focus files | 8 | A ninth fails request validation. |
| Literal search queries | 4 | A fifth fails request validation. |
| Context items | 24 | Required items must all fit; optional items beyond the limit are counted and omitted. |
| Aggregate item content | 96 KiB (98,304 UTF-8 bytes) | Required items must all fit; optional items use deterministic first-fit inclusion. |
| One instruction item | 32 KiB | Inherited from CAH-025; never truncated here. |
| One focus item | 32 KiB and 400 whole lines | Read from line 1 with CAH-028 and report source truncation. |
| One search item | 512 bytes | Exact CAH-029 excerpt; never expanded here. |

- Required instructions are all-or-nothing because silently dropping a narrower instruction can
  change meaning. If all instruction items or all required focus items cannot fit the 24-item and
  96-KiB package, the build fails with `required_context_exceeds_budget`; it does not partially
  include required content.
- Optional search items use deterministic first-fit selection: consider them in defined order,
  include an item when both budgets permit it, otherwise increment the relevant aggregate and
  continue so a later smaller item may fit.
- `content_bytes` is the sum of `len(item.content.encode("utf-8"))`. Labels, report metadata, and
  future provider framing are outside this content budget but remain item-bounded. Bytes and items
  are deliberately reproducible proxies, not token counts or a claim that a provider request fits a
  particular model window.
- Package construction is synchronous and bounded. Later orchestration checks cancellation between
  discovery, reads, searches, and provider work; this unit introduces no event-loop state.

### Fixed, non-leaking failures

CAH-025 and CAH-026 fixed safe errors remain authoritative for source failures.
`ContextBuildError` adds only these package-level failures:

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_context_request` | `Repository context request exceeds the input limit.` | focus/query count or another package-level request shape is invalid |
| `required_context_exceeds_budget` | `Required repository context exceeds the item or byte budget.` | all required instruction and focus items cannot fit |
| `context_build_failed` | `Repository context could not be built safely.` | another bounded internal composition failure occurs |

- No partial package is returned with a failure. Exceptions, reports, values, and their default
  representations contain no absolute paths, denied labels, raw OS/decoder text, or content outside
  admitted included items.
- Every filesystem source is re-admitted through its owning CAH-025/028/029 operation. The builder
  does not cache a prior policy decision as authorization.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if provider-message construction, token
  counting, adaptive ranking, tool dispatch, transcript persistence, or loop control enters this
  unit, or if production churn is likely to exceed roughly 600 changed lines. Do not pad a smaller
  coherent implementation.

## Acceptance criteria

1. One request produces immutable instruction, focus, and optional search items in the exact reviewed
   priority order with canonical provenance.
2. Required instructions and focus files are all-or-nothing; optional search excerpts use
   deterministic first-fit selection under 24-item and 96-KiB limits.
3. Canonical duplicate sources are included once at their highest-priority reason and every included
   item records exact UTF-8 content bytes and source truncation.
4. The inclusion report identifies included sources and aggregate omission reasons without exposing
   denied labels, excluded content, raw errors, or search query text.
5. Input counts, per-kind limits, aggregate item/content budgets, and inherited strict text policy are
   tested exactly and do not use provider token estimates.
6. Public contracts are typed, documented, provider-neutral, and tested locally with no provider,
   subprocess, network, protocol, transcript, TUI, or agent-loop behavior.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Priority and provenance | Combine nested instructions, ordered focus files, and two searches | Unit integration | Exact item kinds, canonical labels, provenance, and order |
| Canonical deduplication | Reach one file through aliases and multiple reasons | Boundary integration | One highest-priority item and exact duplicate aggregate |
| Required all-or-nothing | Build required sources immediately below, at, and above 24 items/96 KiB | Unit | Full package at limits; fixed failure and no partial value above |
| Optional first-fit | Place differently sized search excerpts around remaining capacity | Unit | Exact included items and item/byte omission aggregates |
| Input bounds | Exercise 8/9 focus paths and 4/5 queries plus inherited query limit | Schema/unit | Exact admission at bounds and fixed request failure above |
| Inclusion hygiene | Use ignored, denied, invalid-text, oversized, no-match, and truncated search candidates | Policy integration | Safe aggregates, no excluded label/content/query leak |
| Determinism | Build the same fixture repeatedly with reversed filesystem creation order | Integration | Byte-for-byte equal provider-neutral packages and reports |

## Validation

- Add focused context-builder tests using real CAH-024 through CAH-029 services over deterministic
  fixture workspaces; fake only a narrow race seam when needed.
- Assert item priority, provenance, deduplication, exact byte arithmetic, first-fit behavior,
  all-or-nothing required sources, safe representations, and full failure strings.
- Test focus/query/item/content boundaries below, at, and above without a tokenizer, model, network,
  subprocess, or timing assertion.
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
- Multiple roots, descriptor-relative hardening, filesystem watching, concurrent context builds, and
  production-scale retrieval infrastructure.

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Focus/query/item/content and per-kind limits pass below/at/above evidence.
3. Priority, canonical deduplication, all-or-nothing required sources, optional first-fit selection,
   byte arithmetic, and safe reporting are proved without leaks.
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

- A provider-neutral context-builder module and fixture-workspace tests prove exact selection and
  reporting.
- Integration evidence uses the real instruction, listing, read, and search contracts and compares
  repeated packages for deterministic equality.
- The lesson locates context construction between native repository evidence and the later explicit
  agent loop; its primary teach-back question is: what decisions must remain in the harness before
  any context reaches an LLM?

## Deferred work

- The next core learning unit maps a validated context package into provider-neutral request content
  without importing SDK types into the harness domain.
- E4 introduces capability-classified tool contracts and dispatch; later loop units handle model
  tool-call responses and repeated turns under CAH-022 limits.
- A later evaluation unit measures known-file retrieval and context usefulness before adding ranking,
  embeddings, summarization, or provider-specific token fitting.
