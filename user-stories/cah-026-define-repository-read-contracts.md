# CAH-026 - Define repository read contracts and policy

- **Status:** Planned
- **Milestone / primary epic:** M2 - Read-only coding assistant / E3 - Repository context and
  read-only tools
- **Dependencies:** CAH-024
- **Lesson:** [Repository read policy](../docs/lessons/cah-026-repository-read-policy.md)
- **Learning emphasis:** Core learning unit - harness-owned tool policy and safe capability design
- **Review focus:** The common admission decision every native read operation must reuse before it
  touches repository content

## User story

> As a user, I want every repository read operation to share one explicit ignore and sensitive-path
> policy so that adding a new tool cannot silently broaden what the agent may inspect.

## Single responsibility

CAH-026 owns the common repository-read policy, fixed error vocabulary, and provider-neutral result
contracts used by later native read operations. It exposes pure lexical-path admission and built-in
hard-deny primitives for CAH-025, then composes those primitives with GitIgnoreSpec for ordinary
reads. CAH-025 does not consume this unit's ordinary-read limits, decisions, errors, or ignore
policy. This unit does not list, read, or search user-requested source content and does not register
or dispatch model-callable tools.

## Scope

- Add a focused Python repository-access policy module layered on CAH-024's canonical workspace
  boundary.
- Add the maintained `pathspec` dependency and use `pathspec.GitIgnoreSpec` for Git-compatible root
  and nested `.gitignore` evaluation; commit the resolved `uv.lock` change during implementation.
- Define immutable, typed policy decisions, safe errors, canonical-label records, and shared hard
  limits consumed by CAH-027 through CAH-030.
- Expose
  `normalize_repository_path_components(value: str) -> tuple[str, ...]` as the pure pre-I/O lexical
  admission helper for CAH-025 and the full read policy. It accepts exactly `str`; after JSON parsing
  it enforces the same strict Unicode-scalar, nonempty relative Linux path syntax as the admission
  pipeline, normalizes legal `.` components, returns `()` for the root, and rejects other input
  types, NUL, absolute paths, and every `..` component without constructing a `Path`, resolving a
  target, or touching the filesystem.
- Expose `is_hard_denied_path(components)` as an intentional pure public primitive over an already
  normalized tuple of workspace-relative path components. It performs no resolution or I/O and
  returns only a Boolean; CAH-025 uses it without importing GitIgnoreSpec policy.
- Define the shared model-facing string admission rule used by later path and query request models:
  after JSON parsing, require an exact strict UTF-8 encode/decode round-trip before policy or
  filesystem work.
- Walk the supplied lexical ancestor chain and the resolved canonical target ancestor chain from root
  to leaf. Load only `.gitignore` files whose owning directory is still traversable, interpret rules
  relative to that directory, and evaluate each view independently; an ignored ancestor or target in
  either view denies the target.
- Treat each present `.gitignore` as untrusted policy input: retain its candidate-owner directory for
  rule scope, but resolve its source through `WorkspaceBoundary`, apply canonical hard denial, and
  recheck that admitted source immediately before reading its bounded bytes.
- Keep all behavior native Python, local, deterministic, and side-effect free apart from bounded
  reads of policy files: no subprocess, shell, network, provider, protocol, transcript, or TUI
  change.

## Locked contract

### Admission pipeline and ownership

- `RepositoryPathSyntaxError` is the helper's only failure. It is a typed, policy-neutral
  `ValueError` with the exact fixed message `Repository path syntax is invalid.`; its string and
  representation contain no supplied value. The ordinary read pipeline catches it and maps it to
  `invalid_repository_path`; CAH-025 catches the same value and maps it to
  `invalid_instruction_scope`. Neither consumer exposes the neutral helper exception directly or
  imports the other's error contract.
- The Python harness owns repository read admission. Every later operation validates its input,
  first applies the shared model-facing string admission rule, applies the hard denylist and lexical
  ignore view to supplied relative components, resolves through `WorkspaceBoundary` only when the
  lexical view admits, then applies the hard denylist and canonical ignore view to the resolved
  components. It next checks operation-specific type and limits, then repeats admission and
  resolution immediately before I/O. Lexical checks prevent denied or ignored supplied names from
  becoming an existence oracle or symlink bypass; canonical checks prevent a safe-looking alias from
  bypassing policy on its resolved target.
