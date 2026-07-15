# CAH-009 lesson: Walking-skeleton guide

- **Unit:** CAH-009
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; the execution guide cannot be verified until CAH-005 and CAH-006 exist
- **Story:** [CAH-009](../../user-stories/cah-009-document-walking-skeleton.md)
- **Related architecture:** [Architecture](../architecture.md), [protocol](../protocol.md),
  [agent loop](../agent-loop.md), and [evaluation](../evaluation.md)

> This is a lesson about creating evidence-based documentation later. It does not claim that the
> walking skeleton, its integration fixture, or the final CAH-009 execution guide exists today.

## Quick summary

CAH-009 will explain the first working task from keypress to Python and back to rendered terminal
state, using the real integration fixture as its source of truth. The unit teaches documentation as
an executable companion: examples must match validated protocol data and implemented ownership.

## Learning objectives

After completing this unit, you should be able to:

- trace one command and its event sequence without inventing hidden behavior;
- distinguish accepted architecture, implemented behavior, and future extension;
- explain stdin, stdout, stderr, correlation, sequencing, reduction, and cancellation together;
- keep code, fixtures, conceptual docs, and a learner-facing guide synchronized; and
- decide when a larger organization needs generated or continuously verified documentation.

## Why this unit matters

Cross-process systems are difficult to learn from isolated modules. A guide that follows one real
execution exposes where ownership changes and why apparently minor rules—such as no logging on
stdout—exist. Writing it only after CAH-005 and CAH-006 prevents polished hypothetical prose from
being mistaken for shipped behavior.

## Key concepts

**Executable example:** a protocol sample parsed by both implementations or derived from a fixture,
not JSON copied into prose and left to drift.

**Narrative trace:** a causal explanation of what each process does, what crosses the boundary, and
what becomes visible, rather than a chronological list without ownership.

**Channel discipline:** stdin carries commands, stdout carries only validated events, and stderr
carries bounded human diagnostics. The separation is part of correctness.

**Source of truth:** the implemented protocol models and integration fixture determine exact fields.
The guide explains them but does not redefine them.

**Intentional simplification:** fake output, no provider, no tools, no approvals, and no transcript
are named limits of M0, not missing steps hidden from the reader.

## Architecture and design

The final guide should make this ownership chain explicit:

```text
keypress and input state                        Ink TUI
  -> validated session.start command            stdin / NDJSON
  -> mock orchestration and sequence assignment Python runtime
  -> validated lifecycle and assistant events   stdout / NDJSON
  -> boundary validation and pure reduction      TUI state layer
  -> incremental terminal frames                 Ink rendering
```

| Decision | Owner | Evidence the guide must reference |
| --- | --- | --- |
| Input and keybinding | Ink | Rendering/input test or TUI source |
| Session lifecycle | Python | Runtime lifecycle test and emitted events |
| Wire validity | Pydantic and Zod boundaries | Shared protocol fixtures |
| Event order | Python ordered writer | Monotonic integration event sequence |
| Visible state | TUI reducer/rendering | Intermediate render assertions |
| Completion/cancellation race | Python terminal guard | Controlled integration scenario |

The document must not say that Ink approves a terminal transition or that Python owns display.
It must distinguish a command ID from a session ID and a sequence number from a timestamp. Raw
diagnostics are not events, and an EOF is not successful session completion.

## Practical walkthrough

1. Wait until CAH-005 and CAH-006 have passing real-boundary integration scenarios.
2. Select one normalized successful fixture and one controlled cancellation fixture.
3. Copy examples through a fixture-generation or validation path; do not type plausible IDs by hand.
4. Begin at the user action and name the Ink input handler responsible for `session.start`.
5. Show the exact command line written to child stdin and explain its command ID.
6. Follow `session.started`, multiple deltas, assistant completion, and session completion in sequence.
7. At each event, name boundary validation, state reduction, and the visible change.
8. Trace cancellation separately from keypress through command to one authoritative terminal event.
9. Explain stderr supervision and demonstrate why an arbitrary stdout print breaks parsing.
10. End with the deliberately absent provider, tools, approvals, file changes, and persistence.

The final examples must match actual protocol version, payloads, IDs, timestamps, correlations, and
sequence rules. Link the exact integration test or fixture. If normalized fixtures omit unstable
timestamps, explain the normalization rather than showing unverified literal values.

## Failure scenarios to study

