# 2026-07-31 CAH-021 provider-turn story split

## Purpose

Record the planning correction that separates provider-neutral orchestration, hard safety limits,
and vendor/network integration into independently verifiable M1 units. This note changes delivery
contracts only; it does not claim executable behavior.

## Decision

The dependency order is:

```text
CAH-020 provider port and fake (Done)
    -> CAH-021 one provider-neutral turn (Planned)
    -> CAH-022 hard loop limits (Planned)
    -> CAH-023 OpenAI Responses adapter (Planned)
```

M1 is not complete until CAH-023 passes. The current `MockSession` runtime and TUI remain the only
launched task-to-response path throughout this documentation change.

## Responsibility boundaries

### CAH-021 - provider-stream-to-session orchestration

- Build one request from one task and an injected, already-resolved instruction tuple.
- Start and consume exactly one provider operation through the strict fake.
- Enforce one locked stream grammar, strict completed-text reconciliation, safe failure mapping,
  unavailable-tool behavior, provider cleanup, and exactly one terminal outcome.
- Persist optional bounded usage through a transcript-only `model.usage_observed` evidence record,
  make all new transcripts version 2 with version-1 replay compatibility, and keep lifecycle
  reducers and protocol v1 unchanged.
- Buffer reconciled provider completion until `ProviderCompleted`, enforce a fixed 8192-byte
  protocol-fit ceiling, and cancel plus await provider cleanup on runtime shutdown, stdin EOF, or
  outer cancellation, reporting cleanup as unconfirmed when its barrier fails.
- Shield each admitted lifecycle-event publication through wire write, reducer acceptance, and the
  transcript-observer attempt so cancellation cannot split those views.
- Add an injection/composition seam without activating a network adapter in `main()`.

Instruction discovery and precedence remain E3 work. The planned CAH-021 seam supplies an empty
instruction tuple; the current runtime does not build a provider request.

### CAH-022 - domain safety budgets

- Validate immutable limits without silent clamping.
- Lock finite defaults and maxima for all four limits.
- Charge model-turn admission before provider start.
- Capture an untruncated absolute monotonic provider-work deadline at provider-session allocation,
  let it win an exact event/deadline tie, and let its watcher cancel provider work independently of
  a blocked already-admitted event publication.
- Reserve cumulative accepted assistant output in UTF-8 bytes before emission.
- Count provider tool-call observations before their CAH-021 unavailable-tool handling, including
  the rejecting maximum-plus-one observation.
- Cancel and await provider cleanup when a limit wins.
- Bound a non-conforming cleanup await with one fixed five-second injected grace while keeping the
  selected session outcome and reporting cleanup as unconfirmed.
- Advance transcripts to version 3 with at most one bounded `loop.limits_observed` record and
  version-1/version-2 replay compatibility. A healthy enabled path writes exactly one record before
  its terminal; teardown or an earlier persistence failure can write none, while a persistence
  failure after the record can leave a valid record-only prefix.

CAH-022 precedes every real adapter so network or billable work cannot become the first safety
boundary.

### CAH-023 - OpenAI-specific integration

- Add the SDK dependency, a text-only Responses request/event mapping, safe credential and model
  configuration, and runtime activation at the composition root.
- Allow only the exact `gpt-4.1-mini-2025-04-14` non-reasoning snapshot in both launchers, with
  Python authoritative and a cross-runtime parity test; aliases and every other model fail locally.
- Encode ordered instructions with one exact compact-JSON representation, omit all tool declarations,
  and reject every SDK reasoning/tool event without retaining its content or arguments.
- Use foreground SSE with `stream=true`, `background=false`, and `store=false` explicitly.
- Cancel foreground work by requesting connection termination and joining cleanup through the
  bounded confirmed/unconfirmed path; do not use the background-response cancel endpoint.
- Keep SDK objects and raw provider data inside the adapter.
- Route provider/model options through `run-tui`, its supervisor, and the Python composition root as
  child arguments rather than protocol fields.
- Use a closed structural/semantic Responses event policy, explicit official endpoint,
  `trust_env=false`, `max_retries=0`, and no ambient SDK routing or logging configuration.
- Validate one exact assistant-message/output-text event automaton and reconcile every completed text
  snapshot before accepting the response.
- Distinguish resource cleanup from logical operation closure: cleanup precedes the pending terminal
  queue, cancellation can suppress that queue, and the operation closes only with terminal delivery
  or suppression. Close failures become bounded provider/session evidence without raw exceptions.
- Use SDK fakes in default validation and keep one `live_provider` smoke requiring
  `--run-live-provider`, `--live-provider-model gpt-4.1-mini-2025-04-14`, and credentials outside
  default CI.

Current official OpenAI documentation states that Responses stream through typed semantic SSE
events, Responses are stored by default unless `store` is false, and foreground cancellation means
terminating the connection. Background mode has a distinct server-side cancel endpoint and temporary
storage behavior, so it remains outside CAH-023. `store=false` disables response statefulness and
application-state storage for the request; it is not a universal deletion or abuse-monitoring
control.

## Why the prior story was split

The earlier CAH-021 combined two change drivers:

1. harness-owned request, stream, cancellation, transcript, and terminal semantics; and
2. OpenAI SDK, credentials, data controls, network behavior, and live testing.

Those responsibilities can fail and evolve independently. Keeping them together also placed the
live adapter before CAH-022 hard limits. The split makes each story single-responsibility and makes
the safer dependency order explicit.

## Planned evidence

Each unit must supply its own focused success and meaningful failure tests, current written lesson,
implementation note, full `./scripts/check` result, and ready-for-review pull request. This note
originally required a visual PPTX for every unit; the later presentation freeze supersedes that
requirement. Retained decks through CAH-022 are historical, while CAH-023 and later use Markdown plus
a compact text diagram only. Planning lessons remain `Planned` and do not present pseudocode as
shipped implementation.

## Validation evidence

- `git diff --check` passes.
- The focused repository-policy and check-script suite passes: 24 tests.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passes with 263 Python tests, 30 Python
  protocol-fixture tests, 24 repository-policy tests, 208 TUI tests, 29 TypeScript protocol-fixture
  tests, and 4 real Node/Python boundary tests, plus Python lint/format and TypeScript typecheck/lint.
- No dependency, protocol, runtime, TUI, fixture, or executable-behavior file changed.
- A manual documentation-policy audit confirms 15 reciprocal story/lesson pairs, aligned statuses,
  every required planned-lesson section, three-to-five production reference groups per new lesson,
  Further reading coverage for those references, and the then-current visual-deck policy. The later
  presentation freeze supersedes that visual requirement.

## References

- [CAH-021 story](../cah-021-complete-one-model-turn.md)
- [CAH-022 story](../cah-022-enforce-loop-limits.md)
- [CAH-023 story](../cah-023-add-openai-responses-adapter.md)
- [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- [Responses statefulness](https://developers.openai.com/api/docs/guides/migrate-to-responses#4-decide-when-to-use-statefulness)
- [Responses data controls](https://developers.openai.com/api/docs/guides/your-data#v1responses)
- [Background mode limits](https://developers.openai.com/api/docs/guides/background#limits)
- [Official OpenAI Python SDK](https://github.com/openai/openai-python)
