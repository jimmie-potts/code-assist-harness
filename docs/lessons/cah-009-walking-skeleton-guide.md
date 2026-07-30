# CAH-009 lesson: Walking-skeleton guide

- **Unit:** CAH-009
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; verified against executable scenario fixtures and the real
  Node-to-`uv`-to-Python boundary
- **Story:** [CAH-009](../../user-stories/cah-009-document-walking-skeleton.md)
- **Implemented guide:** [Walking-skeleton execution guide](../walking-skeleton.md)
- **Related architecture:** [Architecture](../architecture.md), [protocol](../protocol.md),
  [agent loop](../agent-loop.md), and [evaluation](../evaluation.md)

> This lesson describes the implemented deterministic mock and the documentation checks delivered
> with CAH-009. Provider, workspace, tool, approval, transcript, and full agent-loop behavior remain
> future work.

## Quick summary

CAH-009 turns the first successful and cancelled cross-process executions into an executable
learning artifact. The guide follows concrete TypeScript and Python functions, and its four exact
NDJSON blocks are checked against shared fixtures, parsed by both protocol implementations, and
compared with the real boundary after normalizing timestamps only.

## Learning objectives

After completing this unit, you should be able to:

- trace one task from Ink keypress through Python and back to an incremental terminal frame;
- distinguish command identity, event correlation, session identity, sequence, and timestamp;
- explain which process owns input, supervision, lifecycle, ordering, validation, and rendering;
- diagnose why arbitrary stdout logging corrupts an NDJSON protocol;
- explain why cancellation is a request and why Python's first terminal selection wins; and
- maintain learner documentation as tested evidence rather than plausible prose.

## Why this unit matters

Cross-process code hides causality when read one module at a time. Before this unit, implementation
and integration tests proved the M0 path, while the lesson still described a guide that did not
exist. CAH-009 connects those artifacts so a learner can follow ownership changes without mistaking
the future agent loop for shipped behavior.

CAH-007 can now place this evidence behind one repository-wide command. Later reducer, transcript,
provider, context, and tool stories also have a concrete baseline they can extend without silently
changing the process boundary.

## Key concepts

**Walking skeleton:** the smallest vertical slice that crosses the intended architectural layers.
Here it is real terminal input, a supervised Python child, validated commands and events, a
deterministic mock, and incremental rendering.

**Executable example:** documentation data verified by the production parsers and stored as a shared
fixture. The guide's marked NDJSON blocks are checked copies whose exact parity is enforced by tests.

**Narrative trace:** a causal explanation that names the owner before and after every boundary. It
connects a message to the state change and visible frame it causes.

**Channel discipline:** stdin carries commands, stdout carries protocol events, and stderr carries
bounded human diagnostics. This separation is part of protocol correctness.

**Normalization:** comparison that replaces an intentionally variable value without weakening the
rest of the contract. The real-boundary check normalizes timestamp values only; protocol version,
type, IDs, correlations, sequences, and payloads remain exact.

**Authoritative terminal event:** one Python-emitted `session.completed` or `session.cancelled` event.
Local `task.submitted` and `cancel.requested` updates make the UI responsive but cannot decide the
session result.

## Architecture and design

The implemented ownership chain is:

```text
App key handler
  -> runApplication callback
  -> PythonRuntimeSupervisor command encoder
  -> child stdin / version 1 NDJSON
  -> CommandLineReader and run_runtime
  -> MockSession and OrderedEventWriter
  -> child stdout / version 1 NDJSON
  -> NdjsonLineReader and parseEventLine
  -> reduceSessionState
  -> App rerender
```

