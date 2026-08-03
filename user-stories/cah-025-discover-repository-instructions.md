# CAH-025 - Discover scoped repository instructions

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-024 and CAH-026
- **Lesson:** [Scoped repository instructions](../docs/lessons/cah-025-repository-instructions.md)
- **Learning emphasis:** Core learning unit - context hierarchy and harness-owned instruction
  selection
- **Review focus:** How the harness locates, safely admits, and scopes authoritative `AGENTS.md`
  candidates without scanning or trusting the provider to choose its own instructions

## User story

> As a user, I want the harness to discover the repository instructions that apply to a selected
> path so that later model context follows local guidance with explicit, testable precedence.

## Single responsibility

CAH-025 owns discovery, security admission, and bounded loading of exact `AGENTS.md` candidates on
the canonical ancestor chain from the workspace root to one scope. It reuses CAH-026's pure lexical
path admission and non-overridable hard-deny classifier without invoking CAH-026's `.gitignore`,
ordinary-read limit, result, or error policy. It does not
interpret prose, discover arbitrary context files, select source-code context, construct a provider
request, or run an agent turn.

## Scope

- Add a focused Python instruction-discovery module that consumes `WorkspaceBoundary` from CAH-024.
- Accept one existing workspace-relative file or directory as the scope; a file uses its canonical
  parent directory and a directory uses itself.
- Probe only the exact filename `AGENTS.md` at the workspace root and each canonical ancestor through
  the scope. Do not recursively walk the repository.
- Return immutable bindings in root-to-nearest order. Each binding carries the canonical target as
  source provenance, the canonical candidate-owner directory as `applies_to`, strict UTF-8 content,
  byte counts, and increasing precedence.
- Apply CAH-026's pure lexical-path admission and shared hard-deny classifier before scope resolution
  or instruction-source content reads while deliberately skipping GitIgnoreSpec evaluation for
  control-plane `AGENTS.md` candidates.
- Keep the implementation native Python and synchronous: no subprocess, shell, network, provider,
  protocol, transcript, or TUI change.

## Locked contract

### Ownership, ordering, and precedence

- The Python harness owns instruction discovery. The TUI and provider may display or consume the
  resulting sources but cannot add, remove, reorder, or select instruction files.
- The public operation is conceptually `discover_for_path(path) -> RepositoryInstructions`.
  Returned values are frozen and contain canonical workspace-relative `source` and `applies_to`
  labels, content, byte counts, and a zero-based precedence rank; they never contain absolute host
  paths.
- The root candidate is first and the nearest candidate is last. Later sources have narrower scope
  and therefore higher precedence. This unit records that order but does not parse prose or merge
  individual directives.
- Internal scope and candidate symlinks are resolved by CAH-024. Discovery follows the canonical
  scope ancestry, not the user-supplied alias. For each ancestor, capture that canonical directory as
  `applies_to` before resolving its exact `AGENTS.md` leaf; preserve the resolved canonical target as
  `source`. A cross-directory internal link therefore keeps physical provenance without changing
  which subtree owns the instruction.
- Binding identity is the candidate owner (`applies_to`), because one exact `AGENTS.md` candidate can
  govern each ancestor. The same canonical target referenced by different owners produces distinct
  bindings and spends source/content budget once per binding. It is not deduplicated into a wider or
  narrower scope merely because the target bytes are shared.
- No discovered file is a source of truth until its supplied scope, canonical scope, and canonical
  source target have passed the workspace boundary and shared hard-deny checks, followed by the
  source type, size, and text checks in this unit. A missing `AGENTS.md` candidate is normal and
  produces no source.
- Before any `WorkspaceBoundary` or filesystem call, pass the supplied scope through CAH-026's pure
  lexical admission helper, catch only its fixed `RepositoryPathSyntaxError`, map that rejection to
  `invalid_instruction_scope`, then pass the normalized components to the hard-deny classifier. This order rejects non-string values, lone surrogates,
  NUL, empty/absolute paths, and every `..` component before construction, resolution, or existence
  inspection. A hard-denied supplied scope maps to `instruction_scope_unavailable` before target
  resolution.
- `.gitignore` does not suppress `AGENTS.md`: instruction files are control-plane input found only at
  exact ancestor locations. Discovery never loads an ancestor `.gitignore` as policy input or invokes
  GitIgnoreSpec. An allowed `AGENTS.md` leaf symlink may resolve to a file literally named
  `.gitignore`; in that deliberate case its bytes are read only as instruction content and receive no
  ignore semantics. The canonical scope plus each resolved instruction target are hard-deny checked
  before content I/O. Either denial uses a fixed unavailable error, avoiding an existence oracle or
  symlink-target bypass.

### Initial reviewed limits

