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
containment, a non-overridable VCS/credential denylist, and nested Git-style ignore rules while
keeping the decision inside the Python harness.

## Learning objectives

After completing this unit, you should be able to:

- explain admission order and why lexical plus canonical checks are both required;
- explain why JSON parsing alone does not guarantee Unicode-scalar text and where the harness rejects
  lone surrogates;
- apply nested `.gitignore` precedence with `GitIgnoreSpec`;
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

A common misconception is that approval makes any read safe. Here, ignored and hard-denied decisions
have no override field. Future approval cannot broaden this boundary.

Another misconception is that a parsed JSON string is automatically safe Unicode. Python can hold
an isolated surrogate in `str`, even though strict UTF-8 cannot encode it. The shared request
boundary performs an exact strict UTF-8 round-trip before building a path or invoking policy. It
does not normalize spelling, because normalization could change which repository name is selected.

## Key concepts

- **Admission pipeline:** validate, lexical deny, canonicalize, canonical deny, ignore policy,
  operation limits, then repeat immediately before I/O.
- **GitIgnoreSpec:** maintained Git-compatible matching for root and nested `.gitignore` files.
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
                   [CAH-026 read-policy gate]
                    /          |             \
          CAH-024 boundary  hard denylist  nested GitIgnoreSpec
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
3. Resolve with CAH-024 and repeat the denylist on canonical components.
4. Load at most 16 applicable strict-UTF-8 `.gitignore` files within byte limits.
5. Evaluate root-to-nearest `GitIgnoreSpec` rules, then re-run admission before use.
6. Test negation, nested scope, aliases, staleness, and every limit boundary.

## Implementation code samples

No implementation exists yet. This is planned pseudocode:

```text
validate_unicode_scalar_utf8(request.path)
validate_relative(request.path)
deny_if_sensitive(request.path.components)
resolved = boundary.resolve_existing(request.path)
deny_if_sensitive(resolved.relative_path.components)
decision = gitignore_policy_for(resolved).check()
return admit(decision)
```

The string check runs before every filesystem or policy call. The two deny checks then close
different alias/oracle gaps. Resolution supplies the canonical label. Ignore matching comes later
because it is repository preference, not permission to re-include a hard deny. A caller repeats
this sequence immediately before access.

## Failure scenarios to study

- **Negated credential:** `.gitignore` says `!.env`; the hard deny still returns generic unavailable.
- **Nested precedence:** a lower `.gitignore` negates a normal root pattern; the path is admitted only
  when parent traversal is available.
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
2. Create root and nested ignore rules whose last match changes the result.
3. Classify each failure as validation, containment, hard deny, ignore, type, or content limit.
4. Teach back: why can neither model arguments nor approval override this read policy?
5. Explain why strict UTF-8 round-trip validation rejects surrogates but deliberately does not
   normalize two canonically equivalent path spellings.

## Key takeaways

- The Python harness owns final repository-read admission.
- Hard denial precedes and dominates Git-style ignore policy.
- Central policy improves governance but introduces availability and operational cost.

## Glossary

- **Admission:** The complete decision that permits one bounded capability use.
- **Hard denylist:** Built-in paths that no lower-trust input can re-include.
- **Ignore negation:** A `!` rule that reverses a normal ignore match within Git semantics.
- **Existence oracle:** A difference in errors that reveals whether protected data exists.

## Further reading

- [CAH-026 delivery contract](../../user-stories/cah-026-define-repository-read-contracts.md)
- [Git `gitignore`](https://git-scm.com/docs/gitignore)
- [PathSpec repository](https://github.com/cpburnz/python-pathspec)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
