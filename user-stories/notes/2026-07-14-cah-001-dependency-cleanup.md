# 2026-07-14 CAH-001 dependency cleanup

## Purpose

Complete CAH-001 by making project metadata and the lockfile agree with ADR 0001. The project owns
its agent loop, so unused LangChain framework packages should not remain installed merely as a
trace of the superseded architecture.

## Decisions retained

- Keep the runtime dependency list empty until an implementation story introduces a package that
  is needed at a real process, provider, or validation boundary.
- Do not add an OpenAI SDK, Pydantic, Ink, Zod, or another future dependency as part of cleanup.
- Regenerate `uv.lock` with `uv`; never edit the lockfile by hand.
- Preserve historical notes that describe the original scaffold. Update active status surfaces
  instead of rewriting dated observations.
- Keep CAH-008 open. Removing dependencies completes CAH-001 but does not enable Ruff's planned
  Google-style public-docstring rules.

## Work completed

`uv remove langchain langchain-openai` removed both direct dependencies and their unused transitive
graph. `pyproject.toml` now declares no runtime dependencies. The regenerated lockfile contains the
local project, pytest and Ruff, and the packages required by those development checks.

The README, story index, lesson index, CAH-001 story, and CAH-001 lesson now report the completed
state. No runtime, protocol, TUI, provider, tool, subprocess, or agent behavior was added.

## Issues encountered

- `uv` was not installed in the WSL environment. Version 0.11.28 was installed with Astral's
  official standalone installer and `UV_NO_MODIFY_PATH=1`, so the installer did not edit a shell
  profile.
- The first sandboxed `uv build` could not resolve the declared Hatchling build backend because
  DNS access to PyPI was restricted. Repeating the same build with package-index access succeeded.
  This was an environment restriction, not a project dependency or source failure.
- Removing the framework packages also removed their transitive packages from the local virtual
  environment. That is expected because no current code imports them.

## Validation evidence

The completed tree passed:

```text
uv lock --check                         Resolved 8 packages
uv run pytest                           1 passed
uv run ruff check .                     All checks passed
uv run ruff format --check .            2 files already formatted
uv build                                source distribution and wheel built
git diff --check                        no whitespace errors
```

An active-claim search found no package metadata or current-status text that describes LangChain as
the MVP orchestrator. Remaining LangChain references are intentional: they record the superseded
decision, prohibit framework ownership in the MVP, or describe a possible future adapter.

## Next unit

CAH-008 is the next dependency-ready unit. It should enable and document the smallest useful Ruff
docstring policy without changing runtime behavior. CAH-002 remains blocked on CAH-008.
