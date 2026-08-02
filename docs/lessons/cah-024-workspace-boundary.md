# CAH-024 lesson: Establish the workspace boundary

- **Unit:** CAH-024
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; no reusable workspace boundary or native repository read is
  implemented yet
- **Story:** [CAH-024](../../user-stories/cah-024-establish-workspace-boundary.md)
- **Visual companion:** [Workspace boundary](assets/cah-024-workspace-boundary.pptx)
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md),
  [Context engineering](../context-engineering.md), and [Safety model](../safety-model.md)

> This lesson describes an accepted implementation plan. Every code block is explicitly labeled
> pseudocode and is not evidence of shipped behavior.

## Quick summary

CAH-024 plans one immutable Python boundary that converts a selected workspace into safe,
canonical path snapshots for later repository operations. The system-design lesson is that the
harness—not the model, TUI, provider, or repository—owns what “inside this workspace” means.

## Learning objectives

After completing this unit, you should be able to:

- explain canonical paths, filesystem identity, containment, and check/use races;
- locate workspace-path authority inside the Python harness;
- distinguish an internal symlink from a symlink escape;
- test stable, non-leaking boundary failures; and
- explain when snapshot checks should graduate to descriptor-relative or sandboxed access.

## Why this unit matters

Instruction discovery, native reads, search, context provenance, and later edits all accept paths.
If each feature invents its own containment rule, a model can reach a different answer depending on
which tool it asks to use. This unit gives those later capabilities one root and one fail-closed
vocabulary before any repository content enters a provider request.

## Junior engineer foundation

A **relative path** such as `src/app.py` needs a starting directory. An **absolute path** such as
`/etc/passwd` chooses its own start and is therefore never a valid model-facing workspace path.

Canonicalization resolves `.` and symlinks. Suppose `docs/current` points to `docs/v2`:

```text
requested: docs/current/guide.md
canonical: docs/v2/guide.md
reported:  docs/v2/guide.md
```

That link is safe only if the target remains below the captured workspace root. A common beginner
misconception is that checking whether one path string starts with another proves containment.
`/work/project-copy` starts with `/work/project` as text but is its sibling. Paths must be compared
by components after canonical resolution.

A second misconception is that validation makes later access permanently safe. Another process can
replace a directory or symlink after the check. CAH-024 returns a snapshot; future tools must resolve
again immediately before access, and stronger designs bind the check to an open descriptor.

## Key concepts

- **Canonical root:** the resolved absolute directory that anchors every operation.
- **Root identity:** the root's device and inode, captured so an object later installed at the same
  pathname is not silently adopted.
- **Containment:** a component-aware proof that a canonical target is the root or its descendant.
- **Canonical relative label:** the target's provider-safe path below the root; an accepted symlink
  reports its target rather than its alias.
- **Safe representation:** ordinary value and error representations omit canonical host paths.
- **Snapshot:** a true statement at the time of resolution, not an open handle or lasting authority.
- **Fixed failure:** a stable code/message pair that reveals neither a host path nor raw OS text.

## Architecture and design

```text
Ink TUI boundary                 Python harness boundary
select one root -- child argv --> runtime composition
render validated events                |
                                       v
                          [CAH-024 WorkspaceBoundary]
                          canonical root + identity
                          relative path -> contained snapshot
                              |                    |
                 future instruction/context   future native read tools
                              |                    |
                              +---------+----------+
                                        v
Agent-loop boundary              provider port -> provider adapter
(chooses when to retrieve)       (receives selected content, never host paths)

Tool boundary: no tool schema or file access in CAH-024; later tools reuse the boundary.
Evidence boundary: no protocol/transcript record in CAH-024; later evidence uses relative labels.
```

The TUI continues to select exactly one workspace and pass its canonical root at process startup.
Python is authoritative after that handoff. `WorkspaceBoundary.from_path` captures the root;
`resolve_existing` accepts only a non-empty relative path, rejects every `..`, follows symlinks, and
returns the canonical target only when it remains inside the same root.

Internal symlinks stay useful, but their aliases do not become durable provenance. Missing leaves
are rejected because this unit supports future reads, not future creates. Root identity is checked
before and after resolution to detect ordinary replacement, while the residual swap race remains
explicit.

## Practical walkthrough

1. Move the Python root invariant into top-level `workspace.py` and have runtime startup delegate to
   `WorkspaceBoundary.from_path`.
2. Capture the root's canonical path and identity in a frozen value.
3. Validate relative syntax before touching the requested path.
4. Resolve strictly, verify component-aware containment, and compute the canonical relative label.
5. Recheck root identity before returning the snapshot.
6. Test normal paths, internal links, escaping links, missing targets, and root replacement. Keep
   provider, protocol, TUI, and repository-content behavior unchanged.

## Implementation code samples

### Planned pseudocode: the intended public seam

The following is **planned pseudocode**, not repository code:

```python
boundary = WorkspaceBoundary.from_path(selected_root)
resolved = boundary.resolve_existing("docs/current/guide.md")

resolved.absolute_path  # local canonical Path
resolved.relative_path  # PurePosixPath("docs/v2/guide.md")
```

