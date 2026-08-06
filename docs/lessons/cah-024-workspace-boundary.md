# CAH-024 lesson: Establish the workspace boundary

- **Unit:** CAH-024
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Verified against implementation
- **Implementation status:** Done — workspace boundary, runtime delegation, focused regressions, and
  the repository-wide gate are verified
- **Story:** [CAH-024](../../user-stories/cah-024-establish-workspace-boundary.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Why containment belongs to the harness and why a validated path is only a
  snapshot, not lasting authorization
- **Visual companion:** None; the Markdown lesson and compact text diagram are authoritative
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md),
  [Context engineering](../context-engineering.md), and [Safety model](../safety-model.md)

## Quick summary

CAH-024 implements one immutable Python boundary that converts a selected workspace into bounded,
canonical path snapshots for later repository operations. The system-design lesson is that the
harness—not the model, TUI, provider, or repository—owns what “inside this workspace” means.

## Learning objectives

After completing this unit, you should be able to:

- explain canonical paths, filesystem identity, containment, and check/use races;
- explain why a Python `str` can still contain a lone surrogate and why path admission must reject
  it before filesystem access;
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
by components after canonical resolution. Checking only the final whole-path target is also too
late: one directory link can leave the workspace and an outside child link can point back in. The
resolver must reject the first canonical prefix that crosses the boundary.

A second misconception is that validation makes later access permanently safe. Another process can
replace a directory or symlink after the check. CAH-024 returns a snapshot; future tools must resolve
again immediately before access, and stronger designs bind the check to an open descriptor.

A Python `str` is not automatically valid Unicode scalar text: it can contain an isolated surrogate
such as `"\ud800"`. Before constructing a path, CAH-024 requires a strict UTF-8 encode/decode
round-trip with exact equality. Valid multibyte text remains unchanged; a lone surrogate fails before
the filesystem can turn it into a platform-dependent error or existence signal.

The lexical gate also bounds work before a filesystem call: at most 4,095 strict-UTF-8 bytes in the
raw supplied spelling, 256 normalized non-dot components, and 255 UTF-8 bytes in one component. All
three endpoints are inclusive. Those are harness budgets, not a promise that every Linux or WSL
mount can create an endpoint path. The selected root consumes additional pathname bytes, Linux
mounts can report different limits, and Windows-backed DrvFS has different name behavior.

## Key concepts

- **Canonical root:** the resolved absolute directory that anchors every operation.
- **Root identity:** the root's device and inode, captured as a best-effort signal for ordinary
  replacement rather than a non-reusable identity anchor.
- **Containment:** a component-aware decision over whether the observed canonical target is the root
  or its descendant.
- **Canonical relative label:** the target's provider-safe path below the root; an accepted symlink
  reports its target rather than its alias.
- **Safe representation:** ordinary value and error representations omit canonical host paths.
- **Snapshot:** a best-effort containment result based on filesystem observations during resolution,
  not an open handle or lasting authority.
- **Fixed failure:** a stable code/message pair that reveals neither a host path nor raw OS text.
- **Unicode-scalar admission:** strict UTF-8 round-trip validation, without normalization, before
  any model-facing path reaches a filesystem API.
- **Path work budget:** one raw-byte ceiling plus normalized-component and per-name ceilings, owned
  by a pure CAH-024 primitive and reused without duplication downstream.

## Architecture and design

```text
Ink TUI boundary                 Python harness boundary
select one root -- child argv --> runtime composition
render validated events                |
                                       v
                          [CAH-024 WorkspaceBoundary]
                          pure 4095-byte/256-part/255-byte-name gate
                          canonical root + identity snapshot
                          relative path -> contained snapshot
                              |                    |
                 future instruction/context   future native read tools
                              |                    |
                              +---------+----------+
                                        v
Agent-loop boundary              provider port -> provider adapter
(chooses when to retrieve)       (receives selected content, never host paths)

Tool boundary: no tool schema or repository-content read in CAH-024; bounded path resolution and
metadata checks establish snapshots that later tools must re-admit.
Evidence boundary: no protocol/transcript record in CAH-024; later evidence uses relative labels.
```

