# Code Assist Harness

Code Assist Harness is a learning-first, local coding agent for Ubuntu under WSL. Its goal is to
inspect and explain a repository, form a plan, propose controlled file changes, run approved
validation commands, show the resulting diff, and summarize the outcome.

The first release is a personal learning project. Its Python core is deliberately separated from
the terminal UI, model provider, and execution environment so it can later become a reusable
harness library.

## Current status

The repository is at the architecture and backlog stage. It currently contains a minimal Python
package and development checks; it does **not** yet contain the Ink TUI, Python runtime, agent loop,
workspace tools, or an OpenAI integration. The first implementation milestone is a model-free
walking skeleton that streams a mocked session across the real Node-Python process boundary.

The original LangChain-based direction has been superseded. The project will own its agent loop
directly. LangChain may be considered later as an adapter, but it is not the MVP orchestrator and
core domain types must not depend on it.

The initial scaffold still declares unused LangChain packages in `pyproject.toml` and `uv.lock`.
Their removal and the corresponding lockfile refresh are tracked by
[CAH-001](user-stories/cah-001-record-architecture-decisions.md), not an architectural exception.

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
- Node and npm once the Ink shell is introduced by CAH-002; that story will add a repository Node
  version pin and `package-lock.json`

An OpenAI API key is not needed for the walking skeleton or default tests. A future live-provider
adapter will read `OPENAI_API_KEY` from the environment; credentials and `.env` files must never be
committed.

## Current setup and checks

Install the current Python scaffold:

```bash
uv sync --dev
```

Run its tests, lint checks, formatting check, and build:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv build
```

CAH-007 will add one repository-wide command covering Python, TypeScript, protocol-contract, and
integration checks without making network requests.

## Planned project layout

```text
src/code_assist_harness/  Python harness core and runtime
tests/                    Python tests mirroring source modules
tui/                      Ink application and TypeScript tests
protocol/                 Shared NDJSON fixtures
evals/                    Deterministic scenario fixtures
docs/                     Architecture and learning documentation
user-stories/             Roadmap, implementation stories, and planning notes
scripts/                  Development and validation entry points
```

Only the Python scaffold, documentation, and backlog exist today. Planned paths are introduced by
the user story that needs them rather than as empty placeholders.

## Documentation map

- [Architecture](docs/architecture.md)
- [Glossary](docs/glossary.md)
- [Protocol](docs/protocol.md)
- [Agent loop](docs/agent-loop.md)
- [Context engineering](docs/context-engineering.md)
- [Tool system](docs/tool-system.md)
- [Safety model](docs/safety-model.md)
- [Evaluation](docs/evaluation.md)
- [User-story backlog](user-stories/README.md)

Documentation is part of the product. Public Python APIs use Google-style docstrings, meaningful
exported TypeScript contracts use TSDoc, and behavioral work updates the relevant conceptual
document alongside code and tests.
