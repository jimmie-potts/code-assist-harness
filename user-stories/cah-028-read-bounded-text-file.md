# CAH-028 - Read one bounded text file

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-026
- **Lesson:** [Bounded repository reads](../docs/lessons/cah-028-bounded-text-file.md)
- **Learning emphasis:** Supporting implementation unit - safe, observable file-content retrieval
- **Review focus:** Strict text admission and deterministic line/byte truncation at the harness
  boundary

## User story

> As a user, I want the harness to read a requested range from one admitted repository text file so
> that later reasoning receives useful evidence without exposing secrets, binary data, or unbounded
> content.

## Single responsibility

CAH-028 owns the native `read_file` operation for one regular UTF-8 repository file. It does not
discover files, search across files, select context, register a model tool, dispatch tool calls, or
continue an agent loop.

## Scope

- Add immutable provider-neutral Python request and result contracts plus a native `read_file`
  service that reuses CAH-024 containment and CAH-026 policy.
- Read one admitted regular file with a 1-based starting line and bounded line and returned-byte
  limits.
- Validate the entire eligible file as strict UTF-8 without NUL before returning any text, then
  return a deterministic whole-line slice with canonical provenance and explicit truncation.
- Use bounded native Python file I/O only. Do not invoke `cat`, `sed`, `git`, `rg`, a shell,
  subprocess, network, provider, protocol, transcript, or TUI path.

## Locked contract

### Request and result

