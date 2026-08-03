# CAH-033 lesson: Stage and validate one tool-aware response

- **Unit:** CAH-033
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; tool-aware response admission is not implemented
- **Story:** [CAH-033](../../user-stories/cah-033-stage-and-validate-tool-aware-response.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Atomic response admission and the rule that untrusted provider output causes no
  text publication or tool action until its complete grammar is accepted
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Agent loop](../agent-loop.md), [Architecture](../architecture.md), and
  [Safety model](../safety-model.md)

> This lesson describes a planned contract. Pseudocode and event names are not shipped-code evidence.

## Quick summary

CAH-033 adds a private staging boundary around one provider turn. The harness accepts either final
text or one call only after completion, usage, and optional opaque-continuation checks all pass. A
normalized provider failure may end any otherwise valid partial prefix; the prefix is discarded and
only the bounded failure classification survives.

## Learning objectives

After this unit, you should be able to:

- distinguish streaming transport from application-level commitment;
- write a closed grammar for final-text and tool-call responses;
- distinguish a valid failure cut point from an invalid prefix that cannot be laundered by failure;
- explain why a proposed call is still untrusted data;
- preserve opaque continuation without interpreting or leaking it; and
- test response admission without a network or wall-clock race.

## Why this unit matters

If the TUI displays early text or a tool starts as soon as a call fragment appears, a later malformed
event cannot undo that action. Atomic admission turns a provider stream into one reviewed domain
decision before anything irreversible or user-visible happens.

## Junior engineer foundation

“Streaming” means values arrive over time; it does not mean each value is already safe to commit.

```text
receive fragments -> stage privately -> validate terminal snapshot -> expose one outcome
```

A common misconception is that `response.completed` validates everything before it. The harness
must still reconcile text, item order, cardinality, usage, and bounds itself.

Another misconception is that accepting one complete call makes its JSON arguments valid. CAH-033
preserves that bounded string without parsing it. Even two `path` members remain raw bytes here;
CAH-034 later uses pair-preserving decode so a normal dictionary cannot silently choose the last one.

## Key concepts

- **Staging:** temporary private storage that has no external side effect.
- **Admission grammar:** the complete legal ordering and cardinality of observations.
- **Atomic outcome:** one immutable accepted result returned all at once.
- **Opaque continuation:** bounded provider state preserved byte-for-byte but never interpreted.
- **Commit point:** the later moment orchestration may publish text or act on a call.
- **Failure cut point:** any still-nonterminal valid prefix after which normalized failure may end the
  turn without committing the prefix.
- **Raw call arguments:** bounded provider text preserved exactly for later CAH-034 admission, not a
  dictionary or typed tool request.

## Architecture and design

```text
Ink TUI                 Python harness                         Provider
  no delta <-----X  publication/dispatch
                     ^                         observations
                     |                              |
               later orchestration        [CAH-033 private stage]
                     ^                    grammar + usage + bounds
                     |                              |
       accepted final OR call OR bounded failure <---+

Native read tools: not reached in this unit
Evidence boundary: no staged text/call/opaque/usage enters transcript or diagnostics
```

Legal success is exactly:

```text
opaque? -> text delta+ -> matching text completed -> usage? -> response completed
opaque? -> one tool call                         -> usage? -> response completed
```

Normalized provider failure follows this separate rule:

```text
valid-nonterminal-prefix -> response.failed
```

The prefix may be empty or may end after opaque continuation, one or more valid text deltas,
reconciled text completion, the call, or either legal post-content usage position. Each branch may
also carry its legal first-position opaque continuation. The collector discards the entire prefix
and returns only the existing bounded failure code, safe message, and retryability. A malformed
prefix followed by failure remains
`provider_invalid_response`; failure cannot make earlier invalid grammar valid. The optional opaque
value is the CAH-032 bounded history value, appears first in the response grammar, and is inserted at
that same position before its call when later replayed.

## Practical walkthrough

1. Start one provider operation under the existing absolute deadline.
2. Collect observations into private bounded state.
3. Select one branch when text or a call appears; never switch branches.
4. Reconcile completion and at most one usage value.
5. Preserve an accepted call's argument string byte-for-byte without parsing or duplicate detection.
6. Close the operation and return one immutable terminal outcome.
7. On normalized provider failure, discard the whole stage and preserve only its bounded
   classification.
