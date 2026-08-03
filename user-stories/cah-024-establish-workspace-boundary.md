# CAH-024 - Establish the workspace boundary

- **Status:** Planned
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
  immutable resolved-path value, and one bounded boundary exception.
- Construct the boundary through `WorkspaceBoundary.from_path(...)`, canonicalizing one existing
  directory and capturing its filesystem identity.
- Resolve existing model-facing relative paths through `resolve_existing(...)`, following symlinks
  and returning a best-effort containment snapshot when the observed canonical target is beneath
  the captured root.
- Admit every model-facing path string only after it survives a strict UTF-8 encode/decode
  round-trip; reject lone surrogates before constructing a `Path` or making any filesystem call.
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
- NUL, absolute paths, and any `..` component are rejected in the same pre-filesystem admission
  stage, including a traversal that would normalize back inside the root. `.` components may be
  normalized; `.` alone names the root.
- Resolution is strict: the requested object and every traversed component must exist. This unit
  does not admit a missing leaf or use a closest-existing-ancestor rule because it performs no create
  or edit operation.
- Symlinks are followed. A symlink whose canonical target stays inside the root is accepted; its
  result reports the target's canonical relative path rather than the requested alias. A file or
  directory symlink whose target leaves the root is rejected.
- Containment is path-component aware. A sibling such as `/workspace-copy` is not inside
  `/workspace`, and string-prefix comparison is prohibited.
- This unit decides only existence and containment. Future read tools remain responsible for file
  type, ignore policy, prohibited locations, byte/count limits, and whether the target is suitable
  for their operation.

### Fixed, non-leaking failures

`WorkspaceBoundaryError` carries exactly one stable code and its corresponding fixed message. It
does not include the supplied path, canonical host path, `OSError`, inode, or environment value.
The original exception may be chained for local debugging but must not become provider, protocol,
diagnostic, or transcript content.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_workspace_root` | `Workspace root must be an existing directory.` | construction cannot resolve an accessible directory |
| `stale_workspace_root` | `The selected workspace is no longer available.` | a snapshot check observes that the captured root is missing, redirected, replaced, or no longer a directory |
| `invalid_workspace_path` | `Workspace path must be a non-empty relative path.` | input is empty, bytes-valued, not a strict Unicode-scalar/UTF-8 round-trip, contains NUL, is absolute, contains `..`, or is otherwise not a valid path value |
| `workspace_path_not_found` | `Workspace path does not exist.` | strict target resolution fails without establishing an escape |
| `workspace_path_outside` | `Workspace path is outside the selected workspace.` | a resolved component or target leaves the canonical root |

Escape takes precedence when the boundary can establish that a symlink resolves outside; otherwise
an inaccessible or dangling target uses the bounded not-found result. Raw filesystem distinctions
are intentionally not exposed.

## Reviewability budget

- **Estimated production-code churn:** 250-400 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
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
4. Empty, bytes-valued, lone-surrogate, NUL-containing, and absolute inputs plus every path
   containing a `..` component fail before any filesystem access with `invalid_workspace_path`;
   valid multibyte scalar paths round-trip unchanged and are not normalized.
5. Component-aware containment rejects symlinked files and directories that resolve outside the
   root, including missing descendants beneath an escaping directory symlink.
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

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Canonical contained path | construct a boundary and resolve `.`, a file, and an internal symlink | unit | immutable values report canonical relative labels without host paths |
| String and syntax admission | try bytes-valued, lone-surrogate, empty, NUL, absolute, `..`, and sibling-prefix paths; include a valid multibyte scalar path | unit | exact fixed code, zero filesystem calls for invalid strings, and unchanged UTF-8 round-trip for valid text |
| Symlink escape | resolve file, directory, and missing-descendant escapes | unit | `workspace_path_outside` without requested or canonical path leakage |
| Missing target | resolve missing and dangling in-workspace paths | unit | `workspace_path_not_found` with no raw `OSError` |
| Root staleness | remove, rename, replace, redirect, and type-change the root | unit | observable replacement produces `stale_workspace_root` |
| Runtime delegation | start with valid and invalid selected roots | integration | current argv, readiness, protocol, and TUI behavior remain unchanged |

## Validation

- Add focused `tests/test_workspace.py` coverage for construction, canonical reporting, `.` root
  reporting, normal and multibyte-scalar descendants, internal file and directory symlinks,
  bytes-valued and lone-surrogate strings, empty, NUL, absolute and traversal inputs, sibling-prefix
  escapes, dangling links, missing targets, escaping missing descendants, root removal, observable
  root replacement, and root type changes.
- For lone-surrogate and other pre-admission failures, inject filesystem spies and assert that path
  construction/resolution, existence checks, and stat operations are never reached.
- Update runtime tests to prove the existing CLI accepts one canonical workspace and maps invalid
  root construction to its bounded startup failure without leaking the supplied path.
- For observable replacement coverage, rename the original root so it remains referenced, create a
  replacement at the captured pathname, assert that its device/inode differs, and then resolve. This
  keeps the test independent of inode-reuse behavior.
- Assert the exact failure-code/message table and check messages plus value representations against
  distinctive temporary path names and raw OS text.
- Use temporary directories and local filesystem operations only; no subprocess, provider, network,
  sleep, or protocol fixture is required for the focused boundary evidence.
- Run `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_workspace.py
  tests/test_runtime.py` and the canonical `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache
  ./scripts/check`.

## Documentation impact

Update `README.md`, `docs/architecture.md`, `docs/context-engineering.md`, `docs/safety-model.md`,
`docs/glossary.md`, the story and lesson indexes, and the backlog with the implemented boundary,
its canonical-reporting rule, fixed failures, and residual check/use risk. Reconcile the Markdown
lesson to the exact modules and tests. Do not add a presentation; the Markdown diagram carries the
architecture position.

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

## Planned evidence

- `src/code_assist_harness/workspace.py` and `tests/test_workspace.py` implement and prove the
  narrow boundary.
- Runtime tests prove delegation preserves the current one-root launch contract and removes raw-path
  startup errors.
- The Markdown lesson locates CAH-024 between runtime workspace selection and future context/read
  tools while keeping provider, tool, and evidence changes absent. No presentation is planned
  evidence for CAH-024.
- Focused tests and the repository-wide non-live gate pass before the story moves to Done.

## Deferred work

- The next E3 unit discovers root and nested repository instructions using this boundary.
- Later native read-tool units add type/ignore/output policy and must call `resolve_existing` again
  immediately before access.
- A later executor-hardening unit may replace snapshot-only containment with descriptor-relative or
  sandbox-enforced access when the threat model justifies its platform and operational cost.
