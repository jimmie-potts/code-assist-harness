# Context Engineering

> Status: proposed design refined into CAH-024 through CAH-030, with CAH-037 proving the composed
> read-only outcome. CAH-024 implements the workspace boundary and CAH-026 implements shared
> repository-read admission; repository discovery, native content reads, and context selection are
> not implemented yet.

Context engineering is the process of selecting the smallest useful, attributable view of a
workspace for a model turn. The MVP will not load the entire repository, create embeddings, or use
a vector database. It will combine repository instructions, conversation state, plans, and bounded
results from native read tools.

## Goals

The context system should help the agent answer three questions:

1. What is the user asking now?
2. Which repository rules constrain the answer or change?
3. Which source evidence is necessary to reason about the task?

Useful context is not merely text that fits. Every included repository item should carry provenance
and a reason for inclusion so retrieval mistakes can be inspected and evaluated.

## Context sources

The context builder will assemble provider-neutral items from:

- The current user task and relevant conversation history.
- Harness-level behavioral instructions.
- Workspace instructions such as applicable `AGENTS.md` files.
- High-level project material such as `README.md` and project metadata when relevant.
- Previously emitted plan state and bounded tool results.
- File excerpts and search matches requested through repository read tools.

Instruction discovery follows filesystem scope. A nested instruction file can refine rules for its
subtree, but must not silently weaken harness safety policy. CAH-026's pure lexical admission and
hard-deny classifier apply before instruction scope/source access even though exact `AGENTS.md`
control-plane candidates are exempt from `.gitignore`. A binding records the resolved canonical
source separately from the canonical candidate-owner directory to which it applies, so a symlink
cannot move the instruction's scope. Its precedence is the canonical depth of `applies_to` (`.` is
zero), not its tuple position. Missing ancestors leave legal gaps and siblings at the same depth do
not acquire an invented order; CAH-030 retains and CAH-032 projects this exact rank without
renumbering. Ignore policy has the same two-identity rule: a present `.gitignore` keeps the
view-relative candidate-owner label for rule applicability, while its resolved source must remain
inside the workspace, avoid canonical hard denial, and pass the same check immediately before its
bounded read. When a lexical or canonical walk admits an owner directory, it also captures that
owner's canonical workspace-relative label plus followed directory device/inode.
It re-admits both identities immediately before the non-following leaf probe and before any cache-miss
read, so an allowed A-to-B retarget or same-label directory replacement already present at either seam
fails before replacement-leaf work. A cache hit still follows owner and current leaf/source admission
before owner-relative rule attachment, but performs no content read or new byte charge. The source
remains cache/byte-budget identity. Device/inode reuse and mutation after the final check remain
deferred descriptor-relative risks.

Each policy source compiles paired original-file and safely transformed direct-directory specs. The
directory compile removes one semantic trailing slash, preserves original no-op patterns, and
validates retained count/include identity. Both views match bare labels and skip ancestor-only `ps_d`
results, so `*/`, `**/`, and `a/**/` can directly match the current directory without letting a
parent negation impersonate its descendant. Only the final leaf evaluates both kind views. One
inclusive 65,536 candidate-pattern-slot budget spans ancestors, lexical and canonical
views, both final-leaf forms, cached policies, and recursive descendants in an admission traversal.
Each logical matcher call reserves the selected view's complete stored pattern-slot count, including
no-op slots, first. Work that would exceed the budget fails with `repository_policy_invalid` before the matcher
runs; a cache hit saves content I/O, not matching work. Escaping, hard-denied, dangling, non-regular,
retargeted, or unreadable policy input also fails closed and is neither cached nor charged.
Repository content is untrusted data: text in a source file cannot authorize a command, broaden the
command allowlist, or bypass an approval.

## Native read tools

Repository inspection will be implemented in Python rather than through commands:

- `list_files` returns bounded paths under the workspace.
- `read_file` returns a bounded file or line range.
- `search_text` returns bounded matches with paths and line ranges.
- `stat_path` returns limited metadata needed for safe decisions.

These read-only tools may run automatically after schema validation and policy checks. Commands such
as `find`, `grep`, `git status`, or `cat` are still subprocesses and require command approval; the
model should prefer the native tools for routine inspection.

