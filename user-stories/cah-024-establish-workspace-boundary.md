# CAH-024 - Establish the workspace boundary

- **Status:** Done
- **Milestone / epic:** M2 - Read-only coding assistant / E3 - Repository context and read-only
  tools
- **Dependencies:** CAH-023
- **Lesson:** [Workspace boundary](../docs/lessons/cah-024-workspace-boundary.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness ownership of containment and the residual risk between checking and
  using a path
- **Planning note:**
  [CAH-024 workspace-boundary planning](notes/2026-08-02-cah-024-workspace-boundary-planning.md)

## User story

> As a user, I want every future repository-context path resolved against one validated workspace
> so that the agent cannot inspect unrelated filesystem locations.

## Single responsibility

CAH-024 owns only the reusable Python path-containment boundary. It turns the already selected
runtime workspace into an immutable root and resolves one existing relative path into a canonical
inside-workspace path or one bounded failure. It does not read repository content, discover
instructions, expose a tool, or add another agent-loop step.

## Scope

- Add top-level `src/code_assist_harness/workspace.py` with an immutable `WorkspaceBoundary`, an
  immutable resolved-path value, one pure `normalize_workspace_relative_path(value: str)` lexical
  primitive, and one bounded boundary exception.
- Construct the boundary through `WorkspaceBoundary.from_path(...)`, canonicalizing one existing
  directory and capturing its filesystem identity.
- Resolve existing model-facing relative paths through `resolve_existing(...)`, following symlinks
  and returning a best-effort containment snapshot when the observed canonical target is beneath
  the captured root.
- Admit every model-facing path string only after it survives the shared 4,095-byte,
  256-component, 255-byte-per-component lexical budget and a strict UTF-8 encode/decode round-trip;
  reject an over-bound value or lone surrogate before constructing a `Path` or making any
  filesystem call.
- Return both the canonical absolute path for later local use and its canonical, workspace-relative
  POSIX label for later provider and evidence use.
- Move or delegate the Python runtime's existing root validation to this boundary without changing
  launch arguments, readiness behavior, protocol fields, or the TUI's workspace selection.
- Cover canonical roots, normal descendants, root reporting, internal symlinks, escape attempts,
  missing paths, and observable stale or replaced roots with deterministic temporary-workspace
  tests.

## Locked contract

### Ownership and public API

- `WorkspaceBoundary` is a frozen, slotted Python value in
  `src/code_assist_harness/workspace.py`. The Python harness owns it; TypeScript, provider adapters,
  transcripts, and repositories do not make containment decisions.
- `WorkspaceBoundary.from_path(value)` is the only constructor. It accepts a string or path-like
  root, expands a leading user marker for the explicitly supplied local root, resolves it strictly,
  requires a directory, and captures the canonical path plus its device and inode identity.
- The boundary exposes the canonical root for local composition but does not expose the originally
  supplied alias. Runtime startup keeps accepting the same one `--workspace PATH` argument and
  stores the boundary rather than maintaining a second path-validation implementation.
- `WorkspaceBoundary.resolve_existing(value)` accepts one string or path-like relative path and
  returns an immutable `ResolvedWorkspacePath` containing:
  - `absolute_path`: the canonical absolute target for local filesystem work; and
  - `relative_path`: the canonical target-relative `PurePosixPath`, using `.` for the root.
- The boundary's canonical root and the resolved value's `absolute_path` are excluded from their
  representations. A default diagnostic or assertion representation may show the safe relative
  label, but never a host path.
- `ResolvedWorkspacePath` is a containment snapshot, not authorization and not an open file. A
  future caller must resolve again immediately before filesystem access.
- `normalize_workspace_relative_path(value)` is the sole model-facing lexical owner. It accepts
  exactly `str`, returns the normalized tuple of non-`.` components (`()` for root `.`), and performs
  no `Path` construction, root inspection, resolution, policy evaluation, or filesystem I/O.
  `resolve_existing` obtains a non-bytes `str` from its local path-like API and then calls the same
  primitive. CAH-026 delegates to it while translating only exception vocabulary.

### Root identity and staleness

- Construction records `st_dev` and `st_ino` from the canonical root. Resolution checks that the
  stored root path still resolves to itself, is a directory, and has the same identity before and
  after target resolution.
- If either snapshot check observes a missing, moved, replaced, type-changed, or newly redirected
  root, the boundary reports it as stale. The runtime creates a new boundary only through an
  explicit new workspace selection.
- Device and inode identity is a best-effort replacement signal, not a non-reusable anchor. Once the
  original directory is no longer held open, the filesystem may recycle its inode for a replacement
  at the same pathname. Two identity checks narrow ordinary replacement races but cannot guarantee
  that every replacement or swap is detected. Descriptor-based traversal and access remain a later
  hardening unit.

### Relative-path admission and canonical reporting

- Model-facing inputs are non-empty relative Linux paths. `resolve_existing` first obtains a `str`
  value (a bytes-valued `PathLike` is invalid), encodes it with strict UTF-8, decodes those bytes
  with strict UTF-8, and requires exact equality with the original string. This admits Unicode
  scalar values without normalization and rejects every lone surrogate before `Path` construction,
  `stat`, `resolve`, existence checks, or any other filesystem access.
- The complete supplied string is at most 4,095 strict-UTF-8 bytes before dot or repeated-separator
  normalization, contains at most 256 normalized non-`.` components, and each component is at most
  255 strict-UTF-8 bytes. All ceilings are inclusive. A constant-time `len(value) > 4095` necessary
  check may reject before encoding; any shorter value is strictly encoded once, then the byte and
  component limits are applied. Counting the raw spelling first prevents redundant `./` segments
  from hiding input work, while the normalized-component limit bounds later ancestor work.
- NUL, absolute paths, and any `..` component are rejected in the same pre-filesystem admission
  stage, including a traversal that would normalize back inside the root. `.` components may be
  normalized; `.` alone names the root.
- Resolution is strict: the requested object and every traversed component must exist. This unit
  does not admit a missing leaf or use a closest-existing-ancestor rule because it performs no create
  or edit operation.
- Symlinks are followed. A symlink whose canonical target stays inside the root is accepted; its
  result reports the target's canonical relative path rather than the requested alias. A file or
  directory symlink whose target leaves the root is rejected.
- Resolution advances from the last contained canonical prefix and checks every next existing
  prefix. A path that follows a directory symlink outside the root is rejected immediately even if
  a later outside symlink would point back inside; final-target containment alone is insufficient.
- Containment is path-component aware. A sibling such as `/workspace-copy` is not inside
  `/workspace`, and string-prefix comparison is prohibited.
- This unit decides only existence and containment. Future read tools remain responsible for file
  type, ignore policy, prohibited locations, byte/count limits, and whether the target is suitable
  for their operation.
- These are harness application budgets, not portability claims. Linux commonly exposes a
  4,096-byte pathname buffer including the terminating NUL and 255-byte names, but mount-specific
  limits vary, the selected root consumes bytes when an absolute path is formed, and WSL DrvFS may
  accept or reject different names than the distro filesystem. An input admitted at this lexical
  ceiling can therefore still receive the existing bounded resolution failure; tests do not claim
  that a 4,095-byte relative path can be created on every supported mount.

### Fixed, non-leaking failures

`WorkspaceBoundaryError` carries exactly one stable code and its corresponding fixed message. It
does not include the supplied path, canonical host path, `OSError`, inode, or environment value.
The original exception may be chained for local debugging but must not become provider, protocol,
diagnostic, or transcript content.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_workspace_root` | `Workspace root must be an existing directory.` | construction cannot resolve an accessible directory |
| `stale_workspace_root` | `The selected workspace is no longer available.` | a snapshot check observes that the captured root is missing, redirected, replaced, or no longer a directory |
| `invalid_workspace_path` | `Workspace path must be a non-empty relative path.` | input is empty, bytes-valued, over the shared path byte/component/name budget, not a strict Unicode-scalar/UTF-8 round-trip, contains NUL, is absolute, contains `..`, or is otherwise not a valid path value |
| `workspace_path_not_found` | `Workspace path does not exist.` | strict target resolution fails without establishing an escape |
| `workspace_path_outside` | `Workspace path is outside the selected workspace.` | a resolved component or target leaves the canonical root |

Every lexical failure, including a size failure, precedes root inspection and filesystem work.
Escape takes precedence when an admitted path lets the boundary establish that a symlink resolves outside; otherwise
an inaccessible or dangling target uses the bounded not-found result. Raw filesystem distinctions
are intentionally not exposed.

## Reviewability budget

- **Estimated production-code churn:** 250-400 changed lines.
- **Delivered production-code churn:** 387 changed lines (342 additions and 45 deletions).
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** One contract neighborhood: runtime-selected root and model-facing relative
  path -> immutable workspace boundary/resolved canonical label -> CAH-025 instruction and CAH-026
  read-policy consumers.
- **Split rule:** stop and refine another story before review if the unit gains filesystem-read,
  instruction-discovery, tool-registration, or agent-loop responsibility, or is likely to exceed
  roughly 600 changed production lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One frozen `WorkspaceBoundary` owns a canonical directory root and its captured device/inode
   identity; callers cannot construct an unvalidated boundary.
2. The Python runtime reuses the boundary for its existing workspace validation without changing the
   single-root CLI, protocol v1, readiness handshake, or TUI behavior.
3. `resolve_existing` accepts `.`, regular descendants, and internal file or directory symlinks and
   returns canonical absolute and target-relative paths.
4. Empty, bytes-valued, lone-surrogate, NUL-containing, absolute, traversal, and over-bound inputs
   fail before any filesystem access with `invalid_workspace_path`; exact 4,095-byte,
   256-component, and 255-byte-name endpoints pass pure lexical admission, valid multibyte scalar
   paths round-trip unchanged, and no Unicode normalization occurs.
5. Component-aware containment rejects symlinked files and directories that resolve outside the
   root, including missing descendants beneath an escaping directory symlink and a later symlink
   that would re-enter the workspace after an earlier escape.
6. Missing and dangling in-workspace paths fail with `workspace_path_not_found`; no create-target or
   closest-existing-ancestor behavior is introduced.
7. A snapshot check that observes a missing, renamed, replaced, redirected, or type-changed root
   fails with `stale_workspace_root`; the contract documents that inode reuse or a swap between
   checks may evade this best-effort detection.
8. Every public value and exception is typed and documented; exception strings and value
   representations contain no supplied or canonical host path or raw OS failure.
9. Focused tests include a happy path and meaningful traversal, symlink-escape, missing-target, and
   stale-root failures without network, provider, subprocess, or timing dependence.
10. The Markdown lesson remains explicitly planned until implementation, then traces the concrete
    path, at least one failure test, and the full repository gate. No presentation is part of
    CAH-024; the Markdown lesson and compact text diagram are the only learning artifacts.

## Acceptance-to-test matrix

| Contract or risk | Implemented test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Canonical contained path | construct a boundary and resolve `.`, a file, and an internal symlink | unit | immutable values report canonical relative labels without host paths |
| String, syntax, and work admission | try bytes-valued, lone-surrogate, empty, NUL, absolute, `..`, and sibling-prefix paths; exercise complete bytes 4,094/4,095/4,096, names 254/255/256 bytes, and 255/256/257 normalized components with multibyte controls | unit | exact fixed code and zero `Path`, root, or filesystem calls for invalid strings; endpoints pass only the pure lexical gate, without claiming the host mount can create the longest value |
| Symlink escape | resolve file, directory, missing-descendant, and escape-then-re-enter paths | unit | first established outside prefix produces `workspace_path_outside` without requested or canonical path leakage |
| Missing target | resolve missing and dangling in-workspace paths | unit | `workspace_path_not_found` with no raw `OSError` |
| Root staleness | remove, rename, replace, redirect, and type-change the root | unit | observable replacement produces `stale_workspace_root` |
| Runtime delegation | start with valid and invalid selected roots | integration | current argv, readiness, protocol, and TUI behavior remain unchanged |

## Validation

- Focused `tests/test_workspace.py` coverage exercises construction, canonical reporting, `.` root
  reporting, normal and multibyte-scalar descendants, internal file and directory symlinks,
  bytes-valued and lone-surrogate strings, empty, NUL, absolute and traversal inputs, sibling-prefix
  escapes, dangling links, missing targets, escaping missing descendants, escape-then-re-enter
  chains, root removal, observable root replacement, and root type changes.
- For lone-surrogate and other pre-admission failures, inject filesystem spies and assert that path
  construction/resolution, existence checks, and stat operations are never reached.
- Test the pure lexical primitive independently at 4,094/4,095/4,096 bytes,
  254/255/256 bytes for one component, and 255/256/257 normalized components. Construct the
  4,095-byte endpoint from sixteen 255-byte names and fifteen separators; construct the 4,096-byte
  case with only legal-size names so the aggregate limit is isolated. Use ASCII plus a multibyte
  scalar to prove byte rather than character counting. Do not create the aggregate endpoint on disk
  or treat lexical admission as a `PATH_MAX` guarantee.
- Runtime tests prove the existing CLI accepts one canonical workspace and maps invalid
  root construction to its bounded startup failure without leaking the supplied path.
- Observable-replacement coverage renames the original root so it remains referenced, creates a
  replacement at the captured pathname, assert that its device/inode differs, and then resolve. This
  keeps the test independent of inode-reuse behavior.
- The tests assert the exact failure-code/message table and check messages plus value representations against
  distinctive temporary path names and raw OS text.
- Tests use temporary directories and local filesystem operations only; no subprocess, provider, network,
  sleep, or protocol fixture is required for the focused boundary evidence.
- The focused workspace/runtime suite and canonical
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passed. The canonical gate reported 1,015
  Python tests with one live smoke deselected, 32 Python protocol cases, 48 repository-policy tests,
  240 TUI tests, 31 TypeScript protocol cases, and four real Node-to-Python integration cases, plus
  passing type, lint, and format checks.

## Documentation impact

Update `README.md`, `docs/architecture.md`, `docs/context-engineering.md`, `docs/safety-model.md`,
`docs/glossary.md`, `docs/walking-skeleton.md`, the story and lesson indexes, and the backlog with
the implemented boundary, its canonical-reporting rule, fixed failures, and residual check/use risk.
Reconcile the Markdown lesson to the exact modules and tests. Do not add a presentation; the Markdown
diagram carries the architecture position.

## Exclusions

- Repository-instruction discovery, precedence, `AGENTS.md` parsing, context selection, context
  budgeting, provenance records, or provider-request construction.
- File listing, reads, search, metadata tools, ignore rules, prohibited-location policy, content or
  line limits, binary detection, or tool schemas and registration.
- Any protocol, fixture, TUI, provider, transcript, approval, or agent-loop behavior change.
- Missing-leaf resolution, structured edits, deletes, diffs, file-hash preconditions, or workspace
  writes.
- Descriptor-relative I/O, `openat2`, sandboxing, filesystem watching, replacement locks, or a claim
  that path-resolution snapshots eliminate time-of-check/time-of-use races.
- Multiple workspace roots, native Windows or macOS paths, remote repositories, archives, or virtual
  filesystems.

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | The selected-root alias is construction input only; the canonical root plus captured device/inode identify the boundary, the execution-time canonical target identifies a resolved path, and only its workspace-relative POSIX label is model-visible. Semantic owner, provenance source, and cache/accounting identity are N/A for this containment-only unit. |
| End-to-end contract | Runtime `--workspace` selection -> `WorkspaceBoundary.from_path` -> stored boundary -> `resolve_existing` -> immutable canonical target/label or fixed error; runtime integration proves the existing readiness/protocol path, and CAH-025/026 consume this API. Evaluation wiring is N/A until the later M2 evaluation unit. |
| Failure and atomicity | Construction or resolution returns one immutable value or one fixed error; invalid Unicode/path syntax reaches zero filesystem calls, stale/escape/missing checks return no target, and no content or tool operation can execute. Cancellation, deadline, and rollback are N/A for this synchronous boundary; the documented post-check pathname race remains. |
| Reachable boundaries | The real boundary and runtime entry exercise accepted scalar paths, every pre-I/O syntax rejection, internal/escaping symlinks, sibling-prefix containment, and observable root removal/replacement before and after target resolution. The inclusive 4,095-byte raw-path, 256-component, and 255-byte-name ceilings are tested independently; a scheduler seam is N/A. |
| Closed grammar and cardinality | One selected existing directory and one non-empty relative Linux path are admitted; `.` is the sole root label, `..`, absolute, NUL, bytes-valued, and lone-surrogate paths are closed out, and exactly five fixed error variants cover construction/resolution. No collection duplicate policy applies. |
| Artifact parity | Story, lesson, compact diagram, architecture/context/safety docs, and test matrix use the same order: construct canonical root -> pre-I/O path admission -> root snapshot -> strict target resolution/containment -> root snapshot -> canonical label, with the same fixed failure precedence and residual race caveat. |
| Independent lenses | Security/identity review covers component containment, symlinks, staleness, and leak-free values; handoff/composition review covers runtime plus CAH-025/026 callers; provider/protocol/limits/scheduler review records those boundaries unchanged and scheduler behavior as N/A. |

## Definition of done

1. All ten acceptance criteria map to deterministic happy-path, boundary, or meaningful failure
   evidence in the matrix and focused tests.
2. Construction and resolution are typed, documented, immutable, expose only the intentional
   public API, and prove strict Unicode-scalar/UTF-8 admission before filesystem access.
3. Stable error codes, messages, and ordinary representations reveal no supplied path, host path,
   raw OS error, device, or inode.
4. Runtime delegation preserves the existing one-root CLI, readiness, protocol, provider, TUI, and
   transcript contracts.
5. Focused tests and the canonical offline `./scripts/check` pass without a model, network,
   subprocess, or timing dependency.
6. The story, planning note, conceptual docs, indexes, and Markdown lesson agree with the delivered
   boundary and its residual check/use risk.
7. The completed lesson replaces pseudocode with focused repository-backed implementation and
   failure-test excerpts; no presentation is added or changed.
8. Delivered production-source churn is recorded and remains within the reviewability target, or
   the work is split before review.
9. The PR is ready for review and every addressed inline review thread is resolved.

## Implementation evidence

- `src/code_assist_harness/workspace.py` and `tests/test_workspace.py` implement and exercise the
  narrow boundary, including bounded lexical admission, canonical reporting, internal and escaping
  symlinks, escape-then-re-enter rejection, missing targets, canonical-label re-admission, and root
  staleness.
- Runtime tests exercise delegation while preserving the current one-root launch contract and
  replacing raw-path startup errors with the fixed boundary surface.
- The Markdown lesson locates CAH-024 between runtime workspace selection and future context/read
  tools while keeping provider, tool, and evidence changes absent. No presentation is planned
  evidence for CAH-024.
- The focused tests and repository-wide non-live gate pass with the counts recorded in Validation.

## Deferred work

- CAH-026 is the next E3 unit and adds shared read contracts plus lexical/hard-deny policy by
  delegating CAH-024's path grammar. CAH-025 then discovers root and nested repository instructions
  through those two boundaries.
- Later native read-tool units add type/ignore/output policy and must call `resolve_existing` again
  immediately before access.
- A later executor-hardening unit may replace snapshot-only containment with descriptor-relative or
  sandbox-enforced access when the threat model justifies its platform and operational cost.
