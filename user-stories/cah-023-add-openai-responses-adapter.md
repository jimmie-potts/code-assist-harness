# CAH-023 - Add the OpenAI Responses adapter

- **Status:** Planned
- **Milestone / epic:** M1 - Conversational core / E2 - Provider interface and explicit agent loop
- **Dependencies:** CAH-022
- **Lesson:** [OpenAI Responses adapter](../docs/lessons/cah-023-openai-responses-adapter.md)

## User story

> As an explicitly configured user, I want the bounded provider-neutral turn to use OpenAI Responses
> so that the first real model capability is available without leaking SDK types into the harness.

## Scope

- Add one OpenAI Python SDK adapter behind CAH-020's `Provider` and `ProviderOperation` protocols.
- Target foreground Responses API streaming over server-sent events; background and resumable modes
  remain excluded.
- Map harness-owned conversation and repository instructions into one text-only Responses request and
  normalize text, completed text, usage, completion, and failure at the adapter boundary.
- Add explicit provider and model selection across the normal `run-tui` launch path and Python
  composition root, plus safe `OPENAI_API_KEY` startup handling.
- Update the production-source network policy so only the concrete adapter may import the approved
  SDK/network surface; provider-neutral core modules remain mechanically isolated.
- Activate the CAH-021 turn only after CAH-022's hard limits are configured.
- Keep deterministic SDK-fake tests in the default gate and provide one separately selected,
  credential-gated live smoke test.

## Locked adapter contract

- Every foreground request sets `stream=true`, `background=false`, and `store=false` explicitly.
- Ordered conversation messages map one-for-one to Responses `input` roles and contents. When the
  repository-instruction tuple is non-empty, the Responses `instructions` value is the literal
  prefix `Repository instructions in precedence order (JSON):\n` followed immediately by a JSON
  array of `{"source":...,"content":...}` objects in tuple order. Serialization uses
  `ensure_ascii=False`, separators `(",", ":")`, insertion order `source` then `content`, and no
  trailing newline; an empty tuple omits the field.
- The request sends no `tools` and no `tool_choice`. CAH-023 is text-only because the current
  `ProviderRequest` cannot declare a tool schema; a future tool story must extend that port before an
  OpenAI function call can become a valid provider-neutral observation.
- The launcher defaults to the existing mock, and `--provider` accepts only `mock` or `openai`.
  OpenAI requires the explicit pair `--provider openai --model MODEL`; `--model` is rejected for the
  mock, and OpenAI is rejected when the model is absent. CAH-023's repository-owned exact-snapshot
  allowlist is `SUPPORTED_OPENAI_TEXT_STREAM_MODELS = {"gpt-4.1-mini-2025-04-14"}`. Aliases,
  prefixes, fine-tunes, reasoning families, and every other model value are rejected locally. The
  repository does not silently track a changing provider default or alias.
- `run-tui` parses and validates those options, its application configuration passes them to
  `PythonRuntimeSupervisor`, and the supervisor forwards them as separate shell-free Python child
  arguments. They are configuration, not NDJSON protocol fields. The Python parser independently
  validates the same pair before composing a provider; a direct Python launch follows the same
  rules. Before exact allowlist membership, model IDs encode to `1..256` UTF-8 bytes and contain no
  Unicode whitespace, control, surrogate, or other category-C code point. TypeScript and Python use
  the same constant and a parity test, while Python remains authoritative before SDK import or
  network access. The fixed rejection is
  `Unsupported OpenAI model. Use gpt-4.1-mini-2025-04-14.` and never echoes the supplied value.
- Missing or locally invalid provider configuration fails safely before a session starts and never
  prints a credential or environment value.
