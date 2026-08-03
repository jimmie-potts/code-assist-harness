# 2026-08-02 CAH-025 Magical Mission TUI

## Purpose

Record why Magical Mission was selected, how the implementation keeps decoration subordinate to
existing harness truth, and the evidence required before CAH-025 can be Done.

## Selected direction

The selected direction is a bright, game-like Star Command dashboard: a double-bordered header,
pink/cyan/violet/gold accents, a Mission Log, a chubby familiar with status-specific expressions, a
`CAST YOUR NEXT COMMAND` input region, and a compact authoritative footer. The wide composition gives
the familiar its own side panel; smaller terminals progressively stack or remove optional decoration.

This is a presentation refinement, not a feature preview. The implementation renders only current
conversation turns, current runtime/session states, existing warnings and failures, the current
workspace, and the existing input/cancellation contract. It does not create plan, tool, result, diff,
repository-read, edit, or approval-decision UI.

## Implemented responsibility split

- `tui/src/app.tsx` still owns draft state, input filtering, code-point backspace, Enter submission,
  local feedback, Escape eligibility, and calls into the supervised runtime owner.
- `tui/src/magical-mission.tsx` receives the draft and immutable runtime/session projections. It owns
  only layout, color, borders, optional emoji, familiar copy, and the rendering of existing facts.
- `resolveMissionPresentation` is a pure terminal-capability decision. It cannot change application
  state or invoke a callback.
- `projectFamiliar` is a total decorative projection. A non-running runtime wins visually because a
  stale cheerful session mascot would contradict the more important child failure, but the canonical
  status regions remain authoritative.

```text
validated RuntimeState + reduced SessionState + parent-owned draft
                              |
                              v
                 app.tsx input/controller boundary
                              |
                              v
          MagicalMissionView + terminal dimensions/capabilities
                              |
                              v
             decorated Ink projection of existing truth

No presentation path writes state, policy, protocol, provider, or transcript data.
```

## Responsive and capability contract

| Input | Presentation decision |
| --- | --- |
| Columns `>= 96` | Wide mission log plus 30-column familiar side panel when height permits |
| Columns `56..95` | Stacked panels |
| Columns `< 56` | Compact linear composition |
| Rows `>= 24` | Optional vertical breathing room |
| Columns `>= 40` and rows `>= 18` | Familiar may be shown, as one borderless line when the layout is not roomy |
| Columns `>= 48` and rows `>= 18` | Optional emoji may be shown independently of the familiar |
| `NO_COLOR` present | No explicit Magical Mission colors |
| `TERM=dumb` | Reduced decoration: no explicit color, emoji, or familiar; classic borders, without promising fully ASCII output |
| Very narrow terminal | Classic borders below 32 columns; task and status text remain |

The dashboard is centered and capped at 132 columns. The palette is deliberately local to the view:
header background `#251b45`, warm header text `#fff7e8`, pink `#ff5da2`, cyan `#59d6ff`, violet
`#c79bff`, gold `#ffd166`, mint `#58d68d`, and red `#ff667d`. Text labels accompany every color and
mascot state.

## State honesty

- `POWER: READY` appears only for a running runtime. The optional heart additionally requires no
  runtime/recording warning and an idle, running, or completed session; it is suppressed for
  approval, cancellation, and failure states. Other runtime states map to `WAKING`, `STOPPING`,
  `OFFLINE`, or `ALERT`.
- Fatal runtime/session errors and runtime/recording warnings render in an alert deck directly below
  the header, ahead of the mission log, while canonical footer status remains visible.
- The familiar has a deterministic expression and text callout for every current runtime/session
  state, but never replaces `Session status:` or `Status:`. Its cancelling callout is
  `CANCELLATION REQUESTED · WAITING FOR PYTHON`. Non-roomy output is one borderless line, and the
  roomy wide side panel omits duplicated canonical status.
- `Runtime warning`, `Recording warning`, safe failure codes/messages, workspace, `Esc to cancel`,
  and `Ctrl+C to exit` retain their existing text.
- Compact input is labeled `Task input`. Larger active, runtime-unavailable, and protocol-failed
  states truthfully say the draft is preserved, submission is waiting for the runtime, or restart is
  required. Prompt and draft share one Ink text flow. Compact runtime status splits status,
  workspace, and Ctrl+C guidance across three lines.
- The current `awaiting_approval` projection is styled as `ACTION REQUIRED`; no decision control,
  response command, or approval authority is added.
- Terminal resize affects composition only. The draft stays in the parent `App`, so switching layouts
  cannot reset it.

## Dependency placement

CAH-025 depends on completed CAH-023 and is scheduled before CAH-024 because the user explicitly
selected the presentation refinement next. It does not depend on the planned Python workspace
boundary, and CAH-024 does not depend on this theme. CAH-024 remains Planned and remains the first
implementation-ready E3 unit.

## Evidence status

Current focused evidence:

- `tui/test/magical-mission.test.tsx`: 41 of 41 cases pass, covering exact layout/degradation
  thresholds, `NO_COLOR`, `TERM=dumb`, all nine session expressions, all seven runtime states, wide
  power/celebration truth, responsive and non-roomy-wide semantic regions, truthful input headings,
  App-owned draft preservation without callbacks, the 30-by-16 emergency projection, alert
  placement, compact warning/failure evidence, and reduced-decoration output;
- combined `app.test.tsx` plus `magical-mission.test.tsx`: 54 of 54 cases pass;
- TUI type checking and the complete TUI lint stage pass;
- the complete TUI suite passes 316 of 316;
- one live `xterm-256color` tmux PTY kept the exact pending draft while the same Ink process resized
  from 110 by 30 to 76 by 24 and then 44 by 20; its wide, stacked, and compact compositions retained
  authoritative status and showed aligned Unicode borders and mascot text in the inspected WSL
  terminal; and
- the 23 repository-policy tests pass with the new story, lesson, note, indexes, and internal links.

The canonical `./scripts/check` gate also passes: 940 Python tests, 32 Python protocol-fixture tests,
35 repository check/policy tests, 281 core TUI tests, 31 TypeScript protocol-fixture tests, and 4
Node-Python boundary tests. `git diff --check` passes. The App-level Ink resize test independently
types and preserves the pending draft across 110, 76, and 44 columns without invoking submission or
cancellation callbacks. Automated coverage also verifies `NO_COLOR` and `TERM=dumb`.

The first GitHub Actions handoff exposed one presentation-sensitive assertion in the real
Node-to-Python boundary test: it searched a raw bordered frame for one uninterrupted cumulative
delta, so legitimate Ink wrapping could make the second delta appear absent. The test now removes
layout-only vertical/box-drawing borders and folds whitespace before checking the same exact delta
content, running status, completion, second task, and frame ordering. Production code and the
process-boundary contract are unchanged; the focused boundary test and canonical repository gate
pass with the hardened evidence path.

## Publication evidence

- Branch: `agent/magical-mission-tui`
- Implementation commit: `8398d2c` (`Apply Magical Mission TUI`)
- Review handoff: ready-for-review [pull request
  #26](https://github.com/jimmie-potts/code-assist-harness/pull/26), targeting
  `codex/implement-cah-023`
- Thread-aware audit at handoff: zero review threads, therefore zero unresolved actionable threads

CAH-025 is **Done**, and its lesson is **Verified against implementation**. No retained presentation
file is added or revised.
