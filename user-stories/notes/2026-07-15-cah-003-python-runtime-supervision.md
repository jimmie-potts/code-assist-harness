# 2026-07-15 CAH-003 Python runtime supervision

## Purpose

Record the implemented process, workspace, stream, failure, and cleanup contracts that complete
CAH-003 without claiming that the CAH-004 NDJSON protocol or readiness handshake exists.

## Decisions

- Preserve the launcher's canonical caller directory and resolve either it or one
  `--workspace PATH` to exactly one existing, symlink-free directory before spawn. Python validates
  the same explicit workspace again instead of trusting an incidental child working directory.
- Launch `uv` with an argument array and `shell: false`. The harness repository is the `uv` project
  and working directory; the selected target repository is a separate Python argument.
- Use `uv run --project REPOSITORY_ROOT`, followed by `--frozen`, `--no-cache`, `--no-sync`,
  `--offline`, `--no-env-file`, `--no-progress`, and `--no-python-downloads`, then
  `-- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE`. Preparing the
  environment with `uv sync --dev` is an explicit prerequisite.
- Configure stdin, stdout, and stderr as separate pipes. Until CAH-004, Python drains and discards
  stdin, Node drains and discards stdout, and no readiness line is emitted. Human diagnostics use
  stderr only.
- Treat the operating-system spawn event as CAH-003's temporary `running` transition, not protocol
  readiness. Treat every unrequested close, including exit code zero, as visible runtime failure.
- Retain only a 4,096-byte stderr tail, redact sufficiently distinctive inherited environment
  values and credential-shaped or quoted assignments, remove terminal controls, and cap the UI
  summary at 1,200 characters. Raw stderr and protocol stdout never enter visible state.
- Bind cleanup to the Ink lifecycle `finally` path. After Ink exits and restores the terminal,
  close child stdin, then escalate to `SIGTERM` and `SIGKILL` for the detached process group only
  when bounded grace periods expire. Resolve cleanup only after the child `close` event. Parent
  `SIGHUP` and `SIGTERM` request Ink unmount and enter this same path; keep their handlers installed
  until child cleanup settles so repeated signals cannot restore default termination mid-cleanup.

## Implemented path

`scripts/run-tui` validates Linux Node and npm, captures `pwd -P`, and forwards the CLI arguments.
`tui/src/workspace.ts` resolves the workspace, and `tui/src/cli.ts` creates one
`PythonRuntimeSupervisor`. `tui/src/runtime-supervisor.ts` builds the exact launch request, owns the
child state machine, drains stdout, gathers diagnostics, and performs idempotent shutdown.
`tui/src/runtime-diagnostics.ts` owns bounding and redaction. `tui/src/run-application.tsx`
subscribes the projection in `tui/src/app.tsx` and guarantees `stop()` even when rendering fails
before spawn.

`src/code_assist_harness/runtime.py` accepts exactly one workspace, resolves it canonically, starts
one `asyncio` loop, and drains stdin with an event-loop file-descriptor reader until EOF. A clean
EOF produces no stdout or stderr. Invalid configuration returns status 2 with a brief stderr-only
diagnostic. No model, command schema, session, tool, transcript, or workspace read exists in this
unit.

## Process-group discovery

The real boundary showed that `uv` can remain a wrapper process with a separate Python descendant.
Signaling only the wrapper PID can therefore leave Python alive with inherited pipes. The Node child
is launched as a detached process-group leader, and shutdown signals the negative leader PID so the
whole group receives escalation.

The wrapper's command line also contains the requested Python module, so command-line matching alone
cannot prove that Python started. On Linux, uv may spawn Python from a worker thread; the runtime
then appears in that thread's `/proc/UV_PID/task/THREAD_ID/children` rather than the leader thread's
child list. The real test walks every task's descendants and requires a Python executable match.

An additional race matters: the uv leader can set an exit code before its Python descendant closes
the inherited streams. The signal helper must not use the leader's `exitCode` as proof that the
group is gone. It continues to signal until the supervisor observes `close`; `ESRCH` is the only
ignored signal failure.

## Test and validation evidence

- Python has eight passing tests, including seven runtime tests for canonical workspace selection,
  missing and file paths, stdin EOF, empty protocol stdout, stderr-only configuration failure, and
  exactly-one-workspace enforcement.
- The TUI has 43 passing tests in ten files. Controlled supervisor tests cover exact argument
  construction, spawn transition, missing `uv`, unrequested exit, stdout exclusion, secret
  redaction, idempotent escalation, the leader-exit/process-group race, and shell-free synchronous
  failure. Rendering and lifecycle tests prove failures are visible, repeated termination signals
  stay intercepted through child cleanup, and cleanup still runs when Ink exit or initial rendering
  fails. Diagnostic tests cover distinctive non-keyword environment values, complete quoted
  assignments, and stderr that ends inside a known secret.
- `tui/test/runtime-boundary.test.ts` starts the actual Node-to-uv-to-Python chain, verifies the
  matching `/proc` entry is a Python executable rather than the `uv` wrapper, stops it, proves both
  recorded PIDs are absent, and confirms the temporary workspace remains empty.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, TUI type checking,
  linting, and tests pass without a model credential or live network request. Manual lifecycle
  validation also confirmed launch, visible running state, a missing-`uv` failure, Ctrl+C exit, and
  `SIGTERM` cleanup with no Python runtime left behind.
- `git diff --check` passes.

## Scope boundary

CAH-003 proves only transport ownership and process lifetime. It does not define a protocol
envelope, send a readiness event, validate messages, start a session, read the selected workspace,
call a provider, apply policy, run tools, or write transcripts.

## Next unit

CAH-004 is dependency-ready. It defines protocol version 1, cross-language validators and fixtures,
and a real readiness contract on the pipes reserved here.