- Public operations accept workspace-relative paths and return only canonical workspace-relative
  POSIX labels. Absolute host paths, user-supplied aliases, and raw filesystem exceptions never enter
  public values or default representations.
- `pathspec.GitIgnoreSpec` is the required Git-style matcher. A root `.gitignore` applies below the
  root; each nested `.gitignore` applies only below its owning directory. Within a file, later rules
  win; across files, the nearest applicable file is evaluated later. Git-style `!` negation may
  re-include a normally ignored path when its parent traversal is available.
- `GitIgnoreSpec` supplies matching, but the policy owns traversal semantics. Each view walks proper
  directory ancestors from root to leaf, evaluates each directory label with the policy files
  available before entering it, and loads that directory's `.gitignore` only after the directory is
  admitted. If an ancestor remains ignored, the view denies immediately: policy files inside or below
  that directory are neither opened nor charged, and a later negation for the leaf cannot rescue it.
  Thus `private/` followed by `!private/keep.py` still denies `private/keep.py`, while
  `private/*` followed by `!private/keep.py` may admit it because `private/` itself stays traversable.
  Only after every proper ancestor admits does the final target match decide that view.
- A policy binding has two identities. Its candidate-owner directory determines where parsed rules
  apply; its resolved canonical source determines containment, hard denial, cache identity, and
  policy-file budgets. Every present `.gitignore` candidate resolves through
  `WorkspaceBoundary.resolve_existing` before content I/O, and `is_hard_denied_path` evaluates the
  resolved source components before type, size, or text admission. A safe internal symlink is
  allowed, but its rules remain relative to the candidate owner rather than moving to the source
  directory. Policy sources do not recursively pass through GitIgnoreSpec because doing so would
  make ignore-policy loading self-referential.
- Ignore admission has two independent views. The lexical view matches the normalized supplied
  workspace-relative path against root-to-nearest policy files on its supplied ancestor chain,
  without replacing that label with a symlink target. The canonical view matches the
  `WorkspaceBoundary` target-relative label against policy files on the resolved target's canonical
  ancestor chain. Each view verifies ancestor traversability and computes normal Git precedence only
  within that view. The target is admitted only when neither view has an ignored ancestor or final
  target; negation in one view cannot cancel an ignored decision in the other. Lexical ancestor
  denial occurs before requested target resolution; canonical ancestor denial occurs after requested
  target resolution but before requested content I/O.
- Policy-file count and byte limits apply to the union of the two applicable ancestor chains.
  Policy candidates that resolve to the same admitted canonical source label are loaded and charged
  once, even though their rules may be evaluated against both labels or at multiple candidate-owner
  scopes. A shared read/parse cache does not reuse a view-relative match result: each view attaches the
  cached rules at that view's owning-directory scope and performs its own ancestor walk. Escaping,
  hard-denied, or otherwise unadmitted policy sources never enter the cache or consume count or byte
  budget. The root policy therefore does not consume the budget twice merely because every request
  has two views. A lexical denial short-circuits before resolving the requested target or loading its
  canonical-chain policy files.
- The final ignored decision is non-overridable. No public input, provider argument, configuration,
  or future approval may request `include_ignored`. A hard-denied path can never be re-included by a
  negation rule.
- Probe each exact `.gitignore` entry without following its leaf, so only an actually absent directory
  entry is normal and a symlink entry remains present even when dangling. Once an entry is observed, a dangling,
  inaccessible, escaping, hard-denied, non-regular, or retargeted source is
  `repository_policy_invalid`; it is not silently treated as absent. Immediately before a cache-miss
  content read, the policy repeats boundary resolution and canonical hard denial, requires the same
  canonical source label observed for that candidate, and rechecks regular-file type and size. The
  admitted source must be no larger than 64 KiB (65,536 bytes), contain no NUL, and decode with strict
  UTF-8. At most 16 distinct admitted canonical policy sources and 256 KiB (262,144 bytes) of
  aggregate policy text may be loaded for one decision. The seventeenth distinct source fails before
  its content is opened.
- Policy snapshots are bounded decisions, not persistent authorization. Callers re-evaluate before
  access; descriptor-relative hardening remains deferred.

### Non-overridable hard denylist

