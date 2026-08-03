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