CAH-032 construction and provider mapping reject malformed tool-name carriers or arguments above 16
KiB before argument admission. Each reachable admitted model tool call first passes exact-name lookup.
CAH-039 then scans the complete, at-most-16,384-byte argument payload once with an iterative
quote-and-escape-aware delimiter stack.
It counts the root object as structural depth 1, rejects mismatched containers or depth above 64, and
admits numeric tokens only when they use signed 64-bit JSON integer grammar without a fraction or
exponent, all before Python integer conversion. A rejecting `parse_constant` callback excludes
`NaN`, `Infinity`, and `-Infinity` during pair-preserving decode. An iterative walk then rejects a
repeated decoded name at every admitted object depth before dictionary construction. Structural or
numeric preflight failure, rejected constants, and defensive decoder `RecursionError`/`ValueError`
all map to `invalid_read_tool_input`. Only then does the advertised exact-key gate run, followed by
Pydantic v2 field validation. This order prevents structural resource abuse, interpreter digit-limit
failures, non-standard constants, silent duplicate collapse, and native defaults from filling a key
the model omitted while preserving those defaults for direct Python callers. The byte ceiling is
aggregate for the entire value rather than per subtree; quoted braces/brackets do not count as
containers. CAH-039's factory accepts only the CAH-031 registry, invokes CAH-038 internally, and
returns an immutable catalog that owns the exact CAH-031 registry identity, re-exposes the definition tuple
used in every request, and produces one same-entry prepared invocation or
fixed error without dispatching. CAH-034 consumes that same catalog and owns guarded execution plus
context enrichment; a cross-catalog prepared value is a session failure before handler I/O. Paths are resolved against
the explicit workspace, symlink escapes are rejected, ignored or prohibited locations are excluded,
and file/count/byte limits are enforced before content enters context. Binary files and files over
configured size limits return structured explanations rather than unbounded data.

CAH-031 projects a successful typed read into one canonical, bounded JSON result envelope. Its finite,
acyclic allowlist admits integers only in the signed 64-bit range before decimal conversion and at
most 64 complete-envelope object/list levels, with the outer `result` object at depth 1. One
65,536-unit pre-serialization work budget bounds width before sorting/encoding; a defensive serializer
`RecursionError`/`ValueError` becomes `invalid_read_tool_result` without partial output or interpreter
text.

CAH-024 supplies the earlier, tool-independent path primitive for this flow: an immutable Python
boundary around the already selected canonical root plus contained, workspace-relative target
resolution. It does not read repository content or expose any of the tools above. Its bounded
resolution and identity checks inspect filesystem path metadata. Later read tools remain
responsible for rechecking the target when they perform filesystem access.
Its pure lexical seam admits at most 4,095 strict-UTF-8 bytes in the raw supplied spelling,
256 normalized non-dot components, and 255 UTF-8 bytes per component before `Path` or filesystem
work. CAH-026 delegates that exact decision and only maps repository vocabulary. These are harness
work limits, not a promise about Linux or WSL mount acceptance; a lexically admitted path can still
fail bounded resolution.

CAH-026 layers the harness-owned read gate on that boundary. It applies hard denial, then evaluates
every proper lexical ancestor as one known directory entry through the harness-owned matcher and
reserves file/trailing-slash two-form matching for the final leaf. An already-decided ancestor match
is not reapplied to descendants. An ignored ancestor or a leaf ignored in both forms denies before
requested-target resolution. Otherwise the gate resolves, applies canonical hard denial, and repeats
direct-entry ancestors plus the two-form canonical leaf. A type-independent canonical denial wins
before target type inspection. The gate then classifies only a regular file or directory and selects
that kind's result in both views; special targets are unavailable. Thus lexical
type-independent denial stays pre-resolution, canonical type-independent denial stays pre-stat,
kind-selected denial still precedes requested-content I/O, and public admissions have only
`file | directory` kinds. CAH-026 defines this reusable service without unused runtime wiring;
CAH-037's sole M2 composition factory creates and shares the per-session policy after the native read
services exist.

For an ordinary runtime task, the **initial** context request defaults to repository scope `.` with
empty `focus_paths` and `search_queries`. Those empty values are explicit rather than task- or
model-inferred. After a native read succeeds, the registry's harness-owned metadata identifies the
execution-time canonical request scope captured by the final native access-time admission first and
then the owner directory of every model-visible returned path. List/search retain that scope in a
dedicated content-suppressed result field even for empty/no-match success: directory search copies the
listing's final scope, while direct-file search copies its final read path. Stat/read use their final
admitted result path, with `read_file` copying the final pre-open path. The loop never re-resolves the
original alias. It discovers all ordered scopes and, after each discovery guard, requires the
bundle's `canonical_scope` to exactly equal the captured scope before atomically adding bindings.
There is no alias fallback, and a mismatch prevents result replay and another provider start.
Deterministic evaluation may inject non-empty initial values through a test-only
composition seam without granting the model context policy authority. For such a request, every
focus/search projection validates with zero I/O, instruction discovery folds and checks `scope` as
the first I/O, and every canonical-distinct focus read/discovery/fold completes before search. Each
query searches only the supplied scope through
`SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)`. Focus paths,
matches, and result paths never become inferred search roots. Each search result's execution-time
canonical request scope must equal root discovery's captured canonical scope before matches are
inspected or another search starts. Every first-occurrence search-match
file owner does become an instruction-discovery scope and joins the required instruction union before
its excerpt can enter context.

