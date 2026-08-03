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

The Ink process starts Python as a child through a resolved and prevalidated Linux `uv` executable,
supervises its lifetime, and terminates it when the TUI exits. Node and Python exchange Linux paths;
neither process crosses into a native-Windows runtime. Native Windows and macOS support are outside
the MVP.

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
- Child stdout is reserved for validated protocol events and is never displayed as an unstructured
  log; an unknown, malformed, or unexpected event fails closed.
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

CAH-002 implements terminal ownership and WSL runtime validation, CAH-003 implements the physical
process boundary, CAH-004 gives that boundary its first validated protocol, CAH-005 exercises a
complete mocked session across it, and CAH-006 adds authoritative cancellation:

- `scripts/run-tui` preserves the canonical caller directory and forwards arguments without
  combining them into a shell string;
- `tui/src/workspace.ts` resolves either that directory or one `--workspace PATH` to an existing,
  symlink-free directory before spawn;
- `tui/src/runtime-supervisor.ts` resolves `uv` from a filtered `PATH`, follows symlinks, rejects a
  resolved path under `/mnt` or a name ending in `.exe`, and requires `.venv/pyvenv.cfg` plus an
  executable `.venv/bin/python` before spawn. A preflight failure cannot invoke `uv` or create the
  environment. The supervisor launches the validated path with `shell: false`, three pipes, and a
  detached process group. Its exact argument array uses `run --project REPOSITORY_ROOT`, then
  `--frozen`, `--no-cache`, `--no-sync`, `--offline`, `--no-env-file`, `--no-progress`, and
  `--no-python-downloads`, selects the prepared interpreter with `--python VENV_PYTHON`, and follows
  with
  `-- python -E -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE`. Its child environment
  copies the parent except for `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `SSLKEYLOGFILE`, and all
  `UV_*` variables; the supported project, environment, and interpreter choices are supplied
  explicitly in argv, while `-E` makes Python ignore any remaining `PYTHON*` variables;
- `src/code_assist_harness/runtime.py` validates that explicit workspace, owns one `asyncio` loop,
  parses bounded protocol commands, starts at most one `MockSession` task, routes a matching
  `session.cancel`, writes validated events to stdout, and drains accepted mock work before clean
  `runtime.shutdown` or stdin EOF;
- `tui/src/runtime-diagnostics.ts` retains a bounded stderr tail, drops a leading partial physical
  line when byte truncation cuts one, redacts distinctive inherited environment values plus
  complete physical-line values for recognized separator-delimited and common camel-case or
  concatenated credential names, strips terminal controls, and bounds the visible summary again;
- after Ink exits and restores the terminal, `tui/src/run-application.tsx` closes stdin, escalates
  to `SIGTERM` and `SIGKILL` for the detached uv/Python process group when necessary, and waits for
  `close` before cleanup is complete. Parent `SIGHUP` and `SIGTERM` first request an Ink unmount so
  they enter that same cleanup path.
- `src/code_assist_harness/protocol/` and `tui/src/protocol.ts` validate strict version 1 messages;
  shared fixtures prove agreement between Pydantic and Zod, and bounded LF readers contain bad
  physical lines;
- after spawn, the supervisor sends `runtime.initialize` and remains `starting` until a matching
  `runtime.ready` confirms the canonical workspace. Invalid or unexpected stdout becomes a visible
  `protocol-failed` state and closes command input;
- after readiness, `tui/src/runtime-supervisor.ts` sends correlated `session.start` commands and
  validates the active event tape before `tui/src/session-state.ts` reduces it. `tui/src/app.tsx`
  preserves editable input while rendering three intermediate accumulations and completion;
- Escape calls `PythonRuntimeSupervisor.cancelSession` only for an addressable running session. The
  TUI projects `cancelling`, while `MockSession` owns cooperative checkpoint interruption and the
  serialized choice between one `session.cancelled` and an already-winning `session.completed`;
  Ctrl+C remains full application exit; and
- `tui/test/runtime-boundary.test.ts` proves completion and cancellation through the real
  Node-to-`uv`-to-Python process tree, another session after cancellation, unchanged workspace
  contents, and process reaping.

An operating-system spawn establishes only the physical process; it is not evidence that Python
accepted a protocol command. Any unrequested close, even with exit code zero, produces a visible
failed state, and the supervisor does not restart the child. CAH-005 proves the deterministic
streaming boundary; CAH-006 proves cancellation without moving lifecycle authority into Ink.