- `OPENAI_API_KEY` is the only accepted `OPENAI_*` provider configuration and the adapter consumes it
  only after OpenAI is explicitly selected. CAH-011 may still inspect recognized secret values at
  process startup solely to seed transcript redaction; that privacy scan cannot select or construct
  a provider. OpenAI selection fails generically, before SDK import/client construction, when any
  other `OPENAI_*` key is present, including `OPENAI_BASE_URL`, `OPENAI_ORG_ID`,
  `OPENAI_PROJECT_ID`, `OPENAI_CUSTOM_HEADERS`, or `OPENAI_LOG`. The async HTTP client is the
  SDK-exported `DefaultAsyncHttpxClient` configured with
  `trust_env=false` and `follow_redirects=false`; the official `https://api.openai.com/v1` endpoint
  is explicit, organization and project are explicit nulls, and SDK retries are disabled with
  `max_retries=0`. Proxy variables, redirects, SDK routing defaults, and hidden HTTP retries cannot
  alter one harness model turn.
- Local API-key validation requires `1..4096` UTF-8 bytes and rejects every Unicode whitespace,
  control, surrogate, or other category-C code point; it makes no prefix assumption. A missing or
  locally malformed key, and a missing, malformed, or non-allowlisted model, fail before network
  access. A syntactically valid but revoked or unauthorized key, or later inaccessibility/retirement
  of the one allowlisted snapshot, can be decided only by the API and is normalized after the one
  explicitly opted-in request.
- SDK objects, raw exceptions, response bodies, headers, request objects, and credentials never enter
  provider-neutral, session, protocol, diagnostic, shared-fixture, or transcript types. Adapter-local
  SDK fakes may construct SDK-shaped values only inside adapter tests.
- `Provider.start()` remains synchronous, lazy, and free of I/O. The operation awaits
  `async_client.responses.create(..., stream=True)` only when `events()` is consumed and owns that
  pending-create task plus every later next-event await.
- Each operation lazily owns one async SDK client and stream. It has distinct `active`,
  `resources_closing`, `terminal_pending`, and `closed` states. Under the state lock, the first
  natural-terminal or cancellation path creates exactly one resource-cleanup task and captures any
  initiating owned create/next-event task that must not cancel itself. The cleanup task cancels and
  reaps other pending owned work, attempts stream close, and attempts client close in a `finally`
  stage even when stream close fails. Stream, client, or both close failures collapse into one
  bounded success/failure sentinel; raw close exceptions never escape.
- Every terminal, `cancel()`, and `wait_closed()` join shields that shared cleanup task. Cancelling a
  joiner propagates cancellation control flow without cancelling the cleanup owner; a later joiner
  observes the same eventual sentinel on every ordinary success or `Exception` path. Direct
  event-loop teardown may cancel the internal owner and remains cancellation control flow, not a
  fabricated sentinel. CAH-022 may therefore cancel and reap its local join awaitable when the
  five-second grace expires while the shielded owner may continue and resource release remains
  explicitly unconfirmed. A later sequential session receives fresh resources, so closing one
  operation does not make the `Provider` unusable.
- A mapped SDK terminal is buffered until the resource cleanup attempt finishes. On cleanup success,
  the pending provider sequence is either `ProviderFailed`, `ProviderCompleted`, or optional
  `ProviderUsageReported` followed by `ProviderCompleted`. The operation remains `terminal_pending`
  after usage. Cancellation in that state suppresses every remaining observation; otherwise the
  custom iterator changes to `closed` atomically, without an intervening await, as it returns the
  final `ProviderCompleted` or `ProviderFailed`. `wait_closed()` therefore cannot return between
  usage and a later terminal, yet is immediately repeatable once CAH-021 receives the terminal.
- Terminal-queue installation and cancellation selection share the operation state lock. If
  cancellation wins while resources are closing, no queue is installed; if terminal installation
  wins, cancellation may still clear the `terminal_pending` queue before its final observation. No
  state path can install a terminal after cancellation has logically closed the operation.
