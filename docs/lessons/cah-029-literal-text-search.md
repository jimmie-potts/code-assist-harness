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
- bound search by recursive depth, files, source bytes, matches, and excerpt bytes;
- explain direct-file failure versus directory-search omission; and
- preserve canonical provenance and deterministic result order.

## Why this unit matters

Search connects a question to an unknown file, but a shell command would introduce executable,
environment, timeout, parsing, and policy surfaces. A native literal operation stays behind the same
read boundary as listing and reading.

## Junior engineer foundation

Literal `a.*b` means the four characters `a`, `.`, `*`, `b`; it is not a regular expression. Match
columns count Unicode scalars, while budgets count UTF-8 bytes. A common misconception is that
limiting matches bounds the scan. Candidate-file and aggregate-byte limits bound work before a match
is found.

Another common misconception is that only `\n` and `\r` split lines. Python also recognizes vertical
tab, form feed, three information separators, NEL, and Unicode line/paragraph separators. Testing
`len(query.splitlines()) == 1` is insufficient because a trailing separator still yields one element;
the request boundary rejects every recognized separator directly.

## Key concepts

- **Canonical order:** path bytes, then 1-based line and column.
- **Safe excerpt:** at most 512 UTF-8 bytes, always containing the complete match.
- **Directory omission:** unsafe candidates become aggregate counts, not leaked labels.
- **Explicit stop reason:** match, file, byte, or listing bounds explain truncation.
- **Closed one-line grammar:** no LF, VT, FF, CR/CRLF, FS, GS, RS, NEL, Unicode line separator, or
  Unicode paragraph separator is admitted in a query.

## Architecture and design

```text
TUI / provider tool call (future)
              |
        Python harness
              |
 CAH-027 candidates + CAH-028 text + CAH-026 policy
              |
       [CAH-029 search_text] ----> canonical matches/excerpts
                                           |
                                  CAH-030 context (later)

Agent-loop dispatch, protocol, and transcript/evidence are unchanged here.
```

`SearchTextRequest.max_depth` defaults to 4 and admits only 1 through 8. A directory search passes
that exact value once to CAH-027 with `recursive=true` and `max_items=500`; it never clamps, offsets,
or substitutes the value. The operation examines at most 500 files and 2 MiB of candidate content,
returns at most 200 matches, and never returns more than 512 bytes per excerpt. These are
reproducible work/output limits, not token estimates.

## Practical walkthrough

1. Apply CAH-026 scalar-text admission, then validate one non-empty, at-most-256-byte query with none
   of Python `str.splitlines()`'s recognized separators, and `max_depth` in the closed range 1-8.
2. Make exactly one CAH-027 recursive request with default 4 or the exact admitted depth, and
   re-admit each canonical candidate before read.
3. Apply CAH-028 text/size rules and search non-overlapping occurrences.
4. Build UTF-8-safe excerpts and sort by path, line, and column.
5. Return explicit limit reasons and aggregate skip counts.

## Implementation code samples

Planned pseudocode only:

```text
listing = list_files(path=request.path, recursive=True,
                     max_depth=request.max_depth, max_items=500)
for path in listing.files:
    text = bounded_strict_text(path)
    for line, column in literal_matches(text, request.query):
        matches.append(bounded_excerpt(path, line, column))
        stop_when_budget_reached()
return ordered_matches_and_summary(matches)
```

Candidates inherit policy, matching has no regex interpretation, excerpt construction owns the
512-byte output bound, and the summary makes every early stop visible.

## Failure scenarios to study

- Regex metacharacters are matched literally rather than executed.
- LF, VT, FF, CR/CRLF, FS/GS/RS, NEL, and Unicode line/paragraph separators fail even at the end of a
  query; nearby non-separator controls prove the check is not an overbroad control-character ban.
- An invalid-text direct file fails; the same file in directory search increments a safe count.
- The 501st candidate or first file beyond 2 MiB is not partially read.
- A long multibyte line is ellipsized without splitting the match or a UTF-8 sequence.
- Depth 0 or 9 and a lone-surrogate query fail before CAH-027 or filesystem work; omitted depth is
  observed as exactly 4 in the one listing request.

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
5. Test each candidate and output limit below, at, and above.
6. Teach back: which budgets limit work before any result reaches an LLM?

## Key takeaways

- The harness owns literal search semantics and budgets.
- Query admission uses a complete, explicit one-line grammar rather than an LF/CR shortcut.
- Policy reuse, fresh admission, canonical order, and explicit truncation are the invariants.
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
