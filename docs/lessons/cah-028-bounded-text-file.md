# CAH-028 lesson: Bounded text-file reads

- **Unit:** CAH-028
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Read one bounded text file](../../user-stories/cah-028-read-bounded-text-file.md)
- **Learning emphasis:** Supporting implementation unit
- **Review focus:** Strict UTF-8 admission, whole-line bounds, and access-time policy recheck
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Tool system](../tool-system.md),
  [Context engineering](../context-engineering.md), and [Safety model](../safety-model.md)

> This is planned behavior. The pseudocode is not a repository implementation excerpt.

## Quick summary

CAH-028 reads one admitted regular file as strict UTF-8 and returns a whole-line slice with exact
provenance and truncation. It is deliberately a small supporting primitive for context and later
tool calls.

## Learning objectives

After completing this unit, you should be able to:

- separate source-size admission from returned-content limits;
- explain strict UTF-8 and whole-line truncation;
- calculate source and returned UTF-8 bytes; and
- test policy, type, text, and replacement-race failures.

## Why this unit matters

Reading “a file” sounds simple until a file is huge, binary, ignored, secret-bearing, replaced, or
encoded unexpectedly. One narrow contract prevents every later caller from inventing different
answers.

## Junior engineer foundation

Characters and bytes are not interchangeable: `é` is one Unicode scalar but two UTF-8 bytes. This
story budgets original and returned bytes, while line numbers are 1-based. A common misconception is
that decoding with replacement is safer; replacement silently changes evidence, so malformed input
fails instead.

## Key concepts

- **Shared path budget:** CAH-024/026 admits at most 4,095 UTF-8 bytes, 256 normalized components,
  and 255 UTF-8 bytes per component before policy or file I/O.
- **Strict text:** Complete source decodes as UTF-8 and contains no NUL.
- **Two budgets:** Source eligibility is 256 KiB; one response is at most 64 KiB and 400 lines.
- **One real producer:** `read_file` and CAH-029 search consume the same final-admission,
  cap-plus-sentinel, strict-text candidate seam.
- **Whole-line slice:** No partial line or partial Unicode encoding is returned.
- **Fresh admission:** Boundary and policy are checked again immediately before open.

## Architecture and design

```text
TUI / provider tool request (future)
              |
        Python harness
              |
 CAH-024 boundary -> CAH-026 policy -> [CAH-028 read_text_candidate] -> repository bytes
                                              |                    |
                                         read_file           CAH-029 search
                                              |
                                    CAH-030 context (later)

Protocol, loop, and transcript/evidence remain unchanged in this unit.
```

The result contains the final pre-open canonical path, exact text, line range, total lines,
source/returned bytes, and truncation. It never copies a stale request alias. Default
representations suppress content.
Runtime calls `RepositoryTextReader(policy: RepositoryReadPolicy)`. Its exact
`read_text_candidate(path, max_source_bytes)` returns one frozen `TextSourceCandidate` and owns final
admission, a cap-plus-one sentinel
read, and strict UTF-8/NUL classification. `read_file(request) -> ReadFileResult` calls that producer
with 262,144 bytes; CAH-029 later calls it with the smaller of that ceiling and its remaining
aggregate budget. The reader retains the exact policy object shared with CAH-027; it never rebuilds
a workspace boundary or independent ignore-policy state.
`ReadFileRequest.path` is required and has no default; only the line and byte bounds have defaults.

## Practical walkthrough

1. Validate the shared path byte/component/name budget, start line, line count, and byte request.
2. Call the shared candidate producer, which rechecks CAH-026 immediately before open and retains
   that final canonical label.
3. Read at most the active cap plus one byte. Classify overflow without decoding the sentinel;
   otherwise strictly decode the complete source and classify decoded NUL as non-text.
4. Map overflow/non-text to the existing safe errors, or select whole lines from admitted text and
   stop before either return bound.
5. Return exact counts and test the producer through both its direct-read and later search consumers.