- If stream/client cleanup fails, a buffered completion is replaced by the fixed, non-retryable
  `unknown` provider failure; an already-buffered provider failure is preserved. After that final
  failure is delivered, repeatable `wait_closed()` raises one bounded adapter cleanup exception so
  CAH-021 emits `provider_cleanup_failed` without changing the selected session failure. Cancellation
  suppresses pending observations, marks the operation logically closed, and raises that same safe
  cleanup exception after joining the cleanup task. Once logically closed, `cancel()` first rejoins
  an unfinished shared cleanup task, then returns `already_closed` after successful resource cleanup
  or repeatably raises the same safe exception after failed cleanup. This records that no later event
  exists without pretending provider resources were released.
- SDK sequence validation captures the first event's non-negative IEEE-754-safe integer as the base
  and requires every later event to increment it by exactly one. A successful response accepts only
  this exact trace:

  1. `response.created`, then optionally one `response.queued`, then exactly one
     `response.in_progress`, all with one response identity;
  2. `response.output_item.added` at `output_index=0` for one `message` item with a stable item ID,
     role `assistant`, and empty content;
  3. `response.content_part.added` for that item at `content_index=0`, containing empty
     `output_text` and no annotations;
  4. one or more non-empty `response.output_text.delta` events with those exact IDs and indices;
  5. exactly one `response.output_text.done`, `response.content_part.done`, and
     `response.output_item.done`, in that order; and
  6. exactly one `response.completed` for the same response.
- The concatenated text deltas must equal the text in `output_text.done`, the completed content part,
  the sole content of the completed message item, and the sole output item in `response.completed`.
  Every snapshot retains item/part identity, index, assistant role, `output_text` type, and empty
  annotations. The completed response has status `completed`, the exact allowlisted snapshot as its
  model, null error and incomplete details, and optional non-negative safe-integer input/output
  usage. Any present total usage equals their sum.
- `response.failed` or `response.incomplete` may replace the remaining success suffix after
  `response.created` and any valid subsequent prefix, but must retain response identity and sequence.
  A top-level `error` may be the first event or may terminate any valid prefix; its sequence becomes
  or continues the same captured base. An SDK exception during create or iteration may likewise
  terminate any prefix through the closed failure table.
- Semantic mapping is exact:
  - `response.output_text.delta` becomes `ProviderTextDelta`;
  - `response.output_text.done` becomes `ProviderTextCompleted`;
  - `response.completed` emits optional `ProviderUsageReported` before `ProviderCompleted`; and
  - `response.failed`, `response.incomplete`, and `error` become one normalized `ProviderFailed`.
- Any function/custom-tool/hosted-tool item or argument event is rejected immediately as
  `invalid_response`; the adapter neither accumulates nor logs its arguments. CAH-021's
  `tool_unavailable` behavior remains covered through the provider-neutral fake, not this text-only
  adapter.
- Duplicate, missing, inconsistent, multi-message, multi-part, reasoning, multimodal, refusal, audio,
  image, tool, annotation, unknown, or otherwise unsupported events become a bounded
  `invalid_response` provider failure. Reasoning is a defensive contract violation because the sole
  allowlisted snapshot is documented as operating without a reasoning step; a future model requires
  an automaton expansion before allowlisting. Raw SDK values are never converted with `str()` or
  `repr()` for diagnostics.
- Failure normalization uses a closed table and fixed safe messages. SDK exceptions are checked in
  subclass-first order. Task cancellation remains control flow. Premature `StopAsyncIteration`,
  `APIResponseValidationError`, JSON/Unicode decode failure while consuming SSE, and adapter-local
  `InvalidSDKObservation` become `invalid_response`. Then `AuthenticationError` or status 401 becomes
  `authentication_failed`; `RateLimitError` or status 429 becomes `rate_limited`;
  `APITimeoutError`, `APIConnectionError`, or `APIStatusError` with status 408, 409, or 500-599 becomes
  `unavailable`; another `APIStatusError` with status 400-499 becomes `request_rejected`; any other
  `OpenAIError` becomes `unknown`; and any remaining non-cancellation `Exception` raised by SDK create
  or iteration also becomes `unknown`. `response.failed` code `server_error` becomes `unavailable`, code
  `rate_limit_exceeded` becomes `rate_limited`, and every other code (including null) becomes
  `unknown`; `response.incomplete` becomes `request_rejected`; and the top-level `error` event
  becomes `unknown` because its documented code is an unconstrained string. Malformed or unsupported
  streams become `invalid_response`.
  `rate_limited` and `unavailable` are retryable; all other rows are not.
