# CAH-025 - Apply the Magical Mission Ink presentation

- **Status:** Done
- **Milestone / epic:** M2 - Read-only coding assistant / E7 - Ink TUI experience
- **Dependencies:** CAH-023
- **Lesson:**
  [Magical Mission Ink presentation](../docs/lessons/cah-025-magical-mission-ink-presentation.md)
- **Implementation note:**
  [CAH-025 Magical Mission TUI](notes/2026-08-02-cah-025-magical-mission-tui.md)

## User story

> As a user, I want the existing conversation shell presented as a joyful Magical Mission dashboard
> so that session progress feels lively while every runtime, session, failure, workspace, and
> keyboard fact remains easy to understand.

## Single responsibility

CAH-025 owns only the presentation of state that already exists: theme colors, decorative wording,
mascot projection, terminal-responsive composition, and reduced-decoration fallbacks. It does not
create or reinterpret runtime or session state, alter input or cancellation behavior, change the
protocol, or invent plans, tools, diffs, repository reads, or approval interactions.

## Scope

- Keep `tui/src/app.tsx` responsible for the editable draft, Enter submission, Unicode-code-point
  backspace, Escape cancellation requests, local input feedback, and the existing supervised
  callbacks.
- Move visible composition into `tui/src/magical-mission.tsx`, a presentation-only Ink view receiving
  immutable runtime/session projections and parent-owned input values.
- Render a bounded Star Command dashboard with a Magical Mission header, mission-log conversation,
  state-derived familiar, command input, warnings, authoritative session status, runtime status,
  workspace, and keyboard guidance.
- Derive `wide`, `stacked`, or `compact` layout from `useWindowSize`: wide begins at 96 columns,
  stacked at 56, and smaller terminals use the compact composition. Height separately controls
  optional spacing and the familiar panel.
- Cap the dashboard at 132 columns. Show the familiar only from 40 columns and 18 rows, and show
  optional emoji only from 48 columns and 18 rows. Honor `NO_COLOR`; for `TERM=dumb`, disable
  explicit color, emoji, and the familiar and select classic borders as a reduced-decoration mode.
- Project one decorative familiar from every existing runtime and session status. A non-running
  runtime receives visual precedence, while the exact runtime and session status text remains
  authoritative and visible.
- Put fatal runtime/session errors and runtime/recording warnings in an alert deck immediately below
  the header. Suppress the decorative heart for warnings, approval, cancellation, and failures.
- Keep non-roomy familiar output to one borderless line. In a roomy wide layout, the familiar side
  panel shows only the face and callout rather than duplicating canonical runtime/session status.
- Describe input availability truthfully: compact mode uses `Task input`; active work says the draft
  is preserved; unavailable runtime and protocol-failed states say why submission must wait. Keep the
  prompt and draft in one Ink text flow, and split compact runtime status, workspace, and Ctrl+C onto
  separate lines.
- Preserve current conversation labels, accumulated stream text, task placeholder, draft,
  warnings, failure codes/messages, cancellation hint, exit hint, and workspace text.
- Add focused semantic rendering coverage without snapshots of ANSI escapes, border glyphs, or
  incidental spacing.

## Presentation contract

| Concern | Implemented presentation | Invariant |
| --- | --- | --- |
| Wide terminal | Header plus side-by-side Mission Log and Familiar when height is roomy | Begins at 96 columns; status footer remains visible |
| Medium terminal | Panels stack; a roomy familiar uses one bordered row and a non-roomy familiar is borderless | Begins at 56 columns; no state or input changes |
| Compact terminal | Linear title, log, command input, and status footer | Decorative content may disappear; task and safety facts do not |
| Low-capability terminal | `NO_COLOR` removes explicit colors; `TERM=dumb` removes emoji/familiar and uses classic borders | Reduced decoration retains the text needed to operate the shell; it is not a promise that every character is ASCII |
| Runtime truth | `POWER: READY` appears only for a running runtime; its heart also requires a celebration-safe session with no warning | Starting, approval, cancellation, warnings, and failures never receive a misleading celebration |
| Familiar | Static callout derived from the existing projection | It never becomes a state machine, timer, focus target, or authority |
| Alerts | Fatal errors and warnings appear directly below the header | Alert evidence precedes the mission log and canonical status remains visible |
| Input | Heading reflects whether submission is available while the parent retains the draft | Presentation never accepts, rejects, or clears input |

## Acceptance criteria

1. `AppProperties`, runtime/session domain types, reducers, command/event schemas, protocol version 1,
   Python behavior, and transcripts are unchanged.
2. `App` retains input ownership and renders the presentation-only `MagicalMissionView`; resize
   changes composition without clearing the draft or causing a callback.
3. At 96 or more columns and 24 or more rows, the screen shows the Star Command header, truthful
   mission/power labels, mission log, dedicated familiar side panel, command input, and authoritative
   status footer. A non-roomy wide layout stacks the log and one borderless familiar line instead.
4. Widths from 56 through 95 columns use the stacked composition. Smaller widths use the compact
   composition. The familiar requires at least 40 columns and 18 rows; emoji require at least 48
   columns and 18 rows.
5. `NO_COLOR` removes explicit theme colors. `TERM=dumb` also removes emoji and the familiar and uses
   classic borders without removing task, feedback, warning, failure, status, workspace, or shortcut
   text. This is a reduced-decoration contract, not a full-ASCII-output guarantee.
6. Every existing runtime and session state has a deterministic familiar projection; runtime failure
   takes decorative precedence over stale session appearance, while canonical status text remains
   unchanged.
