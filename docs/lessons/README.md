# Unit lessons

The lesson library explains the engineering ideas behind each implementation-ready user story.
A user story is the delivery contract; a lesson is the learning companion that explains the
concepts, architecture, design choices, practical failure modes, and how the same problem is often
handled in a production organization.

The lesson set maps one-to-one to the 31 implementation-ready stories. Outcome-level epics do
not receive lesson files until they are refined into a story with acceptance criteria. This keeps a
lesson attached to work that can actually be built and verified.

Each lesson assumes the reader can write code but may be new to the unit's architecture. A dedicated
junior-engineer foundation explains prerequisite concepts, syntax, runtime behavior, and common
misconceptions before the deeper design. Once implementation exists, exact repository code samples
connect those concepts to the shipped path and one important failure or test path.

## How to use a lesson

Read the lesson before starting its story, then keep it open while implementing and validating the
slice. Each lesson deliberately separates three kinds of information:

- **Accepted design:** decisions already locked by an ADR or the architecture baseline.
- **Planned implementation:** the smallest approach intended for this learning-first repository.
- **Production expansion:** examples of additional controls and tools an enterprise might add.

Core learning units deserve the closest review when they teach context selection, the explicit
agent loop, LLM response grammar, tool calling and dispatch, future MCP extension boundaries, safety
ownership, or evaluation. Supporting implementation units retain the same correctness bar but keep
their explanation and exercises tighter when they mainly realize an already-taught contract.

Production tools are examples, not dependencies or blanket recommendations. Tool choice depends on
scale, risk, regulations, existing platform capabilities, operational maturity, and total cost of
ownership. Prefer an official product or project reference when naming a tool, and explain the
capability it represents so the lesson remains useful if the vendor changes.

Retained visual PowerPoint companions through CAH-022 are frozen historical artifacts under
`assets/`. They may diverge from later design corrections and are not authoritative. Starting with
CAH-023, the Markdown lesson and its compact architecture diagram are the only lesson artifacts. Do
not add or revise presentations unless the user explicitly reverses this freeze.

## Lesson sequence

| Order | Unit | Lesson | Lesson status |
| ---: | --- | --- | --- |
| 1 | CAH-001 | [Architecture decisions](cah-001-architecture-decisions.md) | Verified against implementation |
| 2 | CAH-008 | [Educational documentation standards](cah-008-documentation-standards.md) | Verified against implementation |
| 3 | CAH-002 | [Ink application shell](cah-002-ink-application-shell.md) | Verified against implementation |
| 4 | CAH-003 | [Python runtime supervision](cah-003-python-runtime-supervision.md) | Verified against implementation |
| 5 | CAH-004 | [Protocol version 1](cah-004-protocol-v1.md) | Verified against implementation |
| 6 | CAH-005 | [Mocked streaming session](cah-005-mocked-streaming-session.md) | Verified against implementation |
| 7 | CAH-006 | [Session cancellation](cah-006-session-cancellation.md) | Verified against implementation |
| 8 | CAH-009 | [Walking-skeleton guide](cah-009-walking-skeleton-guide.md) | Verified against implementation |
| 9 | CAH-007 | [Repository-wide checks](cah-007-repository-checks.md) | Verified against implementation |
| 10 | CAH-010 | [Session state reducer](cah-010-session-state-reducer.md) | Verified against implementation |
| 11 | CAH-011 | [Append-only transcript](cah-011-append-only-transcript.md) | Verified against implementation |
| 12 | CAH-020 | [Provider interface and fake](cah-020-provider-interface-and-fake.md) | Verified against implementation |
| 13 | CAH-021 | [One provider-neutral turn](cah-021-one-model-turn.md) | Verified against implementation |
| 14 | CAH-022 | [Loop limits](cah-022-loop-limits.md) | Verified against implementation |
| 15 | CAH-023 | [OpenAI Responses adapter](cah-023-openai-responses-adapter.md) | Verified against implementation |
| 16 | CAH-024 | [Workspace boundary](cah-024-workspace-boundary.md) | Verified against implementation |
| 17 | CAH-026 | [Repository read policy](cah-026-repository-read-policy.md) | Verified against implementation |
| 18 | CAH-025 | [Scoped repository instructions](cah-025-repository-instructions.md) | Planned |
| 19 | CAH-027 | [Repository listing and metadata](cah-027-list-files-and-stat-path.md) | Planned |
| 20 | CAH-028 | [Bounded repository reads](cah-028-bounded-text-file.md) | Planned |
| 21 | CAH-029 | [Literal repository search](cah-029-literal-text-search.md) | Planned |
| 22 | CAH-030 | [Budgeted repository context](cah-030-budgeted-context.md) | Planned |
| 23 | CAH-031 | [Read-tool registry](cah-031-read-tool-registry.md) | Planned |
| 24 | CAH-038 | [Bounded provider tool definitions](cah-038-bounded-provider-tool-definitions.md) | Planned |
| 25 | CAH-032 | [Provider-neutral tool contract](cah-032-provider-tool-contract.md) | Planned |
| 26 | CAH-033 | [Tool-aware response admission](cah-033-tool-aware-response-admission.md) | Planned |
| 27 | CAH-039 | [Provider tool-argument admission](cah-039-provider-tool-argument-admission.md) | Planned |
| 28 | CAH-034 | [One read-tool round trip](cah-034-one-read-tool-round-trip.md) | Planned |
| 29 | CAH-035 | [Bounded agent loop](cah-035-bounded-agent-loop.md) | Planned |
| 30 | CAH-036 | [OpenAI tool-call mapping](cah-036-openai-tool-calls.md) | Planned |
| 31 | CAH-037 | [Read-only assistant evaluation](cah-037-read-only-assistant-evaluation.md) | Planned |

