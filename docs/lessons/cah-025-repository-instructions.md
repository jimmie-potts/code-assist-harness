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

CAH-025 teaches hierarchical context: the harness finds only the `AGENTS.md` candidates on the
canonical path from workspace root to a selected scope. It returns ordered, bounded bindings that
separate where an instruction applies from where its bytes live; the LLM never gets to decide which
repository rules apply. CAH-026's reusable hard-deny classifier admits every scope and resolved
source even though `.gitignore` does not suppress this control-plane input; CAH-025 therefore
depends on CAH-026 rather than copying its security policy.

## Learning objectives

After completing this unit, you should be able to:

- explain root-to-nearest instruction precedence;
- distinguish a candidate-owner `applies_to` scope from resolved `source` provenance;
- distinguish discovering instructions from interpreting their prose;
- explain why `.gitignore` exemption never overrides the shared hard deny; and
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

Another misconception is that a symlink moves a rule's scope. If `pkg/AGENTS.md` points to
`shared/rules.md`, the physical `source` is `shared/rules.md`, but its candidate owner—and therefore
its `applies_to` scope—remains `pkg`. The same target linked from two owners creates two bindings;
each binding can govern a different subtree and therefore spends the content budget separately.

## Key concepts

- **Canonical scope:** CAH-024 resolves aliases before discovery, so a symlink cannot create a second
  instruction hierarchy.
- **Control-plane input:** `AGENTS.md` guides later agent behavior. Its exact ancestor candidate is not
  suppressed by `.gitignore`, and discovery never loads ancestor ignore files as policy. A deliberate
  leaf link to a file named `.gitignore` is still only bounded instruction content.
- **Shared lexical and hard deny:** CAH-026 owns pure pre-I/O path normalization and hard-deny
  classification. CAH-025 applies them to the supplied scope before construction/resolution, then
  applies hard denial to canonical scope and every resolved source target before content I/O and
  again before each read.
- **Bounded hierarchy:** At most 16 owner bindings, 32 KiB each, and 128 KiB total are loaded as
  strict UTF-8. Shared target bytes are charged for every distinct owner binding.
- **Provenance and applicability:** `source` names the canonical target while `applies_to` names the
  canonical candidate-owner directory; neither exposes a host path.

## Architecture and design

```text
Ink TUI              Python harness                                  External
   | task/scope          |                                               |
   +-- NDJSON ---------->| WorkspaceBoundary (CAH-024)                   |
                         |          |                                    |
Repository               |          v                                    |
AGENTS.md chain -------->| [CAH-025 scoped discovery] -> CAH-030 mapping -> existing Provider port
                         |       ^ source admission
                         |       |
                         | CAH-026 pure lexical + hard-deny helpers
                         |
Native read tools -------| future; not used here
Transcript/evidence -----| unchanged; instruction content is not persisted here
```

The invariant is simple: the harness walks canonical ancestors only, probes the exact filename, and
captures each ancestor as `applies_to` before resolving the leaf as `source`. Missing candidates are
normal. An escaping or hard-denied target, stale root, invalid source, or exceeded budget fails the
whole operation with a fixed error; discovery never returns a partial bundle.

## Practical walkthrough

1. Build a temporary workspace with root and nested `AGENTS.md` files.
2. Normalize and validate supplied Unicode/path syntax without I/O; reject invalid or hard-denied
   components before `WorkspaceBoundary`, then resolve and reject a hard-denied canonical scope. A
   file scope then uses its canonical parent.
3. Probe one exact candidate per ancestor and capture that ancestor as `applies_to`; never
   recursively scan siblings.
4. Resolve the candidate leaf as `source`, apply CAH-026's classifier to that canonical target, then
   re-resolve and recheck immediately before the bounded read.
5. Validate regular-file type, byte budgets, strict UTF-8, and NUL absence without loading an
   ancestor ignore policy.
6. Return all frozen bindings in increasing precedence, or one fixed failure and no partial result.

## Implementation code samples

No implementation exists yet. This is planned pseudocode, not shipped Python:

