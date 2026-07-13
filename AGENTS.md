# Repository Guidelines

## Project Structure & Module Organization

Application code belongs in `src/code_assist_harness/`. Keep modules focused and expose only
intentional package APIs from `__init__.py`. Tests live in `tests/` and should mirror the source
area they cover, for example `src/code_assist_harness/tools.py` and `tests/test_tools.py`.
Project metadata, dependencies, and tool settings are defined in `pyproject.toml`; commit
`uv.lock` whenever dependency resolution changes. The repository currently has no static assets.

## Build, Test, and Development Commands

- `uv sync --dev` creates the Python 3.12 environment and installs runtime and development
  dependencies from the lockfile.
- `uv run pytest` runs the complete test suite.
- `uv run ruff check .` checks lint rules and import ordering.
- `uv run ruff format --check .` verifies formatting without rewriting files. Use
  `uv run ruff format .` to apply formatting.
- `uv build` creates source and wheel distributions under the ignored `dist/` directory.

## Coding Style & Naming Conventions

Use four-space indentation, type hints for public functions, and a maximum line length of 100
characters. Follow `snake_case` for modules, functions, and variables; `PascalCase` for classes;
and `UPPER_CASE` for constants. Keep imports sorted and prefer small, explicit functions over
hidden global state. Ruff (`E`, `F`, `I`, and `UP`) is the enforced style authority.

## Testing Guidelines

Use pytest. Name test files `test_*.py` and test functions `test_*`. Add focused regression tests
with every behavior change. Unit tests must not make live OpenAI requests; replace network and
model interactions with fakes or mocks. No coverage threshold is configured, so prioritize
meaningful branch and failure-path coverage.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects consistent with history, such as `Initialize agent harness`.
Keep each commit to one logical change. Branch names should be descriptive, such as
`agent/add-tool-registry`. Pull requests must explain what changed, why it changed, and developer
impact; list validation commands and link relevant issues. Include screenshots only for visible UI
changes. Open work as a draft and mark it ready after all checks pass.

## Security & Configuration

Never commit API keys or `.env`. Copy `.env.example` locally and provide `OPENAI_API_KEY` through
the environment. Keep sample values blank or unmistakably fake, and avoid logging credentials or
full provider responses that may contain sensitive data.