The TUI continues to select exactly one workspace and pass its canonical root at process startup.
Python is authoritative after that handoff. `WorkspaceBoundary.from_path` captures the root;
`resolve_existing` first delegates to `normalize_workspace_relative_path`, which rejects
bytes-valued model input, over-bound values, and strings that do not round-trip through strict
UTF-8. It then accepts only a non-empty relative path, rejects NUL and every `..`,
follows symlinks, and returns the canonical target only when it remains inside the same root.

Internal symlinks stay useful, but their aliases do not become durable provenance. Resolution
advances from one already-contained canonical prefix to the next, so an outside traversal cannot be
masked by a later link that re-enters the workspace. Missing leaves are rejected because this unit
supports future reads, not future creates. Root identity is checked before and after resolution to
detect ordinary replacement. The original directory is not held open, so inode reuse or a swap
between checks can still evade detection; that residual risk remains explicit.

The public surface uses one `WorkspaceBoundaryError`, one `ResolvedWorkspacePath`, and five
stable error codes. It does not create separate exception classes for each filesystem observation.

## Practical walkthrough

1. The Python root invariant lives in top-level `workspace.py`, and runtime startup delegates to
   `WorkspaceBoundary.from_path`.
2. Capture the root's canonical path and identity in a frozen value.
3. Apply the 4,095-byte/256-component/255-byte-name budget, strict Unicode-scalar/UTF-8 round-trip,
   and relative syntax before touching the requested path.
4. Resolve each prefix strictly from the last contained target, reject the first escape, and compute
   the canonical relative label.
5. Recheck root identity before returning the snapshot.
6. Test normal paths, internal links, escaping links, missing targets, and observable root
   replacement. Keep provider, protocol, TUI, and repository-content behavior unchanged.

## Implementation code samples

### Important path: one lexical owner before filesystem work

From [`workspace.py`](../../src/code_assist_harness/workspace.py):

```python
if type(value) is not str or not value or len(value) > _MAX_RAW_PATH_BYTES:
    raise _invalid_workspace_path()

try:
    encoded = value.encode("utf-8", errors="strict")
    round_tripped = encoded.decode("utf-8", errors="strict")
except UnicodeError as error:
    raise _invalid_workspace_path() from error

if (
    len(encoded) > _MAX_RAW_PATH_BYTES
    or round_tripped != value
    or "\x00" in value
    or value.startswith("/")
):
    raise _invalid_workspace_path()

components: list[str] = []
encoded_components = encoded.split(b"/")
for component, component_bytes in zip(value.split("/"), encoded_components, strict=True):
    if not component or component == ".":
        continue
    if component == ".." or len(component_bytes) > _MAX_COMPONENT_BYTES:
        raise _invalid_workspace_path()
    components.append(component)
    if len(components) > _MAX_COMPONENTS:
        raise _invalid_workspace_path()
```

The first line rejects foreign string types, emptiness, and an obviously overlong spelling without
constructing a path. Strict UTF-8 conversion rejects lone surrogates and provides the bytes used for
the 4,095-byte budget. The final loop treats `/` as the only separator, removes empty and `.` parts,
rejects `..`, and applies the 255-byte-name and 256-component limits. No `Path`, root, or policy object
is involved in this pure decision.

### Important path: stage resolution before returning a snapshot

From [`workspace.py`](../../src/code_assist_harness/workspace.py):

```python
path_value = self._path_like_string(value)
components = normalize_workspace_relative_path(path_value)

self._assert_current_root()
target: Path | None = None
target_error: WorkspaceBoundaryError | None = None
try:
    target = self._resolve_target(components)
except WorkspaceBoundaryError as error:
    target_error = error

self._assert_current_root()
if target_error is not None:
    raise target_error
if target is None:  # pragma: no cover - defensive invariant
    raise WorkspaceBoundaryError("workspace_path_not_found")

try:
    relative_target = target.relative_to(self.root)
except ValueError as error:  # pragma: no cover - _resolve_target already checks this
    raise WorkspaceBoundaryError("workspace_path_outside") from error

label = "." if not relative_target.parts else relative_target.as_posix()
canonical_components = normalize_workspace_relative_path(label)
canonical_label = "." if not canonical_components else "/".join(canonical_components)
if canonical_label != label:
    raise _invalid_workspace_path()

return ResolvedWorkspacePath(
    absolute_path=target,
    relative_path=PurePosixPath(canonical_label),
)
```

