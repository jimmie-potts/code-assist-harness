# CAH-026 lesson: Repository read policy

- **Unit:** CAH-026
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Verified against implementation
- **Implementation status:** Done
- **Story:** [Define repository read contracts and policy](../../user-stories/cah-026-define-repository-read-contracts.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** The common admission policy every native read must reuse before touching content
- **Visual companion:** None; Markdown and the compact text diagram are authoritative
- **Related architecture:** [Safety model](../safety-model.md),
  [Tool system](../tool-system.md), and [Harness architecture](../architecture.md)

> Verified against the CAH-026 policy implementation, focused temporary-repository tests, and the
> repository-wide offline gate.

## Quick summary

CAH-026 creates the policy gate every native repository read must cross. It owns pure lexical-path
normalization and `is_hard_denied_path(components)`, then combines those primitives with CAH-024
containment and nested Git-style ignore rules for ordinary reads. CAH-025 reuses only those two pure
decisions, so its control-plane `.gitignore` exemption cannot bypass input or credential denial and
does not inherit ordinary-read limits or errors. Ordinary-read policy files are themselves untrusted:
their candidate owner controls rule scope, while their boundary-resolved canonical source must pass
hard denial and bounded pre-read rechecks.

## Learning objectives

After completing this unit, you should be able to:

- explain admission order and why lexical plus canonical checks are both required;
- explain how invalid model-facing path syntax fails before `Path`, resolution, or filesystem I/O;
- explain why the hard-deny table has one pure, reusable classifier with no I/O or rule disclosure;
- explain why JSON parsing alone does not guarantee Unicode-scalar text and where the harness rejects
  lone surrogates;
- apply nested `.gitignore` precedence and ancestor-traversability rules independently to lexical and
  canonical path views;
- explain why a policy candidate's owner controls rule scope while its canonical source controls
  containment, hard denial, caching, and budgets;
- explain why each ignore view snapshots the admitted owner's canonical directory and re-admits that
  owner before probing or reading its `.gitignore`;
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

There is one subtle ordering exception for exact leaf type. Proper lexical ancestors are checked
first. The harness then evaluates both the leaf's file form (`cache`) and directory form (`cache/`).
It can deny before requested-target resolution only when both effective results are ignored. If they
do not both deny, the harness resolves, applies canonical hard denial, and repeats the two-form check
for the canonical view. Only after type-independent canonical denial has had its chance does it
classify the target as `file` or `directory` and select that form's result in both views. This handles
later negation correctly without falsely denying either kind, and it still happens before requested
content is read. Special targets never become a third public kind; they fail as unavailable.

Git also does not let a negated leaf jump across an excluded parent. With `private/` followed by
`!private/keep.py`, the file remains ignored because Git cannot traverse `private/`; no policy below
that directory is available. By contrast, `private/*` leaves the directory itself traversable, so a
later `!private/keep.py` may re-include the file. The harness must walk and admit every ancestor, not
ask only for the leaf's final matcher result.

The `.gitignore` directory entry and the bytes it names are also different identities. If
`pkg/.gitignore` links to `shared/ignore.rules`, the rules still apply below `pkg`; resolving the
source does not move their scope to `shared`. The harness may reuse that allowed canonical source if
another owner links to it, but it first contains and hard-denies the source and rechecks it before
reading. A link outside the workspace or to `.git/config` is an invalid policy source, not permission
to read those bytes. Applying GitIgnoreSpec recursively to the policy source would be circular, so
policy sources receive containment, hard-deny, type, size, and text checks instead.

The owner label can change too. Suppose the lexical owner `pkg-link` resolves to admitted directory A
when the view enters it, then is retargeted to another allowed directory B. Checking only
`pkg-link/.gitignore` would silently select B's leaf while still attaching its rules at `pkg-link`'s
scope. Each view therefore captures A as the admitted canonical owner, re-resolves `pkg-link` before
the non-following leaf probe, and repeats that owner check before a cache-miss read. A persistent
A-to-B change fails before B's leaf is resolved or read. The rule scope remains the view-relative
owner label; the canonical leaf source remains the cache and budget identity.

A common misconception is that approval makes any read safe. Here, ignored and hard-denied decisions
have no override field. Future approval cannot broaden this boundary.

Another misconception is that a shared classifier must also resolve paths or load ignore files.
`is_hard_denied_path` accepts an already normalized tuple of workspace-relative components and
returns only `True` or `False`. It performs no filesystem access and does not reveal which rule
matched. CAH-024's pure `normalize_workspace_relative_path` primitive owns model-facing lexical
normalization and its 4,095-byte, 256-component, and 255-byte-name budgets without constructing a
`Path`. The sibling `normalize_repository_path_components` API delegates to it and translates only
the fixed repository-policy exception vocabulary; callers still own resolution, safe public errors,
and any later ignore evaluation.

That helper accepts exactly `str` and returns `tuple[str, ...]`. Its only failure is the fixed,
content-suppressed `RepositoryPathSyntaxError("Repository path syntax is invalid.")`. Ordinary reads
map it to `invalid_repository_path`; CAH-025 maps it to `invalid_instruction_scope`. A shared corpus
must exactly match CAH-024's tuple and failure result so this adapter cannot create a second lexical
grammar or second set of limits.

Another misconception is that a parsed JSON string is automatically safe Unicode. Python can hold
an isolated surrogate in `str`, even though strict UTF-8 cannot encode it. The shared request
boundary performs an exact strict UTF-8 round-trip before building a path or invoking policy. It
does not normalize spelling, because normalization could change which repository name is selected.

## Key concepts

- **Admission pipeline:** validate, lexical hard deny plus ancestor/two-form leaf ignore, resolve,
  canonical hard deny plus ancestor/two-form leaf ignore, then admit `file | directory` and select
  both views' form before operation limits and final re-admission.
- **GitIgnoreSpec:** maintained Git-compatible matching for root and nested `.gitignore` files.
- **Ancestor traversability:** every proper directory prefix must admit before the policy may load its
  nested rules or let a leaf negation take effect.
- **Shared policy cache:** read and charge a canonically identical policy file once, but attach and
  evaluate its rules independently at each view's owner-relative scope.
- **Policy owner versus source:** the candidate owner supplies GitIgnoreSpec scope; the admitted
  canonical source supplies containment, hard-deny, cache, and budget identity.
- **Owner-stability snapshot:** each lexical or canonical walk captures the candidate owner's
  canonical directory when admitted, then requires that same directory immediately before the leaf
  probe and any cache-miss read.
- **Dual-view ignore:** preserve the normalized supplied label and the resolved target label as
  independent ignore-policy inputs; one view cannot re-include the other.
- **Hard denylist:** conservative VCS and credential names that ignore negation cannot re-include.
- **Pure hard-deny classifier:** one Boolean function over normalized components, without path
  resolution, I/O, GitIgnoreSpec evaluation, or matching-rule disclosure.
- **Pure lexical admission:** delegated strict Unicode-scalar and relative-path normalization that
  rejects empty/absolute/`..`/NUL input and values above 4,095 bytes, 256 normalized components, or
  255 bytes per component before `Path`, resolution, or I/O.
- **Safe error:** one fixed code/message without path, pattern, rule, content, or raw OS detail.
- **Deterministic budget:** bytes and items, not provider tokens.
- **Scalar-text admission:** accept only exact strict UTF-8 round-trips after JSON parsing; reject
  lone surrogates and NUL before policy or filesystem work.

## Architecture and design

```text
Ink TUI ---- NDJSON ----> Python harness <---- provider may request tools later
                              |
       CAH-024 sole lexical admission -> normalized components
          4095 bytes / 256 parts / 255 bytes per name
                              |
              [CAH-026 hard-deny classifier]
                    /                     \
      CAH-025 AGENTS source            ordinary read policy
      (skip `.gitignore`)          (hard deny + GitIgnoreSpec)
                                            |
               lexical prepare: ancestors + both leaf forms ----+
                                            |                    |
                               CAH-024 resolve                   |
                                            |                    v
                              canonical hard deny       owner/.gitignore binding
                                            |             | owner scope | source
              canonical prepare: ancestors + both leaf forms ---+
                                            |             | CAH-024 boundary
                            admit file | directory       | + canonical hard deny
                                            |             v
                         select both views' result    bounded source cache
                    \                     /
                     CAH-024 workspace boundary
                              |
                  admitted bounded local access
                     /                    \
       instruction discovery       CAH-027/028/029 reads
                              |
Repository filesystem --------+
Transcript/evidence: unchanged; denied paths and policy details never enter it
```

The provider can propose a future operation, but only the harness admits it. The gate has no
`include_ignored` or “approved anyway” path. It rechecks before I/O because a policy decision is a
snapshot, not durable authorization. The pure classifier is the single implementation of hard-deny
product policy for both branches; only ordinary reads add ignore semantics.

`RepositoryReadPolicy(boundary: WorkspaceBoundary)` retains the exact supplied boundary. Its exact
`admit_existing(path: str) -> AdmittedRepositoryPath` method returns frozen canonical `path`, `kind`,
and direct-leaf `is_symlink` provenance; kind is only `file | directory`, and special targets are
unavailable. CAH-026 intentionally adds no unused runtime object. CAH-037's sole M2 composition
factory creates the per-session policy after the actual read services exist, then supplies the same
identity to CAH-027 and CAH-028. A direct call creates one decision scope, while recursive consumers
use `_new_admission()` to reuse one policy cache and aggregate budget across descendant admissions
rather than reconstructing a workspace root or authorization decision.

## Practical walkthrough

1. Define immutable decisions, shared ordinary-read limits, one CAH-026 lexical adapter, and fixed
   errors.
2. Delegate `normalize_repository_path_components(value)` to CAH-024's sole lexical primitive and
   implement `is_hard_denied_path(components)`; prove the adapter preserves exact endpoint tuples or
   translates one fixed failure before construction/I/O.
3. Admit path/query strings as unchanged Unicode scalar text, normalize supplied path components,
   then call the classifier.
4. Preserve the normalized supplied label and walk its directory prefixes root-to-leaf. Before
   entering each directory, apply the policies available at that point; load its nested policy only
   after it admits. Match both leaf forms; deny before requested-target resolution when an ancestor
   is ignored or both leaf forms are ignored.
5. When either view admits a candidate-owner directory, preserve its view-relative label and capture
   its canonical directory. Re-admit that label and require the same directory immediately before the
   non-following `.gitignore` probe. For every present candidate, resolve its source through CAH-024
   and apply canonical hard denial.
6. On a cache hit, attach rules only after the owner check and current leaf/source resolution; do not
   reread or recharge content. On a cache miss, re-admit and compare the owner before resolving the
   leaf again, then recheck the source immediately before the bounded read. Cache and charge one
   allowed canonical source once while attaching its rules at each view-relative owner label.
7. When no lexical type-independent denial wins, resolve with CAH-024 and apply the same hard-deny
   classifier to canonical components before target stat/type inspection.
8. Walk the canonical chain, compute both canonical leaf forms, and deny type-independent results.
   Otherwise admit only a regular file or directory, select that kind's effective result in both
   views, and deny before requested content. Cached rules remain attached at each view's owner scope.
9. Re-run admission before use, then test negation, nested scope, policy-source aliases, staleness,
   and every limit boundary.

## Implementation code samples

### Important path: one atomic admission decision

From [`repository_access.py`](../../src/code_assist_harness/repository_access.py):

```python
# `_RepositoryAdmission` is the public-failure scrub around either use mode.
def admit_existing(self, path: str) -> AdmittedRepositoryPath:
    try:
        return self.policy._admit_existing(path, self.state)
    except RepositoryAccessError as error:
        error.__cause__ = error.__context__ = None
        raise

# `RepositoryReadPolicy` creates a fresh scope for one direct decision.
def admit_existing(self, path: str) -> AdmittedRepositoryPath:
    return self._new_admission().admit_existing(path)

def _new_admission(self) -> _RepositoryAdmission:
    return _RepositoryAdmission(self)

# Inside `_admit_existing(path, state)`:
try:
    lexical_components = normalize_repository_path_components(path)
except RepositoryPathSyntaxError:
    raise RepositoryAccessError("invalid_repository_path") from None

if is_hard_denied_path(lexical_components):
    raise RepositoryAccessError("repository_path_unavailable")

lexical_rules = self._prepare_ignore_view(lexical_components, state)
ignored_as_file = self._is_ignored(lexical_rules, lexical_components, is_directory=False)
ignored_as_directory = self._is_ignored(
    lexical_rules,
    lexical_components,
    is_directory=True,
)
if ignored_as_file and ignored_as_directory:
    raise RepositoryAccessError("repository_path_ignored")

requested_label = _label(lexical_components)
resolved = self._resolve_requested(requested_label)
canonical_components = tuple(resolved.relative_path.parts)
if is_hard_denied_path(canonical_components):
    raise RepositoryAccessError("repository_path_unavailable")

canonical_rules = self._prepare_ignore_view(canonical_components, state)
canonical_ignored_as_file = self._is_ignored(
    canonical_rules,
    canonical_components,
    is_directory=False,
)
canonical_ignored_as_directory = self._is_ignored(
    canonical_rules,
    canonical_components,
    is_directory=True,
)
if canonical_ignored_as_file and canonical_ignored_as_directory:
    raise RepositoryAccessError("repository_path_ignored")

kind = self._supported_kind(resolved)
if kind == "directory":
    ignored = ignored_as_directory or canonical_ignored_as_directory
else:
    ignored = ignored_as_file or canonical_ignored_as_file
if ignored:
    raise RepositoryAccessError("repository_path_ignored")
```

The wrapper creates one decision-local state for a direct admission; recursive tools can retain the
internal admission object so every descendant shares the same policy-source cache and aggregate
budget. The outer admission boundary removes both exception chaining attributes, not merely their
rendering, before a safe failure leaves the policy. The first pipeline block translates the one
CAH-024 lexical failure and applies the non-overridable hard deny before policy I/O. The next block
collects lexical rules and computes both leaf forms; only a type-independent denial can stop before
target resolution.
The next block performs canonical hard denial, collects both canonical leaf decisions, and denies a
type-independent canonical result before type inspection. Only then does the resolved kind select
both views' result. One decision-local `state` accounts for policy sources shared by both views.

### Important path: policy files are untrusted inputs

From [`repository_access.py`](../../src/code_assist_harness/repository_access.py):

```python
owner_label = _label(owner.components)
self._policy_checkpoint("before_policy_probe", owner_label)
self._require_same_owner(owner)
candidate_path = self._policy_candidate_path(owner.components)
if not self._policy_leaf_is_present(candidate_path):
    return None

candidate_label = _child_label(owner.components, ".gitignore")
first_source = self._resolve_policy_source(candidate_label)
cached = state.cache.get(first_source.path)
if cached is not None:
    return cached

self._require_policy_capacity(state, first_source.size)
self._policy_checkpoint("before_policy_read", owner_label)
self._require_same_owner(owner)
if not self._policy_leaf_is_present(candidate_path):
    raise RepositoryAccessError("repository_policy_invalid")
current_source = self._resolve_policy_source(candidate_label)
if current_source.path != first_source.path:
    raise RepositoryAccessError("repository_policy_invalid")
self._require_policy_capacity(state, current_source.size)

payload = self._read_policy_bytes(current_source.absolute_path)
if (
    len(payload) > MAX_POLICY_SOURCE_BYTES
    or state.loaded_bytes + len(payload) > MAX_POLICY_BYTES
):
    raise RepositoryAccessError("repository_policy_invalid")
try:
    text = payload.decode("utf-8", errors="strict")
except UnicodeError:
    raise RepositoryAccessError("repository_policy_invalid") from None
if "\x00" in text:
    raise RepositoryAccessError("repository_policy_invalid")
try:
    parsed = GitIgnoreSpec.from_lines(text.split("\n"), backend="simple")
except Exception:
    raise RepositoryAccessError("repository_policy_invalid") from None

state.cache[current_source.path] = parsed
state.loaded_bytes += len(payload)
return parsed
```

The owner check occurs before the non-following leaf probe and again before a cache-miss read. A
cache hit still follows current owner, leaf, and source admission. A miss checks capacity before the
bounded read, validates strict UTF-8/no-NUL text, and only then commits the canonical source to cache
and byte accounting. Pre-read-rejected sources are not opened, cached, or charged. Every unsafe
present candidate maps to the same fixed policy failure, and mapped failures suppress their original
cause so a traceback cannot recover a path, pattern, operating-system message, or repository content.

### Failure path: leaf type changes the effective Git decision

From [`test_repository_access.py`](../../tests/test_repository_access.py):

```python
def test_lexically_ignored_missing_target_is_not_an_existence_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("private-missing.txt\n", encoding="utf-8")
    boundary = WorkspaceBoundary.from_path(workspace)
    policy = RepositoryReadPolicy(boundary)
    original_resolve = WorkspaceBoundary.resolve_existing
    requested_resolutions = 0

    def track_resolution(self: WorkspaceBoundary, value: str) -> ResolvedWorkspacePath:
        nonlocal requested_resolutions
        if value == "private-missing.txt":
            requested_resolutions += 1
        return original_resolve(self, value)

    monkeypatch.setattr(WorkspaceBoundary, "resolve_existing", track_resolution)

    _admit_error(
        policy,
        "private-missing.txt",
        "repository_path_ignored",
    )
    assert requested_resolutions == 0


@pytest.mark.parametrize(
    ("rules", "kind", "admitted"),
    [
        ("cache\n!cache/\n", "file", False),
        ("cache\n!cache/\n", "directory", True),
        ("cache/\n!cache\ncache/\n", "file", True),
        ("cache/\n!cache\ncache/\n", "directory", False),
    ],
)
def test_opposing_leaf_forms_apply_last_match_precedence_per_exact_kind(
    tmp_path: Path,
    rules: str,
    kind: str,
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    target = workspace / "cache"
    if kind == "directory":
        target.mkdir()
    else:
        target.write_text("regular file", encoding="utf-8")

    policy = _policy(workspace)
    if admitted:
        assert policy.admit_existing("cache").kind == kind
    else:
        _admit_error(policy, "cache", "repository_path_ignored")
```

The first test proves a leaf ignored in both forms denies with zero requested-target resolutions.
The parameterized test then locks later-rule precedence when file and directory decisions disagree:
the safely admitted kind selects the exact result rather than letting either form overrule the other.

### Validation evidence

`TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_repository_access.py` passes all
133 focused tests. `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` also passed end to end:
lock/environment checks, Ruff lint/docstrings and format, the complete offline Python suite with one
live-provider smoke deselected, both protocol implementations and shared fixtures, repository-policy
checks, TUI typecheck/lint and tests, and the real Node-to-Python process-boundary tests.

## Failure scenarios to study

- **Negated credential:** `.gitignore` says `!.env`; the hard deny still returns generic unavailable.
- **Instruction-source bypass:** an otherwise valid `pkg/AGENTS.md` is ignored but points to
  `secrets/dev.env`. CAH-025 skips ignore policy but calls the same classifier on the resolved target,
  so it returns its fixed source-unavailable failure without reading bytes or revealing the rule.
- **Untraversable parent:** root rules `private/` then `!private/keep.py` still deny a direct read;
  `private/.gitignore` is never loaded.
- **Traversable-parent control:** `private/*` then `!private/keep.py` may admit the file because the
  directory remains reachable, provided the other path view also admits.
- **Alias disagreement:** the lexical alias is ignored but its canonical target is admitted, or the
  reverse; either disagreement still returns `repository_path_ignored`, a lexical denial performs no
  requested target resolution when its ancestor or both leaf forms decide the result; an ambiguous
  lexical leaf uses the contained target kind without reading requested content, and a
  negation on the admitted side cannot override it.
- **Escaping or denied policy source:** root or nested `.gitignore` points outside the workspace, to
  `.git/config`, or to `secrets/dev.env`. Boundary or hard-deny admission returns exact
  `repository_policy_invalid`; neither policy-source nor requested-content bytes are read or charged.
- **Allowed shared policy source:** `pkg/.gitignore` links to `shared/ignore.rules`. Its source is read
  and charged once, but its rules remain scoped below `pkg`; another owner may attach the cached rules
  at its own scope.
- **Policy-owner retarget:** after a lexical-alias or canonical view captures owner A, its label is
  persistently retargeted to allowed directory B just before the leaf probe or just before a
  cache-miss read. Owner re-admission returns `repository_policy_invalid` before B's leaf is resolved,
  read, cached, charged, or attached at A's scope. Stable controls still admit, and a stable cache hit
  performs the owner plus current leaf/source checks without a content read or new charge.
- **Policy retarget:** an initially allowed policy link points outside or to a denied source at the
  pre-read recheck. The changed source fails with `repository_policy_invalid` before policy-source
  content I/O.
- **Policy replacement:** a present candidate disappears or becomes a directory, special file, or
  oversized regular file before its read. The recheck fails before policy content; a control with no
  directory entry remains a normal absence.
- **Policy bomb:** a 65,537-byte or invalid-UTF-8 `.gitignore` produces
  `repository_policy_invalid` without decoder text. The oversized case is rejected before content;
  invalid text remains a bounded uncommitted candidate and is never cached or charged.
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

1. Trace admission for `link/config` when the link targets `.git/config`; identify each classifier
   call and which caller owns resolution.
2. Create a symlink whose lexical and canonical labels receive opposite ignore decisions; explain
   why access is denied in both orientations.
3. Create root and nested ignore rules whose last match changes one view's result.
4. Classify each failure as validation, containment, hard deny, ignore, type, or content limit.
5. Teach back: why can neither model arguments nor approval override this read policy?
6. Explain why strict UTF-8 round-trip validation rejects surrogates but deliberately does not
   normalize two canonically equivalent path spellings.
7. Compare `private/` and `private/*`: why can the same leaf negation work only in the second case?
8. Test both pure helpers with spies that fail if they construct a `Path`, resolve or open a file,
   construct a GitIgnoreSpec, log a matching rule, or return more than components/a Boolean.
9. Trace `pkg/.gitignore -> shared/ignore.rules`: identify the owner used for matching and the source
   used for containment, hard denial, cache identity, and budget accounting.
10. Retarget both a lexical alias owner and a canonical-chain owner from allowed A to allowed B at
    each owner-check seam. Explain why checking only the leaf would attach the wrong rules, and what
    pathname race remains after the last check.

## Key takeaways

- The Python harness owns final repository-read admission.
- Pure lexical and hard-deny helpers give ordinary reads and CAH-025 identical pre-I/O decisions
  without sharing ignore-policy behavior, ordinary-read limits, or errors.
- Lexical and canonical ignore views each require a traversable ancestor chain, and either denied
  ancestor or leaf denies access.
- Every policy source is contained and canonically hard-denied before a bounded read; safe internal
  aliases preserve candidate-owner scope and share canonical cache/budget accounting.
- Each view re-admits the captured canonical owner before probing and before a cache-miss read, so a
  persistent allowed-to-allowed owner retarget cannot redirect policy while preserving the old scope.
- Hard denial precedes and dominates Git-style ignore policy.
- Central policy improves governance but introduces availability and operational cost.

## Glossary

- **Admission:** The complete decision that permits one bounded capability use.
- **Hard denylist:** Built-in paths that no lower-trust input can re-include.
- **Pure classifier:** A deterministic Boolean decision over normalized components with no I/O or
  observable matching-rule detail.
- **Ignore negation:** A `!` rule that reverses a normal ignore match within Git semantics.
- **Ancestor traversability:** The rule that every parent directory must remain reachable before a
  descendant or nested policy can affect admission.
- **Policy candidate owner:** The directory whose `.gitignore` location determines rule scope.
- **Owner-stability snapshot:** A checked mapping from a view-relative owner label to the canonical
  directory captured when that view admitted it.
- **Policy source:** The boundary-resolved canonical file whose bytes, cache identity, and budget
  supply a policy candidate.
- **Lexical path:** The normalized supplied workspace-relative name before symlinks are resolved.
- **Existence oracle:** A difference in errors that reveals whether protected data exists.

## Further reading

- [CAH-026 delivery contract](../../user-stories/cah-026-define-repository-read-contracts.md)
- [Git `gitignore`](https://git-scm.com/docs/gitignore)
- [PathSpec repository](https://github.com/cpburnz/python-pathspec)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
