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

- **Strict text:** Complete source decodes as UTF-8 and contains no NUL.
- **Two budgets:** Source eligibility is 256 KiB; one response is at most 64 KiB and 400 lines.
- **Whole-line slice:** No partial line or partial Unicode encoding is returned.
- **Fresh admission:** Boundary and policy are checked again immediately before open.

## Architecture and design

```text
TUI / provider tool request (future)
              |
        Python harness
              |
 CAH-024 boundary -> CAH-026 policy -> [CAH-028 read_file] -> repository bytes
                                              |
                                    CAH-030 context (later)

Protocol, loop, and transcript/evidence remain unchanged in this unit.
```

The result contains canonical path, exact text, line range, total lines, source/returned bytes, and
truncation. Default representations suppress content.

## Practical walkthrough

1. Validate path, start line, line count, and byte request.
2. Admit a regular file with CAH-026 and recheck immediately before open.
3. Read at most 256 KiB plus one byte, then strictly decode the entire file.
4. Select whole lines from the 1-based start and stop before either return bound.
5. Return exact counts and test empty, CRLF, no-final-newline, and multibyte cases.

## Implementation code samples

Planned pseudocode only:

```text
source = read_at_most(FILE_LIMIT + 1)
text = strict_utf8_without_nul(source)
lines = text.splitlines(keepends=True)
selected = whole_lines_within(request.max_lines, request.max_bytes)
return ReadFileResult(selected, exact_counts, truncated)
```

The extra byte proves an over-limit source. Full decode validates evidence before slicing. Whole-line
selection makes truncation observable and reproducible.

## Failure scenarios to study

- A 262,145-byte file fails without partial content.
- Invalid UTF-8 and NUL return `repository_not_text`, never replacement text.
- An oversized first selected line returns empty text with `truncated=true`.
- A denied, ignored, escaping, or replaced target returns a fixed safe error.

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
4. Teach back: why validate the complete eligible source before returning a slice?

## Key takeaways

- The harness owns text admission and output bounds.
- Strict decode plus whole-line truncation preserves evidence integrity.
- More formats increase utility and parser/security cost.

## Glossary

- **Source bytes:** Original bytes in the admitted file.
- **Returned bytes:** UTF-8 bytes in the selected text.
- **Replacement decoding:** Substituting malformed bytes with a marker; prohibited here.

## Further reading

- [CAH-028 delivery contract](../../user-stories/cah-028-read-bounded-text-file.md)
- [Python Unicode HOWTO](https://docs.python.org/3/howto/unicode.html)
- [Context engineering](../context-engineering.md)
