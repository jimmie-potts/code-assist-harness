# CAH-003 - Start and supervise the Python runtime

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-002

## User story

> As a user, I want the TUI to start the Python harness automatically so that the application
> behaves as one tool.

## Scope

- Add a minimal Python runtime entry point suitable for child-process execution.
- Add a TUI child supervisor that invokes Python through `uv` with an explicit workspace path.
- Reserve child stdin and stdout for the forthcoming protocol while forwarding or surfacing stderr
  diagnostics separately.
- Define cleanup and visible failure behavior for startup, unexpected exit, and TUI shutdown.

## Acceptance criteria

1. The TUI starts the Python runtime through `uv`, without shell interpolation.
2. The launch directory is the default workspace and an optional `--workspace PATH` is resolved and
   passed explicitly to Python.
3. One process serves exactly one workspace.
4. Child stdin and stdout are pipes reserved for protocol traffic.
5. Python writes human diagnostics only to stderr; neither process writes logs onto protocol stdout.
6. A failed child startup produces an actionable error in the TUI.
7. An unexpected child exit moves the UI into a visible failed state and includes bounded diagnostic
   context without exposing secrets.
8. Normal TUI exit terminates and reaps the child process.
9. Tests cover normal startup, startup failure, unexpected exit, and cleanup without invoking a real
   model.
10. Process supervision and exit ownership are documented in TSDoc and Python docstrings where they
    form public or non-obvious lifecycle contracts.

## Validation

- Run Python pytest and Ruff checks.
- Run TUI type checking, linting, and tests.
- Run supervisor tests with controlled fake child commands or fixtures for each required exit path.
- Launch the application against the real minimal Python entry point and verify normal cleanup; this
  test must not use a model, network, or workspace mutation.
- Inspect captured stdout and stderr to prove protocol and diagnostic channels remain separate.

## Documentation impact

Update architecture and process-boundary documentation with launch arguments, workspace resolution,
pipe ownership, startup failure, unexpected exit, and cleanup behavior. Add the developer launch
command and troubleshooting guidance to the README.

## Out of scope

- Parsing versioned protocol messages beyond any minimal readiness handshake needed to test process
  lifetime; CAH-004 owns the protocol contract.
- Provider calls, transcripts, tools, approvals, or autonomous child restart.