7. `POWER: READY` is rendered only when the runtime is `running`; other runtime states render
   `WAKING`, `STOPPING`, `OFFLINE`, or `ALERT` as appropriate. The heart is absent for runtime or
   recording warnings and for approval, cancellation, failed, or protocol-failed session states.
8. Empty conversation, streaming deltas, completed text, preserved draft, local feedback, runtime and
   recording warnings, session failures, protocol failures, workspace, `Esc to cancel`, and `Ctrl+C
   to exit` remain semantically visible in their existing legal states.
9. Enter submission, code-point backspace, overlap rejection, Escape cancellation eligibility,
   repeated cancellation behavior, and Ctrl+C application exit do not change.
10. The current `awaiting_approval` projection may receive decorative styling only. No approval
    choice, command, key binding, or action authorization is introduced.
11. No plan, tool-call, tool-result, repository-read, diff, or edit panel is rendered or claimed.
12. Type checking, linting, focused TUI tests, the complete TUI suite, documentation checks, and
    `./scripts/check` pass without a model, credential, or network request before the story is Done.
13. Runtime/session failures and runtime/recording warnings render in an alert deck immediately below
    the header. Non-roomy familiar output is one borderless line; the roomy wide side panel does not
    duplicate canonical status.
14. Input headings state `Task input` in compact mode and accurately report active-work draft
    preservation, runtime unavailability, or restart-required protocol failure in larger layouts.
    Compact runtime status keeps status, workspace, and Ctrl+C visible on separate lines.

## Validation

- Test `resolveMissionPresentation` at wide, stacked, compact, low-height, `NO_COLOR`, and
  `TERM=dumb` boundaries, including separate 40-column familiar and 48-column emoji thresholds.
- Test the total familiar mapping across current runtime/session states, including runtime-failure
  precedence, session protocol failure, and the exact cancelling callout that waits for Python.
- Use `ink-testing-library` in `tui/test/magical-mission.test.tsx` to verify the wide selected design
  and that existing task, status, warning, failure, workspace, and keyboard facts remain visible.
- Exercise the 30-by-16 emergency projection and reduced-decoration fallback without asserting exact
  ANSI codes or manually padded border lines. Verify alert-deck ordering and heart suppression.
- Re-run the existing input, streaming, cancellation, terminal-failure, and draft-preservation tests
  in `tui/test/app.test.tsx`.
- Run `npm --prefix tui run typecheck`, `npm --prefix tui run lint`, and `npm --prefix tui test`.
- Run `./scripts/check` as the canonical repository-wide gate and `git diff --check` as a final patch
  check.
- Manually inspect the TUI in WSL at wide, stacked, and compact sizes, including a resize with a
  pending draft. This is supplemental evidence, not a replacement for automated tests.

## Documentation impact

- Add the linked concise Markdown lesson and compact architecture diagram; no presentation is part
  of CAH-025.
- Record the selected design, ownership split, responsive and capability fallbacks, implementation
  discoveries, and final validation evidence in the linked note.
- Update the story and lesson indexes, E7 backlog, README launch description, and architecture status
  and source-tree descriptions.
- Qualify CAH-002's exact terminal frame as completion-time evidence and point readers to CAH-025 for
  the current presentation. Do not modify its frozen visual assets.

## Current implementation evidence

`tui/src/app.tsx` now delegates only rendering to `MagicalMissionView` while retaining its existing
input and callback path. `tui/src/magical-mission.tsx` contains the responsive presentation resolver,
total familiar projection, colors, capability fallback, panels, and canonical status rendering.
`tui/test/magical-mission.test.tsx` supplies 41 passing focused cases: exact layout and independent
familiar/emoji degradation boundaries, `NO_COLOR`/`TERM=dumb`, all nine session and seven runtime
projections, wide power/celebration truth, responsive and non-roomy-wide renders, truthful input
headings, App-owned draft preservation without callbacks, the 30-by-16 emergency projection, alert
ordering, compact warning/failure evidence, and reduced-decoration semantics. The combined
application and Magical Mission tests pass 54 of 54, TUI type checking and lint pass, and 23
repository-policy tests pass. The complete TUI suite passes 317 of 317. The canonical
`./scripts/check` gate passes 940 Python tests, 32 Python protocol-fixture tests, 35 repository
check/policy tests, 281 core TUI tests, 31
TypeScript protocol-fixture tests, and 5 Node-Python boundary tests. One live `xterm-256color` tmux
PTY kept the exact pending draft while the same Ink process resized from 110 by 30 to 76 by 24 and
then 44 by 20. The observed wide, stacked, and compact compositions retained authoritative status
and showed aligned Unicode borders and mascot text in the inspected WSL terminal. The App-level Ink
resize test independently preserves a typed draft across those widths without invoking submission or
cancellation callbacks; `NO_COLOR` and `TERM=dumb` fallbacks are verified semantically. `git diff
--check` passes. The implementation is published from branch `agent/magical-mission-tui` at commit
`8398d2c` in ready-for-review [pull request
#26](https://github.com/jimmie-potts/code-assist-harness/pull/26), targeting
`codex/implement-cah-023`. A later automated review identified two stale `in-progress` references;
both are corrected, its thread is resolved after validation, and the final thread-aware audit reports
zero unresolved actionable threads. The story is **Done**, and its lesson is **Verified against
implementation**.

## Out of scope

- New session states, protocol events, provider behavior, transcript fields, or Python changes.
- Plan, tool, result, diff, edit, repository-read, or approval-decision interfaces.
- Theme selection, persisted visual preferences, animation timers, sound, mouse input, or image
  assets.
- A new JavaScript dependency or lockfile change.
- Any revision to retained presentation files under `docs/lessons/assets/`.
