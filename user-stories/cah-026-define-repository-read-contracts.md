# CAH-026 - Define repository read contracts and policy

- **Status:** Done
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
  adapter for CAH-025 and the full read policy. It accepts exactly `str`, delegates to CAH-024's
  sole `normalize_workspace_relative_path` primitive, preserves its normalized component tuple, and
  translates only the fixed exception vocabulary. It does not duplicate CAH-024's strict Unicode,
  syntax, 4,095-byte, 256-component, or 255-byte-name decisions.
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
- Normalize each admitted policy line with Git's exact line rules: remove one terminal carriage
  return, trim only unescaped trailing ASCII spaces, and preserve tabs and Unicode whitespace. Scan
  that semantic line before PathSpec compilation and fail closed on an unescaped `?`, more than one
  unescaped `*` per ordinary segment, more than one compiler-effective active nonterminal `**` after
  trailing-separator handling, or a bracket expression outside the positive ASCII safe subset.
  Compile file and direct-directory `GitIgnoreSpec` views through the harness adapter that
  prevents PathSpec's broader trim; the directory view safely removes one semantic trailing slash
  only from an active retained pattern. Retained count/include identity is verified so an original
  invalid-range no-op cannot activate. Both match bare labels and skip ancestor-only `ps_d`
  results, so only a direct match may decide the current entry. This preserves global directory
  wildcards such as `*/`, `**/`, and `a/**/` without allowing a parent negation to impersonate a
  descendant match. Reserve file/directory two-form matching for the final leaf.
- Treat each present `.gitignore` as untrusted policy input: retain its view-relative candidate-owner
  label for rule scope, capture that owner's canonical label plus followed directory device/inode
  when the view admits it, and require both identities immediately before the non-following leaf probe
  and again before a cache-miss read. Resolve the leaf source through `WorkspaceBoundary`, apply
  canonical hard denial, and recheck that admitted source immediately before reading its bounded
  bytes.
- Bound ignore matching with one cumulative 65,536 candidate-pattern-slot work budget for each
  admission traversal. Charge work across ancestors, lexical/canonical views, both final-leaf forms,
  cache hits, and recursive descendant admissions rather than resetting it per matcher or path.
- Keep all behavior native Python, local, deterministic, and side-effect free apart from bounded
  reads of policy files: no subprocess, shell, network, provider, protocol, transcript, or TUI
  change.

## Locked contract

### Admission pipeline and ownership

- `RepositoryReadPolicy(boundary: WorkspaceBoundary)` is the exact stateful service boundary. It
  retains the supplied object as read-only `boundary` identity. This contract unit does not add an
  otherwise-unused runtime object: CAH-037's sole M2 composition factory creates one policy per
  session after the native read services exist, and CAH-027/028 services receive that same object.
  Its public direct-admission method is
  `admit_existing(path: str) -> AdmittedRepositoryPath`, where the frozen result contains
  exact canonical workspace-relative `path`, `kind`, and direct-leaf `is_symlink` provenance. `kind`
  is the closed literal set `file | directory`; an existing special target is unavailable rather
  than a third public kind. Recursive
  list/search code uses the same service's internal descendant-admission path rather than constructing
  another boundary or policy. Ignore-source caches, count/byte budgets, and candidate-pattern-slot
  work are local to one public admission/traversal decision and never become persistent authorization.

- `RepositoryPathSyntaxError` is the helper's only failure. It is a typed, policy-neutral
  `ValueError` with the exact fixed message `Repository path syntax is invalid.`; its string and
  representation contain no supplied value. The ordinary read pipeline catches it and maps it to
  `invalid_repository_path`; CAH-025 catches the same value and maps it to
  `invalid_instruction_scope`. Neither consumer exposes the neutral helper exception directly or
  imports the other's error contract.
- CAH-024 owns the lexical algorithm and inclusive path ceilings. This unit's adapter catches only
  CAH-024's fixed lexical failure and raises `RepositoryPathSyntaxError`; it never retries, repairs,
  truncates, normalizes Unicode, or lets an over-bound path reach hard-deny, ignore, boundary, or
  filesystem work.
- The Python harness owns repository read admission. Every later operation validates its input,
  first applies the shared model-facing string admission rule, applies the hard denylist, and walks
  the supplied lexical path's proper directory ancestors. It also evaluates both the lexical leaf's
  file and trailing-slash directory forms. An ignored ancestor or leaf ignored in both forms denies
  before requested-target resolution. The policy otherwise resolves through `WorkspaceBoundary`,
  applies canonical hard denial, and builds the canonical ancestor/two-form leaf decision. A
  canonical ancestor or leaf ignored in both forms denies before target type inspection. Only then
  does the policy admit exactly `file` or `directory` and select that kind's effective result in both
  views; an existing special target fails as unavailable. The operation then checks its own limits and repeats admission and
  resolution immediately before I/O. Hard denials, lexical ancestors, and type-independent leaf
  denials do not become existence oracles; the contained target kind is observed only when exact
  directory-only leaf semantics require it. Canonical hard denial and type-independent ignore checks
  still precede that inspection. Canonical checks prevent a safe-looking alias from
  bypassing policy on its resolved target, and no requested content is read during admission.
