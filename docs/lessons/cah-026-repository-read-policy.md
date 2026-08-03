# CAH-026 lesson: Repository read policy

- **Unit:** CAH-026
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned
- **Story:** [Define repository read contracts and policy](../../user-stories/cah-026-define-repository-read-contracts.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** The common admission policy every native read must reuse before touching content
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Safety model](../safety-model.md),
  [Tool system](../tool-system.md), and [Harness architecture](../architecture.md)

> This lesson describes an accepted plan. It does not claim that repository read policy is shipped.

## Quick summary

CAH-026 creates the policy gate every native repository read must cross. It combines CAH-024
containment, a non-overridable VCS/credential denylist, and nested Git-style ignore rules evaluated
for both the supplied lexical path and its resolved canonical target while keeping the decision
inside the Python harness.

## Learning objectives

After completing this unit, you should be able to:

- explain admission order and why lexical plus canonical checks are both required;
- explain why JSON parsing alone does not guarantee Unicode-scalar text and where the harness rejects
  lone surrogates;
- apply nested `.gitignore` precedence and ancestor-traversability rules independently to lexical and
  canonical path views;
- distinguish a hard deny from a repository ignore; and
- design fixed failures that do not become an existence or secret oracle.

## Why this unit matters

Without one shared gate, `list_files`, `read_file`, and `search_text` can disagree about whether a
path is safe. Policy must be reusable before model-callable tools exist; otherwise tool schemas look
safe while implementations silently diverge.

## Junior engineer foundation

Validation asks “is the request shaped correctly?” Containment asks “is the target inside this
workspace?” Policy asks “even if it is inside, may this capability inspect it?” These are separate
questions.

The path `src/link/config` may look harmless but resolve to `.git/config`; checking only the supplied
name misses the canonical target. Checking only after resolution can reveal whether a denied name
exists. CAH-026 checks the hard denylist both before and after resolution.

Ignore policy has the same two-name problem. A root rule may ignore `generated-link/` while that
symlink resolves to an otherwise admitted `src/generated/`, or a harmless alias may point into a
canonically ignored subtree. CAH-026 evaluates root-to-nearest rules separately against both names.
Either ignored result wins; a `!` negation in one view cannot grant access denied by the other.

Git also does not let a negated leaf jump across an excluded parent. With `private/` followed by
`!private/keep.py`, the file remains ignored because Git cannot traverse `private/`; no policy below
that directory is available. By contrast, `private/*` leaves the directory itself traversable, so a
later `!private/keep.py` may re-include the file. The harness must walk and admit every ancestor, not
ask only for the leaf's final matcher result.

A common misconception is that approval makes any read safe. Here, ignored and hard-denied decisions
have no override field. Future approval cannot broaden this boundary.

Another misconception is that a parsed JSON string is automatically safe Unicode. Python can hold
an isolated surrogate in `str`, even though strict UTF-8 cannot encode it. The shared request
boundary performs an exact strict UTF-8 round-trip before building a path or invoking policy. It
does not normalize spelling, because normalization could change which repository name is selected.

## Key concepts

- **Admission pipeline:** validate, lexical hard deny and ignore, canonicalize only if admitted,
  canonical hard deny and ignore, apply operation limits, then repeat immediately before I/O.
- **GitIgnoreSpec:** maintained Git-compatible matching for root and nested `.gitignore` files.
- **Ancestor traversability:** every proper directory prefix must admit before the policy may load its
  nested rules or let a leaf negation take effect.
- **Shared policy cache:** read and charge a canonically identical policy file once, but attach and
  evaluate its rules independently at each view's owner-relative scope.
- **Dual-view ignore:** preserve the normalized supplied label and the resolved target label as
  independent ignore-policy inputs; one view cannot re-include the other.
- **Hard denylist:** conservative VCS and credential names that ignore negation cannot re-include.
- **Safe error:** one fixed code/message without path, pattern, rule, content, or raw OS detail.
- **Deterministic budget:** bytes and items, not provider tokens.
- **Scalar-text admission:** accept only exact strict UTF-8 round-trips after JSON parsing; reject
  lone surrogates and NUL before policy or filesystem work.

## Architecture and design

```text
Ink TUI ---- NDJSON ----> Python harness <---- provider may request tools later
                              |
                     future tool dispatcher
                              |
                   supplied lexical label
                              |
           hard deny + lexical ancestor walk --deny--> fixed safe error
                              |
                    CAH-024 resolve target
                              |
          hard deny + canonical ancestor walk --deny--> fixed safe error
                              |
                   [CAH-026 admitted target]
                              |
             CAH-027 list / CAH-028 read / CAH-029 search (later)
                              |
Repository filesystem --------+
Transcript/evidence: unchanged; denied paths and policy details never enter it
```

The provider can propose a future operation, but only the harness admits it. The gate has no
`include_ignored` or “approved anyway” path. It rechecks before I/O because a policy decision is a
snapshot, not durable authorization.

## Practical walkthrough

1. Define immutable decisions, shared limits, the scalar-text admission helper, and fixed errors.
2. Admit path/query strings as unchanged Unicode scalar text, then apply the exact credential/VCS
   denylist to supplied path components.
3. Preserve the normalized supplied label and walk its directory prefixes root-to-leaf. Before
   entering each directory, apply the policies available at that point; load its nested policy only
   after it admits. Deny before target resolution if any ancestor or the leaf is ignored.
4. Resolve an admitted lexical path with CAH-024 and repeat the hard denylist on canonical components.
5. Walk the canonical chain by the same rule. Reuse cached rules for policy files already read and
   charged, read only newly reachable files, and still attach every applicable rule set at the
   canonical view's owner-relative scope before denying any ignored ancestor or leaf before I/O.