The denylist is applied to every supplied and canonical path component or basename before
`.gitignore`. VCS and credential-directory component names are case-sensitive on the supported
Linux filesystem. Credential filename and suffix comparisons use ASCII lowercase so an uppercase
extension cannot bypass the same secret-file rule.

`is_hard_denied_path(components)` is the single implementation of this table. Callers first use
`normalize_repository_path_components` or supply an equivalently normalized canonical tuple; the
classifier neither resolves paths nor reveals which entry matched. The full repository-read
pipeline and CAH-025 instruction discovery both call these pure primitives, so the control-plane
exemption from `.gitignore` cannot become a hard-deny bypass.

- Any component exactly `.git`, `.hg`, `.svn`, `.ssh`, `.gnupg`, or `.aws` is denied.
- A basename exactly `.envrc`, `.netrc`, `.npmrc`, `.pypirc`, `.git-credentials`, `credentials`,
  `credentials.json`, `application_default_credentials.json`, `service-account.json`, `id_rsa`,
  `id_dsa`, `id_ecdsa`, or `id_ed25519` is denied.
- A basename exactly `.env` or ending `.env` is denied, covering names such as `dev.env`. A basename
  beginning `.env.` is denied except the exact documentation names `.env.example`, `.env.sample`,
  and `.env.template`.
- A basename ending `.pem`, `.key`, `.p12`, or `.pfx` is denied.
- Denial uses one generic result and never confirms which rule matched. These initial conservative
  defaults are reviewed product policy; broadening or making them configurable requires a later
  design decision and threat-model update.

### Shared operation limits and text rules

| Limit | Initial reviewed default / hard maximum |
| --- | ---: |
| One eligible source file | 256 KiB (262,144 bytes) |
| One returned text payload | 64 KiB (65,536 bytes) |
| One listing response | default 200 / hard 500 items |
| Recursive listing depth | default 4 / hard 8 directory levels |
| One search response | default 100 / hard 200 matches |
| One context package | 24 items and 96 KiB (98,304 content bytes) |

- Every model-facing path or query is already a Python `str` after JSON parsing. Before constructing
  a path, evaluating policy, or accessing the filesystem, the shared admission helper encodes the
  value with strict UTF-8, decodes those bytes with strict UTF-8, and requires exact equality. Lone
  surrogates and literal NUL fail; valid Unicode scalar values pass unchanged, with no Unicode
  normalization. Path fields use `invalid_repository_path`; query and other non-path inputs use
  `repository_input_limit`.
- Repository text means strict UTF-8 without NUL. Replacement decoding, locale fallback, binary
  heuristics that expose raw bytes, token-count estimates, and provider-specific tokenizers are
  prohibited.
- Limits are counted in original or returned UTF-8 bytes and result items as each later story
  specifies. They are deterministic safety budgets, not promises about LLM tokens.

### Fixed, non-leaking failures