- Public operations accept workspace-relative paths and return only canonical workspace-relative
  POSIX labels. Absolute host paths, user-supplied aliases, and raw filesystem exceptions never enter
  public values or default representations.
- `pathspec.GitIgnoreSpec` is the required Git-style matcher. A root `.gitignore` applies below the
  root; each nested `.gitignore` applies only below its owning directory. Within a file, later rules
  win; across files, the nearest applicable file is evaluated later. Git-style `!` negation may
  re-include a normally ignored path when its parent traversal is available.
- Each admitted source supplies a cached pair of kind-specific `GitIgnoreSpec` views, while the policy
  owns direct-entry and traversal semantics. Both views compile the same Git-normalized lines, which
  preserve non-space trailing whitespace; the direct-directory view removes exactly one semantic
  trailing slash safely, without corrupting escaped/trailing whitespace, converting degenerate slash
  forms, or transforming an original no-op.
  The derived compile must preserve retained pattern count and include identity. Each view walks proper
  directory ancestors from root to leaf, evaluates each direct entry label with the policy files
  available before entering it, and loads that directory's `.gitignore` only after the directory is
  admitted. If an ancestor remains ignored, the view denies immediately: policy files inside or below
  that directory are neither opened nor charged, and a later negation for the leaf cannot rescue it.
  Thus `private/` followed by `!private/keep.py` still denies `private/keep.py`, while
  `private/*` followed by `!private/keep.py` may admit it because `private/` itself stays traversable.
  Both compiled views receive bare labels and skip matches whose `ps_d` marker says PathSpec reached
  the candidate only through an ancestor directory. Thus `private` followed by `!private/` re-admits
  `private` and its descendants. In the distinct review case, `private/*` followed by `!private/`
  keeps `private` traversable but ignores the immediate child `private/dir`, because `private/*`
  directly matches that child while the negation is only an ancestor match. The transformed directory
  view is also required for `*/`, `**/`, and `a/**/`: removing their semantic terminator before
  compilation lets each pattern directly match the current bare directory label instead of stopping
  at PathSpec's first ancestor slash.
  Only after every proper ancestor admits does the final target match decide that view. The lexical
  leaf's file and trailing-slash directory forms are both computed before kind inspection. The policy
  may deny early only when both effective results are ignored. Otherwise the safely resolved target
  kind selects the corresponding result before any read of requested content. This preserves later-rule
  negation precedence without falsely denying either a regular file or directory.
- A policy binding has two identities plus an owner-stability snapshot. Its view-relative
  candidate-owner label determines where parsed rules apply; its resolved canonical source determines
  containment, hard denial, cache identity, and policy-file budgets. When either the lexical or
  canonical view admits a candidate-owner directory, it also captures that owner's canonical
  workspace-relative label and the followed target's device/inode identity. Immediately before
  probing the `.gitignore` leaf without following it, and again before any cache-miss content read,
  the policy resolves and follows the owner label itself and requires the same canonical label,
  directory type, device, and inode. Only then may it resolve the leaf. A persistent
  `owner A -> allowed B` retarget or an allowed same-label directory replacement at either checked
  seam is `repository_policy_invalid` before `B/.gitignore` is resolved
  or read, and rules from B cannot be attached at A's scope. Every present `.gitignore` candidate then
  resolves through
  `WorkspaceBoundary.resolve_existing` before content I/O, and `is_hard_denied_path` evaluates the
  resolved source components before type, size, or text admission. A safe internal symlink is
  allowed, but its rules remain relative to the view's captured candidate-owner label rather than
  moving to the owner snapshot or source directory. Policy sources do not recursively pass through
  GitIgnoreSpec because doing so would make ignore-policy loading self-referential.
- Ignore admission has two independent views. The lexical view matches the normalized supplied
  workspace-relative path against root-to-nearest policy files on its supplied ancestor chain,
  without replacing that label with a symlink target. Its proper ancestors can deny immediately. The
  leaf denies pre-resolution only when its file and directory forms are both ignored. The canonical
  view matches
  the `WorkspaceBoundary` target-relative label against policy files on the resolved target's
  canonical ancestor chain, uses exact direct entries for those ancestors, and likewise computes both
  final-leaf forms before kind inspection. Each view
  verifies ancestor traversability and computes normal Git precedence only within that view. An
  ignored ancestor or leaf ignored in both forms denies immediately. Otherwise the resolved
  `file | directory` kind selects both views' exact effective result. The target is admitted only when
  neither selected view is ignored; negation in one view cannot cancel denial in the other. Lexical
  type-independent denial occurs before requested-target resolution; canonical hard denial and
  type-independent ignore denial occur after resolution but before kind inspection; selected denial
  still occurs before requested content I/O.
- Policy-file count and byte limits apply to the union of the two applicable ancestor chains.
  Policy candidates that resolve to the same admitted canonical source label are loaded and charged
  once, even though their rules may be evaluated against both labels or at multiple candidate-owner
  scopes. A shared read/parse cache does not reuse a view-relative match result: each view attaches the
  cached rules at that view's owning-directory scope and performs its own ancestor walk. A cache hit
  does not bypass pathname admission: the pre-probe owner re-admission, non-following leaf probe, and
  current leaf/source resolution all succeed before cached rules are attached; no content is read or
  newly charged on that path. Escaping,
  hard-denied, or otherwise unadmitted policy sources never enter the cache or consume count or byte
  budget. The root policy therefore does not consume the budget twice merely because every request
  has two views. A lexical ancestor or leaf ignored in both forms short-circuits before resolving the
  requested target or loading its canonical-chain policy files.
