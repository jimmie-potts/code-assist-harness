# CAH-001 lesson: Architecture decisions

- **Unit:** CAH-001
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Implementation companion
- **Implementation status:** In progress; the documentation baseline exists, but dependency cleanup
  and final validation remain
- **Story:** [CAH-001](../../user-stories/cah-001-record-architecture-decisions.md)
- **Related architecture:** [Architecture overview](../architecture.md),
  [ADR 0001](../adr/0001-own-the-agent-loop.md), and
  [ADR 0002](../adr/0002-ink-python-process-boundary.md)

> The ADRs are accepted design. The repository currently contains a minimal Python scaffold and
> documentation, not the planned TUI, runtime, protocol, or agent loop. This lesson distinguishes
> those states deliberately.

## Quick summary

This unit turns product choices into durable architecture records before implementation begins. It
teaches how ownership boundaries, explicit non-goals, and superseding decisions prevent code from
quietly choosing an architecture by accident.

## Learning objectives

After completing this unit, you should be able to:

- distinguish an accepted decision, a planned component, and observed implementation;
- explain why the Ink process owns presentation while Python owns orchestration and policy;
- record a superseding decision without erasing the context of the older direction;
- identify when a new choice requires an ADR rather than an incidental code comment.

## Why this unit matters

Every later slice assumes stable answers to questions such as “Which process decides a session is
complete?” and “May a repository broaden command permissions?” Without an accepted baseline, the
first convenient library or component can become the de facto architecture.

CAH-001 also resolves a real conflict: the initial scaffold described LangChain as foundational,
while the learning goal now requires a project-owned loop.

## Key concepts

### Decision records are not progress reports

An ADR records context, a decision, alternatives, and consequences. “Accepted” means the design is
authoritative; it does not mean the corresponding code exists. Story status and tests report
delivery progress.

### Ownership is more durable than a class diagram

The most important boundary says who may decide. Ink owns terminal input and rendering. Python owns
session lifecycle, orchestration, context, tools, policy, and transcripts. Provider and executor
adapters translate external mechanics without taking ownership of domain rules.

### Supersession preserves history

ADR 0001 explicitly replaces the LangChain-foundation direction. The old rationale remains visible
as historical context, while active README, package metadata, and dependencies must align with the
new decision.

### Target layout is not current layout

Architecture documents may describe `tui/`, `protocol/`, and runtime packages before they exist.
Each planned path must be labeled as target behavior and introduced only by its owning story.

## Architecture and design

| Decision | Owner | Accepted boundary |
| --- | --- | --- |
| Agent loop | Python harness core | Explicit and bounded; no framework-owned MVP executor |
| Terminal | Ink/Node parent | Input, rendering, approval presentation, child supervision |
| Process contract | Both boundaries | Versioned NDJSON on stdin/stdout; diagnostics on stderr |
| Side-effect authority | Python safety layer | Reads automatic; edits and commands require defined approval |
| Model access | Provider adapter | OpenAI first; provider SDK types stay outside the core |
| Command execution | Executor adapter | Restricted WSL host first; container adapter later |
| Persistence | Python persistence layer | Redacted events under XDG state, with a future opt-out |

The accepted invariants are:

- both processes run inside Ubuntu under WSL and exchange Linux paths;
- the TUI projects authoritative events and never grants tool permission;
- core domain types do not depend on OpenAI, LangChain, Ink, or an executor implementation;
- approval cannot override policy, and workspace configuration cannot broaden command policy;
- default validation is model-free and network-free; and
- documentation never turns a planned capability into a shipped claim.

## Practical walkthrough

1. **Inventory reality.** Inspect `src/`, `tests/`, `pyproject.toml`, `README.md`, and lockfiles.
   Record what exists before reading the target layout.
2. **Find conflicting intent.** Search product text and dependencies for LangChain. Separate a stale
   architectural claim from code that actually requires compatibility.
3. **Write the ownership map.** For terminal, lifecycle, policy, provider translation, execution,
   and persistence, name one authoritative owner.
4. **Record the decisions.** Read ADRs 0001 through 0005 as a set. Check that each contains context,
   consequences, alternatives, and an implementation-status caveat.