| Scenario | Documentation symptom | Responsible practice | Safe evidence |
| --- | --- | --- | --- |
| Example predates a schema change | Parser rejects guide JSON | Contract validation | Both validators parse every sample. |
| Guide assigns policy to Ink | Ownership narrative is unsafe | Architecture review | Ownership table matches ADRs. |
| Only happy path is documented | Cancellation seems instantaneous | Scenario selection | Cancellation race is traced explicitly. |
| Future provider appears as shipped | Reader searches for nonexistent code | Status discipline | Simplifications and status are prominent. |
| stdout logging seems harmless | Learner adds a debug print | Channel explanation | Corruption test demonstrates the failure. |
| Test moves but link does not | Evidence link becomes dead | Link checking | CI checks local links or records omission. |

## Production expansion

### Example enterprise scenario

A regulated platform has dozens of services and hundreds of engineers. Protocol docs, runbooks,
architecture diagrams, audit explanations, and client examples must stay synchronized across release
trains. Review alone cannot reliably catch every stale payload or broken link, so documentation is
built, linted, versioned, and contract-tested as part of delivery governance.

### Typical production capabilities and tools

These tools represent capabilities; this repository does not require or endorse them:

- [MkDocs](https://www.mkdocs.org/) illustrates building a searchable site from version-controlled
  Markdown when repository navigation no longer scales, while adding theme and plugin upgrades,
  build pipelines, hosting, search indexing, and publication ownership.
- [Mermaid](https://mermaid.js.org/intro/) illustrates source-controlled diagrams that can evolve in
  the same review as architecture text, but renderer-version compatibility, accessibility, and
  diagram review become ongoing maintenance concerns.
- [Vale](https://docs.vale.sh/) illustrates automated terminology and prose-style checks across many
  authors, with continuing cost in rule curation, suppression policy, editor integration, and
  false-positive tuning.
- [OpenAPI](https://spec.openapis.org/oas/latest.html) illustrates a machine-readable contract that
  can drive reference documentation and validation for HTTP APIs while requiring schema ownership,
  compatibility policy, generation tooling, and coordinated version migrations.
- [markdown-link-check](https://github.com/tcort/markdown-link-check) illustrates automated internal
  and external link verification for Markdown repositories, but CI must manage network flakiness,
  redirects, allowlists, and recurring external-link maintenance.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Audience | One learner and contributors | Multiple teams, clients, auditors, support |
| Source | Markdown plus shared fixtures | Versioned portal plus contract registries |
| Verification | Parsers, integration test, link check | Build gates, previews, ownership, release versions |
| Diagrams | Small text diagrams | Generated or source-controlled rendered diagrams |
| Governance | Story review | Documentation owners, retention, compliance approval |
| Operations | Repository navigation | Search, analytics, support feedback, deprecation notices |

### Trade-offs and graduation signals

Plain Markdown is cheap, reviewable, and close to code. A portal and generation pipeline improve
discovery, versioning, and broad consistency but add plugins, hosting, security updates, and editorial
ownership. Graduate when multiple supported versions, external consumers, regulated evidence, or
measured search/support failures exceed what repository-local documents can serve.

## Practical exercises

1. Take the proposed protocol example and list which fields must come from a real fixture.
2. Write a one-paragraph trace that names the owner at every arrow; flag any implicit ownership.
3. Insert a non-JSON stdout line into a sample stream and explain the first observable failure.
4. Draft a checklist that prevents future behavior from being described in the past tense.
5. Design a test that compares normalized guide examples with the integration fixture.

## Key takeaways

- The implementation and validated fixtures are authoritative; the guide explains rather than invents.
- A useful walkthrough connects protocol messages to ownership and visible state.
- Planned, implemented, and deferred behavior must remain visibly distinct.
- Documentation infrastructure is earned by audience, versioning, and governance needs.

## Glossary

- **Contract drift:** a mismatch between documentation, fixtures, or implementations.
- **Executable example:** documentation data verified by the same contract as production data.
- **Narrative trace:** a causal, ownership-aware explanation of one execution.
- **Normalization:** removal or stabilization of intentionally variable fixture fields for comparison.
- **Source of truth:** the artifact authorized to define exact behavior.

See the shared [project glossary](../glossary.md) for command, event, correlation ID, sequence, and TUI.

## Further reading

- [CAH-009 user story](../../user-stories/cah-009-document-walking-skeleton.md)
- [Process protocol](../protocol.md)
- [Agent-loop design](../agent-loop.md)
- [Safety model](../safety-model.md)
- [Project glossary](../glossary.md)
- [MkDocs](https://www.mkdocs.org/)
- [Mermaid](https://mermaid.js.org/intro/)
- [Vale](https://docs.vale.sh/)
- [OpenAPI](https://spec.openapis.org/oas/latest.html)
- [markdown-link-check](https://github.com/tcort/markdown-link-check)
