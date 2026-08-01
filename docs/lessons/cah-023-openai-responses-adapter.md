# CAH-023 lesson: Add the OpenAI Responses adapter

- **Unit:** CAH-023
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no OpenAI SDK, adapter, configuration, or live call exists
- **Story:** [CAH-023](../../user-stories/cah-023-add-openai-responses-adapter.md)
- **Related architecture:** [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [Agent loop](../agent-loop.md), [Safety model](../safety-model.md), and
  [Protocol](../protocol.md)

> This lesson records the accepted future adapter boundary using official OpenAI documentation
> current at planning time. CAH-021 now supplies the provider-neutral turn; CAH-022 must implement
> hard limits before this adapter can be activated. Nothing below is shipped code or evidence of a
> configured provider.

## Quick summary

CAH-023 plans the first vendor adapter: one explicitly configured, bounded foreground OpenAI
Responses stream behind the existing provider port. It teaches how to isolate SDK, network,
credential, event-shape, cancellation, and data-control concerns from the harness-owned loop.

## Learning objectives

After completing this unit, you should be able to:

- map harness-owned requests to a foreground Responses stream without leaking SDK types;
- distinguish foreground connection cancellation from the background cancel endpoint;
- normalize typed SDK events and failures into the CAH-020 contract;
- explain why local transcript opt-out and provider storage are different controls; and
- keep live smoke evidence separate from deterministic default validation.

## Why this unit matters

The provider port is valuable only if a real adapter can implement it without changing the loop.
Introducing the adapter after CAH-022 ensures network and billable work inherits tested hard limits.
Keeping it separate also isolates volatile SDK mappings, credentials, provider data controls, and
live-test policy from provider-neutral orchestration.

## Junior engineer foundation

An **adapter** translates between two interfaces. Here, the outside interface is the OpenAI Python
SDK and the inside interface is `Provider`. The adapter may know both shapes; the loop may know only
the inside shape.

Server-sent events (SSE) deliver a sequence of typed events over one HTTP response. Foreground
streaming ends when the response completes, fails, or its connection is terminated. Background mode
is different: work continues independently and has a server-side cancel endpoint.

```python
# Planned teaching shape, not shipped CAH-023 code.
stream = await async_client.responses.create(
    stream=True, background=False, store=False, ...
)
async for sdk_event in stream:
    validate_and_map_nonterminal_or_buffer_terminal(sdk_event)
# The operation attempts resource cleanup before releasing its buffered terminal queue.
```

CAH-020 still requires `Provider.start()` itself to be synchronous, lazy, and free of I/O. The
adapter performs the awaited create only after its operation's `events()` stream is consumed. This
lets cancellation own a pending create just as it owns a blocked next-event await.

A common misconception is that `--no-transcript` makes a provider request ephemeral. It disables
only local harness files. The adapter separately sets the Responses `store` field, and the account's
data-control and retention policies remain provider concerns.

## Key concepts

- **Composition root:** startup boundary that selects concrete implementations and validates config.
- **SDK mapping:** conversion from provider-specific request and event objects to harness-owned
  values.
- **Foreground stream:** response operation whose lifetime follows the active connection, consumed
  here with the asynchronous Python client.
- **Application-state storage:** provider retention controlled in part by the Responses `store`
  parameter, distinct from local transcripts.
- **Credential gate:** validation that required secret material exists without logging its value.
- **Opt-in smoke test:** minimal explicitly selected live check that supplements deterministic tests.

## Architecture and design

```text
explicit provider + model config
             |
             v
runtime composition root
             |
             v
CAH-021 loop --> Provider port --> OpenAI Responses adapter --> foreground SSE connection
      ^              |                        |
      |        harness-owned events      SDK objects stay here
      |
CAH-022 limits and terminal guard
```

The adapter constructs a foreground streaming request with `stream=true`, `background=false`, and
`store=false`. Current OpenAI documentation describes streaming as typed semantic SSE events,
Responses as stored by default unless `store` is false, and foreground cancellation as terminating
the connection. The background cancel endpoint belongs only to background mode and is excluded.

The runtime composition root owns provider and model selection plus safe credential validation. The
launcher defaults to mock, accepts only `mock` or `openai`, and stays on the mock unless the user
supplies `--provider openai --model MODEL`; a model is required only for OpenAI and is rejected for
the mock. This unit accepts exactly `gpt-4.1-mini-2025-04-14`, a pinned snapshot documented as text
output without a reasoning step. Aliases, prefixes, fine-tunes, reasoning families, and unknown model
values fail locally. `run-tui` parses the pair, the TypeScript supervisor forwards it as separate
shell-free Python arguments, and the Python parser validates it again; a parity test locks both
allowlists, and Python is authoritative before SDK import or network access. These values never
become NDJSON protocol fields. The composition root does not pass API keys through commands,
protocol events, transcripts, or provider-neutral models. Keeping one exact snapshot explicit
prevents a changing service alias from silently altering behavior.

Only `OPENAI_API_KEY` is accepted as provider-specific ambient configuration, and the adapter
consumes it only after OpenAI selection. CAH-011 may still inspect recognized secret values at
process startup solely to seed transcript redaction; that privacy scan cannot select or construct a
provider. Every other `OPENAI_*` key is rejected before SDK import and client construction,
including `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `OPENAI_CUSTOM_HEADERS`, and
`OPENAI_LOG`.
The client pins `https://api.openai.com/v1`, supplies null organization/project values, disables SDK
retries with `max_retries=0`, and uses an async HTTP client with `trust_env=false` and
`follow_redirects=false`. This keeps hidden routes, proxies, redirects, retries, and debug logging
from changing or exposing one harness turn.

Local model validation first permits `1..256` UTF-8 bytes and then requires exact membership in
`SUPPORTED_OPENAI_TEXT_STREAM_MODELS = {"gpt-4.1-mini-2025-04-14"}`. Local key validation permits
`1..4096` UTF-8 bytes. Both reject every Unicode whitespace, control, surrogate, or other category-C
code point; the key validator assumes no prefix. The fixed model rejection is
`Unsupported OpenAI model. Use gpt-4.1-mini-2025-04-14.` and never echoes the supplied value. A
revoked or unauthorized syntactically valid key, or later inaccessibility/retirement of the
allowlisted snapshot, is known only after the explicit live request and is normalized through the
adapter's failure table.

Conversation roles and contents map one-for-one to Responses `input`. When the ordered
repository-instruction tuple is non-empty, `instructions` is the literal prefix
`Repository instructions in precedence order (JSON):\n` followed immediately by a compact JSON
array of `{"source":...,"content":...}` objects in tuple order. Serialization uses
`ensure_ascii=False`, separators `(",", ":")`, insertion order `source` then `content`, and no
trailing newline. An empty tuple omits `instructions`. The request always omits `tools` and
`tool_choice`: the current `ProviderRequest` has no tool-schema declaration, so this adapter is
text-only.

Resource closure and operation closure are deliberately different states. One operation moves
through `active`, `resources_closing`, `terminal_pending`, and `closed`. The first terminal or
cancellation path creates one cleanup task under the state lock; every joiner shields that task, so
cancelling a joiner cannot cancel the shared cleanup owner or corrupt its repeatable bounded result.
Cleanup attempts stream close and then attempts client close in `finally`, even when stream close
fails. A `response.completed` event first becomes a buffered optional usage record plus completion.
Cleanup is attempted before that queue is exposed, but the operation stays `terminal_pending` after
usage. Cancellation at that point suppresses completion. Otherwise a custom iterator marks the
operation closed atomically as it returns the final provider terminal, so `wait_closed()` cannot
return early and cannot deadlock after CAH-021 receives that terminal. Terminal-queue installation
and cancellation use the same state lock: cancellation during resource closure prevents later queue
installation, while cancellation after installation clears the pending queue before logical closure.

On every ordinary success or non-cancellation `Exception` path, cleanup records one bounded result
after both resource attempts. Stream-close failure, client-close failure, or both produce the same
failure sentinel. If cleanup fails, a pending completion becomes the fixed `unknown` provider
failure; an existing provider failure is preserved.
After the failure is delivered, `wait_closed()` repeatably raises a bounded adapter cleanup exception
that CAH-021 converts to its payload-free runtime diagnostic. Cancellation clears pending
observations, joins cleanup, marks logical closure, and raises the same safe exception if cleanup was
not confirmed. If the caller or CAH-022 cancels only that join, control-flow cancellation propagates
while the shielded cleanup owner continues; a later call rejoins it before returning `already_closed`
or raising the stable cleanup exception. No raw close exception escapes, and logical closure never
claims resource closure. If process teardown directly cancels the internal cleanup owner, that
`CancelledError` remains control flow rather than being converted to a sentinel; ordinary operation
paths never directly cancel that task. A CAH-022 grace expiry may therefore leave the shielded owner
running while cleanup remains unconfirmed.

The event policy is a closed automaton. It captures the first non-negative safe-integer
`sequence_number` as an opaque base and requires every later event to increase it by one. The sole
success trace is:

```text
response.created -> [response.queued] -> response.in_progress
-> output_item.added(message, output_index 0, assistant, empty content)
-> content_part.added(output_text, content_index 0, empty text/annotations)
-> one or more non-empty output_text.delta
-> output_text.done -> content_part.done -> output_item.done -> response.completed
```

Every event keeps the same response, item, part, and index identities. Concatenated deltas must equal
the text in all four completed snapshots: output-text done, content-part done, item done, and response
completed. The response contains exactly one assistant message with exactly one output-text part,
empty annotations, status `completed`, the exact allowlisted snapshot, and null error/incomplete
details.
Optional input/output/total usage values are non-negative safe integers and total equals input plus
output.

`response.failed` or `response.incomplete` may terminate after creation and any valid prefix while
retaining response identity and sequence. A top-level `error` may be first or terminate any valid
prefix. SDK exceptions may occur during create or iteration. Each failure path attempts the shared
resource cleanup, then exposes one normalized provider failure through the same terminal-pending
state.

The semantic mapping is:

| SDK event | Adapter action |
| --- | --- |
| `response.created`, optional `response.queued`, `response.in_progress` | Advance the exact lifecycle prefix; emit nothing |
| `response.output_item.added/done`, `response.content_part.added/done` | Validate the one supported item/part structure; emit nothing for text |
| `response.output_text.delta` | Emit `ProviderTextDelta` |
| `response.output_text.done` | Emit `ProviderTextCompleted` |
| Any function, custom-tool, hosted-tool, or argument event | Reject immediately as `invalid_response`; do not accumulate, parse, or log arguments |
| Any reasoning item or reasoning event | Reject as `invalid_response`; the sole allowlisted snapshot is documented as non-reasoning |
| `response.completed` | Buffer optional `ProviderUsageReported` and `ProviderCompleted`; attempt resource cleanup, then expose the queue without closing early after usage |
| `response.failed`, `response.incomplete`, `error` | Normalize and buffer one `ProviderFailed`; attempt resource cleanup, then expose it |

Duplicate, missing, inconsistent, multi-message, multi-part, multimodal, refusal, audio, image, tool,
annotation, and unknown event paths become `invalid_response`; they are never forwarded raw or
stringified into a diagnostic. CAH-021's `tool_unavailable` behavior remains a provider-neutral fake
case for future tool-capable adapters; CAH-023 never emits a tool request. CAH-022 continues to
enforce every budget. Adding a model that can emit reasoning requires a future automaton expansion;
syntactic model acceptance alone never opts into heterogeneous reasoning output.

Failure normalization is also closed and never copies provider text:

| Source | Provider failure | Retryable | Fixed safe message |
| --- | --- | --- | --- |
| `AuthenticationError` or `APIStatusError.status_code == 401` | `authentication_failed` | No | `OpenAI authentication failed. Check OPENAI_API_KEY.` |
| `RateLimitError` or status 429 | `rate_limited` | Yes | `OpenAI rate limit was reached. Try again later.` |
| `APITimeoutError`, `APIConnectionError`, or status 408/409/500-599 | `unavailable` | Yes | `OpenAI is temporarily unavailable. Try again later.` |
| Other `APIStatusError` status 400-499 or `response.incomplete` | `request_rejected` | No | `OpenAI rejected the request.` |
| `response.failed` with literal code `server_error` | `unavailable` | Yes | `OpenAI is temporarily unavailable. Try again later.` |
| `response.failed` with literal code `rate_limit_exceeded` | `rate_limited` | Yes | `OpenAI rate limit was reached. Try again later.` |
| Premature EOF, SDK response-validation/decode failure, or malformed/unsupported stream | `invalid_response` | No | `OpenAI returned an invalid response.` |
| Other `OpenAIError`, unexpected non-cancellation SDK `Exception`, another/null `response.failed` code, top-level `error`, or resource-close failure replacing completion | `unknown` | No | `OpenAI request failed.` |

Exception checks use the listed subclass-first order. Task cancellation remains control flow.
Premature `StopAsyncIteration`, `APIResponseValidationError`, JSON/Unicode SSE decode failures, and
adapter-local `InvalidSDKObservation` become `invalid_response` before operational OpenAI exceptions
use the table; every remaining `Exception` from SDK create or iteration becomes the fixed `unknown`
failure. The total event mapper returns `invalid_response` rather than throwing for an unsupported
shape. The top-level `error` event always uses `unknown` because its documented code is an
unconstrained string. No exception text, event message, code, parameter, request ID, header, response
body, or raw object is interpolated.

## Practical walkthrough

1. Add a constrained SDK dependency and commit the updated lockfile.
2. Extend `run-tui`, the TUI application configuration, supervisor child arguments, and Python
   startup parsing with the same validated provider/model pair.
3. Fail before session admission when OpenAI is selected but required configuration is absent.
   Validate exact membership in the one-snapshot text-stream allowlist before SDK import.
4. Map ordered conversation and repository instructions into one Responses input without copying
   provider objects back into the request domain.
5. Construct a lazy operation; create its one owned async client and await one foreground stream
   with explicit storage and background flags only when its events are consumed.
6. Validate structural events and translate each supported semantic SDK event into the exact
   provider-neutral observation; reject all tool events at the adapter boundary.
7. Normalize SDK exceptions and error events into bounded `ProviderFailure` values.
8. On natural success or failure, finish the resource-cleanup attempt, enter `terminal_pending`, and
   mark logical closure only as the custom iterator returns the last provider observation. On
   cancellation, suppress pending observations, interrupt create/iteration, and join the same cleanup.
9. Test all mapping and cleanup behavior with SDK fakes; make HTTP impossible in the default suite.
10. Narrow the source-policy guard so the concrete adapter is the sole approved SDK/network import
    location and prove provider-neutral modules remain denied.
11. Register `live_provider`; require `--run-live-provider`,
    `--live-provider-model gpt-4.1-mini-2025-04-14`, and `OPENAI_API_KEY`. Marker selection without
    opt-in skips, while explicit opt-in with missing, locally malformed, or non-allowlisted
    configuration fails before network access. Normalize remote authentication, access, or snapshot
    retirement after the selected request. Prove the canonical gate and default CI use
    `-m "not live_provider"` with provider configuration unset and sockets denied.

## Implementation code samples

No CAH-023 implementation exists yet. Planned boundary pseudocode:

```text
configuration = validate_provider_and_model(arguments, environment_presence)
operation = OpenAIResponsesOperation(
    configuration=configuration,
    request=map_request(provider_request),
)

# Lazily from events(), never Provider.start():
async next_owned_sdk_event():
    if client is not created:
        client = AsyncOpenAI(
            api_key=selected_secret,
            base_url="https://api.openai.com/v1",
            organization=None,
            project=None,
            max_retries=0,
            http_client=DefaultAsyncHttpxClient(trust_env=False, follow_redirects=False),
        )
    if sdk_stream is not created:
        sdk_stream = await run_as_owned_create_task(client.responses.create(
            model=configuration.model,
            stream=true,
            background=false,
            store=false,
            input=map_messages_one_for_one(request.messages),
            instructions=encode_instructions_exactly_or_omit(request.instructions),
            # tools and tool_choice are omitted
        ))
    return await run_as_owned_next_task(anext(sdk_stream))

async resource_cleanup_owner(excluded_owned_task):
    cleanup_failed = false
    try:
        await cancel_and_reap_other_owned_work(excluding=excluded_owned_task)
    except any_non_cancellation_exception:
        cleanup_failed = true
    try:
        await close_sdk_stream_if_created()
    except any_non_cancellation_exception:
        cleanup_failed = true
    finally:
        try:
            await close_sdk_client_if_created()
        except any_non_cancellation_exception:
            cleanup_failed = true
    return record_one_bounded_cleanup_result(cleanup_failed)

async join_resources_once(excluded_owned_task=None):
    cleanup_task = atomically_create_once_or_get(resource_cleanup_owner, excluded_owned_task)
    return await shield(cleanup_task)  # cancelling this join never cancels cleanup_task

async prepare_terminal(mapped_terminal_queue):
    cleanup_failed = await join_resources_once(excluded_owned_task=current_owned_next_task)
    if cleanup_failed and queue_would_complete_successfully:
        mapped_terminal_queue = (fixed_unknown_provider_failure(),)
    atomically_install_queue_only_if_cancellation_has_not_won(mapped_terminal_queue)

async next_provider_observation():
    while true:
        if terminal_queue_is_pending:
            # No await between changing to closed and returning the final event.
            return pop_pending_and_atomically_close_on_final()
        try:
            sdk_event = await next_owned_sdk_event()  # includes lazy responses.create
        except task_cancellation:
            raise                                  # cancellation is control flow
        except premature_eof_or_sdk_validation_or_decode_exception:
            mapped = (fixed_invalid_response_provider_failure(),)
        except recognized_openai_exception as error:
            mapped = (map_closed_failure_table_without_raw_values(error),)
        except unexpected_non_cancellation_exception:
            mapped = (fixed_unknown_provider_failure(),)
        else:
            mapped = validate_and_map_total_automaton(sdk_event)  # malformed -> invalid_response
        if mapped is empty:                         # structural SDK event; nothing crosses the port
            continue
        if mapped contains a provider terminal:
            await prepare_terminal(mapped)
            if cancellation_has_won:
                raise StopAsyncIteration
            return pop_pending_and_atomically_close_on_final()
        return the_one_mapped_nonterminal_observation

async cancel():
    atomically_select_cancellation_and_clear_pending_queue()
    try:
        await cancel_and_reap_owned_create_or_next_task_without_leaking_its_exception()
        cleanup_failed = await join_resources_once()
    except caller_task_cancellation:
        ensure_shared_cleanup_was_started()
        mark_logically_closed()
        raise                              # control flow; shared cleanup still owns release
    mark_logically_closed()
    if cleanup_failed:
        raise bounded_adapter_cleanup_error()
```

After implementation, replace this pseudocode with exact adapter request-mapping and cancellation
excerpts plus an SDK-fake failure test. Explain where SDK values stop and harness values begin.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Provider selected without key | Startup cannot construct client | Actionable bounded config error; no value echoed |
| Unknown SDK event | Mapper has no supported variant | One `invalid_response` failure, no raw object |
| Ambient endpoint or SDK logging is configured | Startup sees an unapproved implicit setting | Bounded config failure before SDK client construction |
| Error after partial text | Prefix already crossed the port | Normalized failure; no successful completion invented |
| User cancels pending create or stream | Async provider work is active | Owned task interrupted, connection termination requested, cleanup joined or reported unconfirmed |
| User cancels after usage | Completion is still terminal-pending | Pending completion suppressed; cleanup joined; no later event |
| Stream/client close raises | Resource release cannot be confirmed | Completion becomes fixed `unknown` failure (or prior failure is preserved); `wait_closed()` raises only the bounded cleanup exception |
| Tool event arrives | Request contains no declared tool schema | Immediate `invalid_response`; no arguments retained, parsed, or logged |
| Reasoning event arrives | Allowlisted non-reasoning snapshot violates its contract | Immediate `invalid_response`; no reasoning retained |
| Transcript disabled | Provider call still runs | No local files; request still explicitly uses `store=false` |
| Live marker omitted or opt-in absent | Default suite or marker-only selection runs | No HTTP or cost; marker-only selection skips |
| Explicit live opt-in lacks an allowlisted model or locally valid key | Smoke was deliberately requested | Fail before network access |
| Valid key lacks access or allowlisted snapshot is retired | One live request was explicitly selected | Normalize bounded authentication/request failure after network access |
| SDK import escapes adapter | Core source depends on vendor/network code | Repository policy fails before tests run |

## Production expansion

### Example enterprise scenario

A production organization may route traffic across projects and regions, rotate credentials,
enforce per-tenant data policies, monitor quotas and cost, and run controlled canaries during SDK or
model upgrades. Those controls surround the same adapter boundary and do not transfer session
authority to the SDK.

### Typical production capabilities and tools

These official references describe capabilities, not repository dependencies beyond the selected
OpenAI adapter:

- [OpenAI streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses)
  documents typed semantic events over SSE.
- [OpenAI Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
  distinguishes the `store=false` request control from broader endpoint and organization policy.
- [OpenAI background mode](https://developers.openai.com/api/docs/guides/background#limits)
  distinguishes foreground connection termination from background cancellation.
- [OpenAI Python SDK](https://github.com/openai/openai-python) documents async streaming, client
  configuration, retries, and resource cleanup.
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
  illustrate provider-operation telemetry with additional privacy and operations work.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Provider | One explicitly selected OpenAI adapter | Multiple projects, regions, versions, and routes |
| Streaming | One foreground SSE connection | Proxies, reconnect policy, canaries, and SLOs |
| Credentials | Environment-only local secret | Managed identity, rotation, audit, and least privilege |
| Data controls | Explicit `store=false` plus local opt-out | Tenant policy, residency, ZDR eligibility, and review |
| Testing | SDK fakes plus one opt-in smoke | Conformance, canary, load, and fault-injection suites |

### Trade-offs and graduation signals

A foreground stream is simple and has prompt cancellation, but it cannot resume after connection
loss. Background mode improves long-running reliability while adding provider-side state and polling
complexity. Adopt it only when measured request duration and disconnect rates justify the different
retention, cancellation, and recovery contract. Add multi-provider routing only when availability,
cost, or organizational requirements outweigh its operational burden.

## Practical exercises

1. Draw the exact line where an SDK delta becomes `ProviderTextDelta`.
2. Design an unknown-event fake containing a secret-looking value and prove the failure excludes it.
3. Explain why the background cancel endpoint is wrong for an asynchronously consumed foreground
   stream.
4. Compare `--no-transcript` with `store=false` and list what each does not control.
5. Write the test-selection assertions that prove marker-only selection skips, invalid explicit
   opt-in fails before network access, and the default gate excludes the marker.

## Key takeaways

- The text-only adapter owns SDK translation and connection-cleanup attempts; the harness owns limits
  and session truth.
- Foreground cancellation requests connection termination and reports unconfirmed cleanup safely;
  provider storage and local transcripts are separate controls.
- Deterministic SDK fakes are completion evidence; a live smoke is optional supplemental evidence.

## Glossary

- **Adapter:** component translating an external interface into a harness-owned port.
- **Composition root:** startup location that chooses and wires concrete implementations.
- **Foreground response:** operation coupled to an active connection rather than resumable
  background state.
- **SSE:** server-sent events delivered incrementally over an HTTP response.
- **Statefulness:** provider-side storage that can link or retrieve response state.

See the shared [project glossary](../glossary.md) for provider, model turn, usage, and transcript.

## Further reading

- [CAH-023 user story](../../user-stories/cah-023-add-openai-responses-adapter.md)
- Prerequisites: [CAH-021 provider-neutral turn](cah-021-one-model-turn.md) and
  [CAH-022 loop limits](cah-022-loop-limits.md)
- Local design: [ADR 0001](../adr/0001-own-the-agent-loop.md),
  [agent loop](../agent-loop.md), [safety model](../safety-model.md), and
  [protocol](../protocol.md)
- [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
- [Background mode limits](https://developers.openai.com/api/docs/guides/background#limits)
- [Official OpenAI Python SDK](https://github.com/openai/openai-python)
- [GPT-4.1 mini model](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
- [OpenTelemetry generative AI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
