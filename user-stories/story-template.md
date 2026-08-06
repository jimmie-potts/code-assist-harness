# CAH-XXX - Unit title

- **Status:** Planned
- **Milestone / epic:** Mx / Ex
- **Dependencies:** Name completed or planned prerequisite stories
- **Lesson:** Link the one-to-one Markdown lesson
- **Learning emphasis:** Core learning unit or Supporting implementation unit
- **Review focus:** Name the concept that deserves the learner's closest review

## User story

> As a ..., I want ... so that ... .

## Single responsibility

State the one decision, behavior, or boundary this unit owns. Name the adjacent behavior it does not
own so the scope cannot grow silently during implementation.

## Scope

- List the minimum deliverables.
- Name the intended production modules or seams.
- State whether protocol, transcript, TUI, provider, filesystem, subprocess, or network behavior
  changes.

## Locked contract

Record accepted inputs, outputs, ordering, ownership, exact limits, stable failures, cancellation,
security assumptions, and residual risk. Separate a reversible implementation choice from a product
or architecture decision that would require human agreement.

## Reviewability budget

- **Estimated production-code churn:** 0-000 changed lines.
- **Delivered production-code churn:** Not started; replace with additions plus deletions before Done.
- **Counted paths:** `src/code_assist_harness/` and `tui/src/` additions plus deletions.
- **Excluded from count:** tests, docs, fixtures, lockfiles, and generated artifacts.
- **Planning PR scope:** name the one contract neighborhood refined here, or justify why multiple
  neighborhoods cannot be reviewed independently. Keep milestone-wide planning to a compact
  dependency/responsibility skeleton.
- **Split rule:** stop and refine another story before review if the unit gains a second
  responsibility or is likely to exceed roughly 600 changed production lines. Do not pad a smaller
  coherent implementation.

## Acceptance criteria

1. State one observable happy-path result.
2. State meaningful boundary and failure behavior.
3. Require typed, documented public contracts and fixed non-leaking errors.
4. Require deterministic evidence and honest documentation status.

## Acceptance-to-test matrix

| Contract or risk | Planned test | Layer | Expected evidence |
| --- | --- | --- | --- |
| Happy path | Name the focused scenario | Unit or integration | Exact result or state |
| Boundary | Test below, at, and above a limit where relevant | Unit | Stable admission or failure |
| Failure | Name a meaningful adversarial case | Unit or boundary | Fixed safe outcome and no leak |

## Validation

- Name focused tests and the important fixtures or deterministic fakes.
- Require `./scripts/check` before Done.
- Keep default validation model-free and network-free; identify any explicit optional smoke test.
- Require protocol parity, transcript compatibility, or TUI reducer/render evidence only when those
  boundaries change. Otherwise name the nearest parity assertion proving they remain unchanged.

## Documentation impact

List the story, lesson, conceptual documents, indexes, glossary, planning note, and diagrams that must
match the delivered behavior. Do not add or revise presentation files while the freeze is active.

## Exclusions

- Name tempting adjacent behavior and its later owner.
- Exclude extra providers, interfaces, platforms, side effects, or infrastructure not required by the
  single responsibility.

## Pre-review adversarial audit

Replace every prompt with story-specific evidence or an explicit `N/A` before opening the PR.
Generic checkmarks are not evidence.

