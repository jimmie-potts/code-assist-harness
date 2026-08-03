# CAH-025 - Discover scoped repository instructions

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-024
- **Lesson:** [Scoped repository instructions](../docs/lessons/cah-025-repository-instructions.md)
- **Learning emphasis:** Core learning unit - context hierarchy and harness-owned instruction
  selection
- **Review focus:** How the harness locates authoritative `AGENTS.md` files without scanning or
  trusting the provider to choose its own instructions

## User story

> As a user, I want the harness to discover the repository instructions that apply to a selected
> path so that later model context follows local guidance with explicit, testable precedence.

## Single responsibility

CAH-025 owns only discovery and bounded loading of `AGENTS.md` files on the canonical ancestor chain
from the workspace root to one scope. It does not interpret prose, discover arbitrary context files,
apply `.gitignore`, select source-code context, construct a provider request, or run an agent turn.

## Scope

- Add a focused Python instruction-discovery module that consumes `WorkspaceBoundary` from CAH-024.
- Accept one existing workspace-relative file or directory as the scope; a file uses its canonical
  parent directory and a directory uses itself.
- Probe only the exact filename `AGENTS.md` at the workspace root and each canonical ancestor through
  the scope. Do not recursively walk the repository.
- Return immutable sources in root-to-nearest order with canonical workspace-relative POSIX labels,
  strict UTF-8 content, byte counts, and increasing precedence.
- Keep the implementation native Python and synchronous: no subprocess, shell, network, provider,
  protocol, transcript, or TUI change.

## Locked contract

### Ownership, ordering, and precedence

- The Python harness owns instruction discovery. The TUI and provider may display or consume the
  resulting sources but cannot add, remove, reorder, or select instruction files.
- The public operation is conceptually `discover_for_path(path) -> RepositoryInstructions`.
  Returned values are frozen and contain only canonical workspace labels, content, byte counts, and
  a zero-based precedence rank; they never contain absolute host paths.
- The root candidate is first and the nearest candidate is last. Later sources have narrower scope
  and therefore higher precedence. This unit records that order but does not parse prose or merge
  individual directives.
- Internal symlinks are resolved by CAH-024. Discovery follows the canonical scope ancestry, not the
  user-supplied alias. Canonically duplicate instruction targets appear once at their earliest
  position.
- No discovered file is a source of truth until it has passed the workspace boundary, type, size,
  and text checks in this unit. A missing `AGENTS.md` candidate is normal and produces no source.
- `.gitignore` does not suppress `AGENTS.md`: instruction files are control-plane input found only at
  exact ancestor locations. A scope whose supplied or canonical components include `.git`, `.hg`,
  or `.svn` is unavailable and is never probed; checking both forms avoids an existence oracle and
  a symlink alias bypass.

### Initial reviewed limits

These are conservative byte and item limits, not token estimates. Changing them requires an
explicit contract review rather than a provider-specific adjustment.

| Limit | Initial value | Boundary behavior |
| --- | ---: | --- |
| Ancestor instruction sources | 16 files | A seventeenth existing source fails the bundle. |
| One instruction file | 32 KiB (32,768 bytes) | A file one byte larger is rejected before decode. |
| Aggregate instruction content | 128 KiB (131,072 bytes) | The first source that would cross the total fails the bundle. |

- Files are read as bytes up to one byte beyond the applicable limit, then decoded with Python's
  strict UTF-8 behavior. Replacement decoding is prohibited. A decoded NUL is not valid instruction
  text.
- Byte counts are the original file byte lengths. Newlines and a UTF-8 byte-order mark, if present,
  are not silently rewritten or stripped.
- Discovery returns an empty successful bundle when no candidate exists. It never substitutes a
  README, provider prompt, home-directory file, or global configuration file.

### Fixed, non-leaking failures