```text
components = normalize_repository_path_components(requested_scope)
deny_if_hard_denied(components)
scope = boundary.resolve_existing(requested_scope)
deny_if_hard_denied(scope.relative_path.parts)
for owner in canonical_ancestors(scope):
    candidate = owner / "AGENTS.md"
    if candidate.exists:
        source = boundary.resolve_existing(candidate)
        deny_source_if_hard_denied(source.relative_path.parts)
        source = re_resolve_and_recheck(candidate)
        bindings.append(
            InstructionBinding(
                source=source.relative_path.as_posix(),
                applies_to=owner.as_posix(),
                content=read_bounded_utf8(source),
            )
        )
return RepositoryInstructions(root_to_nearest(bindings))
```

The first helper accepts only `str` and rejects empty/absolute/`..` paths, NUL, and lone surrogates
before `Path`, boundary, or filesystem calls. Its sole fixed, content-suppressed
`RepositoryPathSyntaxError` maps to `invalid_instruction_scope`; the same string corpus must agree
with CAH-024's existing lexical grammar. A hard-denied but otherwise valid supplied scope maps to
`instruction_scope_unavailable`. The loop keeps the owner stable while
resolving physical provenance. Rechecking immediately before the read catches an allowed-to-denied
retarget. The operation stages all bindings locally, so any error returns the fixed failure instead
of an incomplete instruction set.

## Failure scenarios to study

- **Unrelated nested rule:** a sibling `AGENTS.md` is present. It must not appear.
- **Invalid lexical scope:** empty/absolute/`..`, NUL, or lone-surrogate input fails before `Path`,
  boundary resolution, hard-deny matching, or filesystem work.
- **Instruction bomb:** the seventeenth binding or first aggregate byte above 128 KiB fails the whole
  bundle rather than silently dropping a narrower rule.
- **Denied target:** `pkg/AGENTS.md` resolves to `secrets/dev.env`. `.gitignore` exemption does not
  exempt hard denial; the caller receives `instruction_source_unavailable`, the target is not read,
  and no path or matching rule leaks.
- **Shared target:** root and nested candidates resolve to one allowed target. Both bindings remain,
  preserve different `applies_to` labels, and each charges the target bytes.
- **Alias escape or retarget:** an ancestor candidate escapes or becomes denied before the read. The
  fixed `instruction_source_unavailable` failure contains no host path and no partial bindings.
- **Ignore-looking source:** a deliberate candidate link to `.gitignore` loads bounded instruction
  bytes but never activates ignore semantics or ancestor policy loading.
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
2. For `pkg/AGENTS.md -> shared/rules.md`, label `source` and `applies_to`, then repeat with a second
   owner pointing at the same target.
3. Write the 32-KiB and 16-binding boundary cases, including separately charged shared target bytes.
4. Prove invalid lexical scope fails before construction/I/O, an ignored valid `AGENTS.md` loads, and
   a symlink to `dev.env` fails before content I/O.
5. Explain why a candidate linked to `.gitignore` may supply instruction bytes without becoming
   ignore policy.
6. Teach back: why is instruction selection a harness decision rather than an LLM decision?

## Key takeaways

- The Python harness owns which repository instructions apply.
- Pure lexical admission rejects unsafe supplied scope before resolution or filesystem work.
- Canonical owner order and separate target provenance prevent a symlink from widening rule scope.
- `.gitignore` exemption never bypasses CAH-026's shared hard denial.
- Production policy distribution improves scale but adds governance and trust costs.

## Glossary

- **Ancestor chain:** Ordered directories from workspace root through a selected scope.
- **Precedence:** Which source is more specific when guidance conflicts.
- **Source:** The canonical target whose bytes supply one instruction binding.
- **Applies-to scope:** The canonical candidate-owner subtree governed by that binding.
- **Control plane:** Input that governs behavior rather than ordinary repository evidence.
- **Canonical label:** Safe workspace-relative identity after symlink resolution.

## Further reading

- [CAH-025 delivery contract](../../user-stories/cah-025-discover-repository-instructions.md)
- [Context engineering](../context-engineering.md)
- [AGENTS.md specification](https://agents.md/)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