| Audit | Required evidence or explicit N/A |
| --- | --- |
| Identity ledger | Distinguish the lexical/request alias, execution-time canonical target, semantic owner, provenance source, cache or accounting identity, and model-visible label. |
| End-to-end contract | Trace producer -> carrier -> consumer -> observable side effect across upstream/downstream stories, the composition root, and evaluation wiring. Record exact factory/method signatures, return variants, carrier field names, and type-owner/import direction; prove each pseudocode call composes without an invented wrapper or reverse dependency. Trace each bound to the first producer so no earlier adapter/constructor/fake retains, scans, joins, recurses over, or serializes an unbounded value. |
| Failure and atomicity | Cover empty, no-match, partial, error, cancellation, deadline, and rollback paths; name what remains uncommitted and what executes zero times. Give each async checkpoint/transition an exact continue/stop return or private sentinel, show every caller consuming it, and stage synchronous value/error candidates through their mandatory following seam. |
| Reachable boundaries | Exercise below, at, and above each limit through the real upstream producer and the real scheduler seam; do not rely only on impossible synthetic states. |
| Closed grammar and cardinality | Define exact accepted variants, canonical order, duplicate policy, structural depth/item/byte ceilings, and safe mappings for parser or runtime limit failures. |
| Real producer and repeated snapshots | Use framework/SDK/native-generated values in addition to hand-built fixtures. Mutate defaults, required markers, annotations, optional execution-context fields, and every added/done/completed or producer/consumer snapshot that repeats identity or content. For SDK streams, prove mapped-empty observations pump iteratively and raw terminal tuples remain staged through EOF or iterator failure. |
| Failure vocabulary and precedence | Name the owner, exception/result type, exact safe code/message, replayable tool error versus session terminal, diagnostic behavior, and cancellation/deadline precedence for every failure branch. |
| Accounting scope and adoption | State whether each limit is per scalar, per result, per request snapshot, or cumulative per session. Identify the guard-owned linearization point and prove cancellation/deadline both before and after charge/adoption. |
| Lazy async lifecycle | Separate awaitable lock/cleanup edges from the no-await critical section. Trace admission charge -> synchronous lazy start -> one-time iterator claim -> immutable installed-state carrier -> final clock read -> one non-failing pointer commit -> terminal-to-EOF -> cleanup. Prove pre/post-commit winner semantics, joined uninstalled cleanup, an explicitly consumed continuation result, one cleanup owner, force-reap before continuation, and session-wide watcher lifetime. |
| Composition identity | Name the sole factory and explicit runtime profile. Prove exact boundary/service/catalog/definition/handler identities through construction, request advertisement, validation, dispatch, and evaluation wiring; reject same-shaped cross-wiring. |
| Publication and evidence completeness | Define the atomic final publication transaction and whether evidence is complete, partial, or absent. Validate aggregate usage before whole-output reservation and publish neither on rejection. |
| Runtime migration surface | If a default path, opaque ID, lifecycle, transcript, fixture, or cancellation behavior changes, enumerate all external consumers and the exact compatibility or migration decision. |
| Mechanical artifact integrity | Render changed diagrams and nearby prose; prove every success/error arrow reaches the correct owner, code fences are balanced, pseudocode uses exact fields/signatures, and no stale or duplicate handoff prose remains. |
| Artifact parity | Compare the story, lesson, diagram, pseudocode, conceptual docs, and test matrix for the same named stage order and failure precedence. |
| Independent lenses | Name the completed security and identity/indirection review; end-to-end handoff and composition review; and provider/protocol, limits, and scheduler review, with concrete findings or explicit N/A. |

## Definition of done

1. Every acceptance criterion has deterministic happy-path, boundary, and meaningful failure
   evidence at the lowest useful layer.
2. Exact limits are tested below, at, and above the boundary where relevant.
3. Host paths, secrets, raw OS/provider failures, and unbounded repository content do not enter safe
   errors, events, fixtures, transcripts, or default representations.
4. Public contracts are typed and documented; strict schemas reject unsupported values and fields.
5. Focused tests and the canonical offline `./scripts/check` pass without a live model or network.
6. Changed protocol, transcript, provider, or TUI boundaries have their required parity and visible
   evidence; unchanged boundaries are called out honestly.
7. The Markdown lesson uses exact implementation and failure-test excerpts after code exists; no
   presentation work is introduced.
8. Conceptual docs, indexes, backlog, planning note, story status, and lesson status agree.
9. Delivered production-source churn is recorded and stays near the reviewability target or the work
   is split before review.
10. The PR is ready for review and no addressed review thread remains unresolved.

## Planned evidence

- Name the intended implementation modules.
- Name focused tests and integration evidence.
- Name the lesson's architecture position and primary teach-back question.

## Deferred work

- Name the next dependency-ordered unit.
- Record later production hardening without implying it is part of this story.
