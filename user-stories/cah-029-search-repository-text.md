# CAH-029 - Search repository text literally

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-027 and CAH-028
- **Lesson:** [Literal repository search](../docs/lessons/cah-029-literal-text-search.md)
- **Learning emphasis:** Supporting implementation unit - bounded evidence retrieval for later tool
  use
- **Review focus:** Deterministic search budgets and safe result provenance, not regular-expression
  features or provider plumbing

## User story

> As a user, I want the harness to find a literal string in admitted repository text files so that
> later reasoning can locate evidence without invoking an unbounded external search process.

## Single responsibility

CAH-029 owns one case-sensitive literal `search_text` operation over the list/read/policy primitives.
It does not implement regular expressions, fuzzy or semantic ranking, tool registration, MCP,
provider response handling, context selection, or agent-loop continuation.

## Scope

- Add immutable provider-neutral Python request, match, summary, and result contracts plus a native
  literal-search service.
- Search one admitted regular file or a bounded recursive directory using CAH-027 traversal and
  CAH-028 strict text rules.
- Return canonical path, 1-based line and Unicode-scalar column, and one bounded matching-line
  excerpt in deterministic order with explicit truncation and skipped-file counts.
- Use native Python only. Do not invoke `rg`, `grep`, `git`, a shell, subprocess, network, provider,
  protocol, transcript, tool registry, or TUI path.

## Locked contract

### Request and match semantics