8. On invalid grammar or cancellation, discard the whole stage and reap provider work.

## Implementation code samples

### Planned pseudocode: atomic collection

```python
staged = await collect_one_turn(operation)
match staged:
    case AcceptedFinalText(chunks=chunks, usage=usage, continuation=opaque):
        return staged
    case AcceptedToolCall(call=call, usage=usage, continuation=opaque):
        return staged
    case ProviderFailure(code=code, message=message, retryable=retryable):
        return staged  # no staged prefix is attached
```

This code returns data; it does not write protocol events or call the registry.

### Planned pseudocode: commit stays outside

```python
outcome = await collector.collect(operation)
await orchestrator.accept(outcome)
```

The separation makes a test spy able to prove zero external action before collection succeeds.

## Failure scenarios to study

| Scenario | Safe result | Test signal |
| --- | --- | --- |
| text then call | fixed invalid-response failure | zero writer/registry calls |
| call before late duplicate usage | whole turn rejected | no actionable call escapes |
| one call contains duplicate `path` members | accepted raw call for later CAH-034 rejection | zero argument-parser/registry calls |
| completed text differs from deltas | whole turn rejected | staged sentinel absent |
| 65,537-byte opaque item | bound failure | safe representation only |
| cancellation before completion | discard and reap | one terminal winner |
| provider closes early | invalid response | no partial answer |
| provider fails after staged text/call | preserve bounded failure only | no staged sentinel or side effect |
| invalid prefix then provider failure | fixed invalid response | failure cannot launder grammar |

## Production expansion

### Example enterprise scenario

A production agent may stream through queues and approval services. It still needs an explicit
commit point, but may stage encrypted payloads durably with retention and recovery controls.

### Typical production capabilities and tools

- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
  supplies low-latency events; reconciliation and version maintenance add engineering cost.
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
  supplies structured call requests; application validation and execution remain operational work.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html) support cancellation and
  cleanup; race testing and ownership discipline are the cost.
- [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) standardize
  discovery/calls; remote trust, authentication, and result validation add cost.

### Local design versus production design

| Dimension | This unit | Production expansion |
| --- | --- | --- |
| Stage | memory, one turn | durable/distributed admission |
| Grammar | two closed outcomes | versioned multi-provider grammars |
| Commit | after complete validation | coordinated transaction/outbox |
| Opaque state | one bounded value | retention, encryption, recovery policy |
| Cost | delayed visible text | more storage and operational control |

### Trade-offs and graduation signals

Buffering delays visible text but prevents retraction and premature execution. Revisit incremental
publication only after the protocol can represent provisional text and reviewers accept rollback
semantics; never weaken call admission for latency.

## Practical exercises

1. Write the exact observation order for each legal branch.
2. Insert a second usage item and identify the commit that must not occur.
3. Explain why a safe `repr` matters even when opaque data is never logged intentionally.
4. Teach back the difference between receiving a call and authorizing execution.
5. List every valid prefix after which `ProviderFailed` may terminate the turn, then explain why an
   invalid prefix followed by the same event remains invalid.
6. Explain why duplicate call observations violate this grammar while duplicate members inside one
   raw argument string are deferred to CAH-034.

## Key takeaways

- Provider output remains untrusted until the whole turn is admitted.
- Atomic staging protects both the TUI and tools from late grammar failures.
- Atomic call admission preserves raw arguments; it does not parse them or erase duplicate members.
- Normalized provider failure may end any valid partial prefix, but carries none of that staged data.
- The harness can preserve opaque state without understanding or recording it.

## Glossary

- **Closed grammar:** explicit allowed values/order; unknown shapes fail.
- **Optimistic publication:** displaying data before terminal validation.
- **Reconciliation:** proving fragments and terminal snapshots describe one value.
- **Side effect:** externally visible action such as output, dispatch, or persistence.

## Further reading

- [CAH-033 delivery contract](../../user-stories/cah-033-stage-and-validate-tool-aware-response.md)
- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