5. **Align active surfaces.** Update README, package description, contributor guidance, and the
   glossary. Remove unused LangChain dependencies and refresh `uv.lock`; do not add OpenAI yet.
6. **Prove scope discipline.** Confirm no TUI, runtime, model, protocol, tool, or subprocess behavior
   was introduced by this documentation-and-cleanup story.
7. **Validate consistency.** Run the commands in the story, search for active contradictory claims,
   and compare every ADR with the baseline note.

At the current checkpoint, the ADR and conceptual-document set exists. The LangChain packages still
appear in `pyproject.toml`, so CAH-001 remains in progress until removal, lock refresh, and validation
are complete.

## Failure scenarios to study

### Planned design is described as shipped

**Symptom:** a contributor tries to run `tui/` or import runtime modules that do not exist.
**Boundary:** documentation status and story tracking. **Safe outcome:** correct the claim and keep
the story open. **Evidence:** a file inventory agrees with README “current status” language.

### Narrative changes but dependencies do not

**Symptom:** metadata still installs an unused orchestration framework. **Boundary:** CAH-001
dependency cleanup. **Safe outcome:** remove the packages, refresh the lockfile, and prove the
minimal package still builds and tests.

## Production expansion

### Example enterprise scenario

Imagine 40 teams extending one internal agent platform across regulated repositories. Decisions
need discoverable owners, review history, policy checks, and traceability from services to approved
standards. Markdown ADRs still provide useful local rationale, but discovery and governance can no
longer depend on every engineer knowing which repository to search.

### Typical production capabilities and tools

- [MADR](https://adr.github.io/madr/) represents a structured, version-controlled ADR format.
- [Backstage Software Catalog](https://backstage.io/docs/features/software-catalog/) represents
  searchable component ownership and metadata across many teams.
- [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
  represents review routing for architecture-sensitive paths.
- [Open Policy Agent](https://www.openpolicyagent.org/docs) represents automated policy evaluation
  when rules must be consistent across services.

These links illustrate capabilities, not preferred vendors or dependencies for this repository.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One learning-first application | Many services and owning teams |
| Discovery | Markdown beside code | Searchable catalog and indexed decisions |
| Review | Normal code review | Required domain owners and governance workflow |
| Cost | Low setup and direct inspection | Platform operation, taxonomy, and governance overhead |

### Trade-offs and graduation signals

Central governance improves discovery and consistency but can slow decisions and create stale
catalog data. Graduate only when missing ownership, repeated contradictory choices, regulatory
evidence, or cross-team compatibility incidents are measurable. A larger tool should reduce that
observed cost, not exist merely because the organization is larger.

## Practical exercises

1. Choose one ADR and trace its decision into a README statement, story criterion, and future test.
2. Add a fictional target module to a scratch architecture diagram, then write the status sentence
   that prevents readers from assuming it exists.
3. Draft a superseding ADR for a hypothetical native-Windows requirement without editing ADR 0002.

## Key takeaways

- Architecture records establish decision ownership; tests and story status establish delivery.
- The TUI presents and projects, while Python orchestrates and authorizes.
- Supersession should be explicit, historical, and reflected in active metadata and dependencies.
- Production governance is justified by measured coordination or compliance needs, not prestige.

## Glossary

- **ADR:** A versioned record of one architecturally significant decision and its rationale.
- **Accepted design:** An authoritative decision that may still await implementation.
- **Architecture boundary:** A rule assigning responsibility or authority between components.
- **Superseded:** Replaced by a newer explicit decision while retained as historical context.
- **Target architecture:** The agreed destination, including components not yet implemented.

See the shared [project glossary](../glossary.md) for session, event, provider, and tool terms.

## Further reading

- [CAH-001 delivery contract](../../user-stories/cah-001-record-architecture-decisions.md)
- [Architecture overview](../architecture.md)
- [ADR 0001: Own the agent loop](../adr/0001-own-the-agent-loop.md)
- [ADR 0002: Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [ADR 0003: Versioned NDJSON](../adr/0003-ndjson-protocol.md)
- [MADR guidance](https://adr.github.io/madr/)