- `SearchTextRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It
  contains `query`, `path` (default `.`), `max_depth` (default 4, admitted range 1-8), and
  `max_matches` (default 100, admitted range 1-200). Booleans used as integers are rejected.
- `query` is admitted through CAH-026's post-JSON Unicode-scalar/strict-UTF-8 round-trip rule, then
  must be one non-empty line whose UTF-8 encoding is at most 256 bytes. Lone surrogates, NUL,
  carriage return, and newline are rejected with `repository_input_limit` before listing, policy,
  or filesystem work; no Unicode normalization is applied.
- Matching is literal and case-sensitive. It does not interpret regex, glob, Unicode normalization,
  locale, or escape syntax. Occurrences are non-overlapping; after a match, scanning resumes after
  the complete matched query.
- A result match contains canonical workspace-relative POSIX `path`, 1-based `line`, 1-based
  Unicode-scalar `column`, and `excerpt`. Line terminators are excluded from the excerpt.
- Matches are ordered by canonical path UTF-8 bytes, then line, then column. Filesystem traversal
  order cannot change the result.

### Excerpts

- An excerpt is at most 512 UTF-8 bytes and always contains the complete matched query. If the full
  line fits, it is returned exactly without its line terminator.
- For a longer line, reserve the three-byte Unicode ellipsis `…` on each omitted side. After
  reserving the full query and required ellipses, divide remaining bytes equally between the prefix
  and suffix, giving an odd remainder to the suffix. Use the longest UTF-8-boundary-safe suffix
  before and prefix after the match that fit those budgets.
- Each non-overlapping occurrence is a separate match even when occurrences share the same excerpt.
  Content outside the excerpt is never returned or placed in default representations.

### Candidate and result budgets

| Limit | Initial reviewed value | Behavior |
| --- | ---: | --- |
| Query | 256 UTF-8 bytes | Above the limit fails before repository access. |
| Recursive depth | default 4 / hard 8 | Directory search passes the exact request depth to CAH-027 and never examines deeper descendants. |
| Candidate files | 500 | Stop before a 501st admitted file and mark the result truncated. |
| Aggregate candidate content | 2 MiB (2,097,152 bytes) | Stop before reading a file that would cross the budget. |
| One candidate file | 256 KiB (262,144 bytes) | Directory search skips larger files; direct-file search fails. |
| Returned matches | default 100 / hard 200 | Stop at requested count and mark the result truncated when more work remains. |
| One excerpt | 512 UTF-8 bytes | Apply the deterministic excerpt algorithm above. |

- `SearchTextResult` contains an immutable match tuple, `truncated`, one ordered set of
  `limit_reasons` (`matches`, `candidate_files`, `candidate_bytes`, or `listing`),
  `files_examined`, `source_bytes_examined`, and aggregate counts skipped as ignored/unavailable,
  oversized, or non-text. Skipped labels, bytes, and policy reasons are never returned.
- Candidate paths come from exactly one `ListFilesRequest(path=request.path, recursive=true,
  max_depth=request.max_depth, max_items=500)`. Search must pass the admitted value unchanged; it
  may not substitute the default, clamp it, add one, or perform a second walk. Canonical order and
  CAH-027 listing truncation are preserved. A directory search skips invalid UTF-8, NUL-containing,
  oversized, denied, ignored, unavailable, and special files with aggregate counts; a direct-file
  search reports the corresponding CAH-026 fixed error. Direct-file search validates `max_depth`
  for one request contract but does not perform a directory listing.
- A file is admitted, policy-checked, and boundary-resolved immediately before its bounded read.
  Search does not preserve a prior list decision as authorization.
- If adding the next admitted file would cross 2 MiB, it is not partially read and search stops with
  `candidate_bytes`. Item and byte budgets are deterministic safety limits, not token estimates.
- The operation is synchronous and bounded. Later dispatch owns cancellation checks around it; no
  task, event, or protocol cancellation is introduced here.

### Fixed failures

CAH-026's `RepositoryAccessError` table remains authoritative. Invalid query or requested limits use
`repository_input_limit`; direct path, type, text, size, policy, containment, and read failures retain
their exact shared safe code/message. Errors and default representations contain no query, content,
host path, denied label, ignore rule, raw byte, or OS text.

## Reviewability budget

- **Estimated production-code churn:** 400-550 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if regex, fuzzy ranking, indexing,
  tool dispatch, provider serialization, or context selection enters this unit, or if production
  churn is likely to exceed roughly 600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. A valid literal query returns every encountered non-overlapping match in exact canonical
   path/line/column order until a reviewed bound is reached.
2. Each excerpt is at most 512 UTF-8 bytes, contains the full query, uses the exact ellipsis algorithm,
   and never splits a Unicode encoding.
3. Recursive-depth, candidate-file, aggregate-byte, per-file, query, and returned-match bounds
   produce deterministic failures or explicit truncation and aggregate skip counts.
4. Directory search omits ignored, denied, unavailable, non-text, oversized, and unsupported files
   without labels; direct-file search returns the shared fixed safe error.
5. Requests and results are immutable, typed, documented, provider-neutral, and suppress queries and
   excerpts from default representations.
6. Focused tests use only temporary local files and no subprocess, provider, model, or network.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Literal semantics | Search metacharacters, mixed case, and overlapping-looking input | Unit | Exact case-sensitive, non-regex, non-overlapping positions |
| Deterministic order | Create matches in reverse path order and repeated lines | Unit | Canonical path/line/column ordered tuple on repeated runs |
| Excerpt boundary | Place a multibyte match within lines at 511/512/513+ bytes and near each edge | Unit | Exact full or ellipsized excerpt, <=512 bytes, no split character |
| Query/match limits | Test query 255/256/257 bytes and matches 99/100/101 plus 199/200/201 | Unit | Success/truncation at configured bounds and input failure above hard max |
| Recursive depth | Spy on CAH-027 and place matches at depths 1, 4, 8, and 9; omit depth, then request 1, 8, 0, and 9 | Policy integration | Default 4 and admitted 1/8 are passed unchanged in exactly one recursive request; 0/9 fail before listing |
| Candidate budgets | Test 499/500/501 files and 2 MiB below/at/above | Unit | Exact examined counts and ordered limit reasons without partial file read |
| Direct versus tree failure | Use invalid UTF-8, NUL, oversized, ignored, denied, and escaping files | Policy integration | Direct fixed errors; tree skip counts with no skipped label leak |
| Check-before-read | Replace a listed file at a deterministic injected seam | Boundary integration | Search rechecks and omits/fails safely rather than reading replacement |

## Validation

- Add focused literal-search tests using temporary workspaces and the real list/read/policy seams.
- Assert positions using Unicode scalar counts, exact excerpts by UTF-8 byte length, immutable values,
  deterministic order, summary counters, and fixed error hygiene.
- Assert the exact `ListFilesRequest` snapshot for default depth 4 and boundaries 1 and 8, one list
  call per directory search, and zero list/filesystem calls for depths 0 and 9 or a lone-surrogate
  query.
- Exercise every numeric bound below, at, and above without timing assumptions or huge unbounded
  fixtures.
- Keep protocol, transcript, provider, tool registry, and TUI unchanged; the canonical gate supplies
  nearest parity evidence.
- Run focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update tool-system, context-engineering, safety model, glossary, story and lesson indexes, E3
backlog sequence, and the Markdown lesson's compact architecture diagram. Contrast literal native
search with subprocess, regex, indexed, and semantic search. Do not add or revise a presentation.

## Exclusions

- Regex, glob, fuzzy, semantic, embedding, AST/symbol, Git-index, binary, archive, generated-file, or
  incremental indexed search.
- Tool registration, JSON Schema, MCP, provider tool calls, dispatch, loop continuation, protocol
  events, transcript fields, and TUI rendering.
- Context ranking or package construction, instruction interpretation, token estimation, file writes,
  subprocesses, network access, and policy override.
- Descriptor-relative reads, filesystem watching, parallel search, multiple roots, or locale-specific
  matching.

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Query, depth, candidate-file, aggregate-byte, per-file, match, and excerpt limits pass
   below/at/above evidence.
3. Literal positions, canonical ordering, safe excerpts, policy omission, direct fixed errors, and
   check-before-read behavior are proved without leaks.
4. Public request and result contracts are immutable, typed, documented, and reject extra fields.
5. Focused tests and the canonical offline `./scripts/check` pass with no model, subprocess, or
   network.
6. Existing protocol, transcript, provider, tool, and TUI boundaries remain unchanged and pass their
   existing tests.
7. The Markdown lesson uses exact implementation and failure-test excerpts after code exists and
   includes no presentation work.
8. Story, lesson, conceptual docs, indexes, backlog, planning note, and statuses agree.
9. Delivered production-source churn is recorded and remains near the planned range or is split
   before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- A native literal-search module and local fixtures prove positions, excerpts, and budget behavior.
- Integration tests demonstrate that search reuses real canonical traversal, policy, and text
  admission rather than shelling out.
- The lesson positions search as a supporting evidence locator beneath later tool dispatch and
  context selection; its primary teach-back question is: which limits bound work before a search
  result ever reaches an LLM?

## Deferred work

- CAH-030 uses bounded search excerpts as optional context candidates with explicit inclusion
  reasons.
- E4 later exposes search through a validated tool registry and owns dispatch/cancellation evidence.
- Later needs may justify regex, symbols, or an index only after deterministic fixture evaluations
  show literal search is insufficient.