`RepositoryInstructionError` exposes exactly one stable code and fixed message. It does not include
the supplied label, absolute path, file content, raw `OSError`, or decoder details. Boundary errors
are mapped at this API rather than copied verbatim into later provider-visible context.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_instruction_scope` | `Instruction scope must be an existing workspace file or directory.` | the scope is invalid, missing, or an unsupported object |
| `instruction_scope_unavailable` | `Instruction scope is not available.` | the canonical scope is outside policy, stale, or cannot be inspected safely |
| `invalid_instruction_source` | `Repository instruction source must be a regular file.` | an exact candidate exists but is not a regular file |
| `instruction_source_not_text` | `Repository instruction source must be valid UTF-8 text.` | strict decoding fails or decoded content contains NUL |
| `instruction_source_too_large` | `Repository instruction source exceeds the byte limit.` | one source exceeds 32 KiB |
| `instruction_budget_exceeded` | `Repository instructions exceed the source or byte limit.` | source count or aggregate bytes exceed their limits |
| `instruction_read_failed` | `Repository instruction source could not be read.` | a bounded local read fails for another reason |

- The operation is small, synchronous, and has no internal cancellation protocol. A later loop
  caller checks cancellation before starting it and before any subsequent costly operation.
- CAH-024 remains a best-effort check-before-use boundary. This unit resolves immediately before
  each read but does not claim descriptor-relative race protection.

## Reviewability budget

- **Estimated production-code churn:** 300-450 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if the unit gains parsing, context
  ranking, provider integration, or is likely to exceed roughly 600 changed production lines. Do
  not pad a smaller coherent implementation.

## Acceptance criteria

1. Root, intermediate, and nearest `AGENTS.md` files are returned once in canonical root-to-nearest
   order for both file and directory scopes.
2. Missing candidates produce an empty or smaller successful bundle without a recursive scan.
3. Every source is a regular in-workspace file, is at most 32 KiB, and decodes as strict UTF-8 text
   without NUL; aggregate source and byte limits are enforced exactly.
4. Canonical internal symlinks are handled deterministically, while escapes, VCS-administration
   scopes, stale roots, and filesystem failures become fixed non-leaking errors.
5. Public contracts are immutable, typed, and documented; representations and failures contain no
   absolute path or instruction content.
6. Focused tests are local and deterministic, and the lesson distinguishes ordered discovery from
   prose interpretation or model obedience.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Scoped precedence | Build root/intermediate/nearest sources and request file plus directory scopes | Unit | Exact canonical labels, ranks, contents, and root-to-nearest order |
| No recursive scan | Place unrelated sibling and descendant `AGENTS.md` files | Unit | Neither unrelated source appears |
| Canonical alias | Scope through an internal directory symlink | Boundary integration | Canonical ancestor chain and no duplicate source |
| Exact limits | Exercise 32,767/32,768/32,769 bytes, 16/17 files, and aggregate edge | Unit | Success at limits and exact fixed failures above them |
| Text safety | Use invalid UTF-8, NUL, and a valid multibyte boundary | Unit | Strict rejection without replacement or leaked decoder text |
| Containment and leakage | Use escaping symlinks, stale root, VCS scope, and distinctive host names | Boundary integration | Stable code/message and no host path, source text, or raw OS error |

## Validation

- Add focused instruction-discovery tests using temporary workspaces and CAH-024's real boundary.
- Assert exact source order, canonical labels, immutable values, byte counts, representations, and
  the complete failure table.
- Test each numeric limit below, at, and above its boundary without sleep, subprocess, network, or a
  model fake.
- Keep protocol, transcript, provider, and TUI schemas unchanged; the nearest parity evidence is the
  existing full repository gate.
- Run the focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before
  Done.

## Documentation impact

Update the story and lesson indexes, E3 backlog sequence, context-engineering and safety guidance,
glossary entries for instruction scope and precedence, and the Markdown lesson's compact
architecture diagram. Add a planning note for material implementation discoveries. Do not add or
revise a presentation.

## Exclusions

- Parsing instruction prose, resolving conflicting directives, or claiming the model will obey it.
- `.gitignore` and credential policy, arbitrary file discovery, source ranking, tokenization, or
  context-package construction.
- Provider messages, tool schemas or dispatch, MCP, agent-loop continuation, transcripts, protocol,
  TUI rendering, file writes, subprocesses, and network access.
- User-level or home-directory instruction files, multiple roots, remote repositories, and
  descriptor-relative filesystem hardening.

## Definition of done

1. All acceptance criteria map to deterministic happy, boundary, and failure tests.
2. The 16-source, 32-KiB-per-source, and 128-KiB aggregate limits pass below/at/above tests.
3. Strict UTF-8, canonical labels, immutable order, and fixed safe errors are proved without leaks.
4. Public Python contracts are typed and documented; unsupported inputs fail closed.
5. Focused tests and the canonical offline `./scripts/check` pass with no model, subprocess, or
   network.
6. Existing protocol, transcript, provider, and TUI boundaries remain unchanged and pass their
   existing tests.
7. The Markdown lesson uses implementation and failure-test excerpts after code exists and includes
   no presentation work.
8. Story, lesson, conceptual docs, indexes, backlog, planning note, and statuses agree.
9. Delivered production-source churn is recorded and stays near the reviewability range or is split
   before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- A focused Python instruction-discovery module and mirrored unit tests prove the ordered path.
- Temporary-workspace tests prove exact limits, strict text handling, canonical symlink behavior,
  and safe failures.
- The lesson locates instruction selection between the workspace boundary and later context builder;
  its primary teach-back question is: why must the harness, rather than the LLM, select applicable
  repository instructions?

## Deferred work

- CAH-030 combines discovered instructions with bounded repository sources and atomically enriches an
  existing package with a later bundle.
- CAH-026 through CAH-029 define and implement general read policy and native read operations.
- CAH-034 discovers the applicable bundle after a successful tool target is admitted and carries the
  enriched context into its follow-up; CAH-035 repeats that rule across the bounded loop.
