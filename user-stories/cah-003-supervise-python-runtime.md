# CAH-003 - Start and supervise the Python runtime

- **Status:** Done
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-002
- **Lesson:** [Python runtime supervision](../docs/lessons/cah-003-python-runtime-supervision.md)

## User story

> As a user, I want the TUI to start the Python harness automatically so that the application
> behaves as one tool.

## Scope

- Add a minimal Python runtime entry point suitable for child-process execution.
- Add a TUI child supervisor that resolves and validates a Linux `uv`, preflights the prepared
  project environment, and invokes its interpreter with an explicit workspace path.
- Build the child environment from the parent while removing `PYTHONPATH`, `PYTHONHOME`,
  `VIRTUAL_ENV`, and all `UV_*` module, project, environment, and interpreter selection overrides.
- Reserve child stdin and stdout for the forthcoming protocol while forwarding or surfacing stderr
  diagnostics separately.
- Define cleanup and visible failure behavior for startup, unexpected exit, and TUI shutdown.

## Acceptance criteria

1. The supervisor resolves `uv` from filtered `PATH`, follows its real path, and rejects a path
   under `/mnt` or a name ending in `.exe` before spawn.
2. The supervisor requires `.venv/pyvenv.cfg` and executable `.venv/bin/python`; an unprepared
   environment produces an actionable failure without invoking `uv` or creating `.venv`.
3. The TUI starts the Python runtime through the validated `uv`, explicitly selects the prepared
   interpreter, and never uses shell interpolation.
4. The launch directory is the default workspace and an optional `--workspace PATH` is resolved and
   passed explicitly to Python.
5. One process serves exactly one workspace.
6. The child inherits required parent settings but not `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, or
   any `UV_*` variable; supported `uv` behavior is supplied explicitly in the argument array.
7. Child stdin and stdout are pipes reserved for protocol traffic.
8. Python writes human diagnostics only to stderr; neither process writes logs onto protocol stdout.
9. A failed child startup produces an actionable error in the TUI.
10. An unexpected child exit moves the UI into a visible failed state and includes bounded
    diagnostic context without exposing known secrets, common concatenated or camel-case
    credential assignments, or a credential-line remainder cut by the byte-tail boundary.
11. Normal TUI exit terminates and reaps the child process.
12. Tests cover normal startup, preflight and spawn failure, unexpected exit, and cleanup without
    invoking a real model.
13. Process supervision and exit ownership are documented in TSDoc and Python docstrings where they
    form public or non-obvious lifecycle contracts.

## Validation

- Run Python pytest and Ruff checks.
- Run TUI type checking, linting, and tests.
- Run supervisor tests with controlled fake child commands or fixtures for each required exit path.
- Assert preflight accepts a real Linux `uv`, rejects direct and symlink-hidden Windows paths,
  rejects missing venv metadata or interpreter without spawning, and leaves an unprepared
  repository unchanged.
- Assert launch preserves safe environment values, removes `PYTHONPATH`, `PYTHONHOME`,
  `VIRTUAL_ENV`, and all `UV_*` variables without mutating the source, explicitly selects the
  prepared interpreter, and still starts the real runtime with poisoned overrides supplied.
- Seed multi-part authorization and cookie values plus `apiKey`, `authToken`, and `accesskey`
  assignments in stderr and assert their complete physical-line values are absent while benign
  identifiers such as `monkey` and a following diagnostic remain visible.
- Overflow the stderr byte tail inside a credential line and assert the leading partial line is
  dropped; when no complete physical line remains, assert only the omission marker is displayed.
- Launch the application against the real minimal Python entry point and verify normal cleanup; this
  test must not use a model, network, or workspace mutation.
- Inspect captured stdout and stderr to prove protocol and diagnostic channels remain separate.

## Documentation impact

Update architecture and process-boundary documentation with executable and environment preflight,
launch arguments, workspace resolution, pipe ownership, diagnostic truncation, startup failure,
unexpected exit, and cleanup behavior. Add the developer launch command and troubleshooting
guidance to the README.

## Completion evidence

The [CAH-003 runtime-supervision note](notes/2026-07-15-cah-003-python-runtime-supervision.md)
records the exact shell-free `uv` request, canonical workspace contract, stream reservations,
bounded redacted diagnostics, and EOF-to-process-group cleanup path. Python validation passes all
eight tests, including seven runtime tests. TUI validation covers Linux executable and prepared-venv
preflight, environment filtering, complete credential-line redaction, byte-boundary truncation, and
a real Node-to-uv-to-Python boundary test that observes both processes through `/proc` and proves
both are gone after cleanup. No test invokes a model, uses the network, or mutates the selected
workspace.

## Out of scope

- Parsing versioned protocol messages or implementing a readiness handshake; CAH-004 owns the
  protocol contract.
- Provider calls, transcripts, tools, approvals, or autonomous child restart.
