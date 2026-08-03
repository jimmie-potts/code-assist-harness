# CAH-023 - Add the OpenAI Responses adapter

- **Status:** Done
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

- Every foreground request sets `stream=true`, `background=false`, and `store=false` explicitly. It
  also sets `reasoning={"effort":"none","context":"current_turn"}` so Luna does not inherit its
  broader reasoning defaults, and `max_output_tokens=8192` bounds visible plus hidden generated
  tokens at the provider boundary.
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
  mock, and OpenAI is rejected when the model is absent. CAH-023's repository-owned exact-model
  allowlist is `SUPPORTED_OPENAI_TEXT_STREAM_MODELS = {"gpt-5.6-luna"}`. Aliases, prefixes,
  fine-tunes, and every other model value are rejected locally. The
  repository does not silently track a changing provider default or alias.
- `run-tui` parses and validates those options, its application configuration passes them to
  `PythonRuntimeSupervisor`, and the supervisor forwards them as separate shell-free Python child
  arguments. They are configuration, not NDJSON protocol fields. The Python parser independently
  validates the same pair before composing a provider; a direct Python launch follows the same
  rules. Before exact allowlist membership, model IDs encode to `1..256` UTF-8 bytes and contain no
  Unicode whitespace, control, surrogate, or other category-C code point. TypeScript and Python use
  the same constant and a parity test, while Python remains authoritative before SDK import or
  network access. The fixed rejection is
  `Unsupported OpenAI model. Use gpt-5.6-luna.` and never echoes the supplied value.
- Missing or locally invalid provider configuration fails safely before a session starts and never
  prints a credential or environment value.
- `OPENAI_API_KEY` is the only accepted `OPENAI_*` provider configuration and the adapter consumes it
  only after OpenAI is explicitly selected. CAH-011 may still inspect recognized secret values at
  process startup solely to seed transcript redaction; that privacy scan cannot select or construct
  a provider. OpenAI selection fails generically, before SDK import/client construction, when any
  other `OPENAI_*` key is present, including `OPENAI_BASE_URL`, `OPENAI_ORG_ID`,
  `OPENAI_PROJECT_ID`, `OPENAI_CUSTOM_HEADERS`, or `OPENAI_LOG`, or when `SSLKEYLOGFILE` could export
  TLS session secrets. The normal supervisor removes that selector and launches Python with `-E`;
  provider validation repeats the fixed rejection for direct and lazy construction. The SDK-exported
  `DefaultAsyncHttpxClient` is configured with
  `trust_env=false` and `follow_redirects=false`; the official `https://api.openai.com/v1` endpoint
  is explicit, the constructor receives null organization and project only after ambient values are
  rejected again at lazy construction, and SDK retries are disabled with `max_retries=0`. Proxy
  variables, redirects, SDK routing defaults, and hidden HTTP retries cannot alter one harness model
  turn.
- Local API-key validation requires `1..4096` UTF-8 bytes and rejects every Unicode whitespace,
  control, surrogate, or other category-C code point; it makes no prefix assumption. A missing or
  locally malformed key, and a missing, malformed, or non-allowlisted model, fail before network
  access. A syntactically valid but revoked or unauthorized key, or later inaccessibility of the one
  allowlisted model, can be decided only by the API and is normalized after the one
  explicitly opted-in request.
- The optional local `dev.env` workflow is an explicit wrapper rather than ambient runtime loading.
  Repository-root `dev.env` is ignored by the `/dev.env` pattern, must be a readable regular
  non-symlink file with mode `0600`, and contains
  exactly one non-empty `OPENAI_API_KEY=...` assignment plus optional blank lines/comments. The
  wrapper rejects every ambient `OPENAI_*` setting, `SSLKEYLOGFILE`, and every other assignment, never
  sources/evaluates the file, runs through absolute `/usr/bin/python3 -I` so ambient Python import
  settings cannot alter credential admission, and uses `exec` to preserve the selected command. Its
  separate `--init` mode
  creates the root file exclusively with no-follow semantics and mode `0600` before a hidden prompt,
  refuses to replace an existing path, never accepts the key through argv, and removes its created
  file when entry, validation, or persistence fails. Provider/model remain CLI arguments, and the
  runtime retains `uv --no-env-file`.
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
  stage even when stream close fails. Stream, client, or both close failures—including a close
  coroutine that independently raises `CancelledError`—collapse into one bounded success/failure
  sentinel; raw close exceptions never escape. Cancellation of the cleanup owner itself is detected
  separately and remains cancellation control flow.