- Ignore-match work has a separate cumulative limit of 65,536 candidate-pattern probes per admission
  traversal. One probe is one potential pair of an applicable candidate path spelling and one
  compiled policy pattern slot, including a no-op slot the matcher later skips. Before invoking a
  logical evaluation, reserve the selected kind-specific view's complete stored pattern count so
  matcher short-circuit details cannot change accounting. The paired view is not charged for that
  evaluation. The same decision-local state
  charges every ancestor, scoped policy, lexical and canonical view, file/directory leaf form, cache
  hit, and recursive descendant admission. Reading a canonical policy source once avoids duplicate
  bytes and parsing, but attaching its cached rules at another scope or matching another candidate
  still costs probes. The budget never resets for a subtree or view. Exactly 65,536 probes are
  inclusive; a logical evaluation that would cross the limit fails as `repository_policy_invalid`
  before the harness-owned matcher runs.
- One pre-compile linear grammar gate also bounds work inside each admitted PathSpec regex. An
  ordinary slash segment may contain at most one unescaped `*` outside a safe bracket range, and a
  line may contain at most one compiler-effective nonterminal `**` segment with later content.
  Unescaped `?` fails because Git counts UTF-8 bytes while Python regex counts Unicode code points.
  Brackets admit only ASCII alphanumeric members, same-class ascending alphanumeric ranges, and fixed
  `_`, `*`, `?`, or `.` members; this excludes every observed Git/PathSpec range divergence and any
  range that could consume `/`. Escaped wildcards, safe-range wildcards, and terminal globstars remain
  supported. Unsupported syntax
  fails as `repository_policy_invalid` before either kind compile, cache/byte commit, match-work
  charge, or matcher call; this is a deliberate safe subset, not a claim to accept every Git pattern.
- The final ignored decision is non-overridable. No public input, provider argument, configuration,
  or future approval may request `include_ignored`. A hard-denied path can never be re-included by a
  negation rule.
- Immediately before probing each exact `.gitignore` entry, re-admit its owner label and require the
  captured canonical owner label plus followed directory device/inode. Probe the leaf without
  following it, so only an actually absent
  directory entry is normal and a symlink entry remains present even when dangling. Once an entry is
  observed, a dangling, inaccessible, escaping, hard-denied, non-regular, or retargeted source is
  `repository_policy_invalid`; it is not silently treated as absent. Immediately before a cache-miss
  content read, re-admit and compare the owner before resolving the leaf again; then repeat source
  resolution and canonical hard denial, require the same canonical source label observed for that
  candidate, and recheck regular-file type and size. Owner mismatch fails before replacement-leaf
  resolution; source mismatch fails before content I/O. The
  admitted source must be no larger than 64 KiB (65,536 bytes), contain no NUL, and decode with strict
  UTF-8. At most 16 distinct admitted canonical policy sources and 256 KiB (262,144 bytes) of
  aggregate policy text may be loaded for one decision. The seventeenth distinct source fails before
  its content is opened.
- Policy snapshots are bounded decisions, not persistent authorization. Owner label/device/inode and
  source rechecks close deterministic persistent mutations at their explicit seams but do not
  eliminate a pathname race after the final check. Filesystems may reuse device/inode pairs after the
  original owner disappears. Callers re-evaluate before access; descriptor-relative hardening remains
  deferred.

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
| One supplied workspace-relative path | 4,095 strict-UTF-8 bytes, 256 normalized components, and 255 strict-UTF-8 bytes per component |
| One eligible source file | 256 KiB (262,144 bytes) |
| One returned text payload | 64 KiB (65,536 bytes) |
| One listing response | default 200 / hard 500 items |
| Recursive listing depth | default 4 / hard 8 directory levels |
| One search response | default 100 / hard 200 matches |
| One context package | 24 items and 96 KiB (98,304 content bytes) |
| Ignore candidate-pattern probes per admission traversal | 65,536 cumulative work units |

- Every model-facing path or query is already a Python `str` after JSON parsing. Before constructing
  a path, evaluating policy, or accessing the filesystem, the shared admission helper encodes the
  value with strict UTF-8, decodes those bytes with strict UTF-8, and requires exact equality. Lone
  surrogates and literal NUL fail; valid Unicode scalar values pass unchanged, with no Unicode
  normalization. Path fields use `invalid_repository_path`; query and other non-path inputs use
  `repository_input_limit`.