CAH-023 completes the M1 learning sequence by locating the first real-provider adapter behind the
harness-owned loop; the mock remains the default unless OpenAI is selected explicitly. CAH-024 now
opens M2 with workspace-boundary and repository-policy lessons verified against implementation; the
remaining 14 lessons are planned in the documented dependency order above. The
strongest review emphasis falls on context ownership in CAH-025/026/030 and especially the registry,
provider tool exchange, atomic response admission, argument trust boundary, round trip, bounded
loop, OpenAI mapping, and evaluation in CAH-031 through CAH-039. CAH-038 remains a supporting schema
bridge even though its dependency position precedes CAH-032. All M2 lessons are Markdown-only and
use compact text diagrams.

## Required lesson structure

Every unit lesson contains:

1. Metadata that identifies the unit, milestone, lesson status, implementation status, story, and
   related architecture.
2. A quick summary, learning objectives, and an explanation of why the unit matters.
3. A junior-engineer foundation that explains prerequisite ideas, syntax, one small example, and a
   common beginner misconception before using the deeper abstraction.
4. Key concepts, architecture, ownership boundaries, invariants, and deliberately deferred work.
5. A practical walkthrough of the intended or observed implementation and what to inspect.
6. Exact repository code samples after implementation, covering the important path and at least one
   failure or test path with beginner-friendly explanation.
7. Failure scenarios that connect symptoms, responsible boundaries, safe outcomes, and evidence.
8. A production expansion with a realistic enterprise scenario and three to five representative
   tools linked to official references.
9. A direct comparison between the repository approach and a production approach.
10. Trade-offs, operational costs, and measurable signals for graduating to more infrastructure.
11. Practical exercises that work without a live model or network unless explicitly opt-in.
12. A concise takeaway list and a lesson-local glossary.
13. Further reading that links the story, local architecture, and named production references.
14. Retain any linked historical PPTX through CAH-022 without revising it. Starting with CAH-023, do
    not add a presentation; the Markdown architecture diagram carries placement.

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
test scenarios, and surprising failure evidence. Begin with the prerequisite concepts a junior
engineer needs rather than assuming familiarity with the abstraction. When the story is complete:

- replace hypothetical walkthrough details with the actual implementation path;
- add exact implementation and test excerpts with beginner-friendly explanations;
- record which trade-offs were observed rather than merely predicted;
- link the tests or evaluation scenario that proves each important invariant;
- update production comparisons if the implemented seam changed; and
- keep the lesson status consistent with the user story.
