# 2026-07-30 CAH-010 session state reducer

## Outcome

CAH-010 introduces equivalent pure one-session lifecycle reducers in Python and TypeScript. The
existing mock runtime and TUI supervisor route their accepted event tapes through those cores, while
the TUI conversation adapter remains responsible for preserving multiple terminal turns. CAH-011 is
the next dependency-ready unit.

## Locked decisions

- The canonical statuses are `idle`, `starting`, `running`, `awaiting_approval`, `cancelling`,
  `completed`, `cancelled`, and `failed`.
- `task.submitted`, `cancel.requested`, `approval.requested`, and `approval.resolved` are trusted
  domain facts. Approval facts are not protocol-v1 messages because approval identity, action
  binding, and decisions belong to a later story.
- The one-session core is absorbing. A later task creates a fresh core; the TUI's separate
  conversation projection retains prior terminal turns.
- Duplicate and late terminal inputs follow a strict diagnostic policy: return
  `terminal_state_absorbing` with the exact prior state and never create a second terminal outcome.
- Invariant failures expose only a stable code, prior status, and input type. They do not copy task
  text, assistant text, command or session IDs, payloads, or validator output.
- Protocol version 1 is unchanged. Existing `session.failed` now reaches the session lifecycle rather
  than being misclassified as an unexpected runtime event.

## Transition and fixture evidence

The shared fixture suite at `protocol/fixtures/session-lifecycle/v1/` contains:

- 16 legal-transition cases;
- 7 complete replay scenarios;
- 27 invariant-failure cases; and
- 110 complete session-event envelopes validated by both existing wire boundaries.

All 50 cases begin from idle, construct their prior state through setup inputs, compare every
normalized state or failure field, and replay twice in both languages. This keeps Python snake_case
and TypeScript camelCase native without allowing either implementation to generate the other.

## Integration discoveries

`MockSession` allocates a Python-owned session ID before its task necessarily emits
`session.started`. A direct caller can therefore request cancellation during `starting`, even though
the TUI cannot address that session yet. The mock records the request but defers reducing it until
the started event has been written and reduced. This preserves the reviewed transition table rather
than inventing a `starting -> cancelling` edge.

The mock integrates lifecycle reduction as a post-write consistency observer: it reduces only an
event that the ordered writer has successfully emitted. The protocol writer remains the pre-write
validation gate. Moving lifecycle reduction ahead of output would require an explicit transactional
contract so a failed write could not advance in-memory lifecycle state beyond observable history.

The TypeScript core models exactly one session, while the existing Ink experience displays several
completed turns. Keeping `session-lifecycle.ts` separate from `session-state.ts` made that distinction
explicit: the supervisor validates one active tape with the core, and the adapter copies accepted
state into conversation history.

## Validation evidence

- Python core reducer tests: 31 passing.
- TypeScript core reducer tests: 17 passing.
- Shared fixture conformance: 53 Python and 53 TypeScript tests passing.
- Canonical Python stages: 191 core/runtime tests, 30 protocol-fixture tests, and 24 repository-policy
  tests passing.
- Canonical TypeScript stages: 201 core tests, 29 protocol-fixture tests, and 4 genuine
  Node-to-Python boundary tests passing.
- Type checking, ESLint, Ruff linting, and Ruff formatting pass for the changed implementation.
- The ten-slide visual lesson was rendered and inspected at full size; the bundled slide validator
  reported no overflow.
- `TMPDIR=/tmp ./scripts/check` passed as the final canonical completion gate and CI entry point.

## Deferred work

- CAH-011 persists redacted trusted lifecycle inputs—domain facts and validated events—as an
  append-only transcript.
- A later approval story defines approval request and decision wire messages and live producers.
- Provider, tool, policy, and limit failures will reuse `session.failed` through later M1 stories.