- Every terminal, `cancel()`, and `wait_closed()` join shields that shared cleanup task. Cancelling a
  joiner propagates cancellation control flow without cancelling the cleanup owner; a later joiner
  observes the same eventual sentinel on every ordinary success or `Exception` path. Direct
  event-loop teardown may cancel the internal owner and remains cancellation control flow, not a
  fabricated sentinel. When CAH-022's five-second grace expires, it first cancels and reaps that local
  join awaitable, then invokes required `force_cancel_cleanup()`. This session-only authoritative path
  bypasses the shield, marks cleanup unconfirmed, cancels and awaits the actual cleanup owner plus any
  other operation-owned task, closes the stream logically, and makes later ordinary joins fail with
  the bounded adapter cleanup error. No provider-owned local task may remain, although remote resource
  release remains explicitly unconfirmed. Genuine owner cancellation stops remaining sequential
  closes; an independently raised close-time `CancelledError` still records failure and attempts the
  other close. A later sequential session receives fresh resources, so closing one operation does not
  make the `Provider` unusable.
- An SDK create or stream-read awaitable that independently raises `CancelledError` is not treated as
  selected harness cancellation. It enters the closed failure table as one bounded provider failure,
  starts resource cleanup, and cannot leave `wait_closed()` pending. Only cancellation selected by the
  operation or its event consumer may end the stream without a provider terminal.
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
  2. optionally one opaque `reasoning` item at `output_index=0`, represented only by consecutive
     `response.output_item.added` and `response.output_item.done` events with one stable ID, empty
     summary, absent or empty content, and valid progress/completed status;
  3. `response.output_item.added` for one `message` item at `output_index=0` without the reasoning
     envelope or `output_index=1` after it, with a stable item ID, role `assistant`, exact status
     `in_progress`, and empty content;
  4. `response.content_part.added` for that item at `content_index=0`, containing empty
     `output_text` and no annotations;
  5. one or more non-empty `response.output_text.delta` events with those exact IDs and indices;
  6. exactly one `response.output_text.done`, `response.content_part.done`, and
     `response.output_item.done` with exact message status `completed`, in that order; and
  7. exactly one `response.completed` for the same response.
- The concatenated text deltas must equal the text in `output_text.done`, the completed content part,
  the sole content of the completed message item, and that message in `response.completed`.
  Every snapshot retains item/part identity, index, assistant role, `output_text` type, and empty
  annotations. If the optional reasoning item is present, the completed output reconciles it before
  the message without copying, parsing, persisting, or exposing `encrypted_content`. The completed
  response has status `completed`, the exact allowlisted model, null error and incomplete details,
  exact echoed reasoning effort `none` and context `current_turn`, and optional non-negative
  safe-integer input/output usage. Any present total usage equals their sum; any present
  reasoning-token detail is already included in output tokens and cannot exceed it. Reported output
  tokens also cannot exceed the same fixed `8192` cap sent as `max_output_tokens`; an over-cap report
  is `invalid_response` and produces no usage or completion observation.