| Concern | Implemented owner | Invariant |
| --- | --- | --- |
| Draft and keybindings | [`App`](../../tui/src/app.tsx) | Input survives unrelated background events; Escape only requests cancellation. |
| Child and command writes | [`PythonRuntimeSupervisor`](../../tui/src/runtime-supervisor.ts) | A local update is published before its asynchronous command write. |
| Command acceptance and active work | [`run_runtime`](../../src/code_assist_harness/runtime.py) | At most one mock session is active. |
| Mock lifecycle and terminal race | [`MockSession`](../../src/code_assist_harness/mock_session.py) | The first serialized terminal selection wins. |
| Event sequence and stdout write | [`OrderedEventWriter`](../../src/code_assist_harness/protocol/streams.py) | Sequence allocation and one complete write share a lock. |
| Visible session state | [`reduceSessionState`](../../tui/src/session-state.ts) | Only legal, correlated, contiguous events enter the projection. |
| Terminal frames and cleanup | [`runApplication`](../../tui/src/run-application.tsx) | Every update rerenders; every Ink exit path stops the child. |

The source of exact messages is the four scenario fixtures under
[`protocol/fixtures/v1/scenarios`](../../protocol/fixtures/v1/scenarios/). The
[execution guide](../walking-skeleton.md) contains the full messages and explains their position in
the trace. Keeping the wire blocks in one learner-facing document avoids creating two prose copies
that could drift.

## Practical walkthrough

1. Start with the successful command fixture and identify its task and command ID.
2. Follow Enter through `App`, `runApplication`, and `PythonRuntimeSupervisor.submitTask`.
3. Follow the LF-delimited command through `CommandLineReader`, `parse_command_line`, and
   `run_runtime`.
4. Inspect `MockSession.run`: it emits `session.started`, three fixed deltas,
   `assistant.completed`, and `session.completed`.
5. For every event, follow stdout framing and `parseEventLine` into `reduceSessionState`, then connect
   the new projection to the rendered frame.
6. Repeat with the cancellation fixtures. Notice that normal events correlate to the start command,
   while `session.cancelled` correlates to the winning cancel command.
7. Hold the `MockSession` state lock in mind when studying completion versus cancellation. The local
   keypress never outranks the Python terminal guard.
8. Insert a non-JSON stdout line in a copy of the stream and pass it to the event parser. The safe
   result is a visible protocol failure, not ignored console output.
9. Run the shared-fixture and real-boundary tests and compare their assertions with the guide.
10. End by listing the model, workspace, tool, approval, edit, and persistence paths that are still
    absent.

The real application creates fresh command timestamps; `MockSessionRunner` assigns deterministic
session IDs within one runtime. The teaching fixtures hold their timestamps constant so the guide is
repeatable. The automated comparison normalizes only those timestamp values and leaves every other
field under exact comparison.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Verified safe outcome |
| --- | --- | --- | --- |
| Arbitrary text is printed on Python stdout | The physical line is not a JSON event. | TypeScript line reader and `parseEventLine` | Runtime becomes visibly `protocol-failed`; untrusted data is not reduced. |
| An event skips a sequence | The tape is not contiguous. | `reduceSessionState` | Projection fails closed instead of displaying reordered text. |
| `assistant.completed` differs from accumulated deltas | Completion contradicts streamed output. | `reduceSessionState` | The event is rejected as an invalid transition. |
| Cancellation wins before output | Only start and terminal events exist. | `MockSession` terminal guard | `session.cancelled` is sequence 2 and no delayed output follows. |
| One delta wins before cancellation | Partial output is already authoritative. | Shared writer/session lock | The delta is retained and cancellation uses the next sequence. |
| Completion wins the race | A late request cannot rewrite history. | `MockSession` terminal guard | The normal six-event tape ends once; no cancellation event is added. |
| Guide and fixture diverge | Learner sees an unexecutable example. | CAH-009 fixture synchronization test | The documentation check fails on the exact marked block. |

The [real-boundary tests](../../tui/test/runtime-boundary.test.ts) drive the genuine child through
successful rendering, cancellation at controlled positions, repeated tasks, active shutdown, and
process reaping. Python runtime tests control checkpoints and blocked writes without depending on
wall-clock scheduling.

## Production expansion

### Example enterprise scenario

A platform supports several protocol versions across services and client teams. Examples appear in
reference docs, SDK guides, runbooks, architecture diagrams, and audit evidence. A schema release can
invalidate hundreds of samples, so documentation is built, contract-tested, previewed, versioned,
and assigned an owner alongside the runtime change.

### Typical production capabilities and tools

