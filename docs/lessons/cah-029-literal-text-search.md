# CAH-029 lesson: Literal repository search

- **Unit:** CAH-029
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Search repository text literally](../../user-stories/cah-029-search-repository-text.md)
- **Learning emphasis:** Supporting implementation unit
- **Review focus:** Deterministic literal matching, bounded excerpts, and attributable result order
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Tool system](../tool-system.md),
  [Context engineering](../context-engineering.md), and [Safety model](../safety-model.md)

> This is a planned supporting lesson. Literal search has not yet been implemented.

## Quick summary

CAH-029 locates exact text in admitted files with deterministic positions, excerpts, and work
budgets. It favors one teachable retrieval primitive over regex, subprocess, indexing, or semantic
search complexity.

## Learning objectives

After completing this unit, you should be able to:

- define literal, case-sensitive, non-overlapping matching;
- define “one line” using Python's complete `str.splitlines()` separator repertoire;
- bound search by inherited listing entries, recursive depth, source bytes, matches, and excerpt bytes;
- explain direct-file failure versus directory-search omission; and
- preserve canonical provenance and deterministic result order.

## Why this unit matters

Search connects a question to an unknown file, but a shell command would introduce executable,
environment, timeout, parsing, and policy surfaces. A native literal operation stays behind the same
read boundary as listing and reading.

## Junior engineer foundation

Literal `a.*b` means the four characters `a`, `.`, `*`, `b`; it is not a regular expression. Match
columns count Unicode scalars, while budgets count UTF-8 bytes. A common misconception is that
limiting matches bounds the scan. CAH-027's total-entry listing cap and CAH-029's aggregate-byte
limit bound work before a match is found.

Another common misconception is that only `\n` and `\r` split lines. Python also recognizes vertical
tab, form feed, three information separators, NEL, and Unicode line/paragraph separators. Testing
`len(query.splitlines()) == 1` is insufficient because a trailing separator still yields one element;
the request boundary rejects every recognized separator directly.

## Key concepts

- **Canonical order:** path bytes, then 1-based line and column.
- **Safe excerpt:** at most 512 UTF-8 bytes, always containing the complete match.
- **Directory omission:** unsafe candidates become aggregate counts, not leaked labels.
- **Explicit stop reason:** match, byte, or inherited listing bounds explain truncation.
- **Execution-time request scope:** no-match results still retain the canonical file or directory
  actually searched, not a supplied alias that can be retargeted later.
- **Closed one-line grammar:** no LF, VT, FF, CR/CRLF, FS, GS, RS, NEL, Unicode line separator, or
  Unicode paragraph separator is admitted in a query.
- **Shared path budget:** the search root inherits CAH-024/026's 4,095-byte,
  256-normalized-component, and 255-byte-name ceilings independently of the 256-byte query limit.
- **Shared candidate producer:** CAH-029 never opens or decodes a file; it supplies the active
  remaining cap to CAH-028's exact `read_text_candidate` seam.

## Architecture and design

```text
TUI / provider tool call (future)
              |
        Python harness
              |
 CAH-027 candidates ----> [CAH-029 search_text] ----> canonical matches/excerpts
                               |
                 CAH-028 read_text_candidate
                               |
                       CAH-026 policy -> bytes
                                           |
                                  CAH-030 context (later)

Agent-loop dispatch, protocol, and transcript/evidence are unchanged here.
```

Runtime creates
`RepositoryTextSearcher(policy, metadata_reader, text_reader)` only when
`metadata_reader.policy is policy is text_reader.policy`. It retains all three as exact read-only
`policy`, `metadata_reader`, and `text_reader` identities. Its exact
`search_text(request: SearchTextRequest) -> SearchTextResult` method therefore reuses one session
workspace/policy identity across listing, bounded reads, and direct admission; equal-but-distinct
policy objects are not silently combined.

`SearchTextRequest.query` is required and has no default. `max_depth` defaults to 4 and admits only 1
through 8. A directory search passes
that exact value once to CAH-027 with `recursive=true` and `max_items=500`; it never clamps, offsets,
or substitutes the value. CAH-027 counts both files and directories, so one result contains at most
500 total entries and therefore at most 500 candidate files. If another admitted entry exists,
search propagates the `listing` reason rather than claiming a separate file limit it cannot observe.
The operation charges at most 2 MiB of candidate content, returns at most 200 matches, and never
returns more than 512 bytes per excerpt. These are reproducible work/output limits, not token
estimates. A directory result copies the one listing's canonical request scope; a direct-file result
copies the final read's canonical path. That local provenance remains available even with zero
matches and is suppressed from ordinary representations. Every candidate byte actually read under
the per-file/remaining-aggregate cap is charged even when decode fails, NUL causes a tree skip, or no
match exists. The searcher calls CAH-028's real `read_text_candidate` producer exactly once per
candidate with `min(remaining, 262_144)`; it never copies final admission, open, decode, or sentinel
logic. `files_examined` counts those attempts, including a fresh-admission rejection, so it remains a
safe upper bound on physical opens. The producer may observe one additional overflow-sentinel byte per attempted candidate,
but that byte is never charged, decoded, or matched. Thus charged content is at most 2,097,152 bytes,
while physical reads are at most the charged count plus `files_examined`: no more than 2,097,652
bytes with CAH-027's 500-entry ceiling. An allowed pre-open replacement cannot evade either bound.
Reaching the match cap alone does not prove truncation. Search must observe the first extra ordered
occurrence, omit it from the result, and immediately break both the occurrence and candidate loops.
Limit
reasons are projected once in the fixed order `matches`, `candidate_bytes`, `listing`, and
`truncated` is true exactly when that tuple is non-empty.