6. Re-run admission before use, then test negation, nested scope, aliases, staleness, and every limit
   boundary.

## Implementation code samples

No implementation exists yet. This is planned pseudocode:

```text
def admit_ignore_view(label, policy_cache):
    policies = scoped_rules(load_or_reuse_root_policy(policy_cache), owner=".")
    for directory in label.proper_directory_prefixes():
        deny_if_ignored(policies.check(directory.as_directory()))
        cached = load_or_reuse_nested_policy(directory, policy_cache)
        policies.extend(scoped_rules(cached, owner=directory))
    deny_if_ignored(policies.check(label))

validate_unicode_scalar_utf8(request.path)
validate_relative(request.path)
deny_if_sensitive(request.path.components)
lexical = normalized_relative_label(request.path)
admit_ignore_view(lexical, bounded_union)
resolved = boundary.resolve_existing(request.path)
deny_if_sensitive(resolved.relative_path.components)
admit_ignore_view(resolved.relative_path, bounded_union)
return admit(resolved)
```

The string check runs before every filesystem or policy call. In each ignore view, a denied directory
stops the walk before its `.gitignore` is opened, so unreachable policy cannot re-include descendants
or consume the budget. The cache reads and charges a canonically identical file once; it does not
cache an admission decision. Lexical and canonical walks each attach those rules to their own
owner-relative label and evaluate independently. Lexical walking happens before target resolution so
an ignored alias cannot become an existence probe. Canonical walking then catches safe-looking aliases
whose targets or ancestors are ignored. Reaching access requires every ancestor plus the leaf in both
views to admit. A caller repeats this sequence immediately before access.

## Failure scenarios to study

- **Negated credential:** `.gitignore` says `!.env`; the hard deny still returns generic unavailable.
- **Untraversable parent:** root rules `private/` then `!private/keep.py` still deny a direct read;
  `private/.gitignore` is never loaded.
- **Traversable-parent control:** `private/*` then `!private/keep.py` may admit the file because the
  directory remains reachable, provided the other path view also admits.
- **Alias disagreement:** the lexical alias is ignored but its canonical target is admitted, or the
  reverse; either disagreement still returns `repository_path_ignored`, a lexical denial performs no
  target resolution, and a negation on the admitted side cannot override it.
- **Policy bomb:** a 65,537-byte or invalid-UTF-8 `.gitignore` produces
  `repository_policy_invalid` without decoder text.
- **Symlink alias:** a safe-looking name resolves to `.ssh`; canonical denial blocks it.
- **Lone surrogate:** a parsed request contains `"\ud800"`; the field's fixed input error occurs with
  zero policy or filesystem calls.

## Production expansion

### Example enterprise scenario

A company needs centrally versioned policy, repo-specific narrowing, audit explanations for security
staff, and policy updates without redeploying every agent. That may justify a policy engine, but it
must not move final enforcement into the LLM or UI.

### Typical production capabilities and tools

- [PathSpec](https://github.com/cpburnz/python-pathspec) provides maintained Git-style matching with
  low local overhead, but the harness still owns precedence and hard denial.
- [Git ignore rules](https://git-scm.com/docs/gitignore) define familiar nested semantics; matching
  them accurately costs more than a simple glob.
- [Open Policy Agent](https://www.openpolicyagent.org/docs/latest/) supports centrally governed policy
  and explanations, adding a policy language, distribution, and operational ownership.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) separates hosts,
  clients, servers, and tools; remote capabilities add another trust and authorization boundary.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One built-in policy for one workspace | Layered organization, user, and repository policy |
| Reliability | Re-evaluate bounded local files | Versioned distribution, rollback, and cache coherence |
| Operations | Fixed errors and local tests | Policy audit logs, ownership, alerts, and change review |
| Cost | One dependency and explicit code | Policy service, language, deployment, and governance |

### Trade-offs and graduation signals

The local gate is reviewable and fails closed but cannot explain policy centrally or update across a
fleet. Graduate when many installations need coordinated policy changes or audited decision
provenance; preserve local fail-closed enforcement if the central service is unavailable.

## Practical exercises

1. Trace admission for `link/config` when the link targets `.git/config`.
2. Create a symlink whose lexical and canonical labels receive opposite ignore decisions; explain
   why access is denied in both orientations.
3. Create root and nested ignore rules whose last match changes one view's result.
4. Classify each failure as validation, containment, hard deny, ignore, type, or content limit.
5. Teach back: why can neither model arguments nor approval override this read policy?
6. Explain why strict UTF-8 round-trip validation rejects surrogates but deliberately does not
   normalize two canonically equivalent path spellings.
7. Compare `private/` and `private/*`: why can the same leaf negation work only in the second case?

## Key takeaways

- The Python harness owns final repository-read admission.
- Lexical and canonical ignore views each require a traversable ancestor chain, and either denied
  ancestor or leaf denies access.
- Hard denial precedes and dominates Git-style ignore policy.
- Central policy improves governance but introduces availability and operational cost.

## Glossary

- **Admission:** The complete decision that permits one bounded capability use.
- **Hard denylist:** Built-in paths that no lower-trust input can re-include.
- **Ignore negation:** A `!` rule that reverses a normal ignore match within Git semantics.
- **Ancestor traversability:** The rule that every parent directory must remain reachable before a
  descendant or nested policy can affect admission.
- **Lexical path:** The normalized supplied workspace-relative name before symlinks are resolved.
- **Existence oracle:** A difference in errors that reveals whether protected data exists.

## Further reading

- [CAH-026 delivery contract](../../user-stories/cah-026-define-repository-read-contracts.md)
- [Git `gitignore`](https://git-scm.com/docs/gitignore)
- [PathSpec repository](https://github.com/cpburnz/python-pathspec)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
