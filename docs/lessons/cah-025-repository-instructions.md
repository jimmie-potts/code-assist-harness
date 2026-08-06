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
canonical path from workspace root to a selected scope. It retains that canonical scope even when
the binding list is empty, and returns ordered, bounded bindings that separate where an instruction
applies from where its bytes live; the LLM never gets to decide which repository rules apply.
CAH-026's reusable hard-deny classifier admits every scope and resolved
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
  instruction hierarchy. The successful result retains that canonical label so a later stage does
  not have to re-resolve the mutable alias.
- **Control-plane input:** `AGENTS.md` guides later agent behavior. Its exact ancestor candidate is not
  suppressed by `.gitignore`, and discovery never loads ancestor ignore files as policy. A deliberate
  leaf link to a file named `.gitignore` is still only bounded instruction content.
- **Shared lexical and hard deny:** CAH-024 owns pure pre-I/O path normalization and its
  4,095-byte/256-component/255-byte-name budget; CAH-026 delegates that primitive and owns hard-deny
  classification plus repository error mapping. CAH-025 applies them to the supplied scope before construction/resolution, then
  applies hard denial to canonical scope and every resolved source target before content I/O and
  again before each read.
- **Bounded hierarchy:** At most 16 owner bindings, 32 KiB each, and 128 KiB total are loaded as
  strict UTF-8. Shared target bytes are charged for every distinct owner binding.
- **Provenance and applicability:** `source` names the canonical target while `applies_to` names the
  canonical candidate-owner directory; neither exposes a host path.
- **Canonical-depth precedence:** `.` has rank 0 and each segment in canonical `applies_to` adds
  one. A missing candidate leaves a rank gap; the tuple position is not the rank. Equal-depth
  sibling owners have no precedence relationship because their scopes do not contain each other.
  Binding construction rejects a rank that does not equal its owner's depth.
- **Bundle topology:** One result factory uses the admitted `file`/`directory` kind to validate that
  unique owners form a strict root-to-nearest ancestor chain of the file's parent or the directory
  itself. Missing ancestors may leave rank gaps; an unrelated sibling, duplicate, reversal, or
  equal-depth pair is not a valid bundle.
- **Canonical label gate:** Source, owner, and scope strings must exactly match the canonical
  workspace-relative POSIX spelling produced from CAH-024. Absolute/escaping paths, redundant dots or
  separators, NUL, and lone surrogates fail before a bundle exists. On Ubuntu, backslash remains an
  ordinary filename character rather than being treated as a separator.
- **Non-following candidate probe:** The harness checks whether the exact directory entry exists
  without following it. Only true leaf absence beneath a still-admitted owner is skipped. A probe
  error, lost owner, present dangling or looping link, post-probe disappearance, or another unsafe
  resolution is a fixed unavailable-source failure.
- **Stable owner admission:** Before both probe and read, the captured owner must re-resolve to the
  same canonical directory. Rechecking only the leaf cannot catch `owner A -> symlink B`, which would
  otherwise select `B/AGENTS.md` while incorrectly reporting `applies_to=A`. Deterministic mutations
  already present at those seams fail; a pathname mutation after the final check can still race.

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

Runtime constructs exactly
`RepositoryInstructionDiscovery(boundary: WorkspaceBoundary)` once for the session. Its
`discover_for_path(path: str) -> RepositoryInstructions` method reuses that exact boundary object;
it never rebuilds workspace identity from an alias or environment value. Canonical-label, rank, or
topology factory drift raises only
`RepositoryInstructionError(code="invalid_instruction_bundle", message="Repository instruction bundle is invalid.")`
without labels, content, or chained diagnostics.

The invariant is simple: the harness walks canonical ancestors only, probes the exact filename
without following its directory entry, and captures each ancestor as `applies_to` before resolving
the leaf as `source`. Only a proved-absent leaf under a still-admitted owner is normal. A probe error,
lost owner, present but unavailable entry, escaping or hard-denied target, stale root, invalid
source, or exceeded budget fails the whole operation with a fixed error; discovery never returns a
partial bundle.

## Practical walkthrough

1. Build a temporary workspace with root and nested `AGENTS.md` files.
2. Normalize and validate supplied Unicode/path syntax without I/O; reject invalid or hard-denied
   components before `WorkspaceBoundary`, then resolve and reject a hard-denied canonical scope. A
   file scope then uses its canonical parent.
3. Probe one exact candidate per ancestor without following the directory entry and capture that
   ancestor as `applies_to`; skip only true absence and never recursively scan siblings.
4. Resolve the candidate leaf as `source`, apply CAH-026's classifier to that canonical target, then
   re-resolve and recheck immediately before the bounded read.
5. Validate regular-file type, byte budgets, strict UTF-8, and NUL absence without loading an
   ancestor ignore policy.
6. Derive each rank from canonical `applies_to` depth. Pass the canonical scope, its
   `file`/`directory` kind, and the candidate bindings to the sole result factory; it validates
   unique ancestor topology before returning the frozen canonical scope plus root-to-nearest tuple,
   or one fixed construction failure and no partial result.

## Implementation code samples

No implementation exists yet. This is planned pseudocode, not shipped Python:

