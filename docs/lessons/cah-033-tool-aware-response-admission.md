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
- write a closed grammar for final-text, bounded-overflow, and tool-call responses;
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

A common misconception is that `response.completed` validates everything before it. The collector
must still reconcile text, item order, cardinality, and its own staged-output bound; upstream domain
constructors already own opaque-payload and usage-field bounds.

Another misconception is that accepting one complete call makes its JSON arguments valid. CAH-033
preserves that bounded string without parsing it. Even two `path` members remain raw bytes here;
CAH-039 later uses pair-preserving decode so a normal dictionary cannot silently choose the last one.

## Key concepts

- **Staging:** temporary private storage that has no external side effect.
- **Admission grammar:** the complete legal ordering and cardinality of observations.
- **Overflow observation:** a content-free producer signal that text saturated at 8,193 bytes.
- **Atomic outcome:** one immutable accepted result or bounded output-overflow sentinel returned all at once.
- **Opaque continuation:** bounded provider state preserved byte-for-byte but never interpreted.
- **Commit point:** the later moment orchestration may publish text or act on a call.
- **Failure cut point:** any still-nonterminal valid prefix after which normalized failure may end the
  turn without committing the prefix.
- **Raw call arguments:** bounded provider text preserved exactly for later CAH-039 admission, not a
  dictionary or typed tool request.

## Architecture and design

```text
Ink TUI                 Python harness                         Provider
  no delta <-----X  publication/dispatch
                     ^                 bounded observations
                     |                              |
               later orchestration        [CAH-033 private stage]
                     ^                    grammar + usage + bounds
                     |                              |
 accepted final OR call OR failure OR output-overflow <---+

Native read tools: not reached in this unit
Provider adapter: first-producer saturation -> content-free text.overflow marker
Evidence boundary: no staged text/call/opaque/usage enters transcript or diagnostics
```

Legal success is exactly:

```text
opaque? -> text delta+ -> matching text completed -> usage? -> response completed
opaque? -> text delta* -> text overflow marker       -> usage? -> response completed
opaque? -> one tool call                         -> usage? -> response completed
```

Normalized provider failure follows this separate rule:

```text
valid-nonterminal-prefix -> response.failed
```

The prefix may be empty or may end after opaque continuation, valid text deltas, reconciled normal
text completion, the content-free overflow marker, the call, or any legal post-content usage
position. Each branch may
also carry its legal first-position opaque continuation. The collector discards the entire prefix
and returns only the existing bounded failure code, safe message, and retryability. A malformed
prefix followed by failure remains
`provider_invalid_response`; failure cannot make earlier invalid grammar valid. The optional opaque
value is the CAH-032 bounded history value, appears first in the response grammar, and is inserted at
that same position before its call when later replayed. CAH-032 has already admitted the opaque
payload's shape and byte bound, and the usage value is already a validated provider-domain value;
CAH-033 owns only their response ordering and cardinality.

The pure admission API is `ToolAwareTurnAdmission.observe(event: ProviderStreamEvent) -> None`
followed exactly once by
`finish() -> AcceptedFinalText | AcceptedToolCall | ProviderFailure | AssistantOutputOverflow`. It performs no I/O. The exact
session integration is
`ProviderSession._collect_admitted_turn(operation, events)`: CAH-034 has already claimed and validated
the single-use async iterator inside its guarded start transaction. The existing session owner awaits
that iterator under the absolute deadline and cancellation/teardown rules and feeds one fresh
admission state machine. It continues after a provider terminal until EOF, so queued post-terminal
events cannot hide and a pull-driven stream can close naturally. Its exact return adds
`AssistantOutputOverflow | None`; `None` means cancellation, teardown, deadline, or another
authoritative terminal already won and the current read task was reaped. Iterator errors instead
return the fixed invalid-response failure. Outer task cancellation propagates after reaping.
`AcceptedFinalText` has only `chunks: tuple[str, ...]` and optional
`ProviderUsageReported`; it discards a validated opaque item because final text ends the loop.
`AcceptedToolCall` has only `call: ProviderToolCall`, optional
`ProviderOpaqueContinuation`, and optional usage so the later request can replay the opaque item
immediately before the call. Providers and the strict fake emit opaque state only as
`ProviderOpaqueContinuationObserved(continuation=...)`; the bare history value is not a
`ProviderStreamEvent`. Providers signal saturation only as
`ProviderTextOverflowObserved(required_bytes=8193)` with kind `text.overflow`; that frozen event is
content-free and admits no other value. Normal neutral delta/completion text must be exact built-in
strings and pass an O(1) 8,192-character gate before terminal-safe scalar scanning and an inclusive
8,192-byte strict-UTF-8 cap. An adapter/fake never constructs a huge normal text carrier merely so a
downstream collector can reject it.
The shared `provider/models.py` constant `MAX_PROVIDER_TEXT_BYTES=8192` supplies this transport cap to
models, admission, session, fake, and later adapters; it is distinct from the configurable 4,096-byte
M2 session allowance.
`AssistantOutputOverflow(required_bytes=8193)` is the separate core outcome. It bounds memory after
the 8,192-byte protocol-fit ceiling, then lets the existing mutable tracker select exact
`assistant_output_limit_exceeded` without a partial byte charge. An accepted value at or below that
ceiling is still reserved as one complete value against the configured cumulative limit later.

## Practical walkthrough

1. Receive one operation and its already-claimed async iterator from CAH-034's no-await guarded start
   transaction.
