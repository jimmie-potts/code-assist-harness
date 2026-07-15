# CAH-008 - Establish educational documentation standards

- **Status:** Done
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-001
- **Lesson:** [Documentation standards](../docs/lessons/cah-008-documentation-standards.md)

## User story

> As a learner and contributor, I want important abstractions, invariants, and safety decisions
> documented alongside the code so that I can understand not only what the harness does, but why it
> is designed that way.

## Scope

- Define Google-style Python docstrings and TSDoc expectations for meaningful exported TypeScript
  contracts.
- Enable Ruff public-docstring checks for production Python without forcing mechanical test or
  private-helper documentation.
- Establish the initial conceptual-documentation set and its maintenance rule.
- Establish one structured learning companion for every implementation-ready user story.
- Define the required educational metadata for future tools, protocol messages, reducers, and
  non-obvious tests.

## Acceptance criteria

1. Python production modules and public APIs use Google-style docstrings.
2. Exported TypeScript APIs use TSDoc when they represent a meaningful behavioral or wire contract.
3. Core state machines document legal states and transition invariants.
4. Tool documentation covers capability, approval, side effects, cancellation, limits, security,
   and expected failures.
5. Protocol-message documentation identifies process ownership, correlation, ordering, and
   sequencing semantics.
6. Complex tests explain the modeled scenario when setup and intent are not self-evident.
7. Ruff enables applicable `D` rules with the Google convention for public production APIs.
8. Tests are exempt from mandatory docstrings.
9. Trivial private helpers are exempt from mandatory docstrings; private code that encodes security,
   protocol, concurrency, retry, cancellation, or context-selection decisions documents why.
10. The repository contains the glossary introduced by CAH-001.
11. The documented definition of done requires behavioral changes to update relevant API and
    conceptual documentation.
12. Examples, comments, and docstrings do not expose credentials, raw provider responses, or
    sensitive transcript content.
13. The repository documents required sections for every future tool definition: name, purpose,
    input, output, capability, approval, filesystem behavior, subprocess/network behavior, timeout,
    output limit, cancellation, failures, and security considerations.
14. Every implementation-ready story links to a lesson containing status metadata, a quick summary,
    learning objectives, why the unit matters, concepts, architecture and design, a practical
    walkthrough, failure scenarios, production expansion, local-versus-production comparison,
    trade-offs and graduation signals, practical exercises, key takeaways, a lesson-local glossary,
    and further reading.
15. Each production expansion includes a realistic enterprise scenario and three to five
    representative tools linked to official references, with capabilities and operational costs
    described without treating those tools as project dependencies.

## Validation

- Run `uv run ruff check .` and confirm public production APIs are checked while tests are exempt.
- Run `uv run ruff format --check .` and `uv run pytest`.
- Run `git diff --check`.
- Introduce a temporary local public API without a docstring to verify the configured Ruff rule
  reports it, then discard that temporary change before completing the story.
- Review documentation examples for fake values and bounded, non-sensitive content.
- Verify that every implementation-ready story and lesson link has a one-to-one match.
- Verify each lesson's status follows the documented story-to-lesson status mapping.

## Documentation impact

Establishes the documentation standard in `AGENTS.md`, the conceptual documents under `docs/`, and
the unit lesson library under `docs/lessons/`. It also defines the documentation-related clauses
applied to every later story's definition of done.

## Completion evidence

The [CAH-008 documentation-enforcement note](notes/2026-07-15-cah-008-documentation-enforcement.md)
records the final Ruff policy, public-API negative probe, exemption checks, documentation audit, and
validation results. The completed unit changes documentation enforcement only; it adds no runtime
dependency or agent behavior.

## Out of scope

- Adding a documentation-site generator.
- Requiring docstrings on tests, obvious JSX, or trivial private helpers.
- Writing conceptual documents for behavior that has not yet been designed; this story creates the
  standards and initial architecture set.
