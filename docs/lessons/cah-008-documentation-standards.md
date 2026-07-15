# CAH-008 lesson: Educational documentation standards

- **Unit:** CAH-008
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; standards and Ruff docstring enforcement are verified
- **Story:** [CAH-008](../../user-stories/cah-008-establish-documentation-standards.md)
- **Related architecture:**
  [Architecture documentation and testing](../architecture.md#documentation-and-testing),
  [ADR 0001](../adr/0001-own-the-agent-loop.md), and [repository guidance](../../AGENTS.md)

> This lesson is verified against the checked-in Ruff policy, current Python scaffold, and
> completion evidence. It does not claim that future TypeScript exports, tools, or protocol models
> exist.

## Quick summary

This unit makes explanation part of the engineering contract. It teaches where API documentation,
conceptual rationale, user stories, tests, and durable implementation notes belong, then adds enough
mechanical enforcement to catch missing public Python documentation without rewarding boilerplate.

## Learning objectives

After completing this unit, you should be able to:

- choose between a docstring, TSDoc block, conceptual page, ADR, story, and implementation note;
- document responsibility, invariants, failure behavior, side effects, and cancellation succinctly;
- configure public-docstring checks with narrow test exemptions;
- recognize comments that merely paraphrase code or preserve stale behavior claims; and
- keep examples useful without leaking credentials or sensitive provider and transcript data.

## Why this unit matters

The harness deliberately exposes unfamiliar mechanisms: process framing, reducers, cancellation,
policy, edit preconditions, and context budgeting. Correct code without rationale would undermine
the learning goal and make later safety reviews depend on oral history.

Documentation also spans Python and TypeScript. A shared standard prevents wire types, UI state,
and domain types from looking interchangeable simply because all three are statically typed.

## Key concepts

### Document the contract, not the syntax

A useful API description states responsibility, inputs, outputs, exceptions, side effects,
cancellation, security assumptions, and invariants when relevant. It does not translate the next
line of obvious code into English.

### Match the artifact to the question

- **Google-style docstrings:** how a Python production API behaves.
- **TSDoc:** what an exported TypeScript contract means and who owns it.
- **Conceptual documents:** why a subsystem works the way it does.
- **ADRs:** why an architecturally significant option was selected.
- **User stories:** what must be delivered and how completion is demonstrated.
- **Implementation notes:** observed constraints, failure causes, evidence, and follow-up work.

### Exempt noise, not complexity

Tests and trivial private helpers do not need mechanical docstrings. Private code that encodes a
security boundary, protocol invariant, retry rule, cancellation race, or context-selection choice
still explains why the behavior exists.

## Architecture and design

| Artifact | Required content | Verification |
| --- | --- | --- |
| Public Python API | Responsibility and relevant behavior in Google style | Ruff `D` rules and review |
| Exported TypeScript contract | Meaning, ownership, and lifecycle in TSDoc | TypeScript lint/review |
| State machine | Legal states, transitions, and terminal invariants | Reducer tests and conceptual docs |
| Protocol message | Owner, order, correlation, sequence, and failures | Fixtures in both languages |
| Tool definition | Capability, approval, effects, limits, cancellation, security | Registry validation and audit tests |
| Complex test | Scenario intent when setup is not self-evident | Test review |
| Behavioral change | Updated API and relevant concept page | Definition-of-done review |

The standard's invariants are:

- public production Python APIs are typed and documented;
- meaningful exported TypeScript contracts use TSDoc;
- test files and trivial private helpers are exempt from mandatory docstrings;
- safety, protocol, concurrency, cancellation, retry, and context rationale remains documented even
  when implemented privately;
- conceptual status matches observed implementation; and
- examples contain fake, bounded, non-sensitive values.

## Practical walkthrough

1. **Inspect the implemented rule set.** [`pyproject.toml`](../../pyproject.toml) selects Ruff `D`,
   `E`, `F`, `I`, and `UP`, then applies the Google pydocstyle convention.
2. **Observe the enforcement boundary.** The only `D` per-file ignore is `tests/**/*.py`. Production
   modules have no broad documentation exemption, while Ruff naturally treats underscore-prefixed
   helpers as private.
3. **Prove the positive baseline.** The package module docstring passes. The existing undocumented
   test function also passes because it is under `tests/`, and a temporary trivial private-helper
   probe passed in production code.
4. **Probe the failure boundary.** A temporary undocumented public function in the package produced
   `D103 Missing docstring in public function`; removing it restored a clean lint result.
5. **Write TSDoc at ownership seams.** A wire event parser should say that input is untrusted and
   validation precedes UI-state reduction. Obvious JSX needs no ceremonial comment.
6. **Update concepts with behavior.** When a story changes a protocol or safety rule, update the
   relevant page and fixtures in the same change.
7. **Review examples as data.** Search docs, snapshots, and fixtures for credentials, raw provider
   payloads, home paths, and unbounded outputs.

Keep enforcement proportional. The goal is to make missing contracts visible, not to maximize the
number of comments. The exact probe and final command results are recorded in the
[completion note](../../user-stories/notes/2026-07-15-cah-008-documentation-enforcement.md).

## Failure scenarios to study

### Ruff passes because tests and production are both exempt

**Symptom:** a new public package API has no docstring. **Boundary:** lint configuration. **Safe
outcome:** narrow per-file ignores to tests and rerun the temporary negative probe. **Evidence:** the
CAH-008 probe failed in `src/` with `D103`, while the existing undocumented test and a temporary
private helper remained allowed.

### A conceptual page describes planned code as present

**Symptom:** readers search for an event writer that has not been implemented. **Boundary:** status
metadata and story lifecycle. **Safe outcome:** label the section “planned” and update it only when
tests prove the implementation.

### Documentation hides a secret

**Symptom:** a copied environment value appears in an example or snapshot. **Boundary:** authoring,
review, and redaction. **Safe outcome:** remove it, rotate a real credential if necessary, replace it
with an unmistakably fake bounded value, and add a regression search where practical.

## Production expansion

### Example enterprise scenario

Consider a company publishing Python and TypeScript SDKs to hundreds of internal consumers while
maintaining audit-sensitive automation. Documentation must be searchable, versioned with releases,
checked for terminology, generated from API contracts, and owned by the same teams that own code.

### Typical production capabilities and tools

- [Ruff pydocstyle rules](https://docs.astral.sh/ruff/rules/#pydocstyle-d) provide fast, mechanical
  Python docstring coverage at the cost of maintaining rule selection, exemptions, and upgrades.
- [TSDoc](https://tsdoc.org/) provides a portable syntax contract for TypeScript API comments, but
  teams still pay for review or tooling that detects stale and incomplete semantics.
- [Sphinx](https://www.sphinx-doc.org/en/master/) generates cross-referenced Python API and
  conceptual documentation while adding build configuration, themes, hosting, and version upkeep.
- [Vale](https://vale.sh/docs) enforces prose terminology and style rules while requiring a curated
  rule set, suppression policy, and ongoing false-positive tuning.

These are capability examples, not a recommendation to add a documentation platform to the MVP.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Audience | One learner and contributors | Many teams and external or internal consumers |
| Publication | Markdown and source docstrings | Versioned searchable documentation portal |
| Enforcement | Ruff plus focused review | Multi-language API, link, prose, and release gates |
| Cost | Low tooling and direct source access | Build pipelines, hosting, taxonomy, and maintenance |

### Trade-offs and graduation signals

The implemented policy deliberately checks all Google-compatible `D` rules in production rather
than only missing-docstring rules. That makes formatting and section consistency enforceable, but it
also makes Ruff upgrades and exception choices part of maintenance. Exempting only tests avoids
ceremonial test docstrings; review still has to recognize private code whose invariants deserve an
explanation because lint cannot infer semantic risk.

Generated portals improve discovery and versioning but add build failures, theme upgrades, search
infrastructure, and publishing ownership. Graduate when repeated support questions, multiple public
versions, broken cross-references, regulated review evidence, or measurable terminology drift cost
more than the platform would.

## Practical exercises

1. Draft a Google-style docstring for a `ProtocolReader` that includes malformed-input behavior but
   does not describe its line-by-line implementation.
2. Write TSDoc for a pure reducer and state how duplicate or unknown events are handled.
3. Create and remove the CAH-008 negative Ruff probe; record the exact rule that catches it.

## Key takeaways

- Documentation belongs at the boundary where its claim can be maintained and verified.
- Exempt trivial code deliberately, but always explain non-obvious safety and lifecycle rationale.
- A status label is an invariant: accepted design and implemented behavior are different claims.
- Add production documentation machinery only when scale, support, or governance creates evidence
  that source-local documentation is no longer enough.

## Glossary

- **Conceptual document:** A subsystem-level explanation of rationale, boundaries, and behavior.
- **Docstring:** Python source documentation attached to a module or API and available to tools.
- **Meaningful contract:** An exported or public boundary whose behavior is not obvious from types.
- **Negative probe:** A temporary known violation used to prove a check is active.
- **TSDoc:** A standard syntax and semantic convention for TypeScript documentation comments.

See the shared [project glossary](../glossary.md) for protocol and agent-domain terms.

## Further reading

- [CAH-008 delivery contract](../../user-stories/cah-008-establish-documentation-standards.md)
- [CAH-008 completion evidence](../../user-stories/notes/2026-07-15-cah-008-documentation-enforcement.md)
- [Repository documentation rules](../../AGENTS.md#python-style-and-documentation)
- [Unit lesson maintenance rules](README.md)
- [Architecture documentation and testing](../architecture.md#documentation-and-testing)
- [Ruff rule reference](https://docs.astral.sh/ruff/rules/#pydocstyle-d)
- [TSDoc overview](https://tsdoc.org/)
- [Sphinx documentation](https://www.sphinx-doc.org/en/master/)
- [Vale documentation](https://vale.sh/docs)
