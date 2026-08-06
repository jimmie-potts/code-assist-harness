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
  the scope, using a non-following directory-entry check. Do not recursively walk the repository.
- Return the content-suppressed canonical scope plus immutable bindings in root-to-nearest order.
  Each binding carries the canonical target as source provenance, the canonical candidate-owner
  directory as `applies_to`, strict UTF-8 content, byte counts, and canonical-depth precedence.
- Apply CAH-026's pure lexical-path admission and shared hard-deny classifier before scope resolution
  or instruction-source content reads while deliberately skipping GitIgnoreSpec evaluation for
  control-plane `AGENTS.md` candidates.
- Keep the implementation native Python and synchronous: no subprocess, shell, network, provider,
  protocol, transcript, or TUI change.

## Locked contract

### Ownership, ordering, and precedence

- The Python harness owns instruction discovery. The TUI and provider may display or consume the
  resulting sources but cannot add, remove, reorder, or select instruction files.
- The exact public service is `RepositoryInstructionDiscovery(boundary: WorkspaceBoundary)`. It
  retains that boundary object as a read-only `boundary` identity and exposes
  `discover_for_path(path: str) -> RepositoryInstructions`. Runtime composition creates it once from
  the session's CAH-024 boundary; it never reconstructs a root from a path, environment value, or
  later read-policy object. CAH-026's lexical/hard-deny helpers are pure function dependencies, not a
  second workspace owner.
  The frozen result always contains `canonical_scope`, the canonical workspace-relative file or
  directory admitted for this discovery before a file scope is converted to its parent ancestry.
  It remains present when no `AGENTS.md` candidate exists and is never recomputed from the supplied
  alias after return. Bindings contain canonical workspace-relative `source` and `applies_to` labels,
  content, byte counts, and a precedence rank derived from `applies_to`; values never contain
  absolute host paths.
- The root candidate is first and the nearest candidate is last. Later sources have narrower scope
  and therefore higher precedence. This unit records that order but does not parse prose or merge
  individual directives.
- A binding's precedence rank is the depth of its canonical `applies_to` owner relative to the
  workspace root: `.` is rank 0 and every path segment adds one. The rank is not the binding's tuple
  index. Missing ancestor candidates therefore leave legal gaps, and inserting one later does not
  renumber the existing bindings. Equal-depth owners in sibling subtrees have equal ranks and no
  precedence relationship because neither scope contains the other. Immutable binding construction
  validates `precedence == canonical_depth(applies_to)`; a caller cannot inject or retain a
  position-derived rank.
- `RepositoryInstructions` is created only through one result factory. The factory receives the
  already admitted canonical scope plus its `file`/`directory` kind and the candidate bindings, but
  stores only the content-suppressed canonical label and frozen tuple. It derives the effective
  owner scope as the file's parent or the directory itself, then requires every `applies_to` to be a
  path-segment ancestor of or equal to that scope, every owner to be unique, and each later owner to
  be a strict descendant of the prior owner. Combined with depth-derived ranks, this validates the
  complete root-to-nearest topology without filesystem I/O. An unrelated sibling, duplicate owner,
  reversed pair, or equal-depth pair cannot enter a successful bundle; missing ancestors and their
  numeric rank gaps remain legal. Any canonical-label, rank, or topology construction failure is
  exact `RepositoryInstructionError(code="invalid_instruction_bundle",
  message="Repository instruction bundle is invalid.")`; it is content-suppressed and returns no
  bundle.
- `InstructionBinding` and `RepositoryInstructions` construction share one pure canonical-label
  validator for `source`, `applies_to`, and `canonical_scope`. Production passes only exact
  `.as_posix()` values from CAH-024 `ResolvedWorkspacePath.relative_path` or its canonical ancestor
  chain. The validator admits `.` only for the workspace root; otherwise it requires a non-empty,
  relative POSIX label whose components are already in canonical form, contain neither `.` nor `..`,
  and pass strict Unicode-scalar/UTF-8 plus NUL rejection. It normalizes only for comparison and
  requires the rendered canonical label to equal the supplied text exactly, so absolute, escaping,
  repeated-separator, redundant-dot, NUL, and lone-surrogate spellings fail rather than entering a
  bundle. A backslash is an ordinary legal Ubuntu filename character, not an alternate separator.
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
  source type, size, and text checks in this unit. Immediately before the non-following leaf probe
  and again immediately before the bounded content read, re-admit the captured candidate-owner label
  through CAH-024 and require it to resolve to the same canonical directory. Owner disappearance,
  type change, or allowed-to-allowed retarget already present at either deterministic checked seam
  fails as `instruction_source_unavailable`; those mutations cannot preserve `applies_to=A` while
  selecting `B/AGENTS.md`. Probe each exact
  `AGENTS.md` directory entry without following it. Only the exact leaf proved absent beneath a still-admitted owner is normal
  and produces no source. A present dangling or looping symlink, an entry that disappears after the
  probe, or another candidate that cannot be resolved and admitted safely fails with
  `instruction_source_unavailable`; it is never downgraded to a missing candidate. A non-absence
  error from the probe or loss of the owner fails with that same code.