- `ReadFileRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It contains
  `path`, `start_line` (default 1), `max_lines` (default 200), and `max_bytes` (default 32 KiB /
  32,768 bytes). Booleans used as integers are rejected.
- `start_line` is in 1-1,000,000; `max_lines` is in 1-400; and `max_bytes` is in
  1-65,536. Values outside those ranges fail with `repository_input_limit` before access.
- `ReadFileResult` contains the canonical workspace-relative POSIX `path`, exact returned `text`,
  `start_line`, inclusive `end_line` or `None`, `total_lines`, `source_bytes`, `returned_bytes`, and
  `truncated`.
- An empty file succeeds with empty text, `end_line=None`, `total_lines=0`, zero byte counts, and
  `truncated=false`. A start beyond end-of-file also succeeds with empty text and preserves the
  requested `start_line`.
- Lines are recognized using Python's Unicode `splitlines(keepends=True)` behavior after strict
  decode. Original line endings are preserved in returned text; no normalization or synthetic final
  newline is introduced.

### Admission, text, and limits

- Input validation precedes CAH-026 admission. The target must be an admitted regular file; ignored,
  denied, missing, directory, special-object, containment, and stale-root cases use the shared fixed
  error table.
- An eligible source may contain at most 256 KiB (262,144 bytes). The implementation reads no more
  than 262,145 bytes while checking that limit, then strictly decodes the complete source. Invalid
  UTF-8 or any decoded NUL fails with `repository_not_text`; replacement decode is prohibited.
- Selection begins at `start_line`, takes no more than `max_lines` whole lines, and then applies the
  requested returned-byte limit. A line is never split. If the first selected line alone exceeds
  `max_bytes`, return no text with `truncated=true`; do not return a partial Unicode character or
  partial line.
- `returned_bytes` is `len(text.encode("utf-8"))`. `source_bytes` is the original byte length.
  `truncated` is true when content exists at or after `start_line` that is not returned because of a
  line or byte limit; it is false when only earlier lines were intentionally skipped.
- The source is resolved and policy-checked again immediately before opening. This narrows but does
  not eliminate replacement races; descriptor-relative access remains deferred.
- Result values and errors never expose absolute paths, denied labels, raw bytes, decoder details,
  OS text, or content outside the selected range. Default representations may include admitted
  canonical labels but should suppress `text`.
- The operation is synchronous and bounded. A later dispatcher handles cancellation around the
  call; this unit introduces no protocol or asyncio task lifecycle.

### Fixed failures

CAH-026's `RepositoryAccessError` table is reused without an operation-specific exception type:
invalid input, unavailable/ignored/not-found paths, expected file, non-text, source too large, and
bounded read failure all retain their exact shared codes and messages.

## Reviewability budget

- **Estimated production-code churn:** 300-450 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if discovery, search, context ranking,
  tool dispatch, or provider serialization enters this unit, or if production churn is likely to
  exceed roughly 600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. An admitted UTF-8 regular file returns the exact requested whole-line slice with canonical
   provenance and correct source/returned byte and line metadata.
2. Empty files, a start beyond EOF, missing final newlines, CRLF, and multibyte characters have
   explicit deterministic results.
3. Source size 256 KiB, returned size up to 64 KiB, line count up to 400, and start-line bounds are
   enforced exactly without splitting a line or Unicode sequence.
4. Ignored, denied, escaping, stale, non-regular, oversized, invalid-UTF-8, and NUL-containing files
   fail with CAH-026's fixed non-leaking errors.
5. Public values are immutable, typed, documented, provider-neutral, and suppress returned content
   from default representations.
6. Focused tests are deterministic and local, with no subprocess, model, or network behavior.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Exact slice | Read a mixed newline file from a middle line | Unit | Exact preserved text, inclusive line metadata, and byte counts |
| Empty boundaries | Read empty file and start at/beyond final line | Unit | Contracted empty or final-line results and honest truncation |
| Source size | Use 262,143/262,144/262,145-byte valid files | Unit | Success at limit and `repository_source_too_large` above |
| Return limits | Exercise 32-KiB default, 65,536 hard max, overlong first line, and 399/400/401 lines | Unit | Whole-line output, explicit truncation, above-hard input rejection |
| Strict UTF-8 | Use multibyte boundary, invalid bytes, BOM, and decoded NUL | Unit | Exact valid text or fixed `repository_not_text`; no replacement |
| Policy and containment | Directly request ignored, denied, escaping, stale, directory, and FIFO targets | Policy/boundary integration | Exact shared safe error and no path/content/OS leak |
| Race-aware recheck | Replace an admitted target before open at an injected deterministic seam | Unit integration | Final policy/boundary check prevents stale authorization |

## Validation

- Add focused read tests with temporary files covering exact line endings, Unicode, source and result
  budgets, policy, containment, and fixed failures.
- Test numeric limits below, at, and above and assert `returned_bytes` by re-encoding the exact text.
- Assert immutable contracts and ensure result/error representations suppress content, host paths,
  and raw failures.
- Keep protocol, transcript, provider, tool registry, and TUI unchanged; their nearest parity
  evidence remains the canonical gate.
- Run focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update tool-system, context-engineering, safety model, glossary, story and lesson indexes, E3
backlog sequence, and the Markdown lesson's compact architecture diagram. Explain bytes versus
tokens and whole-line truncation. Do not add or revise a presentation.

## Exclusions

- Directory discovery, multi-file reads, literal or regex search, syntax parsing, context selection,
  embeddings, ranking, or provider token counting.
- Tool schemas, registration, MCP, provider tool calls, dispatch, agent-loop continuation, protocol
  events, transcript fields, and TUI rendering.
- Binary/media decoding, encoding detection, generated-file classification, secret content scanning,
  file writes, subprocesses, network access, or policy override.
- Descriptor-relative opening, memory mapping, streaming very large files, multiple roots, and
  platform-specific newline conversion.

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Source-byte, returned-byte, line-count, and start-line limits pass below/at/above evidence.
3. Strict UTF-8, whole-line truncation, canonical labels, policy reuse, and fixed safe errors are
   proved without content or host leakage.
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

- A native bounded-read module and temporary-file tests prove exact slices and strict text behavior.
- Integration tests reuse the real CAH-024/026 boundary and policy rather than a subprocess or fake
  allow decision.
- The lesson positions this supporting operation beneath context selection and later tool dispatch;
  its primary teach-back question is: why does a byte-bounded harness refuse to split an oversized
  first line instead of returning an ambiguous partial result?

## Deferred work

- CAH-029 reuses bounded text rules for literal workspace search.
- CAH-030 combines bounded reads with instructions and search evidence under one context budget.
- E4 later exposes `read_file` through a validated, capability-classified tool contract.
