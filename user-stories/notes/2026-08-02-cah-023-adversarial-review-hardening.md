# 2026-08-02 CAH-023 adversarial-review hardening

## Outcome

The open CAH-023 pull request received a second adversarial pass. The fixes preserve the unit's
single responsibility—strict vendor translation behind the provider port—while closing credential,
runtime-environment, stream-validation, and cleanup-state gaps. No SDK type or agent-loop policy moved
into the TUI, protocol, or provider-neutral loop; the wire schemas only mirror the provider-domain
terminal-text invariant at the untrusted process boundary.

## Required fixes

- The development-key helper now rejects every pre-existing `OPENAI_*` variable and
  `SSLKEYLOGFILE`. Its `--init` path creates `dev.env` exclusively with no-follow semantics and mode
  `0600` before a hidden prompt, refuses replacement, never accepts the key through argv, fsyncs the
  exact assignment, and removes the created file on blank, invalid, cancelled, or failed entry.
- The TUI supervisor removes `SSLKEYLOGFILE` and starts the prepared Python interpreter with `-E`.
  Python provider validation independently rejects the TLS key-log selector at initial and lazy
  client construction, covering direct launches as well as the normal TUI path.
- Provider-name validation rejects non-string and unhashable input through the fixed configuration
  failure rather than leaking a raw `TypeError`.
- Message items must be `in_progress` when added and `completed` when done or reconciled in the final
  response. The completed response must also echo the reviewed Luna reasoning effort `none` and
  context `current_turn`.
- A close coroutine that independently raises `CancelledError` is now a bounded cleanup failure; it
  does not strand the operation or prevent the other resource close. Cancellation of the cleanup
  owner itself remains cancellation control flow.
- An SDK create or stream-read awaitable that independently raises `CancelledError` now enters the
  bounded provider-failure path and starts cleanup. It cannot silently end the iterator or leave
  `wait_closed()` pending; only harness-selected cancellation retains that control-flow meaning.
- The TypeScript and Python command schemas now state the Unicode-scalar invariant for
  `session.start.task` explicitly. A shared escaped-surrogate fixture and an OpenAI-selected child
  regression prove the TUI rejects invalid input before publication or write and Python returns
  recoverable `invalid_payload` before session construction; the child processes shutdown normally
  without HTTP.
- The provider operation port now requires `force_cancel_cleanup()`. Ordinary adapter joiners still
  shield one cleanup owner, but after the five-second harness grace the session cancels/reaps its
  local barrier and invokes this authoritative hook. The OpenAI operation cancels and awaits its real
  owner and any other owned task, leaving no local provider work while reporting remote release as
  unconfirmed. Genuine owner cancellation stops sequential closes; an independently raised close-time
  `CancelledError` still attempts both.
- Completed OpenAI usage now rejects `output_tokens` above the request's fixed 8,192-token cap even
  when totals otherwise reconcile. The invalid response emits neither usage nor completion evidence.
- The canonical `scripts/check` gate now clears `SSLKEYLOGFILE` alongside provider credentials. Its
  regression seeds the variable at every gate layer, and explicit live opt-in independently rejects
  the selector without echoing its value.

## Architecture position

```text
safe --init -> ignored dev.env -> explicit key reader
                                      |
provider/model CLI -> TUI sanitized spawn (`python -E`) -> Python composition root
                                                            |
CAH-021/022 loop + terminal authority -> provider port -> [CAH-023 Luna adapter] -> Responses API
          |                                                   |
          +-> validated session/transcript evidence           +-> strict SSE + cleanup automaton

Tool boundary: unchanged and unavailable in this text-only unit
```

The helper owns local credential-file admission. The supervisor owns child-process isolation. The
composition root owns provider configuration, the adapter owns vendor validation and resource
release, and the harness continues to own limits, cancellation intent, terminal truth, and evidence.

## Review decisions that did not widen the unit

- The allowlist remains the exact reviewed `gpt-5.6-luna` identifier. Adding snapshots or aliases is
  a separate compatibility unit with matching stream and smoke evidence.
- Refusal output remains unsupported and therefore fails closed as `invalid_response`. A future
  refusal contract must first decide its provider-neutral and session semantics; CAH-023 does not
  guess them at the adapter boundary.

## Validation evidence

- Provider configuration and adapter suite: 157 tests passed; focused Ruff and format checks passed.
- Development-key helper suite: 27 tests passed after the blank-key regression was added; focused
  Ruff and format checks passed.
- Runtime-supervisor suite: 39 tests passed; TypeScript type checking and lint passed.
- The canonical `./scripts/check` gate passed: 663 non-live Python tests, 30 Python protocol-fixture
  tests, and 33 repository-policy tests passed; TypeScript type checking and lint passed; 237 TUI,
  29 TypeScript protocol-fixture, and 4 real Node-to-`uv`-to-Python boundary tests passed.
- A six-slide companion was rebuilt and inspected during branch work, then removed before merge under
  the presentation freeze. It is not a retained artifact or validation evidence; the Markdown lesson
  and compact text diagram are authoritative.
- Hostile OpenAI text containing carriage return, OSC-52, or C1 controls now fails as the fixed
  `invalid_response` before the fragment crosses the provider boundary. Provider-domain and both wire
  validators admit TAB/LF layout and reject every other C0/C1 control; deterministic tests cover the
  safe and hostile paths without HTTP.
- After the terminal-text and presentation-freeze follow-up, `./scripts/check` passed with 935
  non-live Python tests, 31 Python protocol-fixture tests, 35 repository-policy/check-script tests,
  238 TUI tests, 30 TypeScript protocol-fixture tests, and 4 real Node-to-Python boundary tests.
- After the session-task Unicode follow-up, `./scripts/check` passed with 940 non-live Python tests,
  32 Python protocol-fixture tests, 35 repository-policy/check-script tests, 240 TUI tests,
  31 TypeScript protocol-fixture tests, and 4 real Node-to-Python boundary tests. The selected-OpenAI
  regression used a fake local key and made no provider request.
- After the cleanup-owner, completed-usage-cap, and canonical TLS-key-log follow-up, the focused
  adapter/session/fake/runtime/check-script suites passed with 266 tests. `./scripts/check` passed with
  948 non-live Python tests, 32 Python protocol-fixture tests, 36 repository-policy/check-script tests,
  240 TUI tests, 31 TypeScript protocol-fixture tests, and 4 real Node-to-Python boundary tests.
- GitHub Actions runs the same canonical gate on the published commit; remote status is verified
  separately. The credential-gated live smoke remains supplemental and was not run.
