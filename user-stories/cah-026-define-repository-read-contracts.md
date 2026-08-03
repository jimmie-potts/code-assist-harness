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
contracts used by later native read operations. It does not list, read, or search source content and
does not register or dispatch model-callable tools.

## Scope

- Add a focused Python repository-access policy module layered on CAH-024's canonical workspace
  boundary.
- Add the maintained `pathspec` dependency and use `pathspec.GitIgnoreSpec` for Git-compatible root
  and nested `.gitignore` evaluation; commit the resolved `uv.lock` change during implementation.
- Define immutable, typed policy decisions, safe errors, canonical-label records, and shared hard
  limits consumed by CAH-027 through CAH-030.
- Define the shared model-facing string admission rule used by later path and query request models:
  after JSON parsing, require an exact strict UTF-8 encode/decode round-trip before policy or
  filesystem work.
- Load only `.gitignore` files on the supplied lexical ancestor chain and the resolved canonical
  target ancestor chain. Evaluate each view independently, with rules interpreted relative to the
  directory that owns each file and ordered from root to nearest; an ignored decision in either view
  denies the target.
- Keep all behavior native Python, local, deterministic, and side-effect free apart from bounded
  reads of policy files: no subprocess, shell, network, provider, protocol, transcript, or TUI
  change.

## Locked contract

### Admission pipeline and ownership

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
- Ignore admission has two independent views. The lexical view matches the normalized supplied
  workspace-relative path against root-to-nearest policy files on its supplied ancestor chain,
  without replacing that label with a symlink target. The canonical view matches the
  `WorkspaceBoundary` target-relative label against policy files on the resolved target's canonical
  ancestor chain. Each view computes normal Git precedence only within that view. The target is
  admitted only when neither final view is ignored; negation in one view cannot cancel an ignored
  decision in the other.
- Policy-file count and byte limits apply to the union of the two applicable ancestor chains.
  Policy inputs that resolve to the same canonical regular file are loaded and charged once, even
  though their rules may be evaluated against both labels. The root policy therefore does not consume
  the budget twice merely because every request has two views. A lexical denial short-circuits before
  resolving the requested target or loading its canonical-chain policy files.
- The final ignored decision is non-overridable. No public input, provider argument, configuration,
  or future approval may request `include_ignored`. A hard-denied path can never be re-included by a
  negation rule.
- A missing `.gitignore` is normal. A present policy file must be a regular file, no larger than 64
  KiB (65,536 bytes), contain no NUL, and decode with strict UTF-8. At most 16 applicable policy files
  and 256 KiB (262,144 bytes) of aggregate policy text may be loaded for one decision.
- Policy snapshots are bounded decisions, not persistent authorization. Callers re-evaluate before
  access; descriptor-relative hardening remains deferred.

### Non-overridable hard denylist

The denylist is applied to every supplied and canonical path component or basename before
`.gitignore`. VCS and credential-directory component names are case-sensitive on the supported
Linux filesystem. Credential filename and suffix comparisons use ASCII lowercase so an uppercase
extension cannot bypass the same secret-file rule.

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
| `repository_policy_invalid` | `Repository ignore policy could not be loaded safely.` | applicable policy input is invalid, oversized, or unreadable |
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
2. Normal Git ignore negation works within each view, but either view's ignored decision wins; no
   cross-view negation, caller override, or pattern can re-include an ignored-in-the-other-view or
   hard-denied path.
3. Policy files enforce 64-KiB per-file, 16-file, 256-KiB aggregate, strict-UTF-8, and no-NUL limits
   with fixed safe failures.
4. Direct ignored targets fail explicitly; traversal consumers can omit ignored and denied
   descendants without disclosing their labels.
5. Shared limits, immutable decisions, and the exact error table are typed, documented, and contain
   canonical labels only when access has been admitted.
6. Every model-facing path/query string passes strict Unicode-scalar/UTF-8 round-trip admission
   without normalization; lone surrogates fail before policy evaluation or any filesystem call.
7. The implementation makes no subprocess, network, provider, protocol, transcript, or TUI change,
   and tests use temporary local repositories only.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Nested ignore precedence | Combine root and nested ignores with later negations in each view | Unit | Each view receives the exact root-to-nearest final decision before the two decisions are combined |
