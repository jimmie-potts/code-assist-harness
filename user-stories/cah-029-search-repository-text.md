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

- `RepositoryTextSearcher(policy: RepositoryReadPolicy, metadata_reader:
  RepositoryMetadataReader, text_reader: RepositoryTextReader)` is the exact service. Construction
  requires `metadata_reader.policy is policy is text_reader.policy` before publication and exposes
  those exact objects through read-only `policy`, `metadata_reader`, and `text_reader` identities plus
  `search_text(request: SearchTextRequest) -> SearchTextResult`. Runtime passes the session's one
  CAH-026 policy and the already-composed CAH-027/028 services; search never rebuilds a workspace,
  creates another ignore policy, or silently accepts equal-but-distinct policy objects.

- `SearchTextRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It
  contains required `query` with no default, `path` (default `.`), `max_depth` (default 4, admitted range 1-8), and
  `max_matches` (default 100, admitted range 1-200). Its path inherits CAH-024/026's inclusive
  4,095-byte, 256-normalized-component, and 255-byte-name lexical budget. Booleans used as integers
  are rejected.
- `query` is admitted through CAH-026's post-JSON Unicode-scalar/strict-UTF-8 round-trip rule, then
  must be one non-empty line whose UTF-8 encoding is at most 256 bytes. “One line” rejects the
  complete boundary repertoire recognized by Python `str.splitlines()`: LF (`U+000A`), vertical tab
  (`U+000B`), form feed (`U+000C`), CR (`U+000D`, including CRLF), file/group/record separators
  (`U+001C` through `U+001E`), next line (`U+0085`), line separator (`U+2028`), and paragraph
  separator (`U+2029`). The implementation checks for separators directly rather than accepting a
  trailing boundary because `splitlines()` returns only one element. Lone surrogates, NUL, and every
  listed separator are rejected with `repository_input_limit` before listing, policy, or filesystem
  work; no Unicode normalization is applied.
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
| Recursive listing entries | CAH-027 hard 500 | Inspect only files in the one bounded listing; propagate listing truncation when another admitted entry exists. |
| Aggregate candidate content | 2 MiB (2,097,152 charged bytes) | Charge at most the remaining budget; a bounded one-byte overflow sentinel may be read only to prove overflow. |
| One candidate file | 256 KiB (262,144 bytes) | Directory search skips larger files; direct-file search fails. |
| Returned matches | default 100 / hard 200 | Return at most the requested count; mark truncation only after observing the first additional occurrence, then stop both scans. |
| One excerpt | 512 UTF-8 bytes | Apply the deterministic excerpt algorithm above. |

- `SearchTextResult` contains the content-suppressed `canonical_request_scope`, an immutable match
  tuple, `truncated`, one immutable tuple of `limit_reasons`, `files_examined`,
  `source_bytes_examined`, and aggregate counts skipped as
  ignored/unavailable, oversized, or non-text. The scope is the canonical workspace-relative path
  used by final native admission: copy `ListFilesResult.canonical_request_scope` for a directory
  search and the final canonical read path for a direct-file search. It remains present for a
  no-match success and is never recomputed from the supplied alias after return. Skipped labels,
  bytes, and policy reasons are never returned.
- `limit_reasons` contains each observed reason at most once in the exact canonical order
  `matches`, `candidate_bytes`, `listing`, independent of detection order. Unknown or duplicate
  members are invalid, and `truncated` is exactly `bool(limit_reasons)`. Implementations collect
  private observation flags and project through this closed order; they do not expose a set whose
  iteration order can drift.
- Reaching `max_matches` is not itself truncation evidence. Continue the ordered occurrence scan
  until it is exhausted or yields the first additional occurrence. Do not construct or append a
  match for that extra occurrence: set the private `matches` observation and immediately break both
  the current file's occurrence loop and the outer candidate loop. The returned tuple therefore has
  at most `max_matches` members, observes exactly one overflow occurrence, and never reads a later
  candidate after that evidence. Exactly `max_matches` occurrences with no extra occurrence is an
  untruncated success.
- Candidate paths come from exactly one `ListFilesRequest(path=request.path, recursive=true,
  max_depth=request.max_depth, max_items=500)`. Search must pass the admitted value unchanged; it
  may not substitute the default, clamp it, add one, or perform a second walk. The 500-item bound
  counts both files and directories, so it yields at most 500 candidate files without a second
  candidate-file limiter. Canonical order is preserved, and `ListFilesResult.truncated` adds the
  `listing` reason. A directory search skips invalid UTF-8, NUL-containing,
  oversized, denied, ignored, unavailable, and special files with aggregate counts; a direct-file
  search reports the corresponding CAH-026 fixed error. Direct-file search validates `max_depth`
  for one request contract but does not perform a directory listing.
- Search never opens or decodes repository content itself. For each candidate it increments
  `files_examined`, computes `remaining = 2_097_152 - source_bytes_examined`, and calls the exact
  CAH-028 producer once as
  `text_reader.read_text_candidate(path, max_source_bytes=min(remaining, 262_144))`. This count is
  intentionally candidate-read attempts, including attempts rejected during fresh final admission;
  it is therefore an honest upper bound on opens and sentinel reads. A prior list decision is never
  authorization, and no CAH-026 policy/open/sentinel/text logic is duplicated in the searcher.
- Search charges exactly `candidate.source_bytes_examined` even when the candidate is non-text or
  has no match. An overflow candidate is never decoded or matched. When `remaining <= 262_144`, it
  records `candidate_bytes` and stops; otherwise the per-file ceiling is the sole active limit and
  produces the existing oversized skip in directory mode or fixed source-too-large failure in
  direct-file mode. Thus an exact 262,144-byte tie has deterministic aggregate-limit precedence.
  A non-text candidate increments the non-text skip in directory mode or produces the fixed non-text
  failure in direct-file mode. Only an admitted `candidate.text` is scanned, and its execution-time
  `candidate.path` supplies direct-mode scope and every match path.
- `source_bytes_examined` never exceeds 2,097,152. Physical bytes returned by the shared reader are
  at most `source_bytes_examined + files_examined`. At most one sentinel byte per attempted candidate
  can be returned, with at most 500 attempts from CAH-027 (and only one in direct-file mode).
  Therefore charged content is at most 2,097,152 bytes and physical reads are at most 2,097,652
  bytes; path
  replacement after a small pre-open snapshot cannot evade either bound. Ignored, denied,
  unavailable, special, and already-known oversized candidates rejected before content open are
  skip-counted but not charged. Item and byte budgets are deterministic safety limits, not token
  estimates.
- The operation is synchronous and bounded. Later dispatch owns cancellation checks around it; no
  task, event, or protocol cancellation is introduced here.

### Fixed failures

CAH-026's `RepositoryAccessError` table remains authoritative. Invalid query or requested limits use
`repository_input_limit`; direct path, type, text, size, policy, containment, and read failures retain
their exact shared safe code/message, including `invalid_repository_path` for an over-bound path
before query execution, listing, or filesystem work. Errors and default representations contain no query, content,
host path, denied label, ignore rule, raw byte, or OS text.

## Reviewability budget

- **Estimated production-code churn:** 400-550 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: CAH-027 candidate listing plus CAH-028 text
  admission -> bounded literal matches and canonical `SearchTextResult` -> CAH-030 context and
  CAH-031 registry consumers.
- **Split rule:** stop and refine another story before review if regex, fuzzy ranking, indexing,
  tool dispatch, provider serialization, or context selection enters this unit, or if production
  churn is likely to exceed roughly 600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One `RepositoryTextSearcher` retains the exact shared policy/reader identities and consumes
   CAH-028's real `read_text_candidate` producer without reconstructing its read path. Query admission
   accepts one non-empty separator-free Unicode-scalar string of at most 256 UTF-8
   bytes and rejects NUL plus every Python `str.splitlines()` boundary before repository access.
2. A valid literal query returns every encountered non-overlapping match in exact canonical
   path/line/column order, up to `max_matches`; only the first additional occurrence proves match
   truncation, is not returned, and stops both occurrence and candidate scans immediately.
3. Each excerpt is at most 512 UTF-8 bytes, contains the full query, uses the exact ellipsis algorithm,
   and never splits a Unicode encoding.
4. Recursive-depth, inherited listing-entry, aggregate-byte, per-file, query, and returned-match
   bounds produce deterministic failures or explicit truncation and aggregate skip counts; every
   opened source is charged even when it is non-text or has no match.
5. Directory search omits ignored, denied, unavailable, non-text, oversized, and unsupported files
   without labels; direct-file search returns the shared fixed safe error.
6. Requests and results are immutable, typed, documented, provider-neutral, preserve execution-time
   canonical request scope, use the exact canonical reason order with
   `truncated == bool(limit_reasons)`, and suppress queries, excerpts, and that local scope from
   default representations.
7. Focused tests use only temporary local files and no subprocess, provider, model, or network.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Literal semantics | Search metacharacters, mixed case, and overlapping-looking input | Unit | Exact case-sensitive, non-regex, non-overlapping positions |
| Complete one-line grammar | Parameterize LF, VT, FF, CR, CRLF, FS, GS, RS, NEL, line separator, and paragraph separator in leading, middle, and trailing positions; probe nearby tab, escape, and unit-separator controls plus ordinary multibyte text | Request boundary | Every splitlines-recognized separator fails with `repository_input_limit` and zero downstream calls; representative non-separators remain eligible subject to the other input rules |
| Shared path request budget | Parameterize 4,094/4,095/4,096 total UTF-8 bytes, 254/255/256 name bytes, and 255/256/257 normalized components independently of query bounds | Request/policy boundary | Endpoints pass lexical admission; above-bound paths return `invalid_repository_path` before list/read/policy work, while invalid query-only controls retain `repository_input_limit` |
| Deterministic order | Create matches in reverse path order and repeated lines | Unit | Canonical path/line/column ordered tuple on repeated runs |
| Excerpt boundary | Place a multibyte match within lines at 511/512/513+ bytes and near each edge | Unit | Exact full or ellipsized excerpt, <=512 bytes, no split character |
| Query/match limits | Test query 255/256/257 bytes; arrange 99/100/101 occurrences for the default cap and 199/200/201 for cap 200, each wholly within one file and split across consecutive files; spy on occurrence and candidate iteration | Unit | 99/100 and 199/200 are complete successes; 101 and 201 return exactly 100/200, observe but do not return exactly the first extra occurrence, add only `matches`, and immediately stop both inner and outer scans; query input above its hard bound fails before access |
| Recursive depth | Spy on CAH-027 and place matches at depths 1, 4, 8, and 9; omit depth, then request 1, 8, 0, and 9 | Policy integration | Default 4 and admitted 1/8 are passed unchanged in exactly one recursive request; 0/9 fail before listing |
| Candidate budgets | Test flat and mixed trees with 499/500/501 admitted listing entries; use eight 256-KiB invalid-UTF-8, NUL, or no-match sources at 2 MiB; exercise remaining aggregate at 262,143/262,144/262,145 bytes; then replace a small allowed candidate with a larger allowed source near the limit; spy on every candidate call | Unit/integration | Every candidate's charged content bytes count even for skipped/nonmatching text; remaining-cap overflow reads only one sentinel, records `candidate_bytes` at and below the tie, uses per-file oversized behavior above it, and performs no decode/match; `source_bytes_examined <= 2,097,152`, physical bytes read `<= source_bytes_examined + files_examined`, and at most 500 sentinel bytes are possible |
| Real candidate producer | Drive text, overflow, and non-text `TextSourceCandidate` values through direct and directory modes while spying on the shared reader | Service integration | Exactly one `read_text_candidate(path, min(remaining, 262_144))` call per attempt; no search-owned admission/open/decode path; canonical scope and matches use `candidate.path` |
| Canonical limit reasons | Produce none, each singleton, `matches+listing`, and `candidate_bytes+listing` in reversed observation orders; inject duplicate/unknown/inconsistent results | Result boundary | Exact tuple order is always `matches`, `candidate_bytes`, `listing`; invalid members or `truncated != bool(limit_reasons)` fail validation |
| Direct versus tree failure | Use invalid UTF-8, NUL, oversized, ignored, denied, and escaping files | Policy integration | Direct fixed errors; tree skip counts with no skipped label leak |
| Check-before-read | Replace a listed file at a deterministic injected seam | Boundary integration | Search rechecks and omits/fails safely rather than reading replacement |
| Empty-result request provenance | Retarget allowed `alias -> A` to allowed `B` at the native pre-list/pre-read seam and run an empty/no-match search; then separately retarget only after return | Boundary integration | Directory scope is copied from CAH-027's final-admission listing and direct-file scope from CAH-028's final read: pre-access retargets inspect/report `B`, while post-return retargets preserve `A`; no result combines stale provenance with replacement work |

## Validation

- Add focused literal-search tests using temporary workspaces and the real list/read/policy seams.
- Assert positions using Unicode scalar counts, exact excerpts by UTF-8 byte length, immutable values,
  deterministic order, canonical reason tuples, summary counters, and fixed error hygiene.
- Parameterize the complete `str.splitlines()` boundary repertoire in leading, middle, and trailing
  positions. Include Unicode NEL/line/paragraph separators and C0 boundaries around VT/FF and
  FS/GS/RS, with tab, escape, and unit separator as non-boundary sentinels; assert rejection occurs
  before any list, policy, or filesystem call.
- Assert the exact `ListFilesRequest` snapshot for default depth 4 and boundaries 1 and 8, one list
  call per directory search, and zero list/filesystem calls for depths 0 and 9 or a lone-surrogate
  query.
- Assert no-match directory and direct-file successes preserve their final native canonical request
  scope. Cover allowed `A -> B` retarget immediately before listing/read and a separate post-return
  retarget, without exposing the scope in representations.
- Exercise every numeric bound below, at, and above without timing assumptions or huge unbounded
  fixtures. Prove opened invalid-text, NUL, and no-match sources consume the aggregate byte budget.
  At an injected pre-open seam, replace a small allowed source with a larger allowed source and prove
  the remaining-budget read plus one sentinel causes no decode/match. Use bounded-reader spies to
  prove the charged counter never exceeds 2,097,152, physical reads never exceed charged bytes plus
  one sentinel per opened candidate, and no more than 500 sentinels are possible.
- Exercise default cap 100 and hard cap 200 with same-file and cross-file 99/100/101 and 199/200/201
  occurrence layouts. Spy on occurrence and candidate iteration to prove that only the first extra
  occurrence is observed, it is never returned, and no later occurrence or candidate is visited.
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

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Keep the supplied search alias distinct from final native `canonical_request_scope`, listed candidate labels, each file's final canonical read path, match path/line/column provenance, skip aggregates, charged content bytes, and uncharged overflow-sentinel bytes. Cache identity is N/A; only canonical paths and bounded excerpts are model-visible. |
| End-to-end contract | Closed query/request validation -> one CAH-027 listing or direct candidate -> exact CAH-028 `read_text_candidate` call with active remaining cap -> literal occurrence/excerpt projection of admitted text -> canonical result -> CAH-030 search evidence and CAH-031 registry consumers. CAH-037 owns later evaluation wiring. |
| Failure and atomicity | Invalid queries/limits execute zero repository work; tree mode safely skip-counts bad candidates while direct mode returns fixed errors; an aggregate sentinel is never decoded/matched, and the first extra occurrence is not returned and stops both scans. Cancellation/deadline/rollback are N/A inside this synchronous bounded search. |
| Reachable boundaries | Real list/read seams exercise query 255/256/257 bytes; depths 1/4/8 and above; 499/500/501 listing entries; aggregate 2-MiB and 262,143/262,144/262,145 remaining-byte ties; 99/100/101 and 199/200/201 matches; and 511/512/513-byte multibyte excerpts. |
| Closed grammar and cardinality | Query is one non-empty, case-sensitive, separator-free Unicode-scalar string with the complete `splitlines()` boundary repertoire rejected; matches are non-overlapping and ordered path/line/column. `limit_reasons` is duplicate-free in exact `matches`, `candidate_bytes`, `listing` order and at most 200 matches are returned. |
| Artifact parity | Story, lesson, diagram, tool/context/safety docs, and tests agree on validation -> one candidate source -> final read admission -> charged bounded read/sentinel decision -> strict text -> ordered occurrences -> first-extra stop -> canonical reasons/result, including direct-versus-tree failures. |
| Independent lenses | Security/identity review covers request/result provenance, shared-reader policy rechecks, skipped labels, and sentinel accounting; real producer/consumer review drives CAH-028 candidate states through direct and tree modes and proves no duplicate open path; limits/scheduler review covers every reachable per-snapshot cap and records provider/protocol changes and in-operation scheduling as N/A. |

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Query scalar, NUL, complete line-separator grammar, byte, depth, inherited listing-entry,
   aggregate-byte, per-file, match, and excerpt boundaries pass deterministic evidence before
   downstream access.
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
