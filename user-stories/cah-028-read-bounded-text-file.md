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

- `RepositoryTextReader(policy: RepositoryReadPolicy)` is the exact service. It retains the supplied
  object as read-only `policy` identity and exposes both
  `read_text_candidate(path: str, max_source_bytes: int) -> TextSourceCandidate` and
  `read_file(request: ReadFileRequest) -> ReadFileResult`. Runtime passes the same CAH-026 policy used
  by CAH-027; the reader never accepts a root path, reconstructs `WorkspaceBoundary`, or creates an
  independent ignore-policy state. The candidate method is the one shared bounded-read seam used by
  CAH-028 and CAH-029; neither consumer may reproduce its policy, open, sentinel, or text-admission
  logic.

- `ReadFileRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It contains
  required `path` with no default, `start_line` (default 1), `max_lines` (default 200), and `max_bytes` (default 32 KiB /
  32,768 bytes). Its path inherits CAH-024/026's inclusive 4,095-byte,
  256-normalized-component, and 255-byte-name lexical budget. Booleans used as integers are rejected.
- `start_line` is in 1-1,000,000; `max_lines` is in 1-400; and `max_bytes` is in
  1-65,536. Values outside those ranges fail with `repository_input_limit` before access.
- `ReadFileResult` contains the canonical workspace-relative POSIX `path`, exact returned `text`,
  `start_line`, inclusive `end_line` or `None`, `total_lines`, `source_bytes`, `returned_bytes`, and
  `truncated`. Its `path` is copied from the final pre-open boundary/policy admission, not the
  supplied alias or an earlier resolution snapshot, including empty and beyond-EOF successes.
- An empty file succeeds with empty text, `end_line=None`, `total_lines=0`, zero byte counts, and
  `truncated=false`. A start beyond end-of-file also succeeds with empty text and preserves the
  requested `start_line`.
- Lines are recognized using Python's Unicode `splitlines(keepends=True)` behavior after strict
  decode. Original line endings are preserved in returned text; no normalization or synthetic final
  newline is introduced.
- `TextSourceCandidate` is a frozen, content-suppressed provider-neutral value with exactly
  `path: str`, `source_bytes_examined: int`, `text: str | None`, `overflowed: bool`, and
  `non_text: bool`. Exactly one state is legal: admitted text has a built-in `str` (including empty),
  `overflowed=false`, and `non_text=false`; overflow has `text=None`,
  `source_bytes_examined=max_source_bytes`, `overflowed=true`, and `non_text=false`; invalid UTF-8 or
  decoded NUL has `text=None`, `overflowed=false`, and `non_text=true`. An overflow sentinel is never
  included in `source_bytes_examined`, decoded, retained, or exposed. The candidate `path` is the
  final canonical label from the admission immediately preceding its open.

### Admission, text, and limits

- Input validation precedes CAH-026 admission. The target must be an admitted regular file; ignored,
  denied, missing, directory, special-object, containment, and stale-root cases use the shared fixed
  error table.
- Path syntax and work-budget failure maps to `invalid_repository_path` before line/byte selection,
  policy, resolution, or content I/O. Other numeric request bounds retain
  `repository_input_limit`.
- `read_text_candidate` validates `max_source_bytes` as an exact non-Boolean integer in 1-262,144,
  performs the final CAH-026 admission, and reads at most `max_source_bytes + 1` bytes. It returns the
  three-state candidate above rather than slicing lines. It strictly decodes only a complete source
  that did not produce the sentinel; replacement decode is prohibited. Policy, containment,
  unavailable, wrong-type, and bounded-read failures retain CAH-026's exact errors.
- `read_file` calls that exact seam with `max_source_bytes=262_144`. An overflow candidate maps to
  `repository_source_too_large`; a non-text candidate maps to `repository_not_text`; only an admitted
  text candidate reaches line selection. Thus an eligible `read_file` source may contain at most
  256 KiB (262,144 bytes), and both direct reading and later search use one real producer rather than
  merely agreeing on prose.
- Selection begins at `start_line`, takes no more than `max_lines` whole lines, and then applies the
  requested returned-byte limit. A line is never split. If the first selected line alone exceeds
  `max_bytes`, return no text with `truncated=true`; do not return a partial Unicode character or
  partial line.
- `returned_bytes` is `len(text.encode("utf-8"))`. `source_bytes` is the original byte length.
  `truncated` is true when content exists at or after `start_line` that is not returned because of a
  line or byte limit; it is false when only earlier lines were intentionally skipped.
- The source is resolved and policy-checked again immediately before opening, and that final
  canonical label is the result's `path`. An allowed-to-allowed alias retarget therefore reports the
  target actually admitted for the read rather than stale provenance. This narrows but does not
  eliminate replacement races; descriptor-relative access remains deferred.
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
- **Planning PR scope:** One contract neighborhood: CAH-026-admitted file path -> bounded strict-text
  read and immutable `ReadFileResult` -> CAH-029 search, CAH-030 focus-context, and CAH-031 registry
  consumers.
- **Split rule:** stop and refine another story before review if discovery, search, context ranking,
  tool dispatch, or provider serialization enters this unit, or if production churn is likely to
  exceed roughly 600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One `RepositoryTextReader` retains the exact shared CAH-026 policy identity. Its candidate seam
   owns final admission, one bounded sentinel read, strict text classification, and canonical
   provenance; `read_file` maps that exact producer into the requested whole-line slice.
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
| Shared path request budget | Exercise 4,094/4,095/4,096 total UTF-8 bytes, 254/255/256 name bytes, and 255/256/257 normalized components | Request/policy boundary | Exact endpoints remain constructible; above-bound paths return `invalid_repository_path` before policy or open |
| Empty boundaries | Read empty file and start at/beyond final line | Unit | Contracted empty or final-line results and honest truncation |
| Source size | Use 262,143/262,144/262,145-byte valid files | Unit | Success at limit and `repository_source_too_large` above |
| Shared candidate seam | Call with active caps 1, 262,143, and 262,144 across exact, overflow, invalid-UTF-8, NUL, and empty sources; spy on policy/open/decode | Unit/service boundary | Exact three-state carrier, one final admission/open, at most cap plus one physical byte, sentinel never decoded/charged, and no duplicated read path |
| Return limits | Exercise 32-KiB default, 65,536 hard max, overlong first line, and 399/400/401 lines | Unit | Whole-line output, explicit truncation, above-hard input rejection |
| Strict UTF-8 | Use multibyte boundary, invalid bytes, BOM, and decoded NUL | Unit | Exact valid text or fixed `repository_not_text`; no replacement |
| Policy and containment | Directly request ignored, denied, escaping, stale, directory, and FIFO targets, including an ignored parent followed by a negated child | Policy/boundary integration | Parent traversal cannot be bypassed by direct leaf access; exact shared safe error and no path/content/OS leak |
| Race-aware recheck | Replace an admitted target before open at an injected deterministic seam, including allowed `alias -> A` retargeted to allowed `B` | Unit integration | Unsafe replacement fails; allowed replacement reads/reports final canonical `B`, never stale `A` or the alias |

## Validation

- Add focused candidate/read tests with temporary files covering exact line endings, Unicode, source
  and result budgets, policy, containment, three-state carrier invariants, and fixed failures.
- Test numeric limits below, at, and above and assert `returned_bytes` by re-encoding the exact text.
- At the deterministic pre-open seam, retarget an allowed alias from `A` to `B`; assert the exact
  final read and `ReadFileResult.path` both use `B`, including an empty-success control.
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

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish the supplied path alias, final pre-open canonical target, candidate canonical `path`, `ReadFileResult.path`, complete charged source bytes, sentinel, selected returned text, and source/returned byte accounting. Semantic owner, cache identity, and separate provenance source are N/A; the final canonical path is the sole model-visible label. |
| End-to-end contract | Strict `ReadFileRequest` -> shared `read_text_candidate(path, 262_144)` -> CAH-024/026 final admission -> bounded native read/sentinel -> complete strict-text classification -> whole-line slice -> immutable result. CAH-029 consumes the same candidate producer with its active remaining budget; CAH-030/031 consume the public operations. |
| Failure and atomicity | Invalid/policy-denied inputs open no content; the whole eligible file must pass size, UTF-8, and NUL checks before any slice is returned; every failure yields no partial text. Empty/beyond-EOF and overlong-first-line results are explicit successes; cancellation/deadline/rollback are N/A inside the synchronous read. |
| Reachable boundaries | Real admitted files exercise 262,143/262,144/262,145 source bytes, returned-byte limits through 65,536 and above-input rejection, 399/400/401 lines, start-line bounds, multibyte edges, and allowed/unsafe alias retargets at the final pre-open seam. |
| Closed grammar and cardinality | The frozen request admits exactly `path`, `start_line`, `max_lines`, and `max_bytes`; one regular strict-UTF-8/no-NUL source yields one whole-line slice using `splitlines(keepends=True)`. No partial line or Unicode sequence is legal, and the shared CAH-026 error vocabulary is closed. |
| Artifact parity | Story, lesson, diagram, tool/context/safety docs, and tests use the same order: request validation -> final policy/boundary admission -> bounded full-source read -> strict decode/NUL check -> line selection -> byte cap -> canonical result, with identical truncation and fixed-error rules. |
| Independent lenses | Security/identity review covers final target provenance, denied/ignored paths, retargets, and content suppression; producer/consumer review drives the real candidate seam through both `read_file` and CAH-029 with identical identity and sentinel behavior; limits/scheduler review covers per-call/line boundaries and records provider/protocol changes plus in-flight scheduler behavior as N/A. |

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