| Relative pattern scope | Repeat a filename inside and outside a nested policy directory | Unit | Nested rule affects only its subtree |
| Lexical/canonical alias policy | Point a supplied alias at a differently named canonical target; independently ignore only the alias, only the target, both, and neither, including an opposing negation | Policy/boundary integration | Either ignored view denies; access requires both views to admit, lexical denial performs no target resolution, and neither label or rule leaks |
| Dual-chain policy budget | Share root and aliased policy files across both chains, then cross the unique-file count and aggregate-byte edges | Unit | Canonically identical policy inputs are charged once; the union still fails closed above 16 files or 256 KiB |
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
  view's ignored decision. A boundary spy proves lexical denial short-circuits before target
  resolution.
- Test every numeric policy boundary below, at, and above; test the shared constants as public
  reviewed defaults rather than duplicated literals. For the two-chain policy budget, prove shared
  canonical policy files are charged once and distinct files across the union are all charged.
- Use injected policy and filesystem spies to prove lone-surrogate and NUL path/query rejection
  happens after JSON parsing but before denylist matching, `Path` construction, resolution, stat, or
  file access. Include valid non-ASCII scalar text to prove no normalization occurs.
- Inspect the dependency and lockfile diff and prove default tests perform no network access.
- Keep protocol, transcript, provider, and TUI schemas unchanged; use the full repository gate as
  nearest parity evidence.
- Run focused Python tests and `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` before Done.

## Documentation impact

Update dependency documentation, context-engineering, safety model, glossary, story and lesson
indexes, E3 backlog sequence, and the Markdown lesson's compact architecture diagram. Record why
GitIgnoreSpec and the non-overridable denylist are separate policy layers. Do not add or revise a
presentation.

## Exclusions

- Listing directories, reading source content, text search, context selection, tool registration,
  dispatch, or model-visible tool results.
- User/workspace configuration that broadens or narrows policy, secret scanning, content
  classification, tokenization, or approval prompts.
- Instruction discovery behavior from CAH-025; `AGENTS.md` remains a separate control-plane input.
- File writes, subprocesses, shell use, network access, protocol events, transcript fields, TUI
  rendering, MCP transport, and agent-loop continuation.
- Descriptor-relative access, filesystem watchers, multiple roots, non-Linux matching semantics,
  and claims that check-before-use removes all races.

## Definition of done

1. Every acceptance criterion has deterministic happy, boundary, and adversarial failure evidence.
2. All policy and shared numeric limits pass below/at/above tests, and model-facing path/query
   strings pass strict Unicode-scalar/UTF-8 boundary tests before filesystem access.
3. GitIgnoreSpec precedence in both lexical and canonical views, lexical pre-resolution denial,
   either-view-denies combination, canonical-only public labels, hard-deny dominance, and no ignored
   override are proved.
4. Public contracts are immutable, typed, documented, and emit only the fixed safe failures.
5. Focused tests and the canonical offline `./scripts/check` pass without a model, subprocess, or
   network.
6. Existing protocol, transcript, provider, and TUI boundaries remain unchanged and pass their
   existing tests.
7. The Markdown lesson includes exact implementation and failure-test excerpts after code exists;
   no presentation work is introduced.
8. Story, lesson, conceptual docs, indexes, backlog, planning note, dependency declaration, lockfile,
   and statuses agree.
9. Delivered production-source churn is recorded and stays near the planned range or is split before
   review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- A repository-access policy module and temporary-repository tests prove exact matching and denial,
  including aliases whose lexical and canonical ignore decisions disagree.
- `pyproject.toml` and `uv.lock` record the reviewed PathSpec dependency without any runtime network
  requirement.
- The lesson locates policy between the workspace boundary and all native read operations; its
  primary teach-back question is: why is an approval or model argument unable to override a denied
  read?

## Deferred work

- CAH-027, CAH-028, and CAH-029 reuse this policy for listing, reading, and literal search.
- CAH-030 applies the shared item and byte limits to deterministic context inclusion.
- E4 later adds schema-validated tool registration and dispatch without moving policy ownership out
  of the harness.
