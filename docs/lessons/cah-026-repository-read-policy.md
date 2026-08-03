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
- apply nested `.gitignore` precedence independently to lexical and canonical path views;
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
              hard deny + lexical GitIgnoreSpec --deny--> fixed safe error
                              |
                    CAH-024 resolve target
                              |
             hard deny + canonical GitIgnoreSpec --deny--> fixed safe error
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
3. Preserve the normalized supplied label, load its applicable lexical-chain policies, and deny
   before target resolution when its root-to-nearest `GitIgnoreSpec` result is ignored.
4. Resolve an admitted lexical path with CAH-024 and repeat the hard denylist on canonical components.
5. Load canonical-chain policies not already charged to the bounded union, evaluate the canonical
   label independently, and deny if that final view is ignored.
6. Re-run admission before use, then test negation, nested scope, aliases, staleness, and every limit
   boundary.

## Implementation code samples

No implementation exists yet. This is planned pseudocode:

```text
validate_unicode_scalar_utf8(request.path)
validate_relative(request.path)
deny_if_sensitive(request.path.components)
lexical = normalized_relative_label(request.path)
lexical_policies = bounded_policies_for(lexical.ancestors)
deny_if_ignored(lexical_policies.check(lexical))
resolved = boundary.resolve_existing(request.path)
deny_if_sensitive(resolved.relative_path.components)
canonical_policies = extend_bounded_union(resolved.ancestors)
deny_if_ignored(canonical_policies.check(resolved.relative_path))
return admit(resolved)
```

The string check runs before every filesystem or policy call. The two hard-deny checks then close
different alias/oracle gaps. Resolution supplies the canonical label while the lexical label remains
available only for admission. Lexical ignore matching happens before target resolution so an ignored
alias cannot become an existence probe. Canonical matching then catches safe-looking aliases whose
targets are ignored. Each view resolves its own precedence, and reaching access requires both to
admit. A caller repeats this sequence immediately before access.

## Failure scenarios to study

- **Negated credential:** `.gitignore` says `!.env`; the hard deny still returns generic unavailable.
- **Nested precedence:** a lower `.gitignore` negates a normal root pattern; the path is admitted only
  when parent traversal is available.
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

## Key takeaways

- The Python harness owns final repository-read admission.
- Lexical and canonical ignore views are independent, and either ignored result denies access.
- Hard denial precedes and dominates Git-style ignore policy.
- Central policy improves governance but introduces availability and operational cost.

## Glossary

- **Admission:** The complete decision that permits one bounded capability use.
- **Hard denylist:** Built-in paths that no lower-trust input can re-include.
- **Ignore negation:** A `!` rule that reverses a normal ignore match within Git semantics.
- **Lexical path:** The normalized supplied workspace-relative name before symlinks are resolved.
- **Existence oracle:** A difference in errors that reveals whether protected data exists.

## Further reading

- [CAH-026 delivery contract](../../user-stories/cah-026-define-repository-read-contracts.md)
- [Git `gitignore`](https://git-scm.com/docs/gitignore)
- [PathSpec repository](https://github.com/cpburnz/python-pathspec)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
