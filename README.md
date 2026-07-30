# Code Assist Harness

Code Assist Harness is a learning-first, local coding agent for Ubuntu under WSL. Its goal is to
inspect and explain a repository, form a plan, propose controlled file changes, run approved
validation commands, show the resulting diff, and summarize the outcome.

The first release is a personal learning project. Its Python core is deliberately separated from
the terminal UI, model provider, and execution environment so it can later become a reusable
harness library.

## Current status

The repository now contains a cancellable M0 mocked-session path. A supervised Ink/TypeScript parent
launches Python through `uv`, completes the validated protocol version 1 readiness handshake, sends
non-empty tasks as correlated `session.start` commands, and renders three deliberately delayed
assistant deltas before completion. While a session is running, Escape sends one correlated
`session.cancel`; Python cooperatively stops the mock and emits the authoritative terminal outcome.
Pydantic and Zod validate strict, hand-maintained wire contracts on both sides; bounded LF readers
contain malformed lines; shared fixtures prove cross-language parity; and real
Node-to-`uv`-to-Python tests prove streaming, cancellation, repeated sessions, and process cleanup.
The application does **not** yet run an agent loop, read the workspace, or integrate with OpenAI.
CAH-009 is the next dependency-ready unit and will document this first end-to-end execution.

The original LangChain-based direction has been superseded. The project will own its agent loop
directly. LangChain may be considered later as an adapter, but it is not the MVP orchestrator and
core domain types must not depend on it.

The superseded LangChain packages have been removed from Python project metadata and `uv.lock`.
Pydantic v2 is the Python runtime's first boundary-validation dependency. The TUI's Ink, React,
Zod, and development dependencies are kept separately in `tui/package.json` and its committed npm
lockfile.

Start with the [architecture overview](docs/architecture.md), the
[decision records](docs/adr/), and the [dependency-ordered backlog](user-stories/README.md).

## MVP boundary

The MVP will:

- inspect, search, and read workspace files automatically;
- answer repository questions and display an implementation plan;
- stage structured edit proposals and ask before applying a complete edit batch;
- ask before every allowlisted subprocess command;
- display proposed and applied diffs;
- run approved tests and linters;
- support cancellation and clean shutdown; and
- write a human-readable, append-only session record unless disabled.

The MVP will not commit, push, branch, access the network through tools, run multiple agents,
resume sessions, use framework-owned orchestration, use embeddings, or run tools in a container.
Native Windows, macOS, and multiple model providers are also outside the initial scope.

## Architecture at a glance

The application will run entirely inside Ubuntu under WSL:

```text
Ink TUI (TypeScript / Node)
  owns terminal input, rendering, approval presentation, and keyboard cancellation
            |
            | versioned NDJSON: commands on stdin, events on stdout
            v
Python harness runtime
  owns session state, the agent loop, context, policy, approval authority, tools, and transcripts
            |
            +-- provider adapter (OpenAI first)
            +-- workspace reads, staged edits, and approved subprocesses

Python stderr is reserved for human-readable diagnostics.
```

Important boundaries:

- The TUI is a projection of harness events, not the orchestrator or policy authority.
- The TUI presents approval requests; Python binds decisions to actions and authorizes them.
- OpenAI SDK objects stay inside the OpenAI provider adapter.
- Process and model-boundary data is validated with Pydantic v2 in Python and Zod in TypeScript.
- Native reads may run automatically, while edits and every subprocess require informed approval.
- Commands are argument arrays, never shell strings, and approval cannot override the allowlist.
- Transcripts live under the WSL XDG state directory, not in the target workspace.

See [architecture.md](docs/architecture.md) for the complete target structure and ownership model.

## Supported development environment

- Ubuntu under WSL
- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Node 22.22.1, pinned in `.node-version`; the enforced TUI range is `>=22.13.0 <23`
- npm 9 or newer

An OpenAI API key is not needed for the walking skeleton or default tests. A future live-provider
adapter will read `OPENAI_API_KEY` from the environment; credentials and `.env` files must never be
committed.

## Current setup and checks

Install the Python scaffold and the locked TUI dependencies:

```bash
uv sync --dev
npm --prefix tui ci
```

`uv sync --dev` is required before launch. The runtime supervisor verifies that `.venv/pyvenv.cfg`
and an executable `.venv/bin/python` already exist before it invokes `uv`; an unprepared checkout
therefore fails without spawning a child or creating `.venv`. The launch then selects that exact
interpreter and starts it without resolving, downloading, or synchronizing dependencies. Launch the
supervised shell from the repository root inside Ubuntu WSL:

```bash
./scripts/run-tui
```

The directory from which the launcher is invoked is the default workspace. Select a different
single workspace with an absolute path, or with a path relative to that launch directory:

```bash
./scripts/run-tui --workspace /path/to/repository
```

The launcher reports actionable setup guidance when Node or npm is missing, rejects Windows Node or
npm executables reached directly or through a symlink, and checks the supported Node range before
npm or the TypeScript loader runs. The runtime supervisor separately resolves `uv` from its filtered
`PATH`, follows symlinks, rejects paths under `/mnt` and names ending in `.exe`, and validates the
prepared project environment before spawn. The TUI then sends a validated `runtime.initialize`
command, waits for the correctly correlated `runtime.ready` event, and displays the canonical
workspace and runtime state. Type a non-empty task and press Enter to start the deterministic mock.
The conversation renders these three fragments as they arrive:

