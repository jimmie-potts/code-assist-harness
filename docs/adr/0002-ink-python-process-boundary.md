# ADR 0002: Use an Ink and Python process boundary

- **Status:** Accepted
- **Date:** 2026-07-13
- **Decision scope:** Terminal ownership, runtime ownership, and supported environment

## Context

The product needs a keyboard-first interface that can render streamed conversation, plans, tool
calls, approvals, errors, and multi-file diffs. Ink provides React-style terminal composition and
component testing. The reusable harness core and its existing project scaffold are Python.

Putting both responsibilities into either process would force the user interface to own domain
decisions or force the Python core to adopt a less suitable interface stack. The boundary also
needs a single supported environment so early process, path, signal, and terminal behavior can be
understood without a platform matrix.

## Decision

The application will consist of two cooperating processes running inside Ubuntu under WSL:

- a TypeScript/Node Ink process owns the terminal; and
- a Python 3.12 process owns the harness runtime and core behavior.

The Ink process starts Python as a child through `uv`, supervises its lifetime, and terminates it
when the TUI exits. Node and Python exchange Linux paths; neither process crosses into a
native-Windows runtime. Native Windows and macOS support are outside the MVP.

The current launch directory is the default workspace. A `--workspace PATH` argument selects a
different workspace explicitly. There is exactly one workspace root per runtime process, and the
resolved path is passed to Python rather than inferred from the child's incidental working
directory. Multi-root operation is deferred.

The child standard streams have exclusive responsibilities:

| Stream | Direction | Responsibility |
| --- | --- | --- |
| stdin | Ink to Python | Versioned protocol commands |
| stdout | Python to Ink | Versioned protocol events only |
| stderr | Python to terminal supervision | Human-readable diagnostics |

The TUI is a projection of Python events. It owns input handling, rendering, approval presentation,
keyboard cancellation, and visible child-process errors. It does not decide whether a tool is
allowed, whether an edit is safe, how context is built, or when an agent turn is complete.

The Node project uses npm, commits `package-lock.json`, and declares a repository Node version
compatible with the selected Ink release. Unsupported Node versions fail with actionable setup
guidance rather than obscure syntax or runtime errors.

## Lifecycle requirements

- Failure to start the child is shown as an actionable TUI failure.
- Unexpected child exit moves the TUI to a visible failed state.
- TUI exit terminates an active child and does not leave terminal-rendering artifacts.
- `Ctrl+C` has documented cancellation and exit semantics.
- Child stdout is reserved for protocol data and never displayed as an unstructured log; CAH-003
  drains it opaquely and CAH-004 owns parsing.
- Child stderr diagnostics cannot corrupt the protocol stream.
- A second session may start after a completed first session without restarting the application.

## Consequences

### Benefits

- Ink can specialize in interactive rendering while Python remains the reusable behavioral core.
- The same Python core can later serve a CLI, web UI, test runner, or direct library caller.
- Child-process failure, shutdown, and protocol behavior are visible architectural concerns and
  can be tested at the real language boundary.
- Restricting the MVP to Ubuntu under WSL removes early cross-platform path and signal ambiguity.

### Costs and risks

- Development now includes two language ecosystems, two lockfiles, and cross-language contracts.
- Streaming, backpressure, process exit, and cancellation must be handled correctly across pipes.
- Node and Python startup errors require translation into one coherent user experience.
- Contributors need compatible Python, `uv`, Node, and npm versions inside WSL.

These costs are addressed with a small protocol, shared fixtures, one repository-wide check, and
an end-to-end mocked integration test before provider behavior is introduced.

## Alternatives considered

### Implement the entire application in Python

Rejected because the selected interface is Ink and the separation between interface projection and
reusable harness behavior is intentional.

### Put orchestration in the Node process

Rejected because policy and loop semantics would become tied to the TUI and would have to be
reimplemented for another caller.

### Run Python as a persistent daemon

Rejected for the MVP because service discovery, stale processes, authentication, and lifecycle
management add complexity without helping the first single-user vertical slices.

### Support native Windows from the beginning

Rejected because divergent paths, signals, executables, and terminal behavior would expand the
test matrix before the core architecture is proven.

## Implementation status

CAH-002 implements terminal ownership and WSL runtime validation. CAH-003 now implements the
physical process boundary:

- `scripts/run-tui` preserves the canonical caller directory and forwards arguments without
  combining them into a shell string;
- `tui/src/workspace.ts` resolves either that directory or one `--workspace PATH` to an existing,
  symlink-free directory before spawn;
- `tui/src/runtime-supervisor.ts` launches `uv` with `shell: false`, three pipes, and a detached
  process group. Its exact argument array uses `run --project REPOSITORY_ROOT`, then `--frozen`,
  `--no-cache`, `--no-sync`, `--offline`, `--no-env-file`, `--no-progress`, and
  `--no-python-downloads`, followed by
  `-- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE`. Its child environment
  copies the parent except for `PYTHONPATH` and `PYTHONHOME`, which could redirect module loading;
- `src/code_assist_harness/runtime.py` validates that explicit workspace, owns one `asyncio` loop,
  writes nothing to stdout, and exits cleanly when its stdin pipe reaches EOF;
- `tui/src/runtime-diagnostics.ts` retains a bounded stderr tail, redacts distinctive inherited
  environment values plus complete physical-line values for secret-named credential headers and
  assignments, strips terminal controls, and bounds the visible summary again; and
- after Ink exits and restores the terminal, `tui/src/run-application.tsx` closes stdin, escalates
  to `SIGTERM` and `SIGKILL` for the detached uv/Python process group when necessary, and waits for
  `close` before cleanup is complete. Parent `SIGHUP` and `SIGTERM` first request an Ink unmount so
  they enter that same cleanup path.

An operating-system spawn currently moves the display to `running`; it is not evidence that Python
accepted a protocol command. Any unrequested close, even with exit code zero, produces a visible
failed state, and the supervisor does not restart the child. Protocol versioning, readiness,
command parsing, and event validation remain CAH-004 work.