- Path ceilings count the complete raw supplied spelling before legal dot/separator normalization,
  then the normalized non-`.` components and each component. They are deterministic harness work
  budgets, not promises about Linux `PATH_MAX`, a mount's `NAME_MAX`, the selected root prefix, or
  Windows-backed WSL behavior. A lexically admitted path may still fail bounded resolution.
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
| `invalid_repository_path` | `Repository path must be a valid workspace-relative path.` | a path exceeds the shared byte/component/name budget, is not a strict Unicode-scalar/UTF-8 round-trip after JSON parsing, or its path syntax fails |
| `repository_path_not_found` | `Repository path does not exist.` | the admitted target is missing |
| `repository_path_unavailable` | `Repository path is not available.` | containment, hard-deny, staleness, or safe inspection fails |
| `repository_path_ignored` | `Repository path is ignored.` | a direct target is excluded by effective ignore rules |
| `repository_expected_directory` | `Repository path must be a directory.` | an operation requires a directory |
| `repository_expected_file` | `Repository path must be a regular file.` | an operation requires a regular file |
| `repository_not_text` | `Repository file must be valid UTF-8 text.` | strict decode fails or NUL is present |
| `repository_source_too_large` | `Repository file exceeds the byte limit.` | an eligible source exceeds 256 KiB |
| `repository_input_limit` | `Repository request exceeds the input limit.` | a request exceeds an operation's fixed input bound |
| `repository_result_limit` | `Repository result exceeds the item or byte limit.` | safe bounded completion is not possible |
| `repository_policy_invalid` | `Repository ignore policy could not be loaded safely.` | an applicable policy source escapes, is hard-denied, dangling, inaccessible, retargeted, non-regular, invalid, outside the bounded matcher grammar, oversized, or unreadable |
| `repository_read_failed` | `Repository content could not be read.` | another bounded local access fails |

- Direct access to ignored or unavailable targets fails with the table above. Recursive listing and
  search omit ignored and denied descendants without reporting their labels or matching rule.
- Common contracts define error and admission behavior; operation-specific result shapes are owned
  by CAH-027 through CAH-030.
- Policy evaluation is synchronous and bounded. Callers check cancellation between operations;
  this unit introduces no event-loop or task lifecycle.

## Reviewability budget

