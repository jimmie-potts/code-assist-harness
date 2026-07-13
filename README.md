# Code Assist Harness

A Python foundation for building an agentic coding harness with LangChain and
the OpenAI API.

This initial version provides the project structure, dependencies, and quality
tooling. It intentionally does not implement an agent or make API requests yet.

## Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- An OpenAI API key for future API-backed features

## Setup

Install the project and its development dependencies:

```bash
uv sync --dev
```

Export your OpenAI API key in your shell:

```bash
export OPENAI_API_KEY="your-api-key"
```

Alternatively, copy the environment template to a local, ignored file and load
it into your shell before running future API-backed commands:

```bash
cp .env.example .env
set -a
source .env
set +a
```

Never commit `.env` or an API key.

## Development checks

Run the test suite:

```bash
uv run pytest
```

Check linting and formatting:

```bash
uv run ruff check .
uv run ruff format --check .
```

## Project layout

```text
src/code_assist_harness/  Python package
tests/                    Test suite
```