## Provenance and attribution

A repository context item should record:

- A workspace-relative source path.
- For an instruction, the canonical directory to which it applies.
- The selected line range or metadata scope.
- A content hash or revision marker when useful for detecting staleness.
- The retrieval tool or rule that selected it.
- A concise inclusion reason.
- Its measured budget cost.

Workspace-relative paths avoid leaking unnecessary personal paths into provider requests and
transcripts. Line ranges let the final answer point back to evidence and let evaluations determine
whether the correct region was retrieved.

Workspace-relative labeling does not make repository content non-sensitive. Explicitly selecting
OpenAI authorizes bounded, policy-admitted context and read-tool results to leave the machine for
that session, and the user-facing configuration must warn that deny/ignore policy does not inspect
ordinary allowed files for embedded secrets. The deterministic mock path sends nothing over the
network.

## Budgeting policy

Budgets are explicit configuration, not a final string truncation. The builder will reserve space
for the user task, provider response, and tool results before selecting optional repository text.
Selection should prefer, in order:

1. Applicable safety and repository instructions.
2. The current task and essential session state.
3. Directly requested or directly matching source excerpts.
4. Nearby definitions and tests that explain behavior.
5. Lower-confidence supporting material.

When an item does not fit, the builder omits it as a unit or creates a clearly identified bounded
excerpt. A later applicable instruction is required: enrichment either adds the complete source
without evicting prior context or fails before result replay and the next provider start. It must not
silently cut JSON, split a tool result into an invalid shape, or remove provenance. The context
builder exposes an inclusion report so a learner can see what was selected, omitted, and why.

## Iterative retrieval

The initial model request should contain enough orientation to choose useful read tools, not a dump
of every file. A typical read-only task can iterate:

```text
task + instructions
  -> list or search relevant paths
  -> identify requested and returned-path owner scopes
  -> add every newly applicable scoped instruction
  -> read bounded source and tests
  -> form a grounded explanation or plan
```

The agent loop applies turn and tool-call limits to this process. Repeated reads should be visible
in metrics so evaluations can distinguish useful investigation from context churn.

## Evaluation questions

Context scenarios should answer:

- Were the known relevant files and instruction scopes found?
- Were source line ranges accurate and sufficient?
- Did excluded, oversized, binary, or outside-workspace content stay excluded?
- Could the answer explain why every repository item was present?
- How many unnecessary reads and repeated reads occurred?
- Did the request stay within the configured context budget?

These tests begin with deterministic workspaces and fake-provider scripts. Live-model retrieval
quality is an optional smoke evaluation outside default checks.

## Implementation stories

### Implemented CAH-024 — Establish the workspace boundary

> As a user, I want every context operation rooted in the selected workspace so that inspection
> cannot wander into unrelated files.

The [implemented story](../user-stories/cah-024-establish-workspace-boundary.md) ends at immutable
Python path values and deterministic validation. Canonical-root, relative-path, limit,
missing-target, symlink-containment, stale-root, and workspace-relative reporting behavior have
focused tests. Instruction discovery, repository-content reads, model tool schemas, and
execution-time race protection remain later work.

### Implemented CAH-026 — Define repository read contracts and policy

> As a user, I want every native read to reuse one containment, ignore, deny, and limit policy so
> that handlers cannot disagree about what repository content is available.

The [implemented story](../user-stories/cah-026-define-repository-read-contracts.md) owns
nested Git-compatible ignore evaluation through PathSpec, a non-overridable credential/VCS denylist,
shared text rules, and fixed safe failures. Ignore rules are evaluated independently against both the
normalized supplied path and its resolved canonical target. Each view admits every directory prefix
through the paired rules' direct-directory view before loading deeper policy; both kind views use bare
labels and skip ancestor-only results, and only the final leaf evaluates both. Either path-name view's ignored ancestor or target denies
access. Its pure lexical-path
and `is_hard_denied_path` helpers perform no I/O and are reused
by CAH-025 so instruction discovery cannot drift to weaker pre-I/O admission. Every present ignore
policy source separately passes workspace resolution, canonical hard denial, and an immediate
pre-read recheck. Each view captures the admitted owner's canonical label plus followed directory
device/inode and requires both before the non-following leaf probe and a cache-miss read; an A-to-B
retarget or same-label replacement fails before replacement-leaf work. The view-relative owner label
still controls rule scope, while the canonical source controls cache and byte-budget identity. Even a
cache hit re-admits the owner and resolves the current leaf/source before attaching cached rules,
without rereading or charging bytes, while still consuming candidate-pattern work. One inclusive
65,536-pattern-slot budget spans both path-name views and every recursive descendant; each logical
evaluation charges only the selected kind view. An over-bound logical
evaluation fails before the matcher runs. CAH-025 does not inherit ordinary-read limits or errors. Direct
admission exposes only regular-file and directory results; special targets are unavailable. This unit
performs no user-requested read operation itself and deliberately defers per-session composition to
CAH-037.