2. Feed each supervised observation to one private `ToolAwareTurnAdmission` state.
3. Select normal text, overflow, or call; never switch branches.
4. Reconcile normal completion or the content-free overflow marker and at most one usage value.
5. Preserve an accepted call's argument string byte-for-byte without parsing or duplicate detection.
6. Continue through terminal to EOF, call `finish`, and return one immutable outcome.

The first provider-specific producer detects text crossing 8,192 UTF-8 bytes, clears its bounded
fragments, and eventually emits only the 8,193 marker after its own terminal structure validates.
CAH-033 clears any earlier staged deltas and converts the marker to the core sentinel. It still
requires response terminal and EOF. Later structural grammar violations win as invalid response; a
legal provider failure wins as that normalized failure. Core also saturates aggregate deltas
defensively and rejects a producer that crosses the bound without the required marker.
7. On normalized provider failure, discard the whole stage and preserve only its bounded
   classification.
8. On invalid grammar or iterator failure, return fixed invalid response; on cancellation, discard the
   stage and reap the current read task. The later session finalizer owns ordinary cleanup.

## Implementation code samples

### Planned pseudocode: atomic collection

```python
admission = ToolAwareTurnAdmission()
while True:  # this loop lives in ProviderSession, not the pure admission object
    try:
        event = await self._next_supervised_event(events)
    except StopAsyncIteration:
        break
    admission.observe(event)
staged = admission.finish()
match staged:
    case AcceptedFinalText(chunks=chunks, usage=usage):
        return staged
    case AcceptedToolCall(call=call, usage=usage, continuation=opaque):
        return staged
    case ProviderFailure(code=code, message=message, retryable=retryable):
        return staged  # no staged prefix is attached
    case AssistantOutputOverflow(required_bytes=8193):
        return staged  # bounded sentinel; no text is retained
```

This code returns data; it does not write protocol events or call the registry.

### Planned pseudocode: lifecycle supervision stays outside

```python
outcome = await provider_session._collect_admitted_turn(operation, claimed_events)
if outcome is None:
    return  # the session owner already selected and reaped a terminal
await orchestrator.accept(outcome)
```

The separation makes a test spy able to prove zero external action before admission succeeds while
the existing session owner—not the pure grammar state—retains deadline, cancellation, and cleanup.
After orchestration selects the returned candidate, that owner's finalizer uses natural
`wait_closed()` or cancel-first supervised cleanup; cleanup failure emits a recoverable diagnostic
without replacing the selected terminal.

## Failure scenarios to study

| Scenario | Safe result | Test signal |
| --- | --- | --- |
| text then call | exact internal `ProviderFailure(code="invalid_response", message="The provider returned an invalid response.", retryable=False)`; emitted `provider_invalid_response` | zero writer/registry calls |
| call before late duplicate usage | whole turn rejected | no actionable call escapes |
| one call contains duplicate `path` members | accepted raw call for later CAH-039 rejection | zero argument-parser/registry calls |
| completed text differs from deltas | whole turn rejected | staged sentinel absent |
| producer attempts a 65,537-byte opaque item | CAH-032 construction rejects before collection | dependency boundary test; no impossible collector event |
| cancellation before completion | discard and reap | one terminal winner |
| provider closes early | invalid response | no partial answer |
| response terminal followed by another event | invalid response after complete iterator consumption | post-terminal event cannot hide behind an early loop break |
| iterator raises | invalid response | distinct from diagnostic-only cleanup failure |
| oversized producer snapshots differ after saturation | bounded overflow marker/outcome | producer checks only type/structure; discarded content equality is deliberately waived |
| overflow then mixed call or post-terminal event | invalid response | structural grammar cannot be laundered by the output limit |
| overflow then legal provider failure | normalized provider failure | failure cut-point semantics remain authoritative |
| marker is missing, duplicated, misplaced, or followed by text/call | invalid response | first-producer bound remains a closed contract |
| staged text crosses 8,192 bytes with exact marker | `AssistantOutputOverflow(8193)` then exact `assistant_output_limit_exceeded` | zero retained/published text and no partial byte charge |
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
| Grammar | three closed success branches | versioned multi-provider grammars |
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
   raw argument string are deferred to CAH-039.
7. Explain why the driver must read through EOF after a terminal and why cleanup failure cannot replace
   an already selected answer or failure.
8. Explain why saturation belongs at the first producer while the harness still owns the limit result.

## Key takeaways

- Provider output remains untrusted until the whole turn is admitted.
- Atomic staging protects both the TUI and tools from late grammar failures.
- Atomic call admission preserves raw arguments; it does not parse them or erase duplicate members.
- Normalized provider failure may end any valid partial prefix, but carries none of that staged data.
- The harness can preserve opaque state without understanding or recording it.
- A content-free overflow marker bounds the first producer without moving limit policy into an adapter.

## Glossary

- **Closed grammar:** explicit allowed values/order; unknown shapes fail.
- **Optimistic publication:** displaying data before terminal validation.
- **Reconciliation:** proving fragments and terminal snapshots describe one value.
- **Side effect:** externally visible action such as output, dispatch, or persistence.

## Further reading

- [CAH-033 delivery contract](../../user-stories/cah-033-stage-and-validate-tool-aware-response.md)
- [CAH-039 argument-admission lesson](cah-039-provider-tool-argument-admission.md)
- [OpenAI streaming Responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html)
