# CAH-002 - Bootstrap the Ink application

- **Status:** Planned
- **Milestone / epic:** M0 - Walking skeleton / E0 - Architecture and WSL walking skeleton
- **Dependencies:** CAH-001, CAH-008
- **Lesson:** [Ink application shell](../docs/lessons/cah-002-ink-application-shell.md)

## User story

> As a developer, I want to launch an Ink application in WSL so that I have a real interface shell
> for subsequent vertical slices.

## Scope

- Add an npm-managed TypeScript/Ink project under `tui/` with a committed `package-lock.json`.
- Pin or declare a compatible Node runtime for the repository and fail clearly on unsupported
  versions.
- Build the static conversation-first application shell and terminal lifecycle.
- Add type checking, linting, and an initial rendering test without Python or model integration.

## Acceptance criteria

1. A documented repository command launches the application from Ubuntu under WSL.
2. The initial screen shows the application title, an empty conversation area, an input area, and a
   status line.
3. The TUI is implemented in TypeScript with meaningful exported contracts documented using TSDoc.
4. The repository pins or clearly declares its supported Node version, and npm metadata enforces a
   compatible range.
5. Missing or unsupported Node versions produce an actionable setup error before rendering.
6. Ctrl+C exits cleanly without leaving terminal rendering artifacts.
7. A test using `ink-testing-library` verifies the important initial screen content.
8. Type checking, linting, and TUI tests complete without network access.
9. No Python child, provider, workspace operation, or subprocess approval behavior is introduced.

## Validation

- Install from the committed lockfile with `npm --prefix tui ci` in a prepared development or CI
  environment.
- Run the TUI type-check, lint, and test scripts documented in `tui/package.json`.
- Run the application in WSL, verify the initial screen, and exit with Ctrl+C.
- Exercise the unsupported-Node check in an isolated test without changing the developer's active
  runtime.
- Run the existing Python checks to confirm the new project does not regress them.

## Documentation impact

Update the README prerequisites, setup, launch command, project layout, and TUI test commands.
Document terminal ownership, static shell responsibilities, Node pinning, and the initial keyboard
contract.

## Out of scope

- Starting Python or defining NDJSON messages.
- Sending user tasks or rendering streamed assistant output.
- Model, filesystem, transcript, policy, or approval behavior.
