# CAH-027 - List files and inspect path metadata

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-026
- **Lesson:** [Repository listing and metadata](../docs/lessons/cah-027-list-files-and-stat-path.md)
- **Learning emphasis:** Supporting implementation unit - bounded repository discovery primitives
- **Review focus:** Deterministic traversal, policy reuse, and output bounding rather than UI or
  provider integration

## User story

> As a user, I want the harness to list an admitted repository subtree and inspect one path's safe
> metadata so that later reasoning can discover relevant files without reading the whole workspace.

## Single responsibility

CAH-027 owns two native metadata operations, `list_files` and `stat_path`, over CAH-026's shared
admission policy. It does not read file content, search text, register model tools, dispatch tool
calls, or decide which files belong in model context.

## Scope

- Add provider-neutral Python request, result, and service contracts for `list_files` and
  `stat_path`.
- Enumerate one admitted directory non-recursively or to a bounded depth, omitting ignored and
  denied descendants and returning deterministic canonical labels.
- Report safe metadata for one admitted regular file or directory: canonical label, kind,
  file-size bytes when applicable, and whether the requested path was an internal symlink.
- Reuse `WorkspaceBoundary` and CAH-026 policy immediately before inspection. Use native Python
  filesystem APIs only, never a subprocess such as `find`, `ls`, or `git`.
- Make no protocol, transcript, provider, tool-registry, agent-loop, network, TUI, or repository
  content change.

## Locked contract

### Requests and results

- `ListFilesRequest` is a strict, frozen Pydantic v2 model with unknown fields forbidden. It contains
  `path` (default `.`), `recursive` (default `false`), `max_depth` (default 4, admitted range 1-8),
  and `max_items` (default 200, admitted range 1-500). Booleans used as integers are rejected.
- Non-recursive listing examines direct children only, regardless of the stored `max_depth` default.
  Recursive depth counts direct children as level 1 and never descends below the requested level.
- `ListFilesResult` contains an immutable tuple of entries, `truncated`, `visited_items`, and
  aggregate counts for descendants omitted as ignored, unavailable, or unsupported. It never lists
  the omitted labels or the policy rule that caused omission.
- Each entry contains the canonical workspace-relative POSIX `path`, `kind` (`file` or `directory`),
  and `is_symlink`. A regular file also carries non-negative `size_bytes`; a directory carries
  `None`. Modification times, owners, permission bits, inode/device values, and absolute paths are
  excluded because they are unnecessary, unstable, or host-revealing.
- `is_symlink` is the result of inspecting the winning candidate's final directory entry without
  following it. It is `true` only when that candidate itself is a symlink; it does not mean that the
  canonical target or one of its descendants is a symlink. `stat_path` applies the same rule to the
  directly requested leaf after containment admission.
- `StatPathRequest` is the same strict, frozen Pydantic form and contains only `path`.
  `StatPathResult` uses the same entry shape. The root label is `.`, and its kind is `directory`.
- The service contracts are provider-neutral Python values, not OpenAI, protocol, JSON Schema, or
  MCP objects. E4 will expose reviewed operations through a tool registry.

### Traversal, ordering, and policy

- Inputs are validated before policy evaluation. A direct ignored target fails with
  `repository_path_ignored`; a direct hard-denied target fails generically with
  `repository_path_unavailable`.
- Recursive discovery applies the hard denylist and effective nested `GitIgnoreSpec` policy before
  adding or descending into each candidate. There is no `include_ignored`, hidden-file override, or
  provider-controlled policy argument.
- Hidden names are otherwise ordinary repository entries. Special filesystem objects such as FIFO,
  socket, block, and character devices are omitted as unsupported and are never opened.
- Internal file and directory symlinks may be reported after canonical containment and policy
  checks. Recursive listing never descends through a directory symlink, preventing cycles and
  alias-driven expansion; a direct request whose path is an internal directory symlink may list its
  canonical target.
- Canonically duplicate results are emitted once. Candidate selection uses the tuple
  `(is_symlink, original_label_utf8)`: every ordinary non-symlink candidate sorts before every
  symlink candidate, and ties use the lowest original workspace-relative POSIX label by UTF-8 bytes.
  Therefore an ordinary target always wins when present; otherwise the lowest original alias wins.
  The emitted `path` is always the canonical target label, while `is_symlink` is copied exactly from
  that winning candidate.
- Enumeration does not stop merely because `max_items` candidates have been found: within the
  depth and 10,000-visit work bounds it must finish candidate collection, select canonical winners,
  sort winners by canonical-label UTF-8 bytes, and only then apply `max_items`. This prevents
  creation or iteration order from letting an early alias defeat a later ordinary target.
- A path whose label cannot be represented as strict UTF-8 or a path that changes during inspection
  is omitted as unavailable during traversal and fails safely for direct `stat_path`.

### Initial reviewed limits and completion

| Limit | Initial value | Behavior |
| --- | ---: | --- |
| Returned entries | default 200 / hard 500 | Return the first requested count and set `truncated` when another admitted entry exists. |
| Recursive depth | default 4 / hard 8 | Never inspect descendants below the requested depth. |
| Visited directory entries | 10,000 | Fail with `repository_result_limit` before an unbounded traversal. |
| Applicable ignore policy | CAH-026 limits | Fail or omit according to direct-versus-descendant policy behavior. |

