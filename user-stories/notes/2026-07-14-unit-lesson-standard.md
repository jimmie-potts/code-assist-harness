# Unit lesson standard - 2026-07-14

## Purpose

This note records how learning material maps to delivery work. It prevents future contributors from
treating a user story, conceptual architecture document, and lesson as interchangeable artifacts.

## Decisions

- One **unit of work** means one implementation-ready user story with an ID, dependencies,
  acceptance criteria, and validation plan.
- Every implementation-ready story has exactly one learning companion under `docs/lessons/`.
- Outcome-level epics do not receive lesson files until they are refined into implementation-ready
  stories. This avoids teaching a hypothetical unit that cannot yet be built or verified.
- A story remains the delivery contract. A conceptual document explains a system-wide concern. A
  lesson teaches the concepts and design of one bounded slice and connects them to exercises and
  production alternatives.
- Lessons must distinguish accepted design, planned implementation, and observed implementation.
  Creating a planned lesson does not change the story's implementation status.
- Every lesson contains a quick summary, learning objectives, key concepts, architecture and
  invariants, practical walkthrough, failure scenarios, production expansion, direct comparison,
  trade-offs and graduation signals, exercises, key takeaways, a local glossary, and further
  reading.
- Production tool references are representative examples, not project dependencies or universal
  recommendations. Each lesson includes three to five official references, and every example
  identifies the capability it illustrates and its operational cost.
- Production comparisons consider scale, durability, security, observability, governance,
  compatibility, team ownership, and build-versus-buy cost when those dimensions matter.
- Lesson status maps to story status: `Planned` remains `Planned`; `In progress` becomes
  `Implementation companion`; `Blocked` becomes `Implementation companion - blocked` with the
  blocker named; and `Done` becomes `Verified against implementation` with evidence links.

## Maintenance rule

Before implementation, a lesson may explain the accepted target design but must label behavior as
planned. During a story, add concrete modules, event shapes, commands, tests, and surprising failure
evidence. A story cannot be marked done until its lesson reflects the implemented path and links the
evidence that proves its important invariants.

When a future implementation-ready story is added:

1. Copy `docs/lessons/lesson-template.md` to a story-specific filename.
2. Add reciprocal links from `user-stories/README.md` and the story file.
3. Link the relevant ADR and conceptual documents.
4. Add three to five production examples only after identifying the capability being compared.
5. Validate local and official-reference links.

## Initial limitation

The first 14 lessons are design-stage learning guides. Only documentation stories CAH-001 and
CAH-008 are in progress; runtime, TUI, protocol, reducer, persistence, provider, and limit behavior
remain unimplemented. Each later story must replace hypothetical walkthrough details with actual
paths and observations instead of allowing the lesson to become stale architecture fiction.

## Review findings and resolutions

- A placeholder story link in the template would have failed local-link checks. The template now
  uses replacement text instead of a deliberately broken path.
- Lesson status initially lacked a rule for in-progress, blocked, and completed work. The lesson
  index now maps every supported story status to explicit lesson wording.
- The first content checklist omitted metadata, failure scenarios, further reading, and an explicit
  production-reference count. The template, contributor guidance, and CAH-008 criteria now require
  the same complete structure and three to five official references.
- Transcript replay was initially described as reproducing identical visible content even though
  redaction and bounding can alter stored values. CAH-011 now promises the same terminal lifecycle
  state and persisted safe fields without claiming removed content can be recovered.
- Provider cancellation initially conflated foreground stream termination with the Responses API's
  background-response lifecycle. CAH-020 and CAH-021 now require foreground connection termination
  for this slice and treat background execution as a separate adapter mode.
- The local `--no-transcript` flag was initially too easy to read as a provider-retention control.
  CAH-021 now separates local persistence from provider `store` configuration and organizational
  retention policy.
- CAH-022 initially implied a second provider turn even though CAH-021 deliberately stops after one.
  Model-turn exhaustion is now exercised at the isolated limit-tracker/preflight seam until a later
  story explicitly introduces multi-turn orchestration.

## Validation evidence

- All 14 implementation-ready stories have exactly one reciprocal lesson link, and all 14 lessons
  use the story-to-lesson status mapping.
- Every lesson contains the required headings and three to five unique official production
  references. All repository-local Markdown targets resolve, code fences are balanced, files end
  with one newline, and no trailing whitespace was found.
- `git diff --check` passed, and `pyproject.toml` parsed successfully with Python 3.12.
- `.venv/bin/pytest` passed with 1 test, `.venv/bin/ruff check .` passed, and
  `.venv/bin/ruff format --check .` reported 2 files already formatted.
- `uv` was not available on `PATH` in this environment, so the equivalent tools from the existing
  `.venv` were used. No TypeScript checks were run because the planned `tui/` project does not yet
  exist.