These tools illustrate capabilities; Code Assist Harness does not require or endorse them:

- [MkDocs](https://www.mkdocs.org/) can publish searchable, version-controlled Markdown, at the cost
  of theme/plugin upgrades, hosting, indexing, and publication ownership.
- [Mermaid](https://mermaid.js.org/intro/) can keep diagrams reviewable as source, while adding
  renderer compatibility, accessibility, and diagram-maintenance work.
- [Vale](https://vale.sh/) can enforce terminology and prose rules across many authors, while teams
  must curate rules, suppressions, and false-positive policy.
- [OpenAPI](https://spec.openapis.org/oas/latest.html) illustrates machine-readable HTTP contracts
  that generate examples and reference pages, with schema governance and compatibility costs.
- [Spectral](https://docs.stoplight.io/docs/spectral/) illustrates programmable contract linting,
  while rule-set ownership and version migrations become operational responsibilities.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Audience | Learner and repository contributors | Multiple client teams, operators, and auditors |
| Source | Four shared NDJSON scenario fixtures | Versioned schema and example registry |
| Verification | Two parsers plus one real boundary | Generated clients, compatibility suites, and release gates |
| Publication | Repository Markdown | Searchable, versioned documentation portal |
| Observability | Deterministic tests and stderr diagnosis | Trace IDs, metrics, dashboards, and runbooks |
| Cost | Small explicit fixtures and tests | Platform ownership, hosting, governance, and migrations |

### Trade-offs and graduation signals

Hand-maintained strict fixtures keep the protocol visible and inexpensive for one repository.
Generation and a hosted portal improve coverage and discovery but can hide simple mechanics behind
tooling and require durable ownership. Graduate when multiple released protocol versions, external
consumers, repeated drift, or support/search data show that repository-local examples no longer
scale.

## Practical exercises

1. For the successful trace, label every transition as local UI state, wire fact, or rendered result.
2. Change one fixture correlation ID and predict whether parsing or reduction rejects it.
3. Remove the second delta and explain why a later sequence remains structurally valid JSON but
   semantically invalid session state.
4. Feed `debug: starting session` to `parseEventLine` and trace the resulting supervisor state.
5. Design a normalized comparison that ignores timestamps without accidentally ignoring sequence or
   correlation.
6. Extend the ownership table for a future provider while keeping its SDK types behind the adapter.

## Key takeaways

- Ink owns interaction and display; Python owns orchestration and terminal session truth.
- stdin, stdout, and stderr are separate correctness boundaries, not interchangeable consoles.
- Command correlation, Python-owned sequence, and strict reduction make streaming explainable.
- Cancellation is pending intent until one authoritative terminal event arrives.
- Documentation becomes trustworthy when examples are fixtures and the real boundary checks them.
- More documentation infrastructure is justified by consumers and drift, not by diagram polish.

## Glossary

- **Channel discipline:** reserving each process stream for one defined class of communication.
- **Executable example:** documentation content validated as part of the implementation contract.
- **Narrative trace:** an ownership-aware explanation of causes, boundaries, and observable effects.
- **Normalization:** controlled replacement of a known variable field during comparison.
- **Terminal selection:** the serialized choice of one final lifecycle outcome.
- **Walking skeleton:** a minimal implementation that crosses the intended architecture end to end.

See the shared [project glossary](../glossary.md) for command, event, correlation ID, sequence,
session, and TUI.

## Further reading

- [Walking-skeleton execution guide](../walking-skeleton.md)
- [CAH-009 user story](../../user-stories/cah-009-document-walking-skeleton.md)
- [Process protocol](../protocol.md)
- [Agent-loop design](../agent-loop.md)
- [Safety model](../safety-model.md)
- [Project glossary](../glossary.md)
- [CAH-007 repository-wide checks](../../user-stories/cah-007-establish-repository-checks.md)
- [MkDocs](https://www.mkdocs.org/)
- [Mermaid](https://mermaid.js.org/intro/)
- [Vale](https://vale.sh/)
- [OpenAPI](https://spec.openapis.org/oas/latest.html)
- [Spectral](https://docs.stoplight.io/docs/spectral/)