- Before any `WorkspaceBoundary` or filesystem call, pass the supplied scope through CAH-026's pure
  lexical admission helper, catch only its fixed `RepositoryPathSyntaxError`, map that rejection to
  `invalid_instruction_scope`, then pass the normalized components to the hard-deny classifier. This order rejects non-string values, lone surrogates,
  NUL, empty/absolute paths, and every `..` component before construction, resolution, or existence
  inspection. A hard-denied supplied scope maps to `instruction_scope_unavailable` before target
  resolution.
- That delegated lexical call inherits CAH-024's inclusive 4,095-byte,
  256-normalized-component, and 255-byte-per-component input budget. An over-bound scope maps to
  `invalid_instruction_scope` before `Path`, hard-deny classification, owner discovery, or any
  filesystem probe. The later canonical-label factory remains a syntax/provenance defense for
  filesystem-produced labels; it does not claim that a short symlink alias bounds the length of its
  canonical target.
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
- Discovery returns the admitted `canonical_scope` plus an empty binding tuple when no candidate
  exists. It never substitutes a README, provider prompt, home-directory file, or global
  configuration file.

### Fixed, non-leaking failures

`RepositoryInstructionError` exposes exactly one stable code and fixed message. It does not include
the supplied label, absolute path, file content, raw `OSError`, or decoder details. Boundary errors
are mapped at this API rather than copied verbatim into later provider-visible context.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_instruction_scope` | `Instruction scope must be an existing workspace file or directory.` | the scope is invalid, missing, or an unsupported object |
| `instruction_scope_unavailable` | `Instruction scope is not available.` | the supplied/canonical scope is hard-denied, outside policy, stale, or cannot be inspected safely |
| `instruction_source_unavailable` | `Repository instruction source is not available.` | an exact candidate is present but dangling, looping, disappears after its non-following probe, resolves outside the workspace or to a hard-denied target, or otherwise cannot be admitted safely |
| `invalid_instruction_source` | `Repository instruction source must be a regular file.` | an exact candidate exists but is not a regular file |
| `instruction_source_not_text` | `Repository instruction source must be valid UTF-8 text.` | strict decoding fails or decoded content contains NUL |
| `instruction_source_too_large` | `Repository instruction source exceeds the byte limit.` | one source exceeds 32 KiB |
| `instruction_budget_exceeded` | `Repository instructions exceed the binding or byte limit.` | binding count or aggregate bytes exceed their limits |
| `instruction_read_failed` | `Repository instruction source could not be read.` | a bounded local read fails for another reason |
| `invalid_instruction_bundle` | `Repository instruction bundle is invalid.` | the sole result factory rejects canonical label, rank, owner uniqueness, or root-to-nearest topology |

- No partial bundle is returned when an existing candidate fails. Errors and default
  representations contain no supplied label, canonical target, deny rule, instruction content, or
  raw OS text.
- The operation is small, synchronous, and has no internal cancellation protocol. A later loop
  caller checks cancellation before starting it and before any subsequent costly operation.
- CAH-024 remains a best-effort check-before-use boundary. This unit re-resolves the candidate and
  reruns containment plus CAH-026 hard denial immediately before each bounded read, so an
  allowed-to-denied retarget or post-probe disappearance observed at that recheck fails as
  `instruction_source_unavailable` without content I/O; it does not claim descriptor-relative race
  protection. Any path mutation after the final re-admission and before resolution/open can still
  race this pathname-based design.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: admitted canonical scope from CAH-024/026 ->
  bounded owner/source discovery and immutable `RepositoryInstructions` bundle -> CAH-030 initial
  context and later scoped-enrichment consumers.
- **Split rule:** stop and refine another story before review if the unit gains parsing, context
  ranking, provider integration, or is likely to exceed roughly 600 changed production lines. Do
  not pad a smaller coherent implementation.

## Acceptance criteria

1. One `RepositoryInstructionDiscovery` retains the exact CAH-024 boundary identity and every success
   retains the admitted canonical scope. Root, intermediate, and nearest
   `AGENTS.md` bindings are returned once in canonical root-to-nearest owner order for both file and
   directory scopes; each carries exact canonical target `source` plus candidate-owner `applies_to`
   provenance. Each rank equals canonical `applies_to` depth, so gaps are legal and equal-depth
   siblings do not imply precedence. The result factory rejects unrelated, duplicate, equal-depth,
   or reordered owners against the supplied file-parent/directory scope.
2. An exact non-following entry probe treats only a proved-absent leaf beneath a still-admitted owner
   as missing and produces an empty or smaller successful bundle without a recursive scan. A probe
   error, owner loss, present dangling or looping symlink, post-probe disappearance, or unsafe
   resolution fails the whole bundle as `instruction_source_unavailable`.
3. Every supplied scope passes CAH-026's pure lexical admission before construction/resolution, and
   every source is a regular in-workspace file whose scope and target pass CAH-026's hard denylist,
   is at most 32 KiB, and decodes as strict UTF-8 text without NUL; aggregate binding and byte limits
   are enforced exactly while `.gitignore` is never loaded as policy input.
4. Canonical internal symlinks preserve target provenance and candidate-owner applicability. The
   same target under different owners remains separately bound, while escapes, denied targets,
   VCS/credential scopes, stale roots, and filesystem failures become fixed non-leaking errors.
5. Public contracts are immutable, typed, and documented; the shared exact canonical-label gate
   prevents absolute/escaping/non-canonical values, and representations and failures contain no host
   path or instruction content.
6. Focused tests are local and deterministic, and the lesson distinguishes ordered discovery from
   prose interpretation or model obedience.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Service identity, precedence, and topology | Assert the exact constructor/method signature and retained boundary identity; build root/intermediate/nearest sources and request file plus directory scopes; compare separate sibling scopes; omit an intermediate candidate, then insert it on a later call; mutate a binding rank; and feed the result factory an unrelated sibling, duplicate owner, reversed chain, and equal-depth pair | Unit/result boundary | Service never reconstructs workspace state; exact canonical target `source`, owner `applies_to`, canonical-depth ranks, contents, and root-to-nearest order; sibling owners have the same depth only across separate bundles, the first result has a rank gap, the later insertion fills it without renumbering existing bindings, and every forged label/rank/topology raises exact `invalid_instruction_bundle` before a bundle exists |
| Exact non-following probe and owner identity | Exercise a truly absent leaf under a still-admitted owner, dangling and looping symlinks, an entry removed after the probe, owner loss, an unsafe resolving target, and captured owner `A` replaced by an allowed symlink to `B` before the probe or before read | Boundary integration | Only true leaf absence is skipped; every probe error, owner mismatch, or present-but-unavailable case fails atomically as `instruction_source_unavailable` without reading replacement source bytes or returning `applies_to=A` for `B/AGENTS.md` |
| No recursive scan | Place unrelated sibling and descendant `AGENTS.md` files | Unit | Neither unrelated source appears |
| Canonical aliases and bindings | Scope through a directory alias; point root and nested candidates at one allowed target | Boundary integration | Canonical owner chain; shared target provenance appears once per distinct `applies_to` binding |
| Stable canonical scope | Discover through `alias -> A` with no instruction files, then retarget the alias to `B` after return | Boundary integration | The empty success retains `canonical_scope=A`; later callers never need to re-resolve the alias |
| Canonical result labels | Construct bindings/bundles with production `ResolvedWorkspacePath.relative_path.as_posix()` values, then mutate source, owner, and scope to absolute, `..`, repeated-separator, redundant-dot, NUL, and lone-surrogate spellings; retain a filename containing backslash as a Linux control | Unit/result boundary | Only exact canonical workspace-relative labels enter frozen results; every hostile/non-canonical spelling fails content-suppressed before CAH-030/provider serialization, while the backslash filename remains one ordinary component |
| Candidate-owner scope | Point `pkg/AGENTS.md` to allowed `shared/rules.md` | Boundary integration | `source="shared/rules.md"`, `applies_to="pkg"`, and package precedence never widens to `shared` |
| Lexical scope admission | Pass a valid scalar path, `.`, a non-string object, empty/absolute/`..` paths, NUL, lone high/low surrogates, and CAH-024's total-byte/component/name endpoints while spying on `Path`, boundary, and filesystem work | Unit/policy integration | The fixed, content-suppressed `RepositoryPathSyntaxError` maps to `invalid_instruction_scope` before construction/resolution/I/O; valid endpoints reach the shared hard-deny classifier unchanged, and the complete parity corpus matches CAH-024's sole lexical primitive |
| Hard-deny reuse and ignore exemption | Point a candidate at `secrets/dev.env`, retarget an admitted candidate before read, use a denied scope, place ignored/invalid/oversized ancestor `.gitignore` files, and separately link one candidate to an allowed `.gitignore` target | Policy/boundary integration | Fixed unavailable error before denied content I/O; no ignore-policy file is loaded, a normal ignored `AGENTS.md` still loads, and a leaf target named `.gitignore` is treated only as bounded instruction text |
| Exact limits | Exercise 32,767/32,768/32,769 bytes, 16/17 owner bindings, and aggregate edge including repeated target content | Unit | Success at limits and exact fixed failures above them |
| Text safety | Use invalid UTF-8, NUL, and a valid multibyte boundary | Unit | Strict rejection without replacement or leaked decoder text |
| Containment and leakage | Use escaping symlinks, stale root, VCS scope, and distinctive host names | Boundary integration | Stable code/message and no host path, source text, or raw OS error |

## Validation

- Add focused instruction-discovery tests using temporary workspaces and CAH-024's real boundary.
- Assert exact owner order, stable canonical scope including an empty alias result, canonical
  target/owner labels, canonical-depth ranks, immutable values, binding-counted bytes,
  representations, and the complete failure table. Prove a missing intermediate owner leaves a
  rank gap, inserting it on a later discovery fills only that rank, and separate equal-depth sibling
  results express no cross-scope precedence.
- Exercise the sole result factory for directory and file-parent ancestry. Reject unrelated,
  duplicate, reversed, and equal-depth owner tuples with a fixed content-suppressed construction
  failure and no filesystem work or partial value.
- Spy on the exact candidate probe and resolver to prove it does not follow the directory entry,
  only true absence is skipped, and dangling/looping links, post-probe disappearance, and unsafe
  resolution map to `instruction_source_unavailable` with no partial result or content read.
  At seams before probe and read, replace owner `A` with an allowed symlink to `B`; prove exact owner
  re-admission fails before replacement leaf resolution or bytes.
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

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish the supplied scope alias, admitted canonical scope, effective file-parent/directory scope, canonical candidate owner (`applies_to`), resolved canonical source, per-binding byte charge, canonical-depth rank, and model-visible canonical labels. One source used by two owners remains two semantic bindings. |
| End-to-end contract | CAH-026 pure syntax/hard-deny admission plus CAH-024 resolution -> exact root-to-scope `AGENTS.md` probes -> owner/source rechecks -> bounded bindings -> sole topology-validating bundle factory -> CAH-030 initial/enrichment consumers and later loop scope discovery. Evaluation wiring is deferred to CAH-037. |
| Failure and atomicity | Only a proved-absent exact leaf is skipped; a present dangling/looping/retargeted/invalid source, owner mismatch, text failure, or budget overflow returns no partial bundle and reads no replacement content. Cancellation/deadline/rollback are N/A inside this synchronous discovery operation; mutation after final pathname re-admission remains a documented race. |
| Reachable boundaries | Real discovery exercises 32,767/32,768/32,769-byte sources, 16/17 owners, and the 128-KiB aggregate edge, including two owners sharing one target. Deterministic seams cover owner retarget before probe/read, and the lexical corpus reaches CAH-026/024 rather than a synthetic result constructor only. |
| Closed grammar and cardinality | One existing file-or-directory scope, exact `AGENTS.md` leaves only, and at most 16 strict-UTF-8/no-NUL bindings are accepted. Canonical labels use the exact label gate; owners must be unique and form a strict root-to-nearest ancestor chain, with depth-derived ranks and legal gaps. |
| Artifact parity | Story, lesson, diagram, context/safety docs, pseudocode, and tests agree on lexical admission -> canonical ancestry -> owner re-admission -> non-following probe -> source admission -> owner/source recheck -> bounded read -> topology-validating factory, including exact absence/failure precedence. |
| Independent lenses | Security/identity review covers owner/source aliases, hard-deny reuse, ignore exemption, and retargets; handoff/composition review covers CAH-030 and later loop consumers; limits/scheduler review covers binding/byte edges and records provider/protocol/scheduler changes as N/A. |

## Definition of done

1. All acceptance criteria map to deterministic happy, boundary, and failure tests.
2. The 16-binding, 32-KiB-per-source, and 128-KiB aggregate limits pass below/at/above tests.
3. Pre-I/O lexical admission, strict UTF-8, canonical target plus owner provenance, canonical-depth
   precedence including gaps and late insertion, non-following exact-entry probes, hard-deny reuse,
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
  canonical-depth rank gaps and late insertion, exact non-following entry probes, canonical
  target/owner symlink behavior, hard-denied targets, `.gitignore` policy exemption, and safe
  failures.
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