## Practical walkthrough

1. Apply the shared path budget and CAH-026 scalar-text admission, then validate one non-empty, at-most-256-byte query with none
   of Python `str.splitlines()`'s recognized separators, and `max_depth` in the closed range 1-8.
2. For a directory, make exactly one CAH-027 recursive request with default 4 or the exact admitted
   depth. For a direct file, admit that file without listing.
3. Increment the attempt count and call CAH-028's shared candidate producer with
   `min(remaining aggregate bytes, 256 KiB)`. Charge its reported content bytes even when skipped or
   unmatched; classify its overflow as aggregate or per-file without decoding a sentinel.
4. Build UTF-8-safe excerpts in canonical order until the requested count is returned. If the next
   occurrence exists, observe but do not return it, mark match truncation, and stop both scans.
5. Preserve the final admitted target as `canonical_request_scope`, even when there are no matches,
   then canonicalize observed reasons and return aggregate skip counts.

## Implementation code samples

Planned pseudocode only:

```python
observed = {"matches": False, "candidate_bytes": False, "listing": False}
source_bytes_examined = 0
physical_bytes_read = 0
files_examined = 0
matches = []
summary = empty_skip_summary()
stop_candidates = False
direct_mode = not metadata_reader.stat_path(request.path).is_directory
if not direct_mode:
    listing = list_files(path=request.path, recursive=True,
                         max_depth=request.max_depth, max_items=500)
    candidates = (entry for entry in listing.entries if entry.kind == "file")
    canonical_scope = listing.canonical_request_scope
    observed["listing"] = listing.truncated
else:
    candidates = (request.path,)
    canonical_scope = None  # copy the final direct-read path below

for candidate in candidates:
    remaining = 2_MiB - source_bytes_examined
    active_cap = min(remaining, 256_KiB)
    files_examined += 1
    try:
        source = text_reader.read_text_candidate(candidate, active_cap)
    except RepositoryAccessError as error:
        handle_direct_error_or_tree_skip(error, direct_mode, summary)
        continue
    source_bytes_examined += source.source_bytes_examined
    physical_bytes_read += source.source_bytes_examined + int(source.overflowed)
    if source.overflowed and remaining <= 256_KiB:
        observed["candidate_bytes"] = True
        break  # aggregate wins the exact 256-KiB tie; no decode or match
    if source.overflowed:
        handle_direct_size_error_or_tree_skip(direct_mode, summary)
        continue
    if source.non_text:
        handle_direct_text_error_or_tree_skip(direct_mode, summary)
        continue
    text = require_type(source.text, str)
    if canonical_scope is None:
        canonical_scope = source.path
    for line, column in literal_matches(text, request.query):
        if len(matches) == request.max_matches:
            observed["matches"] = True  # first extra occurrence is evidence only
            stop_candidates = True
            break
        matches.append(bounded_excerpt(source.path, line, column))
    if stop_candidates:
        break

assert source_bytes_examined <= 2_MiB
assert physical_bytes_read <= source_bytes_examined + files_examined

reasons = tuple(
    reason for reason in ("matches", "candidate_bytes", "listing")
    if observed[reason]
)
return SearchTextResult(
    canonical_request_scope=canonical_scope,
    matches=ordered_matches(matches),
    truncated=bool(reasons),
    limit_reasons=reasons,
    **summary,
)
```

Candidates inherit policy through the real CAH-028 producer, matching has no regex interpretation,
excerpt construction owns the 512-byte output bound, and the summary makes every early stop visible.
The pseudocode shows both directory and direct-file provenance and their exact failure branch; no
second search-owned reader can drift from CAH-028's sentinel or strict-text semantics.

## Failure scenarios to study

- Regex metacharacters are matched literally rather than executed.
- LF, VT, FF, CR/CRLF, FS/GS/RS, NEL, and Unicode line/paragraph separators fail even at the end of a
  query; nearby non-separator controls prove the check is not an overbroad control-character ban.
- An invalid-text direct file fails; the same file in directory search increments a safe count.
- A 501st admitted listing entry is represented by `listing`; after the charged 2-MiB budget is
  exhausted, at most one sentinel byte from the next opened candidate is physically read, and it is
  neither charged nor decoded.