- Provider text admits TAB and LF as explicit layout characters but rejects every other C0/C1
  terminal control before constructing `ProviderTextDelta` or `ProviderTextCompleted`. An unsafe
  fragment is not retained or published and becomes the same fixed `invalid_response` failure as
  other malformed SDK observations. Python and TypeScript protocol validators mirror this invariant
  before assistant text can enter trusted terminal state.
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
- Duplicate, missing, inconsistent, multi-message, multi-part, multimodal, refusal, audio, image,
  tool, annotation, unknown, or otherwise unsupported events become a bounded `invalid_response`
  provider failure. The sole admitted reasoning shape is the optional opaque empty item envelope
  before the message. A second or late reasoning item, non-empty summary/content, reasoning text or
  summary stream event, inconsistent identity/status/index, or a non-`none` effective reasoning mode
  fails closed. Raw SDK values are never converted with `str()` or `repr()` for diagnostics.
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
  `--live-provider-model gpt-5.6-luna` and `OPENAI_API_KEY`; ambient credential presence
  alone never selects it. Marker selection without the opt-in flag skips, while explicit opt-in with
  a missing or malformed key, or a missing, malformed, or non-allowlisted model, fails before network
  access. Remote authentication or model-access rejection is one bounded failed smoke
  result after the deliberate request. `./scripts/check` and default CI use
  `-m "not live_provider"`, unset provider credentials/configuration for the test process, and retain
  the existing socket guard.

## Acceptance criteria

1. The OpenAI SDK dependency is version-constrained in `pyproject.toml` and resolved in `uv.lock`.
2. The adapter structurally implements the existing provider port without changing loop or session
   domain types.
3. Request mapping preserves ordered conversation and repository instructions, selects the exact
   allowlisted model, enables foreground streaming, disables background mode, sets `store=false`,
   disables reasoning effort with current-turn context, and caps generated tokens.
4. Supported SDK stream events match the locked success/failure automaton, snapshot reconciliation,
   and exact provider-neutral ordering required by CAH-021. Structural lifecycle/item/part events
   advance only adapter state and never produce `None` or another placeholder across the port.
5. The request omits tools, and every SDK tool/function-call event fails safely without accumulating,
   parsing, logging, or executing arguments.
6. SDK errors and unknown, missing, duplicate, or malformed stream observations normalize into safe
   provider failures without raw values.
7. `ProviderOperation.cancel()` interrupts pending async creation or iteration, joins the one
   idempotent resource-cleanup task, suppresses pending terminal observations, and guarantees no later
   event; a cleanup error raises only the bounded adapter exception handled by CAH-021. The required
   `force_cancel_cleanup()` method bypasses ordinary joiner shielding only after CAH-022's grace,
   cancels and reaps all operation-owned local tasks, and remains idempotent without claiming remote
   release.
8. The TypeScript launcher and supervisor plus the Python parser and composition root implement the
   explicit provider/model path as child arguments, and OpenAI work cannot begin until CAH-022 limits
   are valid.
9. Missing credentials or unsupported configuration produces actionable bounded diagnostics that may
   name a fixed safe option or environment label but never echo its value or dump the environment.
   The launcher/Python allowlist parity test accepts only `gpt-5.6-luna` and rejects unknown,
   alias-like, and fine-tuned model IDs before SDK import or network access.
   The local credential wrapper rejects unsafe file shape, permissions, content, every ambient
   `OPENAI_*` setting, and `SSLKEYLOGFILE` without echoing the key; its initializer safely creates but
   never replaces the owner-only file. Repository policy proves root `dev.env` is ignored/untracked.
10. Local transcript enablement does not alter `store=false`, and transcript redaction/opt-out behavior
    remains unchanged.
