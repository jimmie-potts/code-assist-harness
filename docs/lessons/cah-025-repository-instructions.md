# CAH-025 lesson: Scoped repository instructions

- **Unit:** CAH-025
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Discover scoped repository instructions](../../user-stories/cah-025-discover-repository-instructions.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Harness-owned instruction scope, precedence, and the treatment of repository
  guidance as untrusted input
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Context engineering](../context-engineering.md) and
  [Harness architecture](../architecture.md)

> This lesson describes an accepted plan. The modules and tests named below do not exist yet.

## Quick summary

CAH-025 teaches hierarchical context: the harness finds only the `AGENTS.md` files on the canonical
path from workspace root to a selected scope. It returns an ordered, bounded instruction bundle;
the LLM never gets to decide which repository rules apply.

## Learning objectives

After completing this unit, you should be able to:

- explain root-to-nearest instruction precedence;
- distinguish discovering instructions from interpreting their prose;
- explain why canonical scope and strict UTF-8 are security boundaries; and
- test deterministic hierarchy, limits, and non-leaking failures.

## Why this unit matters

An agent that loads only root guidance can miss a package-specific rule. An agent that scans every
instruction file can apply rules from unrelated subtrees. CAH-025 gives the later context builder
one harness-owned answer: these sources, in this order, apply to this scope.

## Junior engineer foundation

An ancestor is a directory above a path. For `packages/api/src/app.py`, the candidates are
`AGENTS.md`, `packages/AGENTS.md`, `packages/api/AGENTS.md`, and
`packages/api/src/AGENTS.md`. The root source is broad; the nearest source is more specific.

A common misconception is that “nearest wins” means deleting earlier text. This unit preserves all
applicable sources in order. It records precedence but does not attempt to understand or merge
natural-language rules.

## Key concepts

- **Canonical scope:** CAH-024 resolves aliases before discovery, so a symlink cannot create a second
  instruction hierarchy.
- **Control-plane input:** `AGENTS.md` guides later agent behavior. It is not an arbitrary source file
  and is not suppressed by `.gitignore`.
- **Bounded hierarchy:** At most 16 sources, 32 KiB each, and 128 KiB total are loaded as strict UTF-8.
- **Provenance:** Each source carries a canonical workspace label and precedence rank, never a host
  path.

## Architecture and design

```text
Ink TUI              Python harness                                  External
   | task/scope          |                                               |
   +-- NDJSON ---------->| WorkspaceBoundary (CAH-024)                   |
                         |          |                                    |
Repository               |          v                                    |
AGENTS.md chain -------->| [CAH-025 scoped discovery] -> CAH-030 mapping -> existing Provider port
                         |
Native read tools -------| future; not used here
Transcript/evidence -----| unchanged; instruction content is not persisted here
```

The invariant is simple: the harness walks canonical ancestors only, probes the exact filename, and
returns root-to-nearest sources. Missing candidates are normal. VCS administration scopes,
oversized sources, invalid UTF-8, escapes, and stale roots fail safely.

## Practical walkthrough

1. Build a temporary workspace with root and nested `AGENTS.md` files.
2. Resolve a file scope through `WorkspaceBoundary` and use its canonical parent.
3. Probe one exact candidate per ancestor; never recursively scan siblings.
4. Validate regular-file type, byte budgets, strict UTF-8, and NUL absence.
5. Return frozen sources in increasing precedence and test all limits below, at, and above.

## Implementation code samples

No implementation exists yet. This is planned pseudocode, not shipped Python:

```text
scope = boundary.resolve_existing(requested_scope)
for directory in canonical_ancestors(scope):
    candidate = resolve_exact(directory / "AGENTS.md")
    if candidate.exists:
        sources.append(read_bounded_utf8(candidate))
return RepositoryInstructions(root_to_nearest(sources))
```

The first line removes path aliases. The loop probes only the applicable chain. The read enforces
type and byte/text limits before content exists in a public value. The final line makes precedence
explicit instead of relying on filesystem order.

## Failure scenarios to study

- **Unrelated nested rule:** a sibling `AGENTS.md` is present. It must not appear.
- **Instruction bomb:** the seventeenth source or first aggregate byte above 128 KiB fails the whole
  bundle rather than silently dropping a narrower rule.
- **Alias escape:** an ancestor candidate resolves outside the workspace. The caller receives a
  fixed safe error with no host path.
- **Invalid text:** malformed UTF-8 or NUL is rejected; replacement decoding cannot mutate a rule.

## Production expansion

### Example enterprise scenario

A monorepo has hundreds of teams, generated subtrees, policy attestations, and centrally managed
rules. A production system may need signed instruction sources, ownership metadata, caching, and a
conflict UI while preserving the same harness-owned precedence boundary.

### Typical production capabilities and tools

- [AGENTS.md](https://agents.md/) standardizes repository-local agent guidance; portability improves,
  but teams must govern content and precedence.
- [GitHub Copilot repository instructions](https://docs.github.com/en/copilot/customizing-copilot/adding-repository-custom-instructions-for-github-copilot)
  provide hosted product integration, at the cost of vendor-specific behavior.
- [Model Context Protocol prompts](https://modelcontextprotocol.io/docs/learn/server-concepts#prompts) can expose
  reusable instruction templates across processes, adding transport and trust-boundary work.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One workspace and one ancestor chain | Many repos, teams, and signed rule sources |
| Reliability | Fresh bounded reads | Cache invalidation, versioning, and provenance audits |
| Operations | Deterministic local tests | Policy ownership, telemetry, and conflict workflows |
| Cost | Small explicit module | Services, governance, and cross-product compatibility |

### Trade-offs and graduation signals

The local design is easy to reason about but rereads small files and cannot prove authorship. Add a
cache or signed policy service only when large-repository measurements show discovery cost or when
multiple trust domains require verifiable rule ownership.

## Practical exercises

1. Draw the candidate chain for a root, nested directory, and file scope.
2. Predict the result when two aliases reach the same canonical `AGENTS.md`.
3. Write the 32-KiB and 16-source boundary cases before implementation.
4. Teach back: why is instruction selection a harness decision rather than an LLM decision?

## Key takeaways

- The Python harness owns which repository instructions apply.
- Canonical root-to-nearest order is the central invariant.
- Production policy distribution improves scale but adds governance and trust costs.

## Glossary

- **Ancestor chain:** Ordered directories from workspace root through a selected scope.
- **Precedence:** Which source is more specific when guidance conflicts.
- **Control plane:** Input that governs behavior rather than ordinary repository evidence.
- **Canonical label:** Safe workspace-relative identity after symlink resolution.

## Further reading

- [CAH-025 delivery contract](../../user-stories/cah-025-discover-repository-instructions.md)
- [Context engineering](../context-engineering.md)
- [AGENTS.md specification](https://agents.md/)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
