# CAH-027 lesson: Listing files and safe metadata

- **Unit:** CAH-027
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [List files and inspect path metadata](../../user-stories/cah-027-list-files-and-stat-path.md)
- **Learning emphasis:** Supporting implementation unit
- **Review focus:** Deterministic bounded discovery through the already-reviewed read policy
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Tool system](../tool-system.md) and [Safety model](../safety-model.md)

> This is a planned supporting lesson. No `list_files` or `stat_path` implementation is claimed.

## Quick summary

CAH-027 adds deterministic native discovery without reading file content. It teaches how CAH-026
policy, bounded traversal, canonical provenance, and explicit truncation turn filesystem metadata
into a safe future tool primitive.

## Learning objectives

After completing this unit, you should be able to:

- define safe metadata and exclude unstable host details;
- bound recursion by depth, returned items, and visited entries;
- explain why directory symlinks are reported but not followed recursively; and
- test deterministic ordering independent of filesystem creation order.

## Why this unit matters

The model cannot request a relevant file if it cannot discover names, but an unrestricted recursive
walk can consume unbounded work or expose ignored paths. This unit gives later context and tool
layers one small, policy-reusing discovery primitive.

## Junior engineer foundation

Directory iteration order is not a stable sort order. Two machines may return the same files in a
different sequence. CAH-027 collects within a hard visit budget, canonicalizes admitted labels, and
sorts their UTF-8 bytes. A common misconception is that limiting returned rows also limits work;
the separate 10,000-visited bound limits traversal effort.

## Key concepts

- **Safe metadata:** canonical label, file/directory kind, file bytes, and symlink flag only.
- **Explicit truncation:** a successful partial list says it is partial.
- **No-follow recursion:** directory symlinks are not descended, avoiding cycles and alias expansion.
- **Policy-before-descent:** ignored and denied directories are neither returned nor traversed.
- **Alias tie-break:** prefer the ordinary target path; otherwise use the lowest alias label.
- **Exact symlink evidence:** `is_symlink` describes the selected candidate's final entry, not the
  canonical target in general.
- **Execution-time request scope:** even an empty list records the canonical directory actually
  admitted and inspected, so a later alias retarget cannot rewrite the result's meaning.

## Architecture and design

```text
TUI -- NDJSON --> Python harness <--- provider/tool dispatch (future, unchanged)
                       |
             CAH-024 boundary + CAH-026 policy
                       |
             [CAH-027 list_files / stat_path]
                       |
               repository metadata only

CAH-030 context and transcript/evidence are later/unchanged; no content is read here.
```

Requests permit 1-500 returned items and recursive depth 1-8. Traversal stops with a safe failure
above 10,000 visited entries. Results contain the content-suppressed execution-time canonical
request scope, canonical entry labels, and aggregate omission counts, never the names of denied or
ignored descendants.
Runtime calls these methods on one
`RepositoryMetadataReader(policy: RepositoryReadPolicy)`: `list_files(ListFilesRequest) ->
ListFilesResult` and `stat_path(StatPathRequest) -> StatPathResult`. The reader retains the exact
session policy object; it never reconstructs the workspace boundary or a second ignore cache.
`ListFilesRequest.path` defaults to `.`, while `StatPathRequest.path` is required and has no default.
The request path first crosses CAH-024/026's inclusive 4,095-byte, 256-component, and
255-byte-name lexical budget. An above-bound value is `invalid_repository_path` before policy or
enumeration. These application limits do not claim that every WSL mount accepts an endpoint name.

## Practical walkthrough

1. Validate the strict request and shared path budget, then perform final boundary/policy admission immediately before root
   enumeration or direct stat inspection; retain that canonical target as result provenance.
2. Enumerate native directory entries, applying policy before inclusion or descent.
3. Never descend through directory symlinks or open special objects.
4. Rank candidates by `(is_symlink, original_label_utf8)`, so any ordinary candidate wins and an
   aliases-only set chooses its lowest original label; copy that winner's exact `is_symlink` value.
