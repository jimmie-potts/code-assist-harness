# CAH-002 lesson: Ink application shell

- **Unit:** CAH-002
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; no `tui/` project, Node pin, or Ink screen exists yet
- **Story:** [CAH-002](../../user-stories/cah-002-bootstrap-ink-application.md)
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md) and
  [architecture overview](../architecture.md#process-boundary)

> This lesson describes accepted process ownership and planned CAH-002 behavior. It does not
> describe a shipped TUI. Python child startup begins in CAH-003, not this unit.

## Quick summary

This unit builds the static TypeScript/Ink shell that will eventually project harness events. It
teaches terminal rendering, input ownership, lifecycle cleanup, reproducible Node tooling, and
render-focused testing without introducing Python, protocol, model, or policy behavior.

## Learning objectives

After completing this unit, you should be able to:

- explain how a React renderer owns a terminal frame and keyboard input;
- separate presentational UI contracts from orchestration and safety decisions;
- pin and enforce a compatible Node runtime with an npm lockfile;
- handle normal exit so the terminal is restored predictably.

## Why this unit matters

The walking skeleton needs a real terminal parent before process and protocol complexity arrives.
Building the shell independently makes rendering and lifecycle bugs observable without confusing
them with child-process failures or malformed events.

It also establishes a lasting rule: the TUI may present an approval later, but Python decides
whether an action is allowed and whether a session is complete.

## Key concepts

### Ink is a renderer, not the harness

Ink maps React components to terminal output. Components render conversation, input, and status;
they must not acquire provider, filesystem, command-policy, or session-authority responsibilities.

### A terminal frame is transient state

Interactive output is repeatedly redrawn. Cleanup must unmount the application and restore cursor
and input behavior, especially on `Ctrl+C`, rather than treating exit like printing one final line.

### Runtime pinning makes failures intentional

The selected Ink release determines a compatible Node range. A repository version file and
`package.json` engine metadata should agree, while an early check turns incompatibility into an
actionable message before React renders.

### A lockfile records dependency resolution

`package-lock.json` captures the dependency graph installed by npm. Committing it lets CI use
`npm ci` and separates deliberate upgrades from incidental resolution drift.

### Render tests assert user-observable contracts

The initial test should check the title, empty conversation state, input area, and status line. It
should avoid snapshots of incidental whitespace unless spacing itself is the behavior under test.

## Architecture and design

```text
keyboard input
      |
      v
TypeScript CLI -> Ink App -> title / conversation / input / status
      |
      +-> clean unmount and process exit

No Python child, NDJSON, provider, tool, or workspace operation exists in CAH-002.
```

| Concern | CAH-002 owner | Deferred owner |
| --- | --- | --- |
| Terminal rendering and input | Ink application | — |
| Node compatibility check | TUI CLI bootstrap | — |
| Python process lifetime | Not present | CAH-003 supervisor |
| Wire parsing | Not present | CAH-004 protocol boundary |
| Session and policy decisions | Not present | Python harness core |

The planned invariants are:

- production TUI code is TypeScript and meaningful exports use TSDoc;
- unsupported Node versions fail before terminal rendering begins;
- `Ctrl+C` exits cleanly without leaving rendering artifacts;
- components do not invent session, policy, or approval authority;
- initial screen behavior has a focused `ink-testing-library` test; and
- type checking, linting, and tests need no network or model access.

## Practical walkthrough

1. **Choose the compatible runtime.** At implementation time, confirm the selected stable Ink
   package's Node requirement. Add one repository version pin and a matching `engines.node` range.
2. **Create `tui/package.json`.** Use npm scripts for launch, type checking, linting, and tests.
   Commit the resulting `package-lock.json`; avoid a monorepo orchestrator for this slice.
3. **Configure TypeScript.** Keep CLI entry, application component, and tests type checked. Define
   whether JSX and module settings match the selected Node and test runner versions.
4. **Build the static shell.** Render an application title, empty conversation area, input area,
   and status line. The status may be a local static value such as `idle` in this story.
5. **Handle exit.** Connect `Ctrl+C` to one cleanup path that unmounts Ink and exits successfully.
   Document any exported keyboard contract with TSDoc.
6. **Test the frame.** Render the app with `ink-testing-library`, inspect the last frame, and assert
   the important labels and empty state.
7. **Test the version guard.** Inject or isolate a fake unsupported version; never require a
   developer to replace their active Node installation to exercise the failure.
8. **Validate manually in WSL.** Launch with the documented command, resize if useful, and confirm
   exit returns the cursor and prompt to normal.

## Failure scenarios to study

### Unsupported Node fails deep inside Ink

**Symptom:** a syntax or module-loader error appears before the screen. **Boundary:** CLI bootstrap.
**Safe outcome:** detect the version first and show the supported range plus setup action.
**Evidence:** an isolated test covers an unsupported version.

### `Ctrl+C` leaves a damaged prompt

**Symptom:** the cursor remains hidden or the next shell prompt overwrites the frame. **Boundary:**
Ink lifecycle cleanup. **Safe outcome:** unmount once, restore terminal state, and exit. **Evidence:**
a manual WSL check complements a cleanup unit test.

## Production expansion

### Example enterprise scenario

Suppose a terminal client is distributed to thousands of engineers across several supported Linux
distributions, with staged releases, accessibility expectations, support telemetry, and older
terminal emulators. Rendering remains one component, but packaging and support become products of
their own.

### Typical production capabilities and tools

- [Ink](https://github.com/vadimdemedes/ink) represents component-based terminal rendering, while
  adding React and Node dependency upgrades plus terminal-compatibility testing.
- [ink-testing-library](https://github.com/vadimdemedes/ink-testing-library) represents isolated
  rendering and input tests for terminal components, but fixtures and render assertions must track
  Ink and terminal behavior.
- [npm lockfiles](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/) represent
  repeatable dependency resolution and CI installation, at the cost of dependency-update review and
  ongoing security patching.
- [OpenTelemetry for JavaScript](https://opentelemetry.io/docs/languages/js/) represents optional
  support telemetry, while instrumentation, collector or backend operation, and privacy review add
  ongoing cost.

These tools illustrate capabilities; the last capability is not an MVP dependency or endorsement.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Platform | Ubuntu under WSL | Tested terminal and OS support matrix |
| Distribution | Run from one checkout | Signed packages and staged release channels |
| Rendering tests | Focused initial frame | Compatibility, resize, input, and accessibility suites |
| Cost | One npm project and lockfile | Packaging, telemetry, release, and support ownership |

### Trade-offs and graduation signals

Wider distribution improves accessibility and supportability but multiplies terminal, OS, upgrade,
and privacy requirements. Graduate when there are real external users, recurring environment bugs,
or release rollback needs—not simply because production tools exist.

## Practical exercises

1. Sketch the smallest component tree that renders the four required screen regions.
2. Write a test assertion set that survives color or spacing changes but detects a missing status.
3. Model an unsupported Node check as a pure function and list its actionable error fields.

## Key takeaways

- Ink owns terminal projection and input, not agent orchestration or safety policy.
- Runtime compatibility and clean terminal teardown are user-visible contracts.
- The first shell remains static and model-free so rendering failures are isolated.

## Glossary

- **Frame:** The current terminal output produced by the renderer.
- **Render test:** A test that inspects terminal output from components without a physical TTY.
- **Runtime pin:** Repository metadata selecting a supported Node version.
- **Terminal lifecycle:** Setup, input handling, rendering, unmounting, and restoration on exit.

See the shared [project glossary](../glossary.md) for TUI, runtime, event, and policy terms.

## Further reading

- [CAH-002 delivery contract](../../user-stories/cah-002-bootstrap-ink-application.md)
- [ADR 0002: Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [Ink documentation](https://github.com/vadimdemedes/ink)
- [ink-testing-library documentation](https://github.com/vadimdemedes/ink-testing-library)
- [npm package-lock documentation](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/)
- [OpenTelemetry for JavaScript](https://opentelemetry.io/docs/languages/js/)
