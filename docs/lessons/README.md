# Unit lessons

The lesson library explains the engineering ideas behind each implementation-ready user story.
A user story is the delivery contract; a lesson is the learning companion that explains the
concepts, architecture, design choices, practical failure modes, and how the same problem is often
handled in a production organization.

The first lesson set maps one-to-one to the 14 implementation-ready stories. Outcome-level epics do
not receive lesson files until they are refined into a story with acceptance criteria. This keeps a
lesson attached to work that can actually be built and verified.

## How to use a lesson

Read the lesson before starting its story, then keep it open while implementing and validating the
slice. Each lesson deliberately separates three kinds of information:

- **Accepted design:** decisions already locked by an ADR or the architecture baseline.
- **Planned implementation:** the smallest approach intended for this learning-first repository.
- **Production expansion:** examples of additional controls and tools an enterprise might add.

Production tools are examples, not dependencies or blanket recommendations. Tool choice depends on
scale, risk, regulations, existing platform capabilities, operational maturity, and total cost of
ownership. Prefer an official product or project reference when naming a tool, and explain the
capability it represents so the lesson remains useful if the vendor changes.

## Lesson sequence

| Order | Unit | Lesson | Story status |
| ---: | --- | --- | --- |
| 1 | CAH-001 | [Architecture decisions](cah-001-architecture-decisions.md) | Done |
| 2 | CAH-008 | [Educational documentation standards](cah-008-documentation-standards.md) | Done |
| 3 | CAH-002 | [Ink application shell](cah-002-ink-application-shell.md) | Done |
| 4 | CAH-003 | [Python runtime supervision](cah-003-python-runtime-supervision.md) | Done |
| 5 | CAH-004 | [Protocol version 1](cah-004-protocol-v1.md) | Planned |
| 6 | CAH-005 | [Mocked streaming session](cah-005-mocked-streaming-session.md) | Planned |
| 7 | CAH-006 | [Session cancellation](cah-006-session-cancellation.md) | Planned |
| 8 | CAH-009 | [Walking-skeleton guide](cah-009-walking-skeleton-guide.md) | Planned |
| 9 | CAH-007 | [Repository-wide checks](cah-007-repository-checks.md) | Planned |
| 10 | CAH-010 | [Session state reducer](cah-010-session-state-reducer.md) | Planned |
| 11 | CAH-011 | [Append-only transcript](cah-011-append-only-transcript.md) | Planned |
| 12 | CAH-020 | [Provider interface and fake](cah-020-provider-interface-and-fake.md) | Planned |
| 13 | CAH-021 | [One model turn](cah-021-one-model-turn.md) | Planned |
| 14 | CAH-022 | [Loop limits](cah-022-loop-limits.md) | Planned |

## Required lesson structure

Every unit lesson contains:

1. Metadata that identifies the unit, milestone, lesson status, implementation status, story, and
   related architecture.
2. A quick summary, learning objectives, and an explanation of why the unit matters.
3. Key concepts, architecture, ownership boundaries, invariants, and deliberately deferred work.
4. A practical walkthrough of the intended or observed implementation and what to inspect.
5. Failure scenarios that connect symptoms, responsible boundaries, safe outcomes, and evidence.
6. A production expansion with a realistic enterprise scenario and three to five representative
   tools linked to official references.
7. A direct comparison between the repository approach and a production approach.
8. Trade-offs, operational costs, and measurable signals for graduating to more infrastructure.
9. Practical exercises that work without a live model or network unless explicitly opt-in.
10. A concise takeaway list and a lesson-local glossary.
11. Further reading that links the story, local architecture, and named production references.

Use [the lesson template](lesson-template.md) when a new implementation-ready story is added.

## Status mapping

Lesson status describes how the learning material relates to delivery; it does not replace story
status.

| User-story status | Lesson status | Required lesson wording |
| --- | --- | --- |
| Planned | Planned | Describe accepted design and planned behavior without shipped claims. |
| In progress | Implementation companion | Identify completed documentation or code and name the remaining work. |
| Blocked | Implementation companion - blocked | Name the blocker and preserve the latest verified evidence. |
| Done | Verified against implementation | Link concrete modules, tests, observations, and validation evidence. |

## Production comparison rubric

The production section should evaluate the unit along the dimensions that matter for that problem,
including:

- workload scale, concurrency, and team ownership;
- availability, durability, recovery, and data retention;
- security, identity, secrets, policy, and compliance;
- telemetry, supportability, incident response, and audit evidence;
- compatibility, deployment, and change governance;
- build-versus-buy cost and operational burden; and
- a concrete trigger for adopting the more complex production pattern.

The comparison should not imply that the larger system is automatically better. The MVP often
chooses an in-process or file-based design because it is inspectable, deterministic, inexpensive,
and aligned with the learning goal. Enterprise machinery becomes valuable when a measured risk or
scale requirement outweighs that simplicity.

## Maintenance lifecycle

Before a story is implemented, its lesson describes accepted design and planned behavior and must
not claim the feature exists. During implementation, add concrete module names, event examples,
test scenarios, and surprising failure evidence. When the story is complete:

- replace hypothetical walkthrough details with the actual implementation path;
- record which trade-offs were observed rather than merely predicted;
- link the tests or evaluation scenario that proves each important invariant;
- update production comparisons if the implemented seam changed; and
- keep the lesson status consistent with the user story.
