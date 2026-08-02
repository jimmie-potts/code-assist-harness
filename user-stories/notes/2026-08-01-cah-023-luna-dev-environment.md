# 2026-08-01 CAH-023 Luna and local development environment

## Outcome

CAH-023 now selects `gpt-5.6-luna` and provides one explicit local `dev.env` reader for developer
testing. The change preserves the existing ownership boundary: provider/model remain process
arguments, the Python composition root remains authoritative for provider configuration, and
credentials never enter protocol or harness domain values.

## Luna compatibility decisions

- `gpt-5.6-luna` is the sole allowlisted OpenAI model in Python, TypeScript, and the shared parity
  fixture. The identifier is treated as an exact reviewed model ID, not described as a dated alias.
- Every request explicitly sets reasoning effort `none` and context `current_turn`, avoiding Luna's
  broader defaults for this one-turn harness lesson. `max_output_tokens=8192` bounds visible and
  hidden generated tokens before the harness applies its separate UTF-8 assistant-output limit.
- A success may remain message-only or contain exactly one opaque empty reasoning item before the
  assistant message. The adapter validates item identity, ordering, status, empty summary/content,
  final-output reconciliation, and reasoning-token accounting.
- `encrypted_content` is deliberately ignored rather than copied, parsed, compared, logged,
  persisted, or emitted. Reasoning text/summary events, populated reasoning content, a second or late
  reasoning item, and effective settings outside the reviewed `none`/`current_turn` mode fail closed.
- Reasoning tokens are already included in Responses `output_tokens`; the adapter never double
  counts them in provider-neutral usage.

## Local credential decision

- Repository-root `dev.env` is explicitly ignored by the `/dev.env` pattern, and repository policy
  proves it cannot be tracked without failing the gate.
- `scripts/with-openai-dev-key` is the only repository helper that reads the file. It never sources
  or evaluates content, requires one non-empty `OPENAI_API_KEY=...` assignment in a regular
  non-symlink file with mode `0600`, rejects an ambient-key conflict, and preserves the requested
  command with `exec`.
- Provider/model remain command-line configuration. Direct `run-tui`, `uv`, and `./scripts/check`
  invocations do not auto-load `dev.env`; the runtime continues to use `uv --no-env-file`.
- The key remains local plaintext. File permissions reduce accidental disclosure but do not provide
  encryption, managed rotation, or production secret storage.

## Architecture position

```text
ignored dev.env --explicit reader--> process OPENAI_API_KEY
                                          |
CLI provider/model --> TypeScript preflight --> Python composition root
                                                   |
                    CAH-021/022 loop --> provider port --> CAH-023 Luna adapter --> Responses API
                          |                                      |
                          +--> validated session evidence        +--> opaque reasoning discarded
```

The credential helper owns only local file admission. The adapter owns only vendor request and
stream translation. The harness still owns loop limits, cancellation, terminal truth, and evidence;
the TUI still owns presentation rather than safety policy.

## Validation evidence

- Focused Python adapter/configuration/check-script tests and TypeScript provider/launcher tests pass
  against deterministic fakes without HTTP.
- The local-key helper tests cover exact argument forwarding, non-leakage, missing/symlink/permissive
  files and FIFOs, ambient key and Python-import conflicts, duplicate/empty/unknown assignments,
  Unicode whitespace/control characters, empty commands, and injection-shaped literal data.
- The credential-gated live smoke was not run and remains supplemental evidence.
- Final `./scripts/check` passed offline: 631 Python tests passed with the live-provider test
  deselected, 30 Python protocol-fixture tests and 33 repository-policy tests passed, TUI typecheck
  and lint passed, and the 237 TUI, 29 TypeScript fixture, and 4 Node-Python boundary tests passed.
- All six final slides were rendered and inspected individually with no observed clipping or overlap.
  The template-plan and template-fidelity checks passed with zero issues, and the artifact structural
  overflow test found no object outside the 1280 by 720 canvas. The bundled pixel-margin checker could
  not run through the Windows dependency runtime because its WSL bridge failed before Python startup;
  this note therefore records the exact structural check and visual inspection rather than claiming
  that unavailable checker ran.

## Official references

- [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
- [GPT-5.6 model parameters](https://developers.openai.com/api/docs/guides/latest-model#update-api-and-model-parameters)
- [Responses create parameters](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [API key safety](https://developers.openai.com/api/docs/guides/production-best-practices#api-keys)