### Planned CAH-025 — Discover scoped repository instructions

> As a contributor, I want applicable workspace instructions included with their scope so that the
> agent follows repository-specific rules while preserving harness safety.

The [implementation-ready story](../user-stories/cah-025-discover-repository-instructions.md)
discovers exact root-to-nearest `AGENTS.md` candidates after CAH-026. Its sole result factory uses
the admitted file/directory kind to reject unrelated, duplicate, equal-depth, or reordered owners;
only a unique ancestor chain can become an immutable bundle. One exact canonical-label validator
also keeps absolute, escaping, non-canonical, NUL, and lone-surrogate scope/source/owner spellings out
of every downstream carrier. Every binding preserves the
resolved canonical `source` separately from the canonical candidate-owner `applies_to` scope; the
same source reached through different owners remains separately applicable and charged. It exempts
these control-plane candidates from `.gitignore`, not from hard denial, and locks strict text,
source/binding limits, rechecks, no-partial failure, and non-leaking errors without provider,
registry, or loop behavior.

### Planned CAH-027 through CAH-029 — Add bounded native read operations

> As an agent, I want safe native file listing, reading, searching, and metadata tools so that I can
> investigate without using subprocesses.

The implementation-ready stories separate
[listing and metadata](../user-stories/cah-027-list-files-and-stat-path.md),
[one bounded text read](../user-stories/cah-028-read-bounded-text-file.md), and
[literal text search](../user-stories/cah-029-search-repository-text.md). All reuse CAH-026, resolve
again before access, return deterministic workspace-relative evidence, and stay independent of
provider/tool registration. Literal-search queries reject the complete line-boundary repertoire used
by Python `str.splitlines()`, including its C0, C1, and Unicode separators.

### Planned CAH-030 — Build and explain budgeted context

> As a learner, I want a report of selected and omitted context so that I can understand and improve
> the model input.

The [implementation-ready story](../user-stories/cah-030-build-budgeted-context.md) selects required
instruction bindings for scope, every explicit focus path, and each first-occurrence search-match
owner before admitting focus files or search excerpts under fixed item/UTF-8-byte budgets. It copies
each binding's candidate-owner `applies_to` rather than deriving scope from its source, and uses the
exact supplied-scope search projection above; returned paths expand instruction coverage but never
search roots. It stores each CAH-025 precedence rank unchanged—gaps remain gaps—and CAH-032 copies the
same value into provider context. It also owns pure atomic enrichment with an already-discovered
instruction bundle: prior items retain their relative order, and a late ancestor is inserted before
existing descendants without evicting anything. Its inclusion report distinguishes source and
applicability while preserving admitted provenance and aggregate omission reasons without exposing
denied labels.

### Planned CAH-037 — Evaluate the composed read-only outcome

> As a learner, I want deterministic explain and plan cases so that context usefulness is tested
> through the actual loop rather than inferred from isolated handlers.

The [implementation-ready story](../user-stories/cah-037-prove-read-only-assistant.md) composes the
strict fake, fixture workspaces, context, registry, and bounded loop. It checks exact retrieval and
small grounded answer facts, including root-only initial context followed by complete instruction
coverage for direct and broad-result path owners before replay, plus injected focus/search context
that proves the complete instruction union and exact supplied-scope search projection. Duplicate
argument rejection is also required M2 evidence; semantic ranking and live-model quality remain
future-quality and optional-live concerns respectively. That evidence includes 63/64/65-level
object-array shapes, quote/escape-aware delimiters, signed-64-bit endpoints and overflow,
fraction/exponent rejection, nested and array-contained duplicates, non-finite constants, and
defensive decoder `RecursionError`/`ValueError`, all through CAH-039 before native I/O. Projection
evidence separately checks signed-64-bit result endpoints and overflow, 63/64/65-level complete
envelopes, width/work exhaustion, and defensive serializer `RecursionError`/`ValueError`.