11. SDK-fake tests cover request/model mapping, every transition and reconciliation check in the
    automaton, usage including exact 8,192-output-token acceptance and over-cap rejection without
    usage/completion evidence, exact message statuses and completed reasoning echo, accepted opaque
    reasoning envelopes, rejected reasoning text/tool events, every failure-table row, premature EOF,
    response-validation and JSON/Unicode decode failures, unexpected SDK exceptions, unknown events,
    cancellation before and between output, cancellation after usage, and terminal races without
    HTTP. Resource tests separately cover stream-close failure,
    client-close failure, both failures, and CAH-022 grace force-reap while create, stream close,
    or client close is pending. They distinguish resource closure from operation closure, prove both
    resource closes are attempted on ordinary paths, prove cancelling a joiner does not cancel shared
    cleanup, and prove `wait_closed()` cannot finish while a terminal remains pending. Force-reap tests
    prove the actual owner is cancelled and no local provider task remains. Hostile-close tests prove
    an independently raised close-time `CancelledError` cannot strand cleanup, while true cleanup-owner
    cancellation stops remaining sequential closes as control flow. Separate hostile create/read
    cases prove an independently raised `CancelledError` becomes one bounded failure and cannot
    strand operation closure.
12. The opt-in `live_provider` smoke test performs one minimal bounded response, requires the named
    run option, exact allowlisted model, and locally valid credentials, normalizes remote rejection
    after the request, and is excluded from `./scripts/check` and default CI even when a credential
    happens to be present.
13. The default repository gate deselects `live_provider`, unsets provider configuration and
    `SSLKEYLOGFILE`, and passes with network access denied. Its check-script regression seeds TLS key
    logging and proves every gate layer sees it unset; explicit live opt-in rejects the selector with a
    fixed message that does not echo its value.
14. Repository policy permits the SDK/network dependency only inside the concrete adapter and rejects
    it from provider-neutral loop, session, protocol, persistence, and tool modules.
15. Client-construction tests prove the official endpoint, `trust_env=false`,
    `follow_redirects=false`, null account arguments after construction-time environment revalidation,
    `max_retries=0`, and no Python TLS key log under isolated mode; recognized ambient routing, header,
    log, proxy, and TLS key-log settings cannot redirect, duplicate, or expose the request.
16. TypeScript rejects a `session.start` task containing a lone surrogate before local publication or
    writing; Python classifies the escaped JSON form as recoverable `invalid_payload` before creating
    a provider session. Shared fixture and explicitly selected OpenAI runtime tests prove the child
    remains available without HTTP.

## Validation

- Run adapter contract tests against SDK fakes/mocks, never HTTP.
- Assert a complete structural success trace emits only the locked provider-neutral observations;
  lifecycle/item/part events never cross the provider port.
- Run provider-neutral CAH-021 and limit CAH-022 suites unchanged against the adapter-facing port.
- Exercise the runtime composition root with sanitized fake SDK behavior and assert no secret reaches
  stdout, stderr, protocol events, fixtures, snapshots, or transcripts.
- Exercise TAB/LF success plus carriage-return, OSC-52, and C1 failure paths. Prove unsafe fragments
  become the fixed `invalid_response` before publication, both wire validators reject a shared hostile
  fixture as `invalid_payload`, and stream/client cleanup still runs.
- Exercise an escaped lone surrogate in `session.start.task` through both wire contracts and an
  explicitly selected OpenAI child. Prove local submission is rejected before publication or write,
  direct Python input becomes recoverable `invalid_payload` before session construction, and a later
  shutdown is processed without network access.
- Use distinct sentinels for the API key, model/task/instruction text, function arguments, raw
  headers/request IDs, and exception bodies. Failure diagnostics and public evidence must contain
  none of them; intentionally mapped assistant text remains subject to the existing transcript
  sanitizer rather than this negative-diagnostic assertion.
- Exercise `run-tui` parsing, supervisor argument forwarding, direct Python parsing, client
  construction, pending-create cancellation, blocked-next-event cancellation, terminal-pending
  cancellation, each SDK stream/client close-failure combination, and cleanup-grace cancellation at
  every pending resource stage. Prove ordinary joiners remain shielded, then prove grace expiry
  invokes authoritative force-reap and leaves no provider-owned local task.
- Reconcile completed usage at the exact 8,192-output-token cap and one above it; assert the over-cap
  response becomes `invalid_response` without `ProviderUsageReported` or `ProviderCompleted`.
