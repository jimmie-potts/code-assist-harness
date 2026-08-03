# 2026-08-01 CAH-023 OpenAI Responses adapter

> Historical implementation record. The model-specific request and local-key setup were superseded
> later that day by the [Luna migration note](2026-08-01-cah-023-luna-dev-environment.md); the
> [adversarial-review hardening note](2026-08-02-cah-023-adversarial-review-hardening.md) supersedes
> its cleanup, stream-validation, environment-isolation, and final evidence details.

## Outcome

CAH-023 adds the first real-provider capability without transferring agent-loop ownership to a
vendor SDK. An explicitly selected OpenAI path now enters through the existing provider port, while
the mock remains the default and CAH-021/022 continue to own the session, hard limits, terminal
selection, and transcript evidence.

## Locked decisions

- Provider and model are process configuration, not NDJSON fields. The TypeScript launcher validates
  and forwards separate child arguments; Python validates the pair again before SDK import.
- The only approved snapshot is `gpt-4.1-mini-2025-04-14`. A changing alias, unknown model,
  fine-tune, reasoning family, or model supplied to the mock fails locally with a fixed message.
- `OPENAI_API_KEY` is consumed only after explicit OpenAI selection. Every other `OPENAI_*`
  variable is rejected before client construction so ambient SDK routing, logging, or account
  configuration cannot silently change the turn.
- The production client fixes `https://api.openai.com/v1`, passes null organization/project only after
  rechecking ambient provider configuration at lazy construction, disables SDK retries and redirects,
  and ignores ambient proxy use. Each operation creates its own async client and stream lazily when
  its event iterator is consumed.
- Every request is text-only and explicitly foreground: `stream=true`, `background=false`, and
  `store=false`; `tools` and `tool_choice` are omitted because the provider-neutral request does not
  yet declare a tool schema.
- SDK events are untrusted. A closed automaton accepts one response, one assistant message, one
  output-text part, consecutive sequence numbers, reconciled snapshots, the exact model, and bounded
  usage. Unsupported output fails closed rather than broadening the domain contract implicitly.
- Natural terminals and cancellation share one cleanup owner. That owner cancels/reaps owned
  create/read work and attempts both stream and client close. Joiners shield it, so cancelling a
  join does not cancel resource cleanup.
- A natural terminal remains buffered until cleanup settles. `terminal_pending` distinguishes
  “resource work has settled” from “the final provider event has crossed the port,” allowing
  cancellation after usage to suppress completion without letting `wait_closed()` return early.
- Failure mapping uses fixed codes and messages. SDK payloads, response bodies, headers, request IDs,
  exception strings, credentials, and raw objects never enter provider-neutral events, diagnostics,
  fixtures, or transcripts.

## Architecture position

- `tui/src/provider-configuration.ts` owns early user-facing provider/model validation and the shared
  fixture parity surface.
- `tui/src/runtime-supervisor.ts` forwards validated values as shell-free Python child arguments.
- `src/code_assist_harness/provider/openai_config.py` is the SDK-free authoritative configuration
  boundary.
- `src/code_assist_harness/runtime.py` is the composition root and imports the concrete adapter only
  after successful validation.
- `src/code_assist_harness/provider/openai_responses.py` is the sole production SDK/network boundary;
  it owns request mapping, stream validation, failure normalization, and SDK-resource cleanup.
- `ProviderSession` still owns loop limits, publication ordering, terminal selection, cleanup grace,
  and evidence. The adapter cannot complete a session or authorize a tool.

## Implementation discoveries

SDK async create and stream iteration must be represented as owned tasks rather than bare awaits.
That gives cancellation one stable target whether it arrives before the response stream exists or
while the next event is blocked.

Operation closure and resource closure are different facts. A completion cannot cross the port
until resource cleanup has been attempted, but a cleanup failure must not erase an already selected
provider failure. The adapter therefore replaces only a buffered success with a fixed `unknown`
failure and later reports cleanup uncertainty through one bounded adapter exception.

Cleanup joiners are independently cancellable. The shared owner is shielded and records logical
closure itself when cancellation selected cleanup; this prevents a cancelled first joiner from
leaving a later `wait_closed()` blocked forever.

The official SDK interprets null organization/project constructor arguments as permission to read
environment defaults. The adapter therefore rejects other `OPENAI_*` names at startup and rechecks at
lazy construction before passing those null arguments. Together with `trust_env=false`, that makes
the normal one-request routing boundary explicit; the constructor-argument test alone would not.

## Documentation and learning evidence

The written lesson was replaced with an implementation-backed, compact system-design walkthrough.
Its architecture diagram locates CAH-023 between TUI configuration, the Python composition root,
CAH-021/022 loop ownership, the provider port, the Responses API, the tool boundary, and evidence.

A six-slide companion was generated and inspected during branch work, but it was removed before
merge when the presentation freeze was applied to CAH-023 onward. It is not a retained artifact or
delivery evidence. The authoritative Markdown lesson carries the same architecture position in its
compact text diagram.

## Validation evidence

- Across the canonical gate's three Python stages, 660 tests passed; the `live_provider` test was
  explicitly deselected. An independent full-suite pass before the final adversarial additions also
  confirmed that missing opt-in produces one safe skip rather than a network request.
- The adapter-focused suite passed with 78 deterministic SDK-fake tests covering request mapping,
  the success automaton, malformed and unsupported streams, every bounded failure class,
  cancellation and exact races, terminal-pending behavior, three pending cleanup stages, cleanup
  failure, client construction, and lazy environment revalidation.
- TUI type checking, linting, and all 270 tests passed, including provider/model validation, child
  argument forwarding, shared fixture parity, and unchanged mock defaults.
- The opt-in live smoke was not run. It remains supplemental evidence and cannot be selected by an
  ambient credential alone.
- `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache ./scripts/check` passed: 598 non-live Python behavioral
  tests, 30 Python protocol-fixture tests, 32 repository-policy/check-script tests, 237 TUI unit tests,
  29 TypeScript protocol-fixture tests, and 4 real Node/Python boundary tests. Python lint/format,
  TUI typecheck/lint, lock verification, documentation links, and network policy also passed.

## Deferred work

- E3 must first refine a single-responsibility repository-context unit. CAH-023 does not discover
  instructions, read workspace files, select context, or add tools.
- Tool schemas, tool observations from OpenAI, execution policy, approvals, multiple turns,
  reasoning output, additional model snapshots, background/resumable responses, retry/routing, and
  production telemetry remain outside this unit.