These are conservative byte and item limits, not token estimates. Changing them requires an
explicit contract review rather than a provider-specific adjustment.

| Limit | Initial value | Boundary behavior |
| --- | ---: | --- |
| Ancestor instruction bindings | 16 candidates | A seventeenth existing owner binding fails the bundle. |
| One instruction file | 32 KiB (32,768 bytes) | A file one byte larger is rejected before decode. |
| Aggregate instruction content | 128 KiB (131,072 bytes) | The first binding that would cross the total fails the bundle. |

- Files are read as bytes up to one byte beyond the applicable limit, then decoded with Python's
  strict UTF-8 behavior. Replacement decoding is prohibited. A decoded NUL is not valid instruction
  text.
- Byte counts are the original target byte lengths. Newlines and a UTF-8 byte-order mark, if present,
  are not silently rewritten or stripped. Two owners bound to one target each charge those bytes
  because later provider context contains two separately scoped instruction items.
- Discovery returns an empty successful bundle when no candidate exists. It never substitutes a
  README, provider prompt, home-directory file, or global configuration file.

### Fixed, non-leaking failures

`RepositoryInstructionError` exposes exactly one stable code and fixed message. It does not include
the supplied label, absolute path, file content, raw `OSError`, or decoder details. Boundary errors
are mapped at this API rather than copied verbatim into later provider-visible context.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_instruction_scope` | `Instruction scope must be an existing workspace file or directory.` | the scope is invalid, missing, or an unsupported object |
| `instruction_scope_unavailable` | `Instruction scope is not available.` | the supplied/canonical scope is hard-denied, outside policy, stale, or cannot be inspected safely |
| `instruction_source_unavailable` | `Repository instruction source is not available.` | an exact candidate resolves outside the workspace, to a hard-denied target, or cannot be admitted safely |
| `invalid_instruction_source` | `Repository instruction source must be a regular file.` | an exact candidate exists but is not a regular file |
| `instruction_source_not_text` | `Repository instruction source must be valid UTF-8 text.` | strict decoding fails or decoded content contains NUL |
| `instruction_source_too_large` | `Repository instruction source exceeds the byte limit.` | one source exceeds 32 KiB |
| `instruction_budget_exceeded` | `Repository instructions exceed the binding or byte limit.` | binding count or aggregate bytes exceed their limits |
| `instruction_read_failed` | `Repository instruction source could not be read.` | a bounded local read fails for another reason |

- No partial bundle is returned when an existing candidate fails. Errors and default
  representations contain no supplied label, canonical target, deny rule, instruction content, or
  raw OS text.
- The operation is small, synchronous, and has no internal cancellation protocol. A later loop
  caller checks cancellation before starting it and before any subsequent costly operation.
- CAH-024 remains a best-effort check-before-use boundary. This unit re-resolves the candidate and
  reruns containment plus CAH-026 hard denial immediately before each bounded read, so an
  allowed-to-denied retarget fails without content I/O; it does not claim descriptor-relative race
  protection.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if the unit gains parsing, context
  ranking, provider integration, or is likely to exceed roughly 600 changed production lines. Do
  not pad a smaller coherent implementation.

## Acceptance criteria

1. Root, intermediate, and nearest `AGENTS.md` bindings are returned once in canonical
   root-to-nearest owner order for both file and directory scopes; each carries exact canonical
   target `source` plus candidate-owner `applies_to` provenance.
2. Missing candidates produce an empty or smaller successful bundle without a recursive scan.
3. Every supplied scope passes CAH-026's pure lexical admission before construction/resolution, and
   every source is a regular in-workspace file whose scope and target pass CAH-026's hard denylist,
   is at most 32 KiB, and decodes as strict UTF-8 text without NUL; aggregate binding and byte limits
   are enforced exactly while `.gitignore` is never loaded as policy input.
4. Canonical internal symlinks preserve target provenance and candidate-owner applicability. The
   same target under different owners remains separately bound, while escapes, denied targets,
   VCS/credential scopes, stale roots, and filesystem failures become fixed non-leaking errors.
5. Public contracts are immutable, typed, and documented; representations and failures contain no
   absolute path or instruction content.
6. Focused tests are local and deterministic, and the lesson distinguishes ordered discovery from
   prose interpretation or model obedience.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Scoped precedence | Build root/intermediate/nearest sources and request file plus directory scopes | Unit | Exact canonical target `source`, owner `applies_to`, ranks, contents, and root-to-nearest order |
| No recursive scan | Place unrelated sibling and descendant `AGENTS.md` files | Unit | Neither unrelated source appears |
| Canonical aliases and bindings | Scope through a directory alias; point root and nested candidates at one allowed target | Boundary integration | Canonical owner chain; shared target provenance appears once per distinct `applies_to` binding |
| Candidate-owner scope | Point `pkg/AGENTS.md` to allowed `shared/rules.md` | Boundary integration | `source="shared/rules.md"`, `applies_to="pkg"`, and package precedence never widens to `shared` |
| Lexical scope admission | Pass a valid scalar path, `.`, a non-string object, empty/absolute/`..` paths, NUL, and lone high/low surrogates while spying on `Path`, boundary, and filesystem work | Unit/policy integration | The fixed, content-suppressed `RepositoryPathSyntaxError` maps to `invalid_instruction_scope` before construction/resolution/I/O; valid components reach the shared hard-deny classifier unchanged, and a parity corpus matches CAH-024's established string grammar |
| Hard-deny reuse and ignore exemption | Point a candidate at `secrets/dev.env`, retarget an admitted candidate before read, use a denied scope, place ignored/invalid/oversized ancestor `.gitignore` files, and separately link one candidate to an allowed `.gitignore` target | Policy/boundary integration | Fixed unavailable error before denied content I/O; no ignore-policy file is loaded, a normal ignored `AGENTS.md` still loads, and a leaf target named `.gitignore` is treated only as bounded instruction text |
| Exact limits | Exercise 32,767/32,768/32,769 bytes, 16/17 owner bindings, and aggregate edge including repeated target content | Unit | Success at limits and exact fixed failures above them |
| Text safety | Use invalid UTF-8, NUL, and a valid multibyte boundary | Unit | Strict rejection without replacement or leaked decoder text |
| Containment and leakage | Use escaping symlinks, stale root, VCS scope, and distinctive host names | Boundary integration | Stable code/message and no host path, source text, or raw OS error |

## Validation

- Add focused instruction-discovery tests using temporary workspaces and CAH-024's real boundary.
- Assert exact owner order, canonical target/owner labels, immutable values, binding-counted bytes,
  representations, and the complete failure table.
- Spy on CAH-026's pure lexical and hard-deny helpers plus `Path`, boundary, and filesystem calls to
  prove Unicode/path syntax and supplied-scope denial occur before construction/resolution/I/O, then
  prove canonical scope and candidate-target checks occur before content. Assert that no ancestor
  `.gitignore` is loaded as policy; an explicit candidate target named `.gitignore` is read only as
  bounded instruction content.
- Test each numeric limit below, at, and above its boundary without sleep, subprocess, network, or a
  model fake.
- Keep protocol, transcript, provider, and TUI schemas unchanged; the nearest parity evidence is the
  existing full repository gate.
- Run the focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before
  Done.

## Documentation impact

Update the story and lesson indexes, dependency order, E3 backlog sequence, context-engineering and
safety guidance, glossary entries for instruction source/applicability and precedence, and the
Markdown lesson's compact architecture diagram. Add a planning note for material implementation
discoveries. Do not add or revise a presentation.

## Exclusions

- Parsing instruction prose, resolving conflicting directives, or claiming the model will obey it.
- GitIgnoreSpec evaluation, ordinary-read contracts/limits/errors, configurable policy, arbitrary
  file discovery, source ranking, tokenization, or context-package construction. Only CAH-026's pure
  lexical-path and hard-deny primitives are used here.
- Provider messages, tool schemas or dispatch, MCP, agent-loop continuation, transcripts, protocol,
  TUI rendering, file writes, subprocesses, and network access.
- User-level or home-directory instruction files, multiple roots, remote repositories, and
  descriptor-relative filesystem hardening.

## Definition of done

1. All acceptance criteria map to deterministic happy, boundary, and failure tests.
2. The 16-binding, 32-KiB-per-source, and 128-KiB aggregate limits pass below/at/above tests.
3. Pre-I/O lexical admission, strict UTF-8, canonical target plus owner provenance, hard-deny reuse,
   immutable order, and fixed safe errors are proved without leaks or ignore-policy loading.
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
- Temporary-workspace tests prove exact limits, pre-I/O lexical admission, strict text handling,
  canonical target/owner symlink behavior, hard-denied targets, `.gitignore` policy exemption, and
  safe failures.
- The lesson locates instruction selection between the workspace boundary and later context builder;
  its primary teach-back question is: why must the harness, rather than the LLM, select applicable
  repository instructions?

## Deferred work

- CAH-030 combines discovered instructions with bounded repository sources and atomically enriches an
  existing package with a later bundle.
- CAH-026 first delivers the shared pure lexical/hard-deny helpers plus general read policy; CAH-027
  through CAH-029 implement native read operations.
- CAH-034 discovers the applicable bundle after a successful tool target is admitted and carries the
  enriched context into its follow-up; CAH-035 repeats that rule across the bounded loop.
