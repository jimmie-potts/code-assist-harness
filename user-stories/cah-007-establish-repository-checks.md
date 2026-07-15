# CAH-007 - Establish repository-wide checks

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-009
- **Lesson:** [Repository-wide checks](../docs/lessons/cah-007-repository-checks.md)

## User story

> As a contributor, I want one repeatable validation workflow so that Python, TypeScript, protocol,
> documentation, and integration regressions are caught together.

## Scope

- Add one documented repository command for all non-live checks.
- Preserve focused Python and TUI commands for local iteration.
- Run protocol fixtures in both languages and the real model-free process-boundary integration.
- Add Linux CI with pinned Python and Node setup and lockfile-based installation.

## Acceptance criteria

1. One command, exposed by the repository check script, runs every required non-live check and fails
   if any constituent check fails.
2. Existing pytest and Ruff lint/format commands remain usable independently.
3. The TUI exposes independent type-check, lint, format-check if configured, and test commands.
4. Shared protocol fixtures are parsed and validated by Python and TypeScript tests.
5. The model-free Node-Python integration tests run from the unified workflow.
6. Default checks make no OpenAI or other network request and require no API key.
7. `uv.lock` and `tui/package-lock.json` are committed and CI installs reproducibly from them.
8. Linux CI runs supported Python and Node versions and invokes the same unified command developers
   use under WSL.
9. The README documents WSL prerequisites, setup, focused checks, unified checks, and troubleshooting.
10. CI and local test output clearly identifies the failing ecosystem or integration layer.
11. Documentation examples or links introduced in M0 receive an automated check when a lightweight,
    maintainable option is available; any intentional omission is recorded.

## Validation

- Run the unified check script from a clean dependency installation.
- Run each Python and TUI command independently and compare it with the unified workflow.
- Run checks without `OPENAI_API_KEY` and with tests configured to reject accidental network use.
- Inspect CI configuration to confirm it invokes the repository script rather than duplicating a
  divergent list of commands.
- Intentionally fail one Python, TypeScript, fixture, and integration assertion in separate temporary
  local changes to verify failures propagate; discard those changes before completion.

## Documentation impact

Update README development and CI guidance, `AGENTS.md` validation expectations, and the definition
of done. Document how to run focused versus full checks and why live-provider tests are excluded.

## Out of scope

- Live-provider smoke tests.
- Deployment, release, or publishing workflows.
- Broad monorepo tooling introduced solely to coordinate two projects.