- Eight opened 256-KiB sources spend the complete 2-MiB budget even when they are invalid text,
  contain NUL, or have no match. Near the limit, a small allowed candidate replaced with a larger
  allowed source reads only the remainder plus one sentinel and performs no decode or match. Reader
  spies prove charged bytes stay at or below 2,097,152 and physical reads stay at or below charged
  bytes plus one sentinel per opened candidate (at most 500 sentinels).
- With exactly 256 KiB of aggregate budget remaining, the sentinel observes both ceilings at once;
  `candidate_bytes` wins deterministically. At 256 KiB plus one, per-file oversized behavior wins.
- Multiple limits may be observed in a different runtime order, but the result always emits
  `matches`, `candidate_bytes`, `listing`; duplicate/unknown reasons or an inconsistent `truncated`
  flag are invalid results.
- Same-file and cross-file layouts with 99/100/101 or 199/200/201 occurrences prove that exactly the
  cap is not truncated, while the first extra occurrence is observed but omitted and stops both
  scans before any later occurrence or candidate.
- A long multibyte line is ellipsized without splitting the match or a UTF-8 sequence.
- Depth 0 or 9 and a lone-surrogate query fail before CAH-027 or filesystem work; omitted depth is
  observed as exactly 4 in the one listing request.
- A no-match search through `alias -> A` retains `A` after the alias is retargeted to `B`; a
  direct-file search takes the same provenance from its final read admission.
- If the allowed alias retarget happens before native listing/read admission, search examines and
  reports `B`; if it happens after return, the already captured `A` remains stable.

## Production expansion

### Example enterprise scenario

Large monorepos may need regex, symbol search, ranking, or a remote index. That can improve recall and
latency but adds query languages, stale indexes, services, and new denial-of-service bounds.

### Typical production capabilities and tools

- [ripgrep](https://github.com/BurntSushi/ripgrep) provides fast regex and ignore-aware search, but a
  subprocess and broad options require separate policy and supervision.
- [Git `grep`](https://git-scm.com/docs/git-grep) searches tracked repository data efficiently, while
  tying semantics to Git state and an executable.
- [Elasticsearch search APIs](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
  support distributed indexing and ranking, adding infrastructure and freshness management.
- [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) enables syntax-aware queries, adding
  grammars, parser maintenance, and language-specific behavior.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | Literal UTF-8 search in one workspace | Regex, symbols, ranking, and many repositories |
| Reliability | Fresh bounded scan | Index freshness, shard recovery, and query controls |
| Operations | Local fixtures | Indexers, capacity, alerts, and schema evolution |
| Cost | Predictable CPU and small code | Services, storage, parser/query complexity |

### Trade-offs and graduation signals

Literal search has lower recall but a tiny attack and review surface. Add richer retrieval only when
known-file evaluations show a measurable miss rate that cannot be fixed by better literal queries.

## Practical exercises

1. Compare literal results for `a.*b`, `A`, and `a`.
2. Build a table of every Python `str.splitlines()` separator and explain why a trailing-separator
   test must inspect the input rather than only the number of split results.
3. Calculate line/column versus UTF-8 byte positions for a multibyte string.
4. Snapshot the CAH-027 request for omitted depth and explicit depths 1 and 8; prove 0 and 9 execute
   no listing.
5. Test flat and mixed 499/500/501-entry listings plus each search-owned byte/output limit below, at,
   and above.
6. Fill the 2-MiB budget with invalid-text and no-match sources. Near the limit, replace a small
   allowed source with a larger allowed source and prove only the remainder plus one sentinel is
   read. Add a reader spy and prove `physical <= charged + opened candidates <= 2,097,652`. Reverse
   the detection order of two reasons and compare the identical result tuple.
7. Arrange 99/100/101 and 199/200/201 occurrences first in one file, then across two files. Prove the
   first extra occurrence is the only overflow evidence visited and never appears in the result.
8. Teach back: which budgets limit work before any result reaches an LLM?
9. Retarget a no-match search alias after return and explain why its result must not acquire the
   replacement directory's instruction scope.
10. Delete the shared candidate call in a mutation and explain which admission, byte-accounting, and
    non-text tests must fail before review.

## Key takeaways

- The harness owns literal search semantics and budgets.
- Query admission uses a complete, explicit one-line grammar rather than an LF/CR shortcut.
- Policy reuse, fresh admission, canonical order, and explicit truncation are the invariants.
- A real shared producer—not parallel prose—keeps direct read and search admission consistent.
- No-match success still records which canonical target was searched at execution time.
- Richer search improves recall but adds query, index, and operational complexity.

## Glossary

- **Literal search:** Exact character matching without regex interpretation.
- **Non-overlapping:** Scanning resumes after the complete previous match.
- **Excerpt:** Bounded matching-line context returned with provenance.
- **Line boundary:** Any separator that Python `str.splitlines()` recognizes, including Unicode and
  selected C0/C1 controls.

## Further reading

- [CAH-029 delivery contract](../../user-stories/cah-029-search-repository-text.md)
- [ripgrep guide](https://github.com/BurntSushi/ripgrep/blob/master/GUIDE.md)
- [Git `grep`](https://git-scm.com/docs/git-grep)
