# CAH-025 lesson: Magical Mission Ink presentation

- **Unit:** CAH-025
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; implementation, validation, publication, and review-readiness
  evidence are recorded
- **Story:**
  [CAH-025](../../user-stories/cah-025-apply-magical-mission-ink-presentation.md)
- **Visual companion:** None; the Markdown lesson and compact text diagram are authoritative
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md),
  [architecture overview](../architecture.md#ownership), and
  [session-state reducer](cah-010-session-state-reducer.md)

> This lesson traces the published CAH-025 implementation and its verified evidence. It does not
> present future plan, tool, diff, repository-read, edit, or
> approval-decision interfaces as implemented.

## Quick summary

CAH-025 separates the existing Ink input controller from a responsive Magical Mission view. The view
can be playful because it only decorates immutable runtime/session projections: Python and the
existing reducers still own lifecycle truth, and narrow or reduced-decoration terminals retain the
facts needed to understand and control the application.

## Learning objectives

After studying this unit, you should be able to:

- distinguish authoritative state from decorative presentation;
- explain how terminal columns, rows, `NO_COLOR`, and `TERM=dumb` select safe render variants;
- preserve React-owned input while Ink rerenders after state updates or terminal resize;
- make a mascot mapping total without creating a second state machine; and
- test visible meaning without snapshotting ANSI escapes or incidental border spacing.

## Why this unit matters

A coding agent must make failures, cancellation, workspace, and keyboard controls understandable.
Playful decoration is useful only while those facts remain trustworthy. By isolating presentation,
CAH-025 can add personality without moving orchestration, safety, provider, or terminal authority into
a React view.

This unit is scheduled before CAH-024 but does not implement any M2 repository-context behavior.
CAH-024 remains the first E3 unit and is independently Planned.

## Junior engineer foundation

### A terminal is a grid, not a browser canvas

Ink lays components out in character cells. A terminal reports columns and rows rather than pixels,
and some emoji or Unicode sequences can occupy different visible widths in different terminal/font
combinations. Responsive terminal design therefore removes optional decoration before it removes
meaningful text.

For example, a pure layout choice can be tested without rendering:

```ts
const layout = columns >= 96 ? 'wide' : columns >= 56 ? 'stacked' : 'compact';
```

This expression reads from left to right: use the wide composition at 96 columns, otherwise stack at
56 or more, otherwise use the compact composition. A common misconception is that switching this
value should also clear or recreate screen state. It should not: layout is a projection of width, and
the editable draft remains owned by the parent component.

### Decoration is not authority

`MISSION COMPLETE!` and a happy familiar are decoration. The reducer-derived
`Session status: completed` line is the stable fact. The view may choose a face and color from that
fact, but it cannot decide that a session completed, make a failed runtime look ready, or celebrate
while a warning or approval/cancellation/failure state needs attention.

## Key concepts

### One input controller, one pure view boundary

[`app.tsx`](../../tui/src/app.tsx) retains `useInput`, the draft, local feedback, and the existing
submission/cancellation callbacks. It passes only render inputs to
[`MagicalMissionView`](../../tui/src/magical-mission.tsx). Resize can therefore change the terminal
tree without remounting or resetting the parent-owned draft.

### Progressive presentation fallback

The pure resolver returns `wide`, `stacked`, or `compact`, plus independent choices for spacing,
familiar visibility, emoji, color, and border style. Width, height, and low-capability terminal hints
degrade decoration in layers rather than producing one brittle “mobile” screen. Familiar text starts
at 40 columns and 18 rows, while optional emoji wait until 48 columns and 18 rows. `TERM=dumb`
selects reduced decoration and classic borders; it does not promise that every remaining character
is ASCII.

### Total familiar projection

`projectFamiliar` handles every current runtime and session status. A non-running runtime takes visual
precedence because it is unsafe and confusing to display an enthusiastic ready mascot beside a child
failure. The authoritative runtime and session lines remain visible regardless of the face. When
height is constrained, the familiar is one borderless line. A roomy wide side panel keeps only the
face and callout so it does not repeat the canonical status footer.

### Alerts and celebration are derived independently

Fatal runtime/session errors and runtime/recording warnings occupy a dedicated alert deck directly
below the header, before the mission log. The optional heart has a stricter rule than
`POWER: READY`: Python must be running, no warning may be present, and the session must be idle,
running, or completed. Approval, cancellation, and failure states therefore cannot receive a
misleading celebration.

### Input labels report availability without taking ownership

The view receives the parent-owned draft and gives its heading enough context to stay truthful.
Compact mode says `Task input`; active work says the next-command draft is preserved; a non-running
runtime says submission is waiting; and a protocol-failed session says restart is required. The
prompt plus draft or placeholder share one Ink `Text` flow so wrapping does not visually detach them.
Compact runtime output similarly splits status, workspace, and Ctrl+C guidance onto separate lines.

### Semantic rendering evidence

Tests should assert durable text and state relationships: the exact warning code remains present,
`POWER: READY` never accompanies a failed runtime, the draft survives rerenders, and compact output
retains workspace and shortcuts. ANSI escape sequences, color depth, and exact border padding are not
stable behavioral contracts. [`magical-mission.test.tsx`](../../tui/test/magical-mission.test.tsx)
now covers the pure decisions, total mappings, responsive renders, and capability fallbacks, while
`app.test.tsx` continues to cover the input controller and existing root-screen behavior.

## Architecture and design

```text
terminal keys ──> app.tsx input owner ──> supervisor / protocol ──> Python harness
                      │                         │                       │
terminal size ────────┼─> MagicalMissionView   │                 provider adapter
TERM / NO_COLOR ──────┘       │                │                       │
                              └─ decorated projection           tools: not added
                                 of existing truth              evidence: unchanged

Python/reducers own lifecycle facts. The TUI view owns layout only.
```

Implemented invariants:

- `AppProperties`, command/event schemas, reducer inputs, and Python behavior do not change;
- terminal dimensions and capability hints cannot invoke callbacks or mutate state;
- the familiar and power badge are derived from existing projections;
- the alert deck appears directly below the header and celebration is suppressed during warnings,
  approval, cancellation, or failure;
- exact task, warning, failure, workspace, cancellation, and exit text remains visible;
- input headings describe availability while the editable draft stays parent-owned;
- `awaiting_approval` receives styling only, not a decision control; and
- no plan, tool, result, diff, edit, or repository-read surface is fabricated.

## Practical walkthrough

1. Start in `app.tsx` and verify that `useInput`, `draftRef`, Enter, backspace, and Escape still cross
   the same supervised callbacks.
2. Follow the render into `MagicalMissionView`; note that its properties contain projections and
   display values but no transition or policy callback.
3. Read `resolveMissionPresentation` from its 96/56 column breakpoints through height, emoji, color,
   familiar, and border decisions. Compare the 40-column familiar threshold with the 48-column emoji
   threshold; both also require 18 rows.
4. Trace `projectFamiliar`, first through non-running runtime states and then through every session
   state for a running runtime.
5. Inspect the header, alert deck, mission-log, familiar, command, and footer components. Identify
   which labels are decorative and which reproduce the existing behavioral contract. Verify that
   alerts precede the log and the heart follows its stricter celebration predicate.
6. Run focused view and controller tests, then type-check, lint, run the full TUI suite, and execute
   `./scripts/check` before changing the unit to Done.

## Implementation code samples

### Responsive decisions stay pure

[`resolveMissionPresentation`](../../tui/src/magical-mission.tsx) currently contains:

```ts
const layout: MissionLayout =
  columns >= WIDE_MISSION_COLUMNS
    ? 'wide'
    : columns >= STACKED_MISSION_COLUMNS
      ? 'stacked'
      : 'compact';
const showEmoji =
  !dumbTerminal &&
  columns >= MINIMUM_EMOJI_COLUMNS &&
  rows >= MINIMUM_FAMILIAR_ROWS;

return {
  layout,
  roomy: rows >= ROOMY_MISSION_ROWS,
  showFamiliar:
    !dumbTerminal &&
    columns >= MINIMUM_FAMILIAR_COLUMNS &&
    rows >= MINIMUM_FAMILIAR_ROWS,
  showEmoji,
  colorEnabled: environment.noColor === undefined && !dumbTerminal,
  panelBorder: dumbTerminal || columns < 32 ? 'classic' : 'round',
};
```

The nested conditional selects only a layout string. The returned object makes other degradations
explicit: height controls spacing and familiar visibility, `TERM=dumb` removes richer decoration,
and `NO_COLOR` disables explicit color without changing content. The separate constants let a
borderless familiar remain useful at 40 columns while potentially wider emoji wait until 48; both
choices require 18 rows.

### Input ownership does not move into the theme

[`App`](../../tui/src/app.tsx) delegates its final render after input handling:

```tsx
return (
  <MagicalMissionView
    canCancel={
      runtimeState.status === 'running' &&
      sessionState.status !== 'protocol-failed' &&
      isCancellableSessionStatus(sessionState.status)
    }
    draft={draft}
    inputFeedback={inputFeedback}
    runtimeState={runtimeState}
    sessionState={sessionState}
  />
);
```

The controller computes the existing cancellation hint and passes the exact draft and projections.
There is no view callback, so the new module cannot submit, cancel, approve, or choose a terminal
outcome.

### Compact failure evidence remains complete

[`magical-mission.test.tsx`](../../tui/test/magical-mission.test.tsx) resizes a failure view to 44
columns and checks the complete safe message:

```tsx
await resizeTerminal(failureView, 44, 20);
const frame = normalizedFrame(requiredFrame(failureView));
expect(frame).toContain('(｡•́︿•̀｡) · FAILED');
expect(frame).toContain(
  'ERROR · Session failed (approval.unavailable): Approval could not be completed safely.',
);
expect(frame).toContain('Session status: failed (approval.unavailable)');
expect(frame).toContain(failureMessage);
expect(frame).toContain('ready for another task');
expect(frame).not.toContain('💖');
```

The resize is part of the test setup, while the assertions preserve both themed context and
authoritative evidence. Companion warning and runtime-failure assertions verify that the alert deck
appears before the mission log. The existing root-screen failure cases in
[`app.test.tsx`](../../tui/test/app.test.tsx) separately keep the runtime message and Ctrl+C guidance
visible through `App`.

## Failure scenarios to study

| Failure | Responsible boundary | Safe outcome | Evidence status |
| --- | --- | --- | --- |
| Resize remounts input | `App`/view ownership | Draft remains in the parent while only composition changes | Responsive render plus existing draft-rerender tests pass |
| Failed runtime shows ready power | Familiar/header projection | Runtime failure maps to `ALERT`; exact failure remains visible | Exhaustive seven-runtime mapping cases pass |
| Emoji or color is unusable | Capability resolver | `TERM=dumb` selects reduced decoration/classic borders; `NO_COLOR` removes explicit color | No-color and dumb-terminal render case passes |
| Narrow layout hides a safety fact | Compact view | Failure code/message, workspace where applicable, and shortcuts remain | Compact warning/failure plus 30-by-16 emergency cases pass |
| Warning is buried or celebrated | Alert/header projection | Alert deck precedes the log and the heart is absent | Warning and runtime/session failure assertions pass |
| Input heading overstates availability | Input presentation | Draft is visibly preserved or submission is shown as waiting/restart-required | Responsive semantic-region cases pass |
| Mascot invents a state | `projectFamiliar` | Total mapping consumes existing unions and emits decoration only | Nine-session and seven-runtime tables pass |
| Styled approval implies authority | View boundary | Existing waiting status only; no decision key or command exists | Source audit and canonical gate pass |

Current focused evidence is 41 of 41 Magical Mission cases and 54 of 54 combined application/view
cases, with TUI type checking and lint passing. The complete TUI suite passes 316 of 316. The
canonical `./scripts/check` gate passes 940 Python tests, 32 Python protocol-fixture tests, 35
repository check/policy tests, 281 core TUI tests, 31 TypeScript protocol-fixture tests, and 4
Node-Python boundary tests. One live `xterm-256color` tmux PTY kept the exact pending draft while the
same Ink process resized from 110 by 30 to 76 by 24 and then 44 by 20; all three compositions retained
authoritative status and showed aligned Unicode borders and mascot text in the inspected WSL
terminal. The App-level Ink resize test independently preserves a typed draft across those widths
without invoking submission or cancellation callbacks; semantic tests cover `NO_COLOR` and
`TERM=dumb`. `git diff --check` passes. The implementation is published from branch
`agent/magical-mission-tui` at implementation commit `8398d2c` in ready-for-review
[pull request #26](https://github.com/jimmie-potts/code-assist-harness/pull/26), targeting
`codex/implement-cah-023`. A thread-aware GitHub audit reported zero review threads at handoff.

## Production expansion

A broadly distributed terminal client would need a compatibility matrix across terminals, fonts,
color depths, locales, assistive workflows, and resize behavior. Representative references include:

- [Ink](https://github.com/vadimdemedes/ink) for component rendering and terminal hooks; upgrades add
  compatibility and regression-testing work.
- [Yoga](https://www.yogalayout.dev/) for flexbox layout concepts; more layout sophistication adds
  breakpoint and clipping cases to maintain.
- [Unicode Standard Annex #11](https://www.unicode.org/reports/tr11/) for East Asian character width;
  robust cross-terminal glyph policy requires platform/font testing.
- [NO_COLOR](https://no-color.org/) for a conventional opt-out; honoring it is inexpensive, while a
  complete accessibility settings system adds configuration and support cost.

These references explain capabilities and compatibility concerns; CAH-025 adds no new dependency or
service.

### Local design versus production design

| Dimension | CAH-025 | Broader production client |
| --- | --- | --- |
| Platforms | One pinned Node/Ink line in Ubuntu WSL | Terminal, OS, shell, locale, and font matrix |
| Responsiveness | Two width breakpoints plus height/capability fallbacks | Measured viewport classes and compatibility telemetry |
| Accessibility | Text accompanies color/emoji; reduced-decoration fallback | User preferences, screen-reader workflow, formal review |
| Testing | Pure decisions plus semantic Ink renders | Golden compatibility runs and physical-terminal labs |
| Cost | One local presentation module, no new package | Ongoing design-system, release, and support ownership |

## Trade-offs and graduation signals

The familiar makes lifecycle changes friendlier, but it consumes terminal space and Unicode width can
vary. Hiding it when space or capability is insufficient keeps the local design understandable. A
separate theme system, user preferences, or terminal compatibility service would be justified only
after recurring user needs or measured rendering defects outweigh the cost of another configuration
and test surface.

## Practical exercises

1. Predict the presentation at 95 by 24, 48 by 18, 47 by 18, 40 by 18, and 40 by 17 before reading
   the resolver result.
2. Add a hypothetical session state on paper and identify the compiler/test evidence needed to keep
   the familiar mapping total.
3. Explain why `POWER: READY` must inspect runtime state even though the session may still look idle or
   completed.
4. Identify which strings may disappear in compact mode and which are behavioral facts that must
   remain.
5. Trace a typed draft across an Ink resize and explain why the view cannot clear it.

## Key takeaways

- A playful TUI remains safe when decoration only projects existing state.
- Width, height, color, and terminal capability are presentation inputs, not lifecycle events.
- Parent-owned input survives responsive rerenders.
- Text keeps failures and controls understandable when colors, borders, emoji, or the familiar drop
  away.
- CAH-025 changes no provider, tool, approval, protocol, or transcript boundary.

## Glossary

- **Authoritative status:** Reducer/runtime truth that presentation cannot choose or override.
- **Capability fallback:** A simpler render selected when terminal features or dimensions are limited.
- **Character cell:** One terminal grid position; some visible Unicode sequences span more than one.
- **Familiar:** The decorative Magical Mission mascot projected from current status.
- **Presentation projection:** A view derived from existing state without mutation or side effects.
- **Semantic render test:** An assertion about visible meaning rather than exact ANSI or spacing.

## Further reading

- [CAH-025 delivery contract](../../user-stories/cah-025-apply-magical-mission-ink-presentation.md)
- [CAH-025 implementation note](../../user-stories/notes/2026-08-02-cah-025-magical-mission-tui.md)
- [CAH-002 Ink shell lesson](cah-002-ink-application-shell.md)
- [CAH-010 session-state reducer lesson](cah-010-session-state-reducer.md)
- [ADR 0002: Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [Architecture ownership](../architecture.md#ownership)
- [Ink documentation](https://github.com/vadimdemedes/ink)