```text
Mock response:
the task crossed the process boundary
and streamed back successfully.
```

Together they form `Mock response: the task crossed the process boundary and streamed back
successfully.` The session status moves from idle through starting and running to completed; after
completion, another task can run without restarting the application. Entering only whitespace
shows local feedback and sends no command. Input submitted during an active session is preserved
with feedback rather than sent.

The mock pauses for 500 ms before each delta so its lifecycle is visible during manual use. After
`session.started` makes the Python-owned session ID addressable, the running status shows
`Esc to cancel`. Press Escape once to enter `cancelling`; the TUI waits for Python rather than
optimistically declaring success. If cancellation wins, Python emits `session.cancelled`, the TUI
shows `cancelled · ready for another task`, and no later assistant or terminal event is accepted.
If normal completion wins first, `completed` remains authoritative. Repeated or late Escape presses
are harmless local no-ops.

Ctrl+C still exits the whole application rather than cancelling only the session. The lifecycle
sends `runtime.shutdown`; Python drains an accepted bounded mock before exiting, and Node then
closes stdin, terminates the detached process group if it does not exit within bounded grace
periods, and awaits the child close event. `SIGHUP` and `SIGTERM` also request an Ink unmount and
enter this same cleanup path.

Startup troubleshooting:

- If startup says `uv` was not found or resolves to a Windows path, install and select Linux `uv`
  inside Ubuntu WSL, then retry.
- If startup reports that the project environment is unprepared, run `uv sync --dev` in this
  repository and retry. The supervisor checks for `.venv/pyvenv.cfg` and executable
  `.venv/bin/python` before `uv` starts, so this failure does not create or update `.venv`.
- If Python exits with an environment or import diagnostic, rerun `uv sync --dev`; launch never
  updates the lockfile or prepared environment for you. The supervised child intentionally removes
  inherited `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, and every `UV_*` variable; supported project,
  environment, and interpreter choices are supplied explicitly in the argument array instead.
- If workspace selection fails before Ink renders, check that the `--workspace` value exists, is a
  directory, and is accessible from Ubuntu WSL.
- If Python exits after spawning, the TUI shows a bounded, sanitized stderr summary and remains in
  a failed state until Ctrl+C. The supervisor does not restart it automatically.
- If startup reports a protocol failure, inspect the safe failure code. Unsupported, unknown,
  malformed, mismatched, and timed-out readiness messages never enter trusted TUI state; the
  supervisor closes command input and reaps the child during normal cleanup.

Run the current Python checks and build:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

Run the TUI checks individually or together:

```bash
npm --prefix tui run typecheck
npm --prefix tui run lint
npm --prefix tui test
npm --prefix tui run check
```

`npm --prefix tui test` includes `tui/test/runtime-boundary.test.ts`, which launches the genuine
offline `uv`/Python child, exercises streamed completion and cancellation, starts another session,
and verifies cleanup. The `npm --prefix tui run check` command adds TypeScript type checking and
linting around that suite.

The TUI start and test scripts set `TMPDIR=/tmp`. This avoids a WSL environment failure observed
when inherited `TEMP` and `TMP` values named a missing Windows directory. The checks use installed
local packages and do not require a model, credentials, or network access.

CAH-007 will add one repository-wide command covering Python, TypeScript, protocol-contract, and
integration checks without making network requests.

## Current and planned project layout

```text
src/code_assist_harness/  Current runtime and Pydantic protocol boundary; future harness core
tests/                    Current Python tests mirroring source modules
tui/                      Current supervised Ink app, Zod protocol boundary, metadata, and tests
scripts/run-tui           Current WSL-aware launcher and argument-forwarding boundary
protocol/                 Current reviewed cross-language NDJSON fixtures
evals/                    Planned deterministic scenario fixtures
docs/                     Architecture and learning documentation
docs/lessons/             Unit-by-unit learning companions
user-stories/             Roadmap, implementation stories, and planning notes
```

The Python runtime, supervised TUI, protocol messages and fixtures, deterministic mocked streaming,
cooperative session cancellation, conversation projection, documentation, and backlog exist today.
Broader evaluation, provider, workspace-read, tool, policy, transcript, and agent paths remain
planned and are introduced only by the story that needs them.

## Documentation map

- [Architecture](docs/architecture.md)
- [Glossary](docs/glossary.md)
- [Protocol](docs/protocol.md)
- [Agent loop](docs/agent-loop.md)
- [Context engineering](docs/context-engineering.md)
- [Tool system](docs/tool-system.md)
- [Safety model](docs/safety-model.md)
- [Evaluation](docs/evaluation.md)
- [Unit lessons](docs/lessons/README.md)
- [User-story backlog](user-stories/README.md)

Documentation is part of the product. Public Python APIs use Google-style docstrings, meaningful
exported TypeScript contracts use TSDoc, and behavioral work updates the relevant conceptual
document alongside code and tests.