`RepositoryAccessError` carries one code and fixed message. It contains no input path, host path,
denylist rule, ignore pattern, raw OS text, or repository content.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_repository_path` | `Repository path must be a valid workspace-relative path.` | a path is not a strict Unicode-scalar/UTF-8 round-trip after JSON parsing or its path syntax fails |
| `repository_path_not_found` | `Repository path does not exist.` | the admitted target is missing |
| `repository_path_unavailable` | `Repository path is not available.` | containment, hard-deny, staleness, or safe inspection fails |
| `repository_path_ignored` | `Repository path is ignored.` | a direct target is excluded by effective ignore rules |
| `repository_expected_directory` | `Repository path must be a directory.` | an operation requires a directory |
| `repository_expected_file` | `Repository path must be a regular file.` | an operation requires a regular file |
| `repository_not_text` | `Repository file must be valid UTF-8 text.` | strict decode fails or NUL is present |
| `repository_source_too_large` | `Repository file exceeds the byte limit.` | an eligible source exceeds 256 KiB |
| `repository_input_limit` | `Repository request exceeds the input limit.` | a request exceeds an operation's fixed input bound |
| `repository_result_limit` | `Repository result exceeds the item or byte limit.` | safe bounded completion is not possible |
| `repository_policy_invalid` | `Repository ignore policy could not be loaded safely.` | an applicable policy source escapes, is hard-denied, dangling, inaccessible, retargeted, non-regular, invalid, oversized, or unreadable |
| `repository_read_failed` | `Repository content could not be read.` | another bounded local access fails |

- Direct access to ignored or unavailable targets fails with the table above. Recursive listing and
  search omit ignored and denied descendants without reporting their labels or matching rule.
- Common contracts define error and admission behavior; operation-specific result shapes are owned
  by CAH-027 through CAH-030.
- Policy evaluation is synchronous and bounded. Callers check cancellation between operations;
  this unit introduces no event-loop or task lifecycle.

## Reviewability budget

- **Estimated production-code churn:** 300-450 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Split rule:** stop and refine another story before review if the unit starts performing a read
  tool's business operation, adds configuration layers, or is likely to exceed roughly 600 changed
  production lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One typed Python policy composes CAH-024 containment, the exact hard denylist, and applicable root
   plus nested `GitIgnoreSpec` rules for both the supplied lexical and resolved canonical ancestor
   chains in deterministic precedence order.
2. Pure public lexical admission rejects invalid Unicode/path syntax before `Path` construction or
   I/O, and one pure hard-deny classifier implements the exact table without I/O or rule disclosure;
   the full read policy consumes both primitives and produces the same decisions as their direct
   calls from the same normalized components.
3. Every proper ancestor remains traversable in both views before a leaf negation can take effect.
   Normal Git ignore negation works within each view only under that rule, either view's ignored
   ancestor or target wins, and no cross-view negation, caller override, or pattern can re-include an
   ignored-in-the-other-view or hard-denied path.
4. Every present policy candidate preserves its owner-relative rule scope while its source passes
   `WorkspaceBoundary`, canonical hard denial, regular-file, 64-KiB per-file, 16-distinct-source,
   256-KiB aggregate, strict-UTF-8, and no-NUL admission. The source is re-resolved and rechecked
   immediately before a cache-miss read. Containment, hard-deny, disappearance, non-regular,
   retarget, and pre-read size failures perform no policy-source content read. Invalid UTF-8 or NUL
   may be detected only in one bounded, uncommitted policy candidate; it is never exposed, cached, or
   charged, and every failure prevents requested content I/O under fixed
   `repository_policy_invalid`.
5. Direct ignored targets fail explicitly; traversal consumers can omit ignored and denied
   descendants without disclosing their labels.
6. Shared limits, immutable decisions, and the exact error table are typed, documented, and contain
   canonical labels only when access has been admitted.
7. Every model-facing path/query string passes strict Unicode-scalar/UTF-8 round-trip admission
   without Unicode normalization; lone surrogates fail before policy evaluation or any filesystem
   call.
8. The implementation makes no subprocess, network, provider, protocol, transcript, or TUI change,
   and tests use temporary local repositories only.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Ancestor traversal and nested precedence | Compare `private/` plus `!private/keep.py` with the traversable-parent control `private/*` plus `!private/keep.py`; put an invalid nested policy below the ignored directory | Unit | The ignored parent denies direct access, its nested policy is never opened or charged, and leaf negation works only in the traversable-parent control |
| Relative pattern scope | Repeat a filename inside and outside a nested policy directory | Unit | Nested rule affects only its subtree |
| Lexical/canonical alias policy | Point a supplied alias at a differently named canonical target; independently ignore only an ancestor or leaf of the alias, only an ancestor or leaf of the target, both, and neither, including an opposing leaf negation | Policy/boundary integration | Either view's ignored ancestor or leaf denies; access requires both complete walks to admit, lexical denial performs no requested target resolution, canonical denial performs no requested content I/O, and neither label nor rule leaks |
| Dual-chain policy budget | Share root and aliased policy files across both chains, give the two view owners different labels, then cross the unique-file count and aggregate-byte edges | Unit | Canonically identical policy inputs are read/charged once but their cached rules are scoped and evaluated in both views; the union still fails closed above 16 files or 256 KiB |
| Policy-source containment | Point root and nested `.gitignore` candidates outside the workspace and at `.git/config` or `secrets/dev.env`; use an actually absent control, a safe internal symlink, a dangling candidate, and pre-read disappearance/retarget/type/size replacements | Policy/boundary integration | Only the absent entry is normal; every present unsafe source returns exact `repository_policy_invalid` and causes no requested content read; pre-read rejection opens no policy content, the internal source is committed once after validation, and its rules remain scoped to each candidate owner |
| Shared lexical admission | Pass scalar relative paths, `.`, redundant legal `.` components, a non-string object, empty text, absolute paths, every `..` placement, NUL, and lone high/low surrogates while spying on `Path`, boundary, and filesystem calls | Unit/read-policy integration | Valid components normalize deterministically; invalid inputs raise only the fixed, content-suppressed `RepositoryPathSyntaxError` before construction, resolution, or I/O; ordinary reads map it to their fixed vocabulary |
| CAH-024 lexical parity | Run the representative string corpus through the pure helper and CAH-024's existing pre-filesystem admission, creating targets only for accepted controls | Policy/boundary integration | Both accept/reject the same string grammar without Unicode normalization; valid helper components reflect only legal path-component normalization, and PathLike-only CAH-024 inputs remain outside the model-facing helper contract |
| Shared hard-deny primitive | Call `is_hard_denied_path` directly for every exact component, basename, suffix, case rule, documented `.env` exception, empty-root tuple, and a normal control; run the same normalized components through the read policy | Unit/read-policy integration | The pure call performs no path or filesystem I/O, returns only a Boolean, and the read policy makes the same deny/admit decision without revealing the matching rule |
| Non-overridable denial | Try ignore negation and a fabricated override for every denylist class | Unit/schema | Generic unavailable result; unsupported override rejected |
| Exact policy limits | Exercise 65,535/65,536/65,537 bytes, 16/17 files, aggregate edge | Unit | Success at limits and fixed failure above |
| Strict text | Use invalid UTF-8 and NUL in applicable `.gitignore` files | Unit | `repository_policy_invalid` with no decoder or content leak |
| Model-facing strings | After JSON parsing, pass multibyte scalar text, lone high/low surrogates, and NUL as path/query values | Request/policy boundary | Scalars round-trip unchanged; invalid values use the field's fixed error with zero policy/filesystem calls |
| Check-before-use | Replace an admitted target or root before the final decision | Boundary integration | Re-evaluation fails safely rather than preserving authorization |
| Error hygiene | Use distinctive paths, patterns, and raw OS failures | Unit | Exact table strings and leak-free representations |

## Validation

- Add focused policy tests for GitIgnoreSpec semantics, nested scope, negation, directory patterns,
  denylist precedence, canonical symlinks, stale roots, and exact safe errors. Exercise the complete
  lexical/canonical ignore truth table and prove an opposing negation cannot override the other
  view's ignored decision. Direct-access regressions prove `private/` plus `!private/keep.py` denies
  in both lexical and canonical views, while `private/*` plus `!private/keep.py` admits only when the
  other view also admits. A boundary spy proves lexical ancestor denial starts no requested target
  resolution; an I/O spy proves canonical ancestor denial starts no requested content access.
- Cover root and nested policy candidates that symlink outside the workspace or to `.git/config` and
  `secrets/dev.env`, plus an actually absent entry, an allowed internal-policy-source control, a
  present dangling link, and deterministic disappearance, retarget, directory/special-file, and
  oversized-file replacements between initial admission and the cache-miss read. Boundary and I/O
  spies prove canonical hard denial and every pre-read rejection precede policy-source content access;
  only the absent entry is ignored; rejected sources never enter cache or budgets; invalid UTF-8/NUL
  is held only as a bounded uncommitted candidate; every failure uses exact leak-free
  `repository_policy_invalid`; and a shared allowed source is read and charged once only after full
  validation while its rules remain candidate-owner relative.
- Put an invalid or oversized `.gitignore` below an already ignored directory and prove it is never
  opened or charged and cannot replace `repository_path_ignored` with `repository_policy_invalid`.
- Test every numeric policy boundary below, at, and above; test the shared constants as public
  reviewed defaults rather than duplicated literals. For the two-chain policy budget, prove shared
  canonical policy files are charged once and distinct files across the union are all charged.
- Test `normalize_repository_path_components` and `is_hard_denied_path` as pure functions, including
  scalar paths, the empty root tuple, non-string/absolute/empty/`..`/NUL/surrogate failures, exact
  fixed helper exception/message/representation, case rules, suffix rules, and the three documented
  `.env` examples. `Path`, filesystem, and boundary spies prove both primitives perform no I/O. Run
  the same string corpus through CAH-024's established lexical admission and prove parity. Read-policy
  integration proves ordinary repository reads use the public primitives and map the neutral lexical
  failure into their own fixed error vocabulary.
- Use injected policy and filesystem spies to prove lone-surrogate and NUL path/query rejection
  happens after JSON parsing but before denylist matching, `Path` construction, resolution, stat, or
  file access. Include valid non-ASCII scalar text to prove no Unicode normalization occurs.
- Inspect the dependency and lockfile diff and prove default tests perform no network access.
- Keep protocol, transcript, provider, and TUI schemas unchanged; use the full repository gate as
  nearest parity evidence.
- Run focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update dependency documentation, context-engineering, safety model, glossary, story and lesson
indexes, E3 backlog sequence, and the Markdown lesson's compact architecture diagram. Record why
GitIgnoreSpec and the non-overridable denylist are separate policy layers, why CAH-026 precedes
CAH-025 in delivery, and why the shared classifier exposes a decision rather than deny-rule detail.
Do not add or revise a presentation.

## Exclusions

- Listing directories, reading source content, text search, context selection, tool registration,
  dispatch, or model-visible tool results.
- User/workspace configuration that broadens or narrows policy, secret scanning, content
  classification, tokenization, or approval prompts.
- Instruction discovery behavior from CAH-025; `AGENTS.md` remains a separate control-plane input.
  This unit supplies only pure lexical-path and hard-deny decisions that CAH-025 consumes.
- File writes, subprocesses, shell use, network access, protocol events, transcript fields, TUI
  rendering, MCP transport, and agent-loop continuation.
- Descriptor-relative access, filesystem watchers, multiple roots, non-Linux matching semantics,
  and claims that check-before-use removes all races.

## Definition of done

1. Every acceptance criterion has deterministic happy, boundary, and adversarial failure evidence.
2. All policy and shared numeric limits pass below/at/above tests, and model-facing path/query
   strings pass strict Unicode-scalar/UTF-8 boundary tests before filesystem access.
3. Pure lexical admission performs no construction/resolution/I/O and rejects invalid syntax before
   hard-deny classification; the hard-deny classifier is the only implementation of the exact table,
   performs no I/O or rule disclosure, and has parity evidence through the full read policy.
4. GitIgnoreSpec precedence and ancestor traversability in both lexical and canonical views, lexical
   denial before requested target resolution, denial before requested content I/O, either-view-denies
   combination, canonical-only public labels, hard-deny dominance, and no ignored override are
   proved. Every present policy source has owner/source identity, boundary and hard-deny admission,
   pre-read recheck, fixed failure, safe internal-symlink, and canonical cache/budget evidence.
5. Public contracts are immutable, typed, documented, and emit only the fixed safe failures.
6. Focused tests and the canonical offline `./scripts/check` pass without a model, subprocess, or
   network.
7. Existing protocol, transcript, provider, and TUI boundaries remain unchanged and pass their
   existing tests.
8. The Markdown lesson includes exact implementation and failure-test excerpts after code exists;
   no presentation work is introduced.
9. Story, lesson, conceptual docs, indexes, backlog, planning note, dependency declaration, lockfile,
   and statuses agree.
10. Delivered production-source churn is recorded and stays near the planned range or is split before
   review.
11. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- A repository-access policy module and temporary-repository tests prove exact matching and denial,
  including aliases whose lexical and canonical ignore decisions disagree.
- Pure lexical/classifier tests plus read-policy integration prove pre-I/O path admission and the
  hard-deny table cannot drift inside ordinary-read policy; CAH-025 owns the later control-plane
  consumer evidence.
- `pyproject.toml` and `uv.lock` record the reviewed PathSpec dependency without any runtime network
  requirement.
- The lesson locates policy between the workspace boundary and all native read operations; its
  primary teach-back question is: why is an approval or model argument unable to override a denied
  read?

## Deferred work

- CAH-025 consumes only the pure lexical-path and hard-deny helpers while retaining its explicit
  `.gitignore` exemption for instruction control-plane files.
- CAH-027, CAH-028, and CAH-029 reuse the full read policy for listing, reading, and literal search.
- CAH-030 applies the shared item and byte limits to deterministic context inclusion.
- E4 later adds schema-validated tool registration and dispatch without moving policy ownership out
  of the harness.