- The corresponding safe messages are literal and exhaustive:
  - `authentication_failed`: `OpenAI authentication failed. Check OPENAI_API_KEY.`;
  - `rate_limited`: `OpenAI rate limit was reached. Try again later.`;
  - `unavailable`: `OpenAI is temporarily unavailable. Try again later.`;
  - `request_rejected`: `OpenAI rejected the request.`;
  - `invalid_response`: `OpenAI returned an invalid response.`; and
  - `unknown`: `OpenAI request failed.`
- Messages are fixed per row and never interpolate exception text, event messages, codes,
  parameters, request IDs, or headers.
- The adapter uses the SDK's asynchronous client so streaming never blocks the harness event loop.
  Cancellation covers a pending create call and a blocked next-event await, requests foreground
  connection termination, attempts SDK stream/client closure, and awaits its owned task. A failed
  close follows the bounded unconfirmed-cleanup path above. The background Responses cancel endpoint
  is not used.
- `--no-transcript` controls only local harness files. Explicit `store=false` controls Responses
  statefulness and application-state storage for this request, subject to the provider account's
  broader data controls; neither setting is described as universal deletion, an abuse-monitoring
  control, or Zero Data Retention.
- The live test is registered as `live_provider` and runs only with `--run-live-provider` plus
  `--live-provider-model gpt-4.1-mini-2025-04-14` and `OPENAI_API_KEY`; ambient credential presence
  alone never selects it. Marker selection without the opt-in flag skips, while explicit opt-in with
  a missing or malformed key, or a missing, malformed, or non-allowlisted model, fails before network
  access. Remote authentication, access, or snapshot-retirement rejection is one bounded failed smoke
  result after the deliberate request. `./scripts/check` and default CI use
  `-m "not live_provider"`, unset provider credentials/configuration for the test process, and retain
  the existing socket guard.

## Acceptance criteria

1. The OpenAI SDK dependency is version-constrained in `pyproject.toml` and resolved in `uv.lock`.
2. The adapter structurally implements the existing provider port without changing loop or session
   domain types.
3. Request mapping preserves ordered conversation and repository instructions, selects the exact
   allowlisted snapshot, enables foreground streaming, disables background mode, and sets
   `store=false`.
4. Supported SDK stream events match the locked success/failure automaton, snapshot reconciliation,
   and exact provider-neutral ordering required by CAH-021. Structural lifecycle/item/part events
   advance only adapter state and never produce `None` or another placeholder across the port.
5. The request omits tools, and every SDK tool/function-call event fails safely without accumulating,
   parsing, logging, or executing arguments.
6. SDK errors and unknown, missing, duplicate, or malformed stream observations normalize into safe
   provider failures without raw values.
7. `ProviderOperation.cancel()` interrupts pending async creation or iteration, joins the one
   idempotent resource-cleanup task, suppresses pending terminal observations, and guarantees no later
   event; a cleanup error raises only the bounded adapter exception handled by CAH-021.
8. The TypeScript launcher and supervisor plus the Python parser and composition root implement the
   explicit provider/model path as child arguments, and OpenAI work cannot begin until CAH-022 limits
   are valid.
9. Missing credentials or unsupported configuration produces actionable bounded diagnostics that may
   name a fixed safe option or environment label but never echo its value or dump the environment.
   The launcher/Python allowlist parity test accepts only `gpt-4.1-mini-2025-04-14` and rejects its
   alias plus unknown, reasoning, and fine-tuned model IDs before SDK import or network access.
10. Local transcript enablement does not alter `store=false`, and transcript redaction/opt-out behavior
    remains unchanged.