## Implementation code samples

Planned pseudocode only:

```python
candidate = reader.read_text_candidate(request.path, max_source_bytes=262_144)
if candidate.overflowed:
    raise repository_source_too_large()
if candidate.non_text:
    raise repository_not_text()

text = require_type(candidate.text, str)
lines = text.splitlines(keepends=True)
selected = whole_lines_within(request.max_lines, request.max_bytes)
return ReadFileResult(path=candidate.path,
                      text=selected, **exact_counts, truncated=truncated)
```

The candidate owns the extra byte and never decodes or charges it. Full decode validates evidence
before slicing. Whole-line selection makes truncation observable and reproducible. CAH-029 receives
the same three-state carrier, so a prose-level promise cannot drift from the actual producer.

## Failure scenarios to study

- A path at 4,096 bytes, 257 components, or a 256-byte name fails as
  `invalid_repository_path` before policy or open; each exact endpoint remains lexically valid.
- A 262,145-byte file fails without partial content.
- Invalid UTF-8 and NUL return `repository_not_text`, never replacement text.
- An oversized first selected line returns empty text with `truncated=true`.
- A denied, ignored, escaping, or replaced target returns a fixed safe error.
- An allowed `alias -> A` retargeted to allowed `B` before open reads and reports `B`; the earlier
  alias resolution never becomes success provenance.

## Production expansion

### Example enterprise scenario

Production retrieval may need archives, PDFs, encodings, generated-file classification, and secret
scanning. Each decoder expands the trusted computing base and needs its own limits.

### Typical production capabilities and tools

- [Python `open`](https://docs.python.org/3/library/functions.html#open) provides local file I/O with
  explicit modes and encoding, but not policy or content classification.
- [Apache Tika](https://tika.apache.org/) extracts many document formats, adding a service/runtime and
  a much larger parser attack surface.
- [Trivy secret scanning](https://trivy.dev/latest/docs/scanner/secret/) can detect credential
  patterns, adding scan time, false positives, and rule maintenance.
- [MCP resources](https://modelcontextprotocol.io/docs/learn/server-concepts) can expose remote
  content uniformly, adding transport authorization and provenance concerns.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One UTF-8 regular file | Many formats, encodings, and remote resources |
| Reliability | Fixed byte/line limits | Parser isolation, retries, and content quarantine |
| Operations | Local tests | Scanner/parser updates and telemetry |
| Cost | Small native implementation | Services, CPU, security review, and false positives |

### Trade-offs and graduation signals

Strict UTF-8 excludes useful documents but keeps evidence predictable. Add a format only when
evaluations need it, then isolate its parser and retain canonical provenance and output limits.

## Practical exercises

1. Compute byte counts for ASCII and multibyte lines.
2. Predict results for empty, beyond-EOF, and oversized-first-line reads.
3. Write below/at/above tests for source and returned bytes.
4. Retarget an admitted alias from one allowed file to another and identify which canonical label
   the result must carry.
5. Teach back: why validate the complete eligible source before returning a slice?
6. Explain why CAH-029 passes its remaining aggregate budget to this producer instead of opening the
   file again itself.

## Key takeaways

- The harness owns text admission and output bounds.
- Success provenance comes from final read admission, not the mutable request alias.
- Strict decode plus whole-line truncation preserves evidence integrity.
- Sharing the real bounded candidate producer prevents direct reads and search from drifting on
  admission, byte charging, or sentinel handling.
- More formats increase utility and parser/security cost.

## Glossary

- **Source bytes:** Original bytes in the admitted file.
- **Returned bytes:** UTF-8 bytes in the selected text.
- **Replacement decoding:** Substituting malformed bytes with a marker; prohibited here.

## Further reading

- [CAH-028 delivery contract](../../user-stories/cah-028-read-bounded-text-file.md)
- [Python Unicode HOWTO](https://docs.python.org/3/howto/unicode.html)
- [Context engineering](../context-engineering.md)
