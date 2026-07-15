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
- Add a TUI child supervisor that invokes Python through `uv` with an explicit workspace path.
- Build the child environment from the parent while removing `PYTHONPATH` and `PYTHONHOME` module
  discovery overrides.
- Reserve child stdin and stdout for the forthcoming protocol while forwarding or surfacing stderr
  diagnostics separately.
- Define cleanup and visible failure behavior for startup, unexpected exit, and TUI shutdown.

## Acceptance criteria

1. The TUI starts the Python runtime through `uv`, without shell interpolation.
2. The launch directory is the default workspace and an optional `--workspace PATH` is resolved and
   passed explicitly to Python.
3. One process serves exactly one workspace.
4. The child inherits required parent settings but not `PYTHONPATH` or `PYTHONHOME`.
5. Child stdin and stdout are pipes reserved for protocol traffic.
6. Python writes human diagnostics only to stderr; neither process writes logs onto protocol stdout.
7. A failed child startup produces an actionable error in the TUI.
8. An unexpected child exit moves the UI into a visible failed state and includes bounded diagnostic
   context without exposing known secrets or any remainder of a recognized secret-named multi-part
   credential line.
9. Normal TUI exit terminates and reaps the child process.
10. Tests cover normal startup, startup failure, unexpected exit, and cleanup without invoking a
    real model.
11. Process supervision and exit ownership are documented in TSDoc and Python docstrings where they
    form public or non-obvious lifecycle contracts.

## Validation

- Run Python pytest and Ruff checks.
- Run TUI type checking, linting, and tests.
- Run supervisor tests with controlled fake child commands or fixtures for each required exit path.
- Assert launch preserves safe environment values, removes both Python path overrides without
  mutating the source, and still starts the real runtime with poisoned overrides supplied.
- Seed multi-part authorization and cookie values in stderr and assert the complete physical-line
  values are absent while a following diagnostic remains visible.
- Launch the application against the real minimal Python entry point and verify normal cleanup; this
  test must not use a model, network, or workspace mutation.
- Inspect captured stdout and stderr to prove protocol and diagnostic channels remain separate.

## Documentation impact

Update architecture and process-boundary documentation with launch arguments, workspace resolution,
pipe ownership, startup failure, unexpected exit, and cleanup behavior. Add the developer launch
command and troubleshooting guidance to the README.

## Completion evidence

The [CAH-003 runtime-supervision note](notes/2026-07-15-cah-003-python-runtime-supervision.md)
records the exact shell-free `uv` request, canonical workspace contract, stream reservations,
bounded redacted diagnostics, and EOF-to-process-group cleanup path. Python validation passes all
eight tests, including seven runtime tests. TUI validation passes 46 tests in ten files, including
environment-filtering and complete credential-line redaction regressions plus a real
Node-to-uv-to-Python boundary test that observes both processes through `/proc` and proves both are
gone after cleanup. No test invokes a model, uses the network, or mutates the selected workspace.

## Out of scope

- Parsing versioned protocol messages or implementing a readiness handshake; CAH-004 owns the
  protocol contract.
- Provider calls, transcripts, tools, approvals, or autonomous child restart.