11. SDK-fake tests cover request/model mapping, every transition and reconciliation check in the
    automaton, usage, rejected reasoning/tool events, every failure-table row, premature EOF,
    response-validation and JSON/Unicode decode failures, unexpected SDK exceptions, unknown events,
    cancellation before and between output, cancellation after usage, and terminal races without
    HTTP. Resource tests separately cover stream-close failure,
    client-close failure, both failures, and CAH-022 grace cancellation while create, stream close,
    or client close is pending. They distinguish resource closure from operation closure, prove both
    resource closes are attempted, prove cancelling a joiner does not cancel shared cleanup, and
    prove `wait_closed()` cannot finish while a terminal remains pending.
12. The opt-in `live_provider` smoke test performs one minimal bounded response, requires the named
    run option, exact allowlisted snapshot, and locally valid credentials, normalizes remote rejection
    after the request, and is excluded from `./scripts/check` and default CI even when a credential
    happens to be present.
13. The default repository gate deselects `live_provider`, unsets provider configuration, and passes
    with network access denied.
14. Repository policy permits the SDK/network dependency only inside the concrete adapter and rejects
    it from provider-neutral loop, session, protocol, persistence, and tool modules.
15. Client-construction tests prove the official endpoint, `trust_env=false`,
    `follow_redirects=false`, explicit null account routing, and `max_retries=0`; recognized ambient
    routing, header, log, and proxy values cannot redirect or duplicate the request.

## Validation

- Run adapter contract tests against SDK fakes/mocks, never HTTP.
- Assert a complete structural success trace emits only the locked provider-neutral observations;
  lifecycle/item/part events never cross the provider port.
- Run provider-neutral CAH-021 and limit CAH-022 suites unchanged against the adapter-facing port.
- Exercise the runtime composition root with sanitized fake SDK behavior and assert no secret reaches
  stdout, stderr, protocol events, fixtures, snapshots, or transcripts.
- Use distinct sentinels for the API key, model/task/instruction text, function arguments, raw
  headers/request IDs, and exception bodies. Failure diagnostics and public evidence must contain
  none of them; intentionally mapped assistant text remains subject to the existing transcript
  sanitizer rather than this negative-diagnostic assertion.
- Exercise `run-tui` parsing, supervisor argument forwarding, direct Python parsing, client
  construction, pending-create cancellation, blocked-next-event cancellation, terminal-pending
  cancellation, each SDK stream/client close-failure combination, and cleanup-grace cancellation at
  every pending resource stage.
- Run a negative source-policy probe that places an SDK/network import in a provider-neutral module
  and proves the canonical gate rejects it.
- Prove the registered marker plus explicit opt-in are both required, and that the default gate
  deselects the marker even when the parent shell contains a fake credential.
- Optionally run the separately documented live smoke command; it is supplemental evidence, not a
  completion requirement.

## Documentation impact

Document provider/model selection, credential setup, request and event mapping, foreground
cancellation, storage and transcript boundaries, SDK-fake testing, and the opt-in live command.
Update the agent-loop, architecture, safety, evaluation, README, glossary, and provider lesson. Add
the required written and visual CAH-023 learning evidence when implemented.

## Out of scope

- Background or resumable Responses, conversation objects, `previous_response_id`, provider-hosted
  tools, built-in tools, application retries, backoff, routing, failover, or multiple providers.
- Additional model snapshots or aliases, reasoning-output compatibility, tool execution, workspace
  context discovery, multiple model turns, or LangChain. A future model is added only with an
  explicit compatibility review and matching automaton/fake/live-smoke evidence.
- Production telemetry pipelines, quota services, cost governance, or organization-wide retention
  configuration.

## Current official references

- [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
- [Responses data controls](https://developers.openai.com/api/docs/guides/your-data#v1responses)
- [Background mode and cancellation limits](https://developers.openai.com/api/docs/guides/background#limits)
- [Official OpenAI Python SDK](https://github.com/openai/openai-python)
- [GPT-4.1 mini model](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
