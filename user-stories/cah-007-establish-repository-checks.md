# CAH-007 - Establish repository-wide checks

- **Status:** Done
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-009
- **Lesson:** [Repository-wide checks](../docs/lessons/cah-007-repository-checks.md)
- **Visual companion:** [Repository-wide checks](../docs/lessons/assets/cah-007-repository-checks.pptx)

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

## Delivered evidence

- `./scripts/check` runs 11 fail-fast labeled stages from any working directory with uv/npm offline,
  provider credentials removed, top-level Python/Node process-network guards preloaded, and the
  prepared dependency environments left unchanged.
- The first stage uses `uv sync --check --locked --offline` to reject a missing or drifted Python
  environment, and every Python tool invocation uses `--no-sync`.
- The clean gate passed 149 Python tests across core, fixture, and repository-policy stages, plus 159
  TypeScript tests across core, fixture, and real Node-Python integration stages.
- Script tests prove exact order, offline settings, network-guard preloads, credential removal,
  labels, and nonzero propagation. Four restored transient probes stopped at Python tests, Python
  fixtures, TUI tests, and the real integration layer respectively.
- Repository policy tests validate local Markdown targets and anchors, the complete TUI package-lock
  graph, the top-level Python/Node runtime guards, and the current M0 Python/TypeScript source-network
  denylist, including synthetic failure cases. The lock test rejects a missing transitive entry
  without reading or changing `node_modules`. The real Python child retains the runtime supervisor's
  ambient-selector sanitization and is covered by source policy rather than `PYTHONPATH` injection.
- [The Linux workflow](../.github/workflows/check.yml) pins its Ubuntu image, Python/Node version
  files, uv release, and action commits; installs through `uv sync --locked` and `npm ci`; and invokes
  the same repository script. Remote workflow status remains pull-request evidence rather than a
  local completion claim.
- The linked 10-slide visual companion was rendered and inspected slide by slide and passed the
  presentation overflow test with no overflow detected.

## Documentation impact

README development and CI guidance, `AGENTS.md` validation and visual-lesson expectations, the
definition of done, architecture/evaluation guidance, the lesson, and the backlog now describe the
implemented gate. Focused checks remain documented, while live-provider tests remain excluded.

## Out of scope

- Live-provider smoke tests.
- Deployment, release, or publishing workflows.
- Broad monorepo tooling introduced solely to coordinate two projects.