- Item and depth limits are deterministic and not token estimates. Values above hard maxima fail
  request validation with `repository_input_limit`; zero and negative values are invalid.
- Truncation is an explicit successful result, not silent loss. `visited_items` includes every child
  inspected before policy, including omitted children, and never exceeds 10,000.
- The operation is synchronous and bounded. A later agent loop checks cancellation before dispatch
  and after return; this unit adds no task or protocol cancellation behavior.
- CAH-026's fixed `RepositoryAccessError` table is authoritative. No list/stat error includes the
  request, host path, ignored pattern, deny reason, raw OS failure, or partial unsafe metadata.

## Reviewability budget

- **Estimated production-code churn:** 350-500 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if content reading, search, tool
  registration, or provider serialization enters this unit, or if production churn is likely to
  exceed roughly 600 changed lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. `stat_path` returns only the canonical label, supported kind, safe size, and internal-symlink flag
   for admitted regular files, directories, and the workspace root.
2. `list_files` returns deterministic, deduplicated entries for direct and bounded-recursive
   requests with exact depth, item, visited-entry, alias-winner, and `is_symlink` accounting.
3. Ignored and hard-denied descendants are omitted without labels; direct access fails with the
   CAH-026 fixed error, and no override exists.
4. Recursive traversal does not follow directory symlinks, special files are never opened, and
   canonical containment is rechecked immediately before inspection.
5. Results truncate explicitly at the requested item bound and fail safely at the 10,000-visited
   hard bound.
6. All public values are immutable, typed, documented, provider-neutral, and tested without
   subprocess or network access.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Safe metadata | Stat root, regular file, directory, and internal symlinks | Unit/boundary | Exact canonical entry values and no unstable metadata |
| Deterministic listing | Vary creation/iteration order for an ordinary target plus lower/higher aliases, then for aliases only; place the eventual winner after `max_items` candidates | Unit | Ordinary target wins with `is_symlink=false`; otherwise lowest original alias wins with `is_symlink=true`; canonical output and truncation are identical on repeated runs |
| Depth behavior | Build a tree beyond levels 1, 4, and 8 | Unit | Exact direct and recursive membership at each boundary |
| Item behavior | Request 199/200/201 and 499/500/501 available items | Unit | Exact count and explicit `truncated`; above-hard input rejected |
| Ignore and denial | Combine nested ignores, an ignored parent with a negated child, the traversable-parent control, VCS/credential paths, and direct requests | Policy integration | The ignored parent is pruned before descent despite the leaf negation; otherwise omitted aggregate counts or fixed direct errors reveal no label |
| Symlink and special files | Add internal/escaping/cyclic links plus FIFO where supported | Boundary integration | Internal entries safe, no directory-link recursion, unsafe objects omitted |
| Traversal hard stop | Generate 10,000 and 10,001 visited children | Unit | Completion at limit and fixed `repository_result_limit` above |

## Validation

- Add focused tests for both operations using temporary workspaces and CAH-024/026 real boundaries.
- Assert strict request validation, immutable results, exact sorting, canonical labels, omission
  counters, safe representations, and the shared error table. Snapshot the ordinary-target and
  aliases-only winner cases, including exact `is_symlink` values.
- Test depth, returned-item, and visited-entry limits below, at, and above; avoid timing assertions.
- Use native local filesystem setup only. Any FIFO test is capability-gated and does not open the
  object; no subprocess, provider, model, or network is permitted.
- Keep protocol, transcript, provider, and TUI boundaries unchanged and run the focused tests plus
  `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update tool-system, context-engineering, safety model, glossary, story and lesson indexes, E3
backlog sequence, and the Markdown lesson's compact architecture diagram. Document why deterministic
native traversal is intentionally smaller than shelling out to familiar CLI tools. Do not add or
revise a presentation.

## Exclusions

- File contents, line ranges, literal or regular-expression search, context ranking, instruction
  interpretation, or token budgets.
- Tool registration, JSON Schema, MCP, provider tool calls, dispatch, loop continuation, protocol
  events, transcript records, and TUI rendering.
- Following directory symlinks during recursion, special-file reads, Git index semantics, filesystem
  watching, descriptor-relative traversal, or multiple workspace roots.
- File writes, subprocesses, shell commands, network access, permissions, approvals, or configuration
  that broadens policy.

## Definition of done

1. Every acceptance criterion maps to deterministic happy, boundary, and adversarial tests.
2. Depth 1-8, result 1-500, and visited 10,000 limits pass below/at/above evidence where applicable.
3. Canonical sorting, deduplication, ignore/deny omission, direct fixed errors, and symlink behavior
   are proved without host or policy leaks.
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

- Native list/stat modules and temporary-workspace tests prove deterministic discovery and metadata.
- Integration tests reuse the real boundary and policy rather than fake admission decisions.
- The lesson positions these supporting primitives beneath later context and tool-dispatch layers;
  its primary teach-back question is: why must traversal policy run before both result inclusion and
  directory descent?

## Deferred work

- CAH-028 reads one admitted text file and CAH-029 searches admitted text files.
- CAH-030 selects bounded evidence from these operations for provider-neutral context.
- E4 later gives these operations reviewed tool schemas, capability metadata, and dispatch behavior.