- Run a negative source-policy probe that places an SDK/network import in a provider-neutral module
  and proves the canonical gate rejects it.
- Prove the registered marker plus explicit opt-in are both required, and that the default gate
  deselects the marker even when the parent shell contains a fake credential.
- Exercise the explicit `dev.env` reader with a fake child and prove exact argument forwarding,
  non-leakage, non-evaluation, strict permissions, exclusive safe initialization, and rejection before
  child execution.
- Optionally run the separately documented live smoke command; it is supplemental evidence, not a
  completion requirement.

## Documentation impact

Document provider/model selection, the explicit local `dev.env` workflow, request and event mapping, foreground
cancellation, storage and transcript boundaries, SDK-fake testing, and the opt-in live command.
Update the agent-loop, architecture, safety, evaluation, README, glossary, and provider lesson. The
Markdown lesson and its compact text diagram are the authoritative CAH-023 learning evidence; no
presentation is part of the unit.

## Delivered implementation

- `openai_config.py` validates the provider/model pair and accepted environment before the SDK is
  imported. The mock remains the default; OpenAI requires the one repository-approved Luna model.
- `openai_responses.py` implements the lazy async adapter, exact request mapper, closed stream
  automaton, bounded usage reconciliation, bounded failure table, ordinary shielded cleanup joins,
  and authoritative force-reap behind the existing provider port.
- The TypeScript launcher and supervisor forward provider/model as separate child arguments, remove
  ambient TLS key logging, and start Python with `-E`, while the canonical repository gate also clears
  TLS key logging and Python independently revalidates provider configuration at the authoritative
  composition root. A shared fixture locks cross-language allowlist parity.
- The TypeScript and Python command schemas admit only Unicode scalar values for session task text;
  TypeScript rejects lone surrogates before writing, while Python classifies their escaped JSON form
  as `invalid_payload` before a provider session can be constructed.
- `scripts/with-openai-dev-key` safely initializes or imports only the ignored root development key
  into one explicitly selected command and rejects pre-existing OpenAI or TLS key-logging environment
  configuration; normal runtime and validation paths never auto-load the file.
- Deterministic SDK fakes cover request mapping, successful and malformed streams, failure
  normalization, usage-cap reconciliation, partial output, terminal races, cancellation,
  resource-close failures, and force-reap at each pending resource stage without HTTP. The separately
  registered live smoke remains explicit and supplemental.
- The linked Markdown lesson and compact text diagram locate the adapter inside the TUI, harness,
  provider, tool, and evidence boundaries and focus on loop ownership rather than SDK mechanics.

Detailed validation evidence is recorded in the original
[CAH-023 implementation note](notes/2026-08-01-cah-023-openai-responses-adapter.md) and its
[Luna/local-environment migration note](notes/2026-08-01-cah-023-luna-dev-environment.md). The
[adversarial-review hardening note](notes/2026-08-02-cah-023-adversarial-review-hardening.md) records
the later boundary fixes and current validation.

## Out of scope

- Background or resumable Responses, conversation objects, `previous_response_id`, provider-hosted
  tools, built-in tools, application retries, backoff, routing, failover, or multiple providers.
- Additional model IDs or aliases, reasoning summaries/text or non-`none` effort, tool execution,
  workspace context discovery, multiple model turns, or LangChain. A future model is added only with an
  explicit compatibility review and matching automaton/fake/live-smoke evidence.
- Production telemetry pipelines, quota services, cost governance, or organization-wide retention
  configuration.

## Current official references

- [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
- [Responses data controls](https://developers.openai.com/api/docs/guides/your-data#v1responses)
- [Background mode and cancellation limits](https://developers.openai.com/api/docs/guides/background#limits)
- [Official OpenAI Python SDK](https://github.com/openai/openai-python)
- [GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [GPT-5.6 reasoning parameters](https://developers.openai.com/api/docs/guides/latest-model#update-api-and-model-parameters)