- **Estimated production-code churn:** 300-450 changed lines.
- **Delivered production-code churn:** 839 additions and 0 deletions.
- **Counted paths:** `src/code_assist_harness/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Variance:** direct-entry Git semantics, cumulative and per-pattern match-work admission,
  Git-exact line normalization, and owner/source snapshot hardening raised the unit above the
  roughly-600 reviewability target. The delivered 839 additions still implement one read-admission
  responsibility; the review-driven grammar fixes must precede the same PathSpec side effect, so
  splitting them from that gate would weaken reviewability rather than create a separately shippable
  outcome.
- **Planning PR scope:** One contract neighborhood: CAH-024 canonical paths plus model-facing
  strings -> shared lexical/hard-deny/ignore-policy decision -> CAH-025's pure-primitive use and
  CAH-027 through CAH-030 ordinary-read consumers.
- **Split rule:** stop and refine another story before review if the unit starts performing a read
  tool's business operation, adds configuration layers, or is likely to exceed roughly 600 changed
  production lines. Do not pad a smaller coherent implementation.

## Acceptance criteria

1. One typed Python policy composes CAH-024 containment, the exact hard denylist, and applicable root
   plus nested `GitIgnoreSpec` rules for both the supplied lexical and resolved canonical ancestor
   chains in deterministic precedence order.
   The exact `RepositoryReadPolicy` constructor/method retains one CAH-024 boundary identity for all
   later native read services. Its frozen result admits only `file | directory`; special targets fail
   unavailable. Runtime composition remains with CAH-037's sole M2 service-composition factory.
2. Pure public lexical admission rejects invalid Unicode/path syntax before `Path` construction or
   I/O, and one pure hard-deny classifier implements the exact table without I/O or rule disclosure;
   the full read policy consumes both primitives and produces the same decisions as their direct
   calls from the same normalized components.
3. Every proper ancestor remains traversable in both views before a leaf negation can take effect.
   Each ancestor is one direct directory entry evaluated against the cached direct-directory
   `GitIgnoreSpec`; file decisions use the paired semantic-line view. Both receive bare labels and
   skip ancestor-only `ps_d` matches. Normal Git ignore
   negation works within each view only under that rule, either view's ignored ancestor or target wins,
   and no cross-view negation, caller override, or pattern can re-include an ignored-in-the-other-view
   or hard-denied path. `private` then `!private/` re-admits the parent and descendants because the
   parent match is not reapplied. `private/*` then `!private/` re-admits the parent but denies an
   immediate child directly matched by `private/*`; the negation's ancestor-only match cannot
   impersonate a direct child match. Global directory wildcards `*/`, `**/`, and `a/**/` still match
   the current directory entry. Only the final leaf evaluates both kind-specific views before its
   admitted kind is known.
4. Every present policy candidate preserves its view-relative owner label as rule scope and captures
   that owner's canonical workspace-relative label plus followed directory device/inode when the
   lexical or canonical view admits it. The owner is re-admitted and required to retain both
   identities immediately before the non-following leaf probe and again before any cache-miss read; a
   retarget or same-label directory replacement fails before resolving the replacement leaf. Its
   source passes `WorkspaceBoundary`, canonical hard denial, regular-file, 64-KiB per-file,
   16-distinct-source, 256-KiB aggregate, strict-UTF-8, and no-NUL admission. The source is re-resolved
   and rechecked immediately before a cache-miss read. Containment, hard-deny, disappearance,
   non-regular, retarget, and pre-read size failures perform no policy-source content read. Invalid
   UTF-8 or NUL may be detected only in one bounded, uncommitted policy candidate; it is never
   exposed, cached, or charged, and every failure prevents requested content I/O under fixed
   `repository_policy_invalid`. These identity checks narrow pathname races but cannot prevent
   mutation after the final seam or filesystem reuse of a device/inode pair.
5. Direct ignored targets fail explicitly; traversal consumers can omit ignored and denied
   descendants without disclosing their labels.
6. Shared limits, immutable decisions, and the exact error table are typed, documented, and contain
   canonical labels only when access has been admitted. One inclusive 65,536 candidate-pattern-slot
   budget spans every ancestor, lexical/canonical view, final-leaf form, cache hit, and recursive
   descendant in an admission traversal. Each logical evaluation reserves the selected kind-specific
   view's full stored pattern-slot count before invocation; work that would exceed the budget fails
   before matcher execution under the existing fixed `repository_policy_invalid` result. Before
   PathSpec sees a semantic line, the harness preserves Git-significant trailing whitespace and
   rejects Unicode-sensitive `?`, backend-divergent bracket syntax, or ambiguous repeated wildcards
   under the same fixed failure, with no cache, byte, match-work, or matcher effect.
7. Every model-facing path/query string passes strict Unicode-scalar/UTF-8 round-trip admission
   without Unicode normalization; lone surrogates fail before policy evaluation or any filesystem
   call.
8. The implementation makes no subprocess, network, provider, protocol, transcript, or TUI change,
   and tests use temporary local repositories only.

## Acceptance-to-test matrix

| Contract or risk | Implemented test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Ancestor traversal and nested precedence | Compare `private/` plus `!private/keep.py` with the traversable-parent control `private/*` plus `!private/keep.py`; put an invalid nested policy below the ignored directory | Unit | The ignored parent denies direct access, its nested policy is never opened or charged, and leaf negation works only in the traversable-parent control |
| Direct-entry kind semantics | Evaluate `private` then `!private/` and `private/*` then `!private/` against the direct directory, an immediate child, and a deeper descendant; inspect the paired cached views | Unit | The first pair re-admits the parent and descendants; the second re-admits the parent but denies a child directly matched by `private/*`, so traversal stops. Both views use bare labels and skip ancestor-only `ps_d` matches |
| Global directory wildcards | Exercise `*/` plus `!foo/`, `**/` plus `!foo/`, and `a/**/` against the re-admitted parent, its directly matched child, and an invalid nested policy below that child | Unit | Safe terminator removal lets each wildcard match the current directory entry rather than PathSpec's first ancestor slash; the child is ignored, traversal stops, and nested policy is not read |
| Derived-view identity | Compile positive and negated invalid-range no-ops, significant trailing whitespace, escaped spaces, and degenerate slash forms through both kind views | Unit | Original no-ops remain no-ops, retained count/include identity is unchanged, and safe directory transformation neither activates malformed syntax nor changes the intended filename |
| Git line semantics | Exercise CR/CRLF, unescaped and escaped trailing ASCII spaces, terminal backslash parity, and literal terminal tabs, NBSP, and em space in file and directory patterns | Unit/policy integration | Only Git-ignorable ASCII spaces and one line-ending CR are removed; non-space whitespace stays literal in both kind views and cannot become a false negation |
| Bounded pattern grammar | Use the reported five-`*` attack, doubled-separator active globstars, Unicode `?` mismatches, slash-spanning/negated/escaped/POSIX bracket bypasses, terminal-globstar controls, escaped wildcards, safe ASCII ranges, and common linear patterns | Unit/policy integration | Unsupported repetition or backend-divergent wildcard/bracket syntax returns exact `repository_policy_invalid` before PathSpec compile or matcher execution and before cache/byte/match-work commit; supported controls retain Git behavior |
| Relative pattern scope | Repeat a filename inside and outside a nested policy directory | Unit | Nested rule affects only its subtree |
| Lexical/canonical alias policy | Point a supplied alias at a differently named canonical target; independently ignore only an ancestor or leaf of the alias, only an ancestor or leaf of the target, both, and neither, including an opposing leaf negation | Policy/boundary integration | Either view's ignored ancestor or leaf denies; lexical type-independent denial performs no requested-target resolution, canonical hard/two-form denial precedes kind inspection, the resolved kind selects both views' ambiguous leaf results before requested-content I/O, and neither label nor rule leaks |
| Result-kind closure | Admit a regular file, directory, direct symlink to each, and an existing special target | Policy/boundary integration | Results contain canonical `file | directory` only, preserve direct-leaf symlink provenance, and map the special target to generic unavailable |
| Dual-chain policy budget | Share root and aliased policy files across both chains, give the two view owners different labels, then cross the unique-file count and aggregate-byte edges | Unit | Canonically identical policy inputs are read/charged once but their cached rules are scoped and evaluated in both views; the union still fails closed above 16 files or 256 KiB |
| Policy-owner stability | In both lexical-alias and canonical views, capture an owner's canonical label plus followed device/inode; at both checkpoints mutate the label to allowed directory B and independently replace the directory at the same canonical label; include stable-owner and cache-hit controls plus spies for replacement-leaf resolution/probe/read, cache attachment/commit, and budget charge | Policy/boundary integration | Every label or followed-identity mismatch returns exact `repository_policy_invalid` before replacement-leaf work; B or replacement rules cannot attach at the captured scope and no replacement content enters cache or budget, while stable owners preserve the view-relative scope |
| Policy-source containment and cache reuse | Point root and nested `.gitignore` candidates outside the workspace and at `.git/config` or `secrets/dev.env`; use an actually absent control, a safe internal symlink, a dangling candidate, pre-read disappearance/retarget/type/size replacements, and a stable cache hit | Policy/boundary integration | Only the absent entry is normal; every present unsafe source returns exact `repository_policy_invalid` and causes no requested content read; pre-read rejection opens no policy content, the internal source is committed once after validation, and a cache hit still re-admits the owner and resolves the current leaf/source before owner-relative attachment without rereading or charging content |
| Shared lexical admission and work bounds | Pass scalar relative paths, `.`, redundant legal `.` components, a non-string object, empty text, absolute paths, every `..` placement, NUL, and lone high/low surrogates; separately exercise 4,094/4,095/4,096 total bytes, 254/255/256 name bytes, and 255/256/257 normalized components | Unit/read-policy integration | The adapter exactly matches CAH-024, valid endpoints normalize deterministically, and invalid inputs raise only the fixed content-suppressed `RepositoryPathSyntaxError` before construction, policy, resolution, or I/O |
| CAH-024 lexical parity | Run the representative string corpus through the pure helper and CAH-024's existing pre-filesystem admission, creating targets only for accepted controls | Policy/boundary integration | Both accept/reject the same string grammar without Unicode normalization; valid helper components reflect only legal path-component normalization, and PathLike-only CAH-024 inputs remain outside the model-facing helper contract |
| Shared hard-deny primitive | Call `is_hard_denied_path` directly for every exact component, basename, suffix, case rule, documented `.env` exception, empty-root tuple, and a normal control; run the same normalized components through the read policy | Unit/read-policy integration | The pure call performs no path or filesystem I/O, returns only a Boolean, and the read policy makes the same deny/admit decision without revealing the matching rule |
| Non-overridable denial | Try ignore negation and a fabricated override for every denylist class | Unit/schema | Generic unavailable result; unsupported override rejected |
| Exact policy limits | Exercise 65,535/65,536/65,537 bytes, 16/17 files, aggregate edge | Unit | Success at limits and fixed failure above |
| Ignore-match work budget | Drive one traversal through a below-limit intermediate total and exactly 65,536 cumulative candidate-pattern slots, including no-op slots, across ancestors, both views, both final-leaf forms, cache hits, and recursive descendants; then attempt a whole logical evaluation whose reserved slots exceed the remaining budget and spy on matcher calls | Unit/policy integration | Work never resets at a view, cache, or descendant boundary; below-limit and exact-limit work succeed, and the next over-bound whole evaluation returns exact `repository_policy_invalid` before the harness-owned matcher runs |
| Strict text | Use invalid UTF-8 and NUL in applicable `.gitignore` files | Unit | `repository_policy_invalid` with no decoder or content leak |
| Model-facing strings | After JSON parsing, pass multibyte scalar text, lone high/low surrogates, and NUL as path/query values | Request/policy boundary | Scalars round-trip unchanged; invalid values use the field's fixed error with zero policy/filesystem calls |
| Check-before-use | Replace an admitted target or root before the final decision | Boundary integration | Re-evaluation fails safely rather than preserving authorization |
| Error hygiene | Use distinctive paths, patterns, and raw OS failures | Unit | Exact table strings, leak-free representations and tracebacks, and no retained `__cause__` or `__context__` chain |

## Validation

- Add focused policy tests for GitIgnoreSpec semantics, nested scope, negation, directory patterns,
  denylist precedence, canonical symlinks, stale roots, and exact safe errors. Exercise the complete
  lexical/canonical ignore truth table and prove an opposing negation cannot override the other
  view's ignored decision. Direct-access regressions prove `private/` plus `!private/keep.py` denies
  in both lexical and canonical views, while `private/*` plus `!private/keep.py` admits only when the
  other view also admits. A boundary spy proves lexical ancestor and two-form leaf denial start no
  requested target resolution; canonical two-form controls prove type-independent canonical denial
  precedes target stat; opposing file/directory rule and negation controls prove the safely resolved
  kind selects both views' exact effective leaf results; and an I/O spy proves every post-resolution denial starts no
  requested content access.
- Add direct-entry regressions for `private` followed by `!private/` and `private/*` followed by
  `!private/`. Prove the first pair re-admits the parent and descendants without reapplying the
  already-decided parent match. Prove the second pair admits `private` but denies an immediate child
  directly matched by `private/*`; the negation's ancestor-only match cannot impersonate a direct
  child match, and traversal prevents deeper policy or content work. Prove the semantic-line file
  view and safely transformed directory view both match bare labels and final-leaf controls select the
  intended kind-specific result.
- Add global-directory-wildcard regressions for `*/`, `**/`, and `a/**/`. Prove they directly match
  the current directory after safe terminator removal, deny the child below a re-admitted parent, and
  prevent nested policy or requested-content work below that child.
- Prove positive and negated invalid-range patterns remain no-ops in the derived view, retained
  pattern count/include identity is unchanged, and CR, ASCII-space escaping, non-space trailing
  whitespace, and degenerate-slash controls retain Git's meaning.
- Reproduce the repeated-`*` backtracking attack without a timing assertion and prove the pattern is
  rejected before matcher execution. Exercise one versus two local stars, one versus two active
  globstars, terminal globstars, escaped/range stars, and representative common linear patterns.
  Reject Unicode-sensitive `?`, recognized/unknown/malformed POSIX classes, negated or escaped ranges,
  and ranges that can span `/` before PathSpec compilation. Exercise doubled trailing separators that
  change effective globstar position while positive same-class ASCII ranges, fixed safe range members,
  comments, and escaped wildcard literals remain supported.
- Cover root and nested policy candidates that symlink outside the workspace or to `.git/config` and
  `secrets/dev.env`, plus an actually absent entry, an allowed internal-policy-source control, a
  present dangling link, and deterministic disappearance, retarget, directory/special-file, and
  oversized-file replacements between initial admission and the cache-miss read. Boundary and I/O
  spies prove canonical hard denial and every pre-read rejection precede policy-source content access;
  only the absent entry is ignored; rejected sources never enter cache or budgets; invalid UTF-8/NUL
  is held only as a bounded uncommitted candidate; every failure uses exact leak-free
  `repository_policy_invalid`; and a shared allowed source is read and charged once only after full
  validation while its rules remain candidate-owner relative.
- In both the lexical-alias and canonical owner walks, use deterministic seam hooks to retarget an
  admitted owner label from canonical directory A to a different allowed directory B, and separately
  replace A while preserving the same canonical label. Exercise both mutations immediately before
  the non-following `.gitignore` probe and independently immediately before a cache-miss read. Prove
  canonical-label and followed device/inode comparison returns the fixed failure before any
  replacement-leaf resolution/probe/read, cached-rule attachment, cache commit, or budget charge.
  Stable controls prove owner-relative scope is preserved. A cache-hit control proves owner
  re-admission plus current leaf/source resolution still precedes attachment, while content read and
  new byte charge remain zero.
- Put an invalid or oversized `.gitignore` below an already ignored directory and prove it is never
  opened or charged and cannot replace `repository_path_ignored` with `repository_policy_invalid`.
- Test every numeric policy boundary below, at, and above; test the shared constants as public
  reviewed defaults rather than duplicated literals. For the two-chain policy budget, prove shared
  canonical policy files are charged once and distinct files across the union are all charged.
- Drive one traversal through below-limit intermediate totals and exactly 65,536 candidate-pattern
  probes across mixed ancestors, views, leaf forms, cached policy sources, and recursive descendants.
  Prove one decision-local counter never resets, cache reuse avoids bytes but not match work, exactly
  65,536 is admitted, and a matcher spy observes no harness-owned matcher call for the next logical
  evaluation when its full stored pattern-slot reservation would exceed the remaining budget. Include
  no-op compiled slots so accounting cannot depend on later skips.
- Test `normalize_repository_path_components` and `is_hard_denied_path` as pure functions, including
  scalar paths, the empty root tuple, non-string/absolute/empty/`..`/NUL/surrogate failures, exact
  fixed helper exception/message/representation, case rules, suffix rules, and the three documented
  `.env` examples. `Path`, filesystem, and boundary spies prove both primitives perform no I/O. Run
  the same string and below/at/above byte/component/name corpus through CAH-024's sole lexical
  primitive and prove exact tuple/failure parity. Endpoint tests remain pure; they do not assume the
  temporary filesystem can create an aggregate-maximum path. Read-policy
  integration proves ordinary repository reads use the public primitives and map the neutral lexical
  failure into their own fixed error vocabulary.
- Use injected policy and filesystem spies to prove lone-surrogate and NUL path/query rejection
  happens after JSON parsing but before denylist matching, `Path` construction, resolution, stat, or
  file access. Include valid non-ASCII scalar text to prove no Unicode normalization occurs.
- Inspect the dependency and lockfile diff and prove default tests perform no network access.
- Keep protocol, transcript, provider, and TUI schemas unchanged; use the full repository gate as
  nearest parity evidence.
- Focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passed before Done.

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

## Pre-review adversarial audit

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Keep the supplied lexical alias and each view-relative policy owner distinct from the captured canonical owner label, its followed directory device/inode snapshot, resolved canonical `.gitignore` source, canonical source cache/byte identity, final canonical target, and model-visible canonical POSIX label. A cached source never changes the candidate owner's rule scope. Device/inode reuse and mutation after the final seam remain explicit residual risks. |
| End-to-end contract | CAH-024 boundary plus pure syntax/hard-deny primitives -> pre-resolution lexical ancestor/two-form leaf evaluation -> target resolution -> canonical hard deny -> canonical ancestor/two-form leaf evaluation -> closed kind admission -> select both views -> owner/leaf/source rechecks -> bounded `GitIgnoreSpec` decision -> CAH-027/028/029/030 consumers. CAH-037 owns runtime composition and evaluation wiring. |
| Failure and atomicity | Lexical type-independent denial performs zero requested-target resolution; canonical hard/two-form denial precedes target kind inspection; kind-selected denial performs zero requested-content I/O; an unsafe policy candidate never attaches rules, enters cache, or consumes budget. Special targets are unavailable. Owner/source mismatch and every policy failure return one fixed error; cancellation/deadline/rollback are N/A inside this synchronous bounded policy decision. |
| Reachable boundaries | Real dual lexical/canonical walks exercise 65,535/65,536/65,537-byte policy sources, below-limit and exact-65,536 candidate-pattern work followed by a whole-evaluation overflow, 16/17 distinct canonical sources, and the 256-KiB aggregate edge, including shared sources, cache hits, descendants, direct-entry ancestors, and deterministic pre-probe/pre-read retarget and same-label replacement seams. Unicode admission also runs through the pure helper and full policy consumer. |
| Closed grammar and cardinality | The exact hard-deny table is non-overridable; each admitted policy source becomes one Git-normalized semantic line set, passes the bounded wildcard/bracket scanner, and compiles one file view plus one safely transformed direct-directory view. Both match bare labels and skip ancestor-only `ps_d` results; only the selected view's complete slots are charged per logical evaluation. At most 16 distinct strict-UTF-8/no-NUL sources totaling 256 KiB and 65,536 cumulative candidate-pattern slots are admitted, with exact fixed direct-versus-traversal outcomes and no override field. |
| Artifact parity | Story, lesson, diagram, safety/tool/context docs, and tests use the same order: syntax -> lexical hard deny/direct-entry ancestors/two-form leaf -> boundary resolution -> canonical hard deny/direct-entry ancestors/two-form leaf -> `file | directory` kind -> select both views -> operation checks -> final re-admission, and agree on owner label plus followed identity, source identity, fixed errors, byte/cache/match accounting, and residual races. |
| Independent lenses | Security/identity review covers aliases, owner/source retargets, same-label owner replacement, symlinks, deny precedence, and cache identity; handoff/composition review covers the CAH-025 primitive consumer and CAH-027-030 full-policy consumers; limits/scheduler review covers exact byte/source/match-work budgets and records provider/protocol/scheduler changes as N/A. |

## Definition of done

1. Every acceptance criterion has deterministic happy, boundary, and adversarial failure evidence.
2. All policy and shared numeric limits pass below/at/above tests, and model-facing path/query
   strings pass strict Unicode-scalar/UTF-8 boundary tests before filesystem access.
3. Pure lexical admission performs no construction/resolution/I/O and rejects invalid syntax before
   hard-deny classification; the hard-deny classifier is the only implementation of the exact table,
   performs no I/O or rule disclosure, and has parity evidence through the full read policy.
4. GitIgnoreSpec precedence and ancestor traversability in both lexical and canonical views, lexical
   direct-entry ancestor/two-form leaf denial before requested-target resolution, canonical
   hard/direct-entry ancestor/two-form leaf denial
   before kind inspection, kind-selected matching in both views before requested content I/O, either-view-denies
   combination, canonical-only public labels, hard-deny dominance, and no ignored override are
   proved. Every present policy source has view-relative owner/source identity, captured canonical
   owner label plus followed device/inode, pre-probe and pre-cache-miss owner stability, boundary and
   hard-deny admission, pre-read source recheck, fixed failure, safe internal-symlink, cache-hit, and
   canonical cache/budget evidence. Original-line file and safely transformed direct-directory views,
   bare-label matching, ancestor-only filtering, and `*/`/`**/`/`a/**/` regressions are proved.
   Exactly 65,536 cumulative candidate-pattern probes are inclusive, and an over-bound logical
   evaluation fails before matcher execution.
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

## Implementation evidence

- [`repository_access.py`](../src/code_assist_harness/repository_access.py) implements the immutable
  result, fixed failures, shared limits, pure helpers, direct-entry ancestor and two-form-leaf
  paired-`GitIgnoreSpec` gate, owner label/followed-identity plus source rechecks, and decision-local
  cache/byte/match-work budgets without a user-content read operation. Its internal
  descendant-admission scope reuses that same cache and aggregate budget across one future traversal;
  its public failure boundary removes hidden exception context as well as suppressing rendered chains.
- [`test_repository_access.py`](../tests/test_repository_access.py) exercises pure-helper parity,
  every denylist class, exact direct-entry/two-form Git precedence, lexical/canonical alias
  disagreement, owner/source mutation seams, Git-exact line semantics, bounded pattern grammar,
  policy-source safety, cache identity, shared traversal accounting, non-leaking tracebacks, and
  below/at/above limits in the focused suite. CAH-025 owns the later
  control-plane consumer evidence.
- `pyproject.toml` admits maintained `pathspec>=1.1,<2`, and `uv.lock` resolves PathSpec 1.1.1 without
  adding runtime network behavior.
- The lesson locates policy between the workspace boundary and all native read operations; its
  primary teach-back question is: why is an approval or model argument unable to override a denied
  read?

## Deferred work

- CAH-025 consumes only the pure lexical-path and hard-deny helpers while retaining its explicit
  `.gitignore` exemption for instruction control-plane files.
- CAH-027, CAH-028, and CAH-029 reuse the full read policy for listing, reading, and literal search.
- CAH-037's sole M2 composition factory creates the per-session policy only after the actual read
  services exist; CAH-026 deliberately leaves no unused runtime wiring behind.
- CAH-030 applies the shared item and byte limits to deterministic context inclusion.
- E4 later adds schema-validated tool registration and dispatch without moving policy ownership out
  of the harness.
