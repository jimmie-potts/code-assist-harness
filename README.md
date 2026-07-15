# Code Assist Harness

Code Assist Harness is a learning-first, local coding agent for Ubuntu under WSL. Its goal is to
inspect and explain a repository, form a plan, propose controlled file changes, run approved
validation commands, show the resulting diff, and summarize the outcome.

The first release is a personal learning project. Its Python core is deliberately separated from
the terminal UI, model provider, and execution environment so it can later become a reusable
harness library.

## Current status

The repository now contains a minimal Python package and a launchable static Ink/TypeScript shell.
The shell renders the conversation-first frame, validates its WSL Node runtime before loading Ink,
and exits cleanly on Ctrl+C. It does **not** yet start Python, define the NDJSON protocol, run an
agent loop, access a workspace, or integrate with OpenAI. The next unit, CAH-003, adds Python child
startup and supervision without adding model behavior.

The original LangChain-based direction has been superseded. The project will own its agent loop
directly. LangChain may be considered later as an adapter, but it is not the MVP orchestrator and
core domain types must not depend on it.

The superseded LangChain packages have been removed from Python project metadata and `uv.lock`.
Python runtime dependencies remain empty. The TUI's Ink, React, and development dependencies are
kept separately in `tui/package.json` and its committed npm lockfile.

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

Launch the static shell from the repository root inside Ubuntu WSL:

```bash
./scripts/run-tui
```

The launcher reports actionable setup guidance when Node or npm is missing, rejects a Windows Node
executable reached through WSL, and checks the supported Node range before npm or the TypeScript
loader runs. The initial shell is intentionally not connected to Python or task submission. Press
Ctrl+C to let Ink unmount and restore the terminal.

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

The TUI start and test scripts set `TMPDIR=/tmp`. This avoids a WSL environment failure observed
when inherited `TEMP` and `TMP` values named a missing Windows directory. The checks use installed
local packages and do not require a model, credentials, or network access.

CAH-007 will add one repository-wide command covering Python, TypeScript, protocol-contract, and
integration checks without making network requests.

## Current and planned project layout

```text
src/code_assist_harness/  Current minimal Python package; future harness core and runtime
tests/                    Current Python tests mirroring source modules
tui/                      Current static Ink application, npm metadata, and TypeScript tests
scripts/run-tui           Current WSL-aware TUI launcher
protocol/                 Planned shared NDJSON fixtures
evals/                    Planned deterministic scenario fixtures
docs/                     Architecture and learning documentation
docs/lessons/             Unit-by-unit learning companions
user-stories/             Roadmap, implementation stories, and planning notes
```

The Python scaffold, static TUI, documentation, and backlog exist today. Protocol, evaluation,
provider, tool, and agent paths remain planned and are introduced only by the story that needs them.

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