The resolver first passes the requested spelling through the one lexical owner. It checks the root
before resolution, stages either a target or fixed error, and checks the root again before releasing
either outcome; observed staleness therefore wins over a target failure. `relative_to` supplies the
component-aware label. Running that canonical label through the same primitive prevents a short
symlink alias from manufacturing an over-budget model-visible result.

### Failure path: a short alias cannot bypass the output budget

From [`test_workspace.py`](../../tests/test_workspace.py):

```python
def test_resolve_existing_revalidates_canonical_label_limits(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    boundary = WorkspaceBoundary.from_path(workspace)
    deep_target = workspace
    for _index in range(257):
        deep_target /= "d"
        deep_target.mkdir()
    (workspace / "short-alias").symlink_to(deep_target, target_is_directory=True)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing("short-alias")

    _assert_error(caught.value, "invalid_workspace_path")
    assert str(tmp_path) not in repr(caught.value)
```

The input alias is tiny, but its canonical target has 257 components. The test proves that the
provider-facing label cannot bypass the shared component budget and that the fixed failure does not
leak the temporary host path.

### Validation evidence

`TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passed after the final prefix-containment
regression. It reported 1,015 Python tests with one opt-in live smoke deselected, 32 Python protocol
cases, 48 repository-policy tests, 240 TUI tests, 31 TypeScript protocol cases, and four real
Node-to-Python integration cases; type checking, linting, and formatting also passed.

## Failure scenarios to study

| Scenario | Responsible boundary | Safe result | Evidence |
| --- | --- | --- | --- |
| `/etc/passwd` or `../outside` | input admission | `invalid_workspace_path` before resolution | parameterized syntax tests |
| lone surrogate or bytes-valued path | string admission | `invalid_workspace_path` with zero filesystem calls | injected filesystem-spy test |
| path above any shared byte/component/name ceiling | lexical work admission | `invalid_workspace_path` with zero `Path`, root, or filesystem calls | independent 4,094/4,095/4,096, 254/255/256, and 255/256/257 tests |
| internal file/directory symlink | canonical containment | accept and report target-relative path | symlink happy-path tests |
| symlink escapes, then a later link re-enters | prefix-by-prefix canonical containment | `workspace_path_outside` at the first outside prefix | `test_resolve_existing_rejects_escape_even_when_a_later_symlink_reenters` |
| missing or dangling in-root target | strict resolution | `workspace_path_not_found` | missing-path tests |
| root removal or observable replacement | identity snapshot | `stale_workspace_root` | root-mutation tests |
| inode reuse or a swap between checks | snapshot limitation | may evade detection; later tools re-resolve | threat-model review |
| path changes after return | future caller | re-resolve before access; snapshot makes no guarantee | documented residual-risk test boundary |

## Production expansion

### Example enterprise scenario

A multi-tenant coding service may inspect untrusted repositories while other processes mutate the
same filesystem. A pathname snapshot is then too weak: the service may need descriptor-relative
resolution, an OS sandbox, or an isolated mount per job.

### Typical production capabilities and tools

- [Python `pathlib`](https://docs.python.org/3/library/pathlib.html) provides the local path and
  canonicalization primitives used by this learning unit.
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
3. Replace the workspace directory after constructing the boundary and explain both what the
   identity snapshot detects and how inode reuse can evade it.
4. Identify the exact future line where a native read tool must resolve again before opening a file.
5. Explain why Unicode normalization would change path identity and is therefore not part of the
   UTF-8 round-trip check.
6. Teach back the exact owner and stage order from runtime selection through lexical admission,
   target resolution, the second root check, and the returned relative label.
7. Explain why moving containment into the TUI, provider adapter, or future MCP server would create a
   second and weaker policy authority.
8. Draw an outside directory symlink whose child points back inside and explain why final-target-only
   containment would accept the wrong traversal.

## Key takeaways

- The Python harness owns one workspace-containment rule for every later repository capability.
- One pure lexical primitive bounds both requested spellings and canonical model-visible labels.
- Canonical, component-aware containment rejects escapes and the identity snapshot detects ordinary
  replacement, but neither result is a lasting filesystem capability.
- Descriptor-relative or sandboxed access is stronger when the threat model justifies its platform
  and operating cost.

## Glossary

- **Canonical path:** an absolute path after links and dot components are resolved.
- **Containment:** a component-aware decision that an observed canonical path is a root or one of
  its descendants.
- **Device and inode:** filesystem identity values that distinguish live objects but may be reused
  after an object is no longer referenced.
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