5. Preserve the final admitted directory as `canonical_request_scope`, including when no entry is
   returned; finish bounded candidate collection before sorting canonical winners and applying
   `max_items`, then return explicit truncation.
6. For direct `stat_path`, copy canonical path and symlink evidence from that same final admission and
   inspection; never reuse an earlier target label.

## Implementation code samples

Planned pseudocode only:

```text
admitted_root = final_admit(request.path)
for entry in bounded_walk(admitted_root, depth=request.max_depth):
    if policy.admits(entry) and supported(entry):
        results.add(canonical_metadata(entry))
return ListFilesResult(
    canonical_request_scope=admitted_root.path,
    entries=sorted(results)[:request.max_items],
    **truncation_summary,
)
```

The walk owns effort limits; policy runs before a result or recursive step; canonical metadata avoids
host paths. Deduplication happens before the final slice, so a later ordinary path cannot lose to an
earlier alias merely because of iteration order.

## Failure scenarios to study

- A cyclic directory symlink is listed safely but never followed.
- A direct ignored path returns the fixed ignored error; recursive discovery omits its label.
- The 10,001st visited entry fails instead of turning a small output request into unbounded work.
- A path replaced during inspection is rechecked and becomes a fixed safe failure.
- An alias encountered before its ordinary target does not win: bounded collection finishes before
  canonical winner selection and truncation.
- An empty `alias -> A` listing keeps `A` as its canonical request scope even if the alias is
  retargeted to `B` immediately after the native operation returns.
- If an allowed alias changes from `A` to `B` immediately before enumeration or direct stat, the
  operation inspects and reports `B`; it never reports `A` beside `B` metadata.

## Production expansion

### Example enterprise scenario

A monorepo with millions of files may require an indexed catalog and incremental filesystem events.
That improves latency but introduces cache freshness and service operations.

### Typical production capabilities and tools

- [Python `os.scandir`](https://docs.python.org/3/library/os.html#os.scandir) supplies efficient native
  metadata locally, but still needs policy and bounds.
- [Git `ls-files`](https://git-scm.com/docs/git-ls-files) understands tracked and excluded files, but a
  subprocess adds process and repository-state semantics this unit avoids.
- [`fd`](https://github.com/sharkdp/fd) provides fast parallel discovery and ignore handling, at the
  cost of another executable and a wider option surface.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One bounded live walk | Indexed multi-repository catalog |
| Reliability | Fresh checks, explicit truncation | Freshness guarantees and index recovery |
| Operations | Local deterministic tests | Indexers, monitoring, and rebuilds |
| Cost | Small native Python operation | Storage, background work, and synchronization |

### Trade-offs and graduation signals

Keep the live walk until fixture evaluations or measurements show unacceptable latency near the hard
visit bound. An index is justified only with a tested freshness contract.

## Practical exercises

1. Predict direct versus recursive results for an ignored directory.
2. Create two symlinks to one file and explain canonical deduplication.
3. Add the ordinary target after both aliases and predict the exact `is_symlink` value.
4. Test depth and item limits below, at, and above.
5. Teach back: why are visited entries and returned entries separate budgets?
6. Retarget an empty directory alias after return and explain why the immutable scope must still name
   the directory actually listed.

## Key takeaways

- The harness owns bounded repository discovery.
- Policy-before-descent and deterministic canonical ordering are the key invariants.
- Empty success still carries execution-time provenance; the request alias is not later authority.
- Indexes improve scale but add freshness and operational costs.

## Glossary

- **Visited item:** A directory child inspected before admission.
- **Truncation:** An explicit successful result that omits later admitted items.
- **Special object:** A FIFO, socket, or device that is neither a regular file nor directory.

## Further reading

- [CAH-027 delivery contract](../../user-stories/cah-027-list-files-and-stat-path.md)
- [Python `os.scandir`](https://docs.python.org/3/library/os.html#os.scandir)
- [Git `ls-files`](https://git-scm.com/docs/git-ls-files)