```text
components = normalize_repository_path_components(requested_scope)
deny_if_hard_denied(components)
scope = boundary.resolve_existing(requested_scope)
deny_if_hard_denied(scope.relative_path.parts)
scope_kind = require_file_or_directory(scope)
owner_scope = scope.parent if scope_kind is FILE else scope
for owner in canonical_ancestors(owner_scope):
    require_exact_directory(re_admit(owner), expected=owner)
    candidate = owner / "AGENTS.md"
    probe = probe_exact_entry_without_following(candidate)
    if probe is ABSENT:
        continue
    source = resolve_present_candidate_or_unavailable(candidate)
    deny_source_if_hard_denied(source.relative_path.parts)
    require_exact_directory(re_admit(owner), expected=owner)
    source = re_resolve_and_recheck(candidate)
    bindings.append(
        InstructionBinding.create(
            source=source.relative_path.as_posix(),
            applies_to=owner.as_posix(),
            precedence=canonical_depth(owner),
            content=read_bounded_utf8(source),
        )
    )
return RepositoryInstructions.create(
    canonical_scope=scope.relative_path.as_posix(),
    scope_kind=scope_kind,
    bindings=root_to_nearest(bindings),
)
```

The first helper accepts only `str` and rejects empty/absolute/`..` paths, NUL, lone surrogates, and
values above the shared byte/component/name ceilings before `Path`, boundary, or filesystem calls.
Its sole fixed, content-suppressed
`RepositoryPathSyntaxError` maps to `invalid_instruction_scope`; the same string corpus must agree
with CAH-024's existing lexical grammar and sole lexical primitive, including
4,094/4,095/4,096 total-byte,
254/255/256 name-byte, and 255/256/257 component tests. A hard-denied but otherwise valid supplied scope maps to
`instruction_scope_unavailable`. The non-following probe distinguishes true absence from a present
entry that cannot be followed safely; dangling/looping links and post-probe disappearance map to
`instruction_source_unavailable`, as does any non-absence probe error. The checked seams keep the
owner snapshot stable while resolving physical provenance. Its rank comes from owner depth, so
missing candidates can leave gaps without changing the meaning of later ranks. Rechecking
immediately before the read catches a persistent allowed-to-denied retarget; disappearance observed
at that recheck keeps the same unavailable-source outcome. Mutation after the check remains a
pathname race. The operation stages all bindings locally, so any error returns
the fixed failure instead of an incomplete instruction set.

## Failure scenarios to study

- **Unrelated nested rule:** a sibling `AGENTS.md` is present. It must not appear.
- **Missing ancestor and late insertion:** root and `pkg/api` bindings have ranks 0 and 2 when
  `pkg/AGENTS.md` is absent. A later discovery after inserting it returns ranks 0, 1, and 2; the
  existing ranks do not move.
- **Forged precedence:** a constructed binding claims rank 1 for `pkg/api`. Result validation rejects
  it rather than letting tuple position or a caller override canonical owner depth.
- **Forged bundle topology:** a candidate tuple repeats an owner, reverses two owners, or inserts
  `other` into the chain for `pkg/api/app.py`. The result factory rejects it before CAH-030 can trust
  or copy any binding.
- **Forged result label:** a valid owner/rank pair carries `/host/secret`, `../escape`, or a
  non-canonical spelling as `source`. The shared label validator rejects it before CAH-030/032 can
  serialize a host path; a literal backslash filename remains a valid Linux control.
- **Present but unavailable entry:** dangling/looping links and a candidate removed after the
  non-following probe fail as `instruction_source_unavailable`; they are not treated as absent.
- **Owner retarget:** captured owner `A` is replaced by an allowed symlink to `B` at the deterministic
  seam before probe or read. Exact owner re-admission observes the persistent mutation and fails
  before that seam's later work, so no returned binding reports owner `A` with replacement bytes.
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
- **Post-return alias retarget:** an empty discovery through `alias -> A` still reports `A` after the
  alias points to `B`; downstream work uses the captured canonical label, not the alias.

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
4. Prove invalid lexical scope fails before construction/I/O, an ignored valid `AGENTS.md` loads,
   and a symlink to `dev.env` fails before content I/O.
5. Explain why a candidate linked to `.gitignore` may supply instruction bytes without becoming
   ignore policy.
6. Teach back: why is instruction selection a harness decision rather than an LLM decision?
7. Retarget an empty-discovery alias and explain why the returned canonical scope remains useful
   even without an instruction binding.
8. Remove an intermediate candidate, record the rank gap, insert it, and explain why existing ranks
   stay stable. Compare two sibling owners at that depth, then contrast true absence with a dangling
   symlink.

## Key takeaways

- The Python harness owns which repository instructions apply.
- Pure lexical admission rejects unsafe supplied scope before resolution or filesystem work.
- Canonical owner order and separate target provenance prevent a symlink from widening rule scope.
- Canonical owner depth, not tuple position, gives precedence stable meaning across missing and late
  ancestor candidates.
- A non-following exact-entry probe makes only true absence normal; present unsafe entries fail
  closed.
- A successful empty bundle still carries stable canonical scope for downstream composition.
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
