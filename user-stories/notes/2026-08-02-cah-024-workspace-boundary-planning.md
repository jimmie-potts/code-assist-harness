# 2026-08-02 CAH-024 workspace-boundary planning

## Purpose

Record the decisions that refine E3's workspace-boundary outcome into one implementation-ready,
single-responsibility unit. This note describes planned behavior only; it does not claim that
`WorkspaceBoundary`, native reads, or repository context are implemented.

## Outcome

CAH-024 will add one immutable Python boundary that owns a canonical-root snapshot and existing-path
containment for every later repository-context capability. The unit stops after returning a
canonical inside-workspace snapshot or a fixed safe failure.

```text
one TUI-selected root -> Python WorkspaceBoundary -> contained path snapshot
                                                \-> fixed non-leaking failure
```

No file content, tool call, provider request, protocol event, or transcript record is part of this
unit.

## Human-decision audit

No unresolved product or architecture decision blocks implementation:

- ADR 0002 already fixes one explicit workspace root per runtime process and assigns context and
  safety decisions to Python rather than the TUI.
- The safety model already requires model-facing paths to be relative, path and symlink escape to be
  rejected, and checks to be repeated before later execution.
- Context engineering already places path containment before instruction discovery, native reads,
  provenance, and budgeting.
- The project's host-first MVP permits a documented residual filesystem race and defers stronger
  descriptor or container enforcement.

The remaining choices are implementation details inside those accepted boundaries and are locked
below so the unit can begin without another design checkpoint.

## Locked decisions

### One reusable Python value

- Add top-level `src/code_assist_harness/workspace.py`.
- `WorkspaceBoundary` is frozen and slotted. `from_path` strictly canonicalizes one existing
  directory and captures its device/inode identity.
- The Python runtime delegates its current root validation to this value. The TUI continues to
  select one root and no protocol field changes.
- `resolve_existing` returns an immutable local canonical path plus its canonical target-relative
  POSIX label. `.` is the label for the root.
- The canonical root and resolved absolute path are excluded from ordinary value representations;
  only the workspace-relative label is safe to show by default.

### Relative, existing paths only

- Empty, absolute, and `..`-containing inputs are invalid before target resolution. A traversal is
  rejected even when lexical normalization would bring it back inside.
- Resolution is strict. A missing requested object is not a proposed create target.
- Internal symlinks are allowed when their canonical targets remain inside the root. Reporting uses
  the target-relative path, not the symlink alias.
- Escaping file and directory symlinks are denied with component-aware containment. A missing
  descendant beneath an escaping directory link is still an escape when that outside ancestor can
  be established.

### Root replacement detection is best effort

- The root's canonical path and device/inode identity are checked before and after resolving a
  target.
- When either snapshot check observes removal, rename, replacement, redirection, or a change away
  from directory type, the boundary produces a stale-root failure.
- The boundary does not retain an open handle to the original root. Once that object is no longer
  referenced, its inode may be recycled for a replacement at the same pathname, so the snapshot
  cannot promise that every replacement is detected.
- A caller selects a new workspace by constructing a new boundary; mutation of the existing value
  is unavailable.

### Fixed failure surface

The planned exception surface is closed:

| Code | Message |
| --- | --- |
| `invalid_workspace_root` | `Workspace root must be an existing directory.` |
| `stale_workspace_root` | `The selected workspace is no longer available.` |
| `invalid_workspace_path` | `Workspace path must be a non-empty relative path.` |
| `workspace_path_not_found` | `Workspace path does not exist.` |
| `workspace_path_outside` | `Workspace path is outside the selected workspace.` |

Neither the requested path, canonical host path, OS message, device, nor inode may enter these
messages or default value representations. Chained local exceptions are not provider, protocol,
diagnostic, or transcript evidence.

## Residual risk and ownership handoff

`resolve_existing` returns a best-effort containment snapshot. Checking the root on both sides of
target resolution catches ordinary observable replacement but cannot prevent a path from changing
after the method returns, being swapped away and back between system calls, or receiving a recycled
device/inode pair after the original root is no longer held.

Future native read tools must call the method again immediately before access and then enforce their
own file-type, ignore, prohibited-location, and output policies. A later security unit can adopt
descriptor-relative traversal, `openat2`, Landlock, or container isolation if the threat model
outgrows host-path snapshots. CAH-024 must not imply those controls already exist.

## Responsibility split

### CAH-024 owns

- canonical root construction and identity;
- relative-path syntax admission;
- strict existing-target resolution;
- internal-symlink canonicalization and escape denial;
- canonical target-relative reporting; and
- bounded root/path failure classification.

### Later E3 units own

- root and nested repository-instruction discovery and precedence;
- list, read, search, and metadata tool schemas and behavior;
- ignore and prohibited-location policy;
- file type, encoding, line, byte, count, and search-result limits;
- context-item provenance, inclusion reasons, and budgets; and
- provider-turn integration and retrieval evaluation.

### Other epics own

- edit/create/delete paths, hashes, diffs, and stale proposals;
- approvals, subprocess execution, and descriptor/container hardening; and
- new TUI, protocol, transcript, or provider surfaces.

## Planned evidence

- Focused temporary-workspace tests cover construction, root reporting, normal descendants,
  internal file and directory symlinks, absolute/traversal input, sibling-prefix and symlink escape,
  missing and dangling targets, escaping missing descendants, and observable root
  removal/replacement/type change.
- Runtime tests prove delegation preserves one-root startup and replaces raw-path errors with the
  fixed boundary surface.
- Exact error-table assertions and distinctive temporary path values prove messages do not leak.
- The Markdown lesson locates CAH-024 between runtime selection and future context/read tools while
  showing provider, tool, and evidence boundaries as unchanged. The frozen deck is not planned
  evidence.
- Focused tests and `./scripts/check` must pass before the story moves from Planned to Done.

The six-slide planned visual companion was duplicated from the established CAH-023 lesson pattern
and edited through artifact-tool. Every source and final slide was inspected individually, the
template-fidelity check passed with zero issues, and the presentation overflow test reported
`Test passed. No overflow detected.` These checks validate the historical planning artifact only;
they are not evidence that `WorkspaceBoundary` or any read behavior exists. The deck is now frozen
and may contradict later design corrections; this note, the story, and the Markdown lesson govern.
Its known obsolete terms are `WorkspacePathError`, `WorkspacePath`, and “5 fixed error classes”;
the authoritative contract uses one `WorkspaceBoundaryError`, one `ResolvedWorkspacePath`, and five
stable error codes.

## Lesson format handoff

CAH-024 is the final unit with a historical visual lesson. All committed presentation files are
frozen. Starting with CAH-025, each implementation-ready story keeps its concise Markdown learning
companion and embedded architecture diagram, but no PowerPoint deck is part of the unit. Historical
decks and their validation evidence remain unchanged even when later design corrections diverge.

## Implementation handoff

Begin with the immutable values and fixed exception table in `workspace.py`, then add focused tests
before changing runtime delegation. Do not add instruction discovery or a read tool to make the
boundary appear more useful; the deliberately small seam is what lets those later units share one
well-tested security decision.