The constructor establishes one trusted anchor. The resolver takes a model-facing relative path.
The two outputs deliberately serve different consumers: local filesystem code needs an absolute
path, while provider and evidence layers must use only the workspace-relative label. The absolute
path is also excluded from the value's ordinary representation so an assertion or debug message
does not expose it by default.

### Planned pseudocode: a meaningful failure test

The following is also **planned pseudocode**, not implemented evidence:

```python
outside = temporary_parent / "outside"
(workspace / "escape").symlink_to(outside, target_is_directory=True)

with raises(WorkspaceBoundaryError) as caught:
    boundary.resolve_existing("escape/secret.txt")

assert caught.value.code == "workspace_path_outside"
assert str(outside) not in str(caught.value)
```

The test makes an ordinary relative request whose symlink target crosses the root. The first
assertion proves fail-closed classification; the second proves that the host path does not become
error content.

## Failure scenarios to study

| Scenario | Responsible boundary | Safe planned result | Planned evidence |
| --- | --- | --- | --- |
| `/etc/passwd` or `../outside` | input admission | `invalid_workspace_path` before resolution | parameterized syntax tests |
| internal file/directory symlink | canonical containment | accept and report target-relative path | symlink happy-path tests |
| symlink to outside | canonical containment | `workspace_path_outside` | file, directory, and missing-descendant tests |
| missing or dangling in-root target | strict resolution | `workspace_path_not_found` | missing-path tests |
| root removed or replaced | identity check | `stale_workspace_root`; adopt nothing | root-mutation tests |
| path changes after return | future caller | re-resolve before access; snapshot makes no guarantee | documented residual-risk test boundary |

## Production expansion

### Example enterprise scenario

A multi-tenant coding service may inspect untrusted repositories while other processes mutate the
same filesystem. A pathname snapshot is then too weak: the service may need descriptor-relative
resolution, an OS sandbox, or an isolated mount per job.

### Typical production capabilities and tools

- [Python `pathlib`](https://docs.python.org/3/library/pathlib.html) provides the local path and
  canonicalization primitives planned for this learning unit.
- [Linux `openat2`](https://man7.org/linux/man-pages/man2/openat2.2.html) can constrain resolution
  relative to an already-open directory descriptor, reducing path-replacement races at the cost of
  Linux-specific code and careful descriptor lifecycle ownership.
- [Linux Landlock](https://docs.kernel.org/userspace-api/landlock.html) can restrict a process's
  filesystem access, adding kernel-version, policy, and test-matrix obligations.
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec) supports isolated
  mount namespaces through a container runtime, adding image, startup, patching, and operations
  cost.

These are comparisons, not approved CAH-024 dependencies.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | one explicit WSL workspace | many isolated tenant workspaces |
| Containment | canonical path plus identity snapshot | descriptor- or sandbox-enforced access |
| Symlinks | internal allowed; escapes rejected | policy may deny all or bind resolution to descriptors |
| Reliability | re-resolve before each later access | handles, watchers, isolation, and recovery |
| Operations | deterministic temporary-directory tests | kernel/runtime compatibility, telemetry, and incident response |
| Cost | small Python seam and low cognitive load | platform-specific code and infrastructure ownership |

### Trade-offs and graduation signals

The snapshot is portable within the project's WSL boundary and easy to teach, but it cannot close
every race. Graduate when the harness executes concurrently with untrusted filesystem mutation,
handles repositories for other users, or records a containment race in testing or operations. The
stronger design buys enforcement while adding platform coupling, resource cleanup, and deployment
work.

## Practical exercises

1. Draw why `/work/repo-copy` is not a child of `/work/repo` despite the shared text prefix.
2. Predict the reported path when `alias/file.py` links to `src/file.py` inside the root.
3. Replace the workspace directory after constructing the boundary and explain why identity matters.
4. Identify the exact future line where a native read tool must resolve again before opening a file.

## Key takeaways

- The Python harness owns one workspace-containment rule for every later repository capability.
- Canonical, component-aware containment plus root identity rejects common escapes and replacement,
  but the returned path remains only a snapshot.
- Descriptor-relative or sandboxed access is stronger when the threat model justifies its platform
  and operating cost.

## Glossary

- **Canonical path:** an absolute path after links and dot components are resolved.
- **Containment:** proof that one canonical path is a root or one of its descendants.
- **Device and inode:** filesystem identity values used to distinguish objects at the same pathname.
- **Path alias:** a requested symlink spelling that names another canonical target.
- **TOCTOU:** time-of-check/time-of-use; a change between validation and access.

See the shared [project glossary](../glossary.md) for workspace, context item, provider, tool, and
transcript.

## Further reading

- [CAH-024 delivery contract](../../user-stories/cah-024-establish-workspace-boundary.md)
- [CAH-024 planning decisions](../../user-stories/notes/2026-08-02-cah-024-workspace-boundary-planning.md)
- [ADR 0002](../adr/0002-ink-python-process-boundary.md),
  [Context engineering](../context-engineering.md), and [Safety model](../safety-model.md)
- [Python `pathlib`](https://docs.python.org/3/library/pathlib.html)
- [Linux `openat2`](https://man7.org/linux/man-pages/man2/openat2.2.html)
- [Linux Landlock](https://docs.kernel.org/userspace-api/landlock.html)
- [OCI Runtime Specification](https://github.com/opencontainers/runtime-spec)
