import {Box, Text, useWindowSize} from 'ink';
import type {ReactElement} from 'react';

import type {RuntimeState} from './runtime-supervisor.js';
import {isActiveSessionStatus} from './session-lifecycle.js';
import type {ConversationTurn, SessionState} from './session-state.js';

const WIDE_MISSION_COLUMNS = 96;
const STACKED_MISSION_COLUMNS = 56;
const MINIMUM_FAMILIAR_COLUMNS = 40;
const MINIMUM_EMOJI_COLUMNS = 48;
const MINIMUM_FAMILIAR_ROWS = 18;
const ROOMY_MISSION_ROWS = 24;
const MAXIMUM_MISSION_COLUMNS = 132;

const STAR_COMMAND_COLORS = {
  headerBackground: '#251b45',
  headerText: '#fff7e8',
  pink: '#ff5da2',
  cyan: '#59d6ff',
  violet: '#c79bff',
  gold: '#ffd166',
  mint: '#58d68d',
  red: '#ff667d',
} as const;

/** Responsive arrangements supported by the Magical Mission terminal view. */
export type MissionLayout = 'wide' | 'stacked' | 'compact';

/** Non-sensitive terminal hints that control presentational degradation. */
export interface MissionTerminalEnvironment {
  /** Disable optional color when the conventional environment hint is present. */
  readonly noColor?: string | undefined;
  /** Select a reduced-decoration, classic-border view for a terminal declaring itself `dumb`. */
  readonly term?: string | undefined;
}

/** Pure presentation choices derived from terminal dimensions and capabilities. */
export interface MissionPresentation {
  /** Horizontal composition selected for the available terminal columns. */
  readonly layout: MissionLayout;
  /** Whether optional vertical breathing room can be rendered. */
  readonly roomy: boolean;
  /** Whether the dedicated mascot projection has enough safe room. */
  readonly showFamiliar: boolean;
  /** Whether optional emoji decoration is safe for this terminal. */
  readonly showEmoji: boolean;
  /** Whether Magical Mission supplies explicit foreground/background colors. */
  readonly colorEnabled: boolean;
  /** Border style selected without using emoji or manually padded glyphs. */
  readonly panelBorder: 'round' | 'classic';
}

/** Static mascot text projected from existing runtime and session truth. */
export interface FamiliarProjection {
  /** Expressive, non-authoritative face shown only when room permits. */
  readonly face: string;
  /** Decorative wording paired with canonical status text elsewhere on screen. */
  readonly callout: string;
  /** Compact status wording used when a full mascot panel would not fit. */
  readonly compactStatus: string;
  /** Palette role used in color-capable terminals. */
  readonly color: string;
}

/** Presentation-only values consumed by the selected Magical Mission view. */
export interface MagicalMissionViewProperties {
  /** Current child lifecycle projection; the view never changes it. */
  readonly runtimeState: RuntimeState;
  /** Current conversation/session projection; the view never reduces it. */
  readonly sessionState: SessionState;
  /** Exact editable task buffer owned by the parent input controller. */
  readonly draft: string;
  /** Immediate local submission feedback owned by the parent input controller. */
  readonly inputFeedback?: string | undefined;
  /** Whether the current projected state makes the existing Escape request available. */
  readonly canCancel: boolean;
  /** Optional deterministic capability seam; production uses `TERM` and `NO_COLOR`. */
  readonly terminalEnvironment?: MissionTerminalEnvironment;
}

/**
 * Select a responsive, capability-aware presentation without changing application state.
 *
 * @param columns - Current terminal width in character cells.
 * @param rows - Current terminal height in character cells.
 * @param environment - Non-sensitive terminal capability hints.
 * @returns Pure layout and decoration choices for the current render.
 */
export function resolveMissionPresentation(
  columns: number,
  rows: number,
  environment: MissionTerminalEnvironment = {},
): MissionPresentation {
  const dumbTerminal = environment.term === 'dumb';
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
}

/**
 * Project one decorative familiar expression from existing authoritative state.
 *
 * A non-running runtime takes visual precedence because session work cannot be acted on normally in
 * that condition. The canonical runtime and session status regions remain visible and authoritative.
 *
 * @param runtimeState - Current supervised child projection.
 * @param sessionState - Current reduced session projection.
 * @returns One total static mascot mapping with a text status companion.
 */
export function projectFamiliar(
  runtimeState: RuntimeState,
  sessionState: SessionState,
): FamiliarProjection {
  if (runtimeState.status !== 'running') {
    switch (runtimeState.status) {
      case 'starting':
        return familiar('૮ ˶• ﻌ •˶ ა', 'PYTHON IS WAKING UP…', 'WAKING', STAR_COMMAND_COLORS.cyan);
      case 'failed-to-start':
        return familiar(
          '૮ ˶× ﻌ ×˶ ა',
          'RUNTIME FAILED TO START',
          'RUNTIME FAILED',
          STAR_COMMAND_COLORS.red,
        );
      case 'protocol-failed':
        return familiar(
          '૮ ˶⊙ ﻌ ⊙˶ ა',
          'RUNTIME PROTOCOL FAILED',
          'PROTOCOL FAILED',
          STAR_COMMAND_COLORS.red,
        );
      case 'unexpectedly-exited':
        return familiar(
          '(⊙﹏⊙)',
          'RUNTIME EXITED UNEXPECTEDLY',
          'RUNTIME EXITED',
          STAR_COMMAND_COLORS.red,
        );
      case 'stopping':
        return familiar(
          '૮ ˶- ﻌ -˶ ა',
          'RUNTIME STOPPING…',
          'STOPPING',
          STAR_COMMAND_COLORS.gold,
        );
      case 'stopped':
        return familiar('૮ ˶ᵕ ﻌ ᵕ˶ ა', 'RUNTIME STOPPED', 'STOPPED', STAR_COMMAND_COLORS.violet);
    }
  }

  switch (sessionState.status) {
    case 'idle':
      return familiar(
        '૮ ˶ᵔ ᵕ ᵔ˶ ა',
        'READY FOR A MISSION!',
        'READY',
        STAR_COMMAND_COLORS.mint,
      );
    case 'starting':
      return familiar(
        '૮ ˶• ᴗ •˶ ა',
        'SUMMONING THE MISSION…',
        'SUMMONING',
        STAR_COMMAND_COLORS.cyan,
      );
    case 'running':
      return familiar('٩(ˊᗜˋ*)و', 'POWERING UP!', 'RUNNING', STAR_COMMAND_COLORS.pink);
    case 'awaiting_approval':
      return familiar('(๑•̀ᗝ•́)૭', 'ACTION REQUIRED', 'ACTION REQUIRED', STAR_COMMAND_COLORS.gold);
    case 'cancelling':
      return familiar(
        '૮ ˶• ﻌ •˶ ა',
        'CANCELLATION REQUESTED · WAITING FOR PYTHON',
        'CANCELLING',
        STAR_COMMAND_COLORS.gold,
      );
    case 'completed':
      return familiar('ヽ(>∀<☆)ノ', 'MISSION COMPLETE!', 'COMPLETE', STAR_COMMAND_COLORS.mint);
    case 'cancelled':
      return familiar(
        '૮ ˶ᵔ ﻌ ᵔ˶ ა',
        'MISSION CANCELLED',
        'CANCELLED',
        STAR_COMMAND_COLORS.gold,
      );
    case 'failed':
      return familiar('(｡•́︿•̀｡)', 'MISSION FAILED', 'FAILED', STAR_COMMAND_COLORS.red);
    case 'protocol-failed':
      return familiar(
        '(⊙﹏⊙)',
        'PROTOCOL FAILED · RESTART REQUIRED',
        'PROTOCOL FAILED',
        STAR_COMMAND_COLORS.red,
      );
  }
}

/**
 * Render the responsive Magical Mission projection for the existing Ink controller.
 *
 * The component adds no timers, focus targets, state transitions, or callbacks. Terminal resize can
 * only select a different composition; the parent keeps the same draft and immutable projections.
 *
 * @param properties - Existing UI projections plus the parent-owned draft and feedback.
 * @returns A wide, stacked, or compact Star Command terminal tree.
 */
export function MagicalMissionView({
  runtimeState,
  sessionState,
  draft,
  inputFeedback,
  canCancel,
  terminalEnvironment = {
    noColor: process.env.NO_COLOR,
    term: process.env.TERM,
  },
}: MagicalMissionViewProperties): ReactElement {
  const {columns, rows} = useWindowSize();
  const presentation = resolveMissionPresentation(columns, rows, terminalEnvironment);
  const familiarProjection = projectFamiliar(runtimeState, sessionState);

  return (
    <Box alignItems="center" flexDirection="column">
      <Box
        flexDirection="column"
        maxWidth={MAXIMUM_MISSION_COLUMNS}
        paddingX={presentation.layout === 'compact' ? 0 : 1}
        width="100%"
      >
        <MissionHeader
          presentation={presentation}
          runtimeState={runtimeState}
          sessionState={sessionState}
        />
        <MissionAlerts
          presentation={presentation}
          runtimeState={runtimeState}
          sessionState={sessionState}
        />

        <Box
          flexDirection={
            presentation.layout === 'wide' && presentation.roomy ? 'row' : 'column'
          }
          marginTop={presentation.roomy ? 1 : 0}
        >
          <MissionLog presentation={presentation} turns={sessionState.turns} />
          {presentation.showFamiliar ? (
            <FamiliarPanel
              projection={familiarProjection}
              presentation={presentation}
            />
          ) : null}
        </Box>

        <MissionInput
          draft={draft}
          presentation={presentation}
          runtimeState={runtimeState}
          sessionState={sessionState}
        />
        {inputFeedback === undefined ? null : (
          <Text {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
            INPUT NOTICE · {inputFeedback}
          </Text>
        )}

        <Box flexDirection="column" marginTop={presentation.roomy ? 1 : 0}>
          <SessionStatus
            canCancel={canCancel}
            presentation={presentation}
            state={sessionState}
          />
          <RuntimeStatus presentation={presentation} state={runtimeState} />
        </Box>
      </Box>
    </Box>
  );
}

function MissionHeader({
  presentation,
  runtimeState,
  sessionState,
}: {
  readonly presentation: MissionPresentation;
  readonly runtimeState: RuntimeState;
  readonly sessionState: SessionState;
}): ReactElement {
  const title = `${presentation.showEmoji ? '✨ ' : ''}Code Assist Harness`;
  const mission = `MISSION: ${statusLabel(sessionState.status)}`;

  if (presentation.layout === 'compact') {
    return (
      <Box flexDirection="column">
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.pink)}>
          {title}
        </Text>
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.violet)}>STAR COMMAND</Text>
      </Box>
    );
  }

  return (
    <Box
      backgroundColor={
        presentation.colorEnabled ? STAR_COMMAND_COLORS.headerBackground : undefined
      }
      {...missionBorderColor(presentation, STAR_COMMAND_COLORS.violet)}
      borderStyle={presentation.panelBorder === 'classic' ? 'classic' : 'double'}
      flexDirection={presentation.layout === 'wide' ? 'row' : 'column'}
      justifyContent="space-between"
      paddingX={1}
    >
      <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.headerText)}>
        {title} // STAR COMMAND
      </Text>
      <Text {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
        {mission} · POWER: {runtimePower(runtimeState)}
        {showCelebration(runtimeState, sessionState, presentation) ? ' 💖' : ''}
      </Text>
    </Box>
  );
}

function MissionAlerts({
  presentation,
  runtimeState,
  sessionState,
}: {
  readonly presentation: MissionPresentation;
  readonly runtimeState: RuntimeState;
  readonly sessionState: SessionState;
}): ReactElement | null {
  const runtimeFailure = runtimeFailureAlert(runtimeState);
  const sessionFailure = sessionFailureAlert(sessionState);
  const runtimeWarning = runtimeState.status === 'running' ? runtimeState.warning : undefined;
  const recordingWarning =
    runtimeState.status === 'running' ? runtimeState.recordingWarning : undefined;

  if (
    runtimeFailure === undefined &&
    sessionFailure === undefined &&
    runtimeWarning === undefined &&
    recordingWarning === undefined
  ) {
    return null;
  }

  return (
    <Box
      {...missionBorderColor(presentation, STAR_COMMAND_COLORS.gold)}
      borderStyle={presentation.panelBorder}
      flexDirection="column"
      marginTop={presentation.roomy ? 1 : 0}
      paddingX={1}
    >
      {runtimeFailure === undefined ? null : (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          ERROR · {runtimeFailure}
        </Text>
      )}
      {sessionFailure === undefined ? null : (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          ERROR · {sessionFailure}
        </Text>
      )}
      {runtimeWarning === undefined ? null : (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          WARNING · Runtime warning ({runtimeWarning.code}): {runtimeWarning.message}
        </Text>
      )}
      {recordingWarning === undefined ? null : (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          WARNING · Recording warning ({recordingWarning.code}): {recordingWarning.message}
        </Text>
      )}
    </Box>
  );
}

function MissionLog({
  presentation,
  turns,
}: {
  readonly presentation: MissionPresentation;
  readonly turns: readonly ConversationTurn[];
}): ReactElement {
  return (
    <Box
      {...missionBorderColor(presentation, STAR_COMMAND_COLORS.violet)}
      borderStyle={presentation.panelBorder}
      flexDirection="column"
      flexGrow={1}
      paddingX={1}
    >
      <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.violet)}>
        MISSION LOG · Conversation
      </Text>
      <Conversation presentation={presentation} turns={turns} />
    </Box>
  );
}

function Conversation({
  presentation,
  turns,
}: {
  readonly presentation: MissionPresentation;
  readonly turns: readonly ConversationTurn[];
}): ReactElement {
  if (turns.length === 0) {
    return <Text dimColor>No messages yet.</Text>;
  }
  return (
    <>
      {turns.map((turn, index) => (
        <Box
          key={turn.commandId}
          flexDirection="column"
          marginBottom={presentation.roomy || index < turns.length - 1 ? 1 : 0}
        >
          <Text>
            <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.cyan)}>
              {presentation.showEmoji ? '🍓 ' : ''}You:
            </Text>{' '}
            {turn.task}
          </Text>
          <Text>
            <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.violet)}>
              {presentation.showEmoji ? '🐣 ' : ''}Assistant:
            </Text>{' '}
            {assistantText(turn, presentation)}
          </Text>
        </Box>
      ))}
    </>
  );
}

function FamiliarPanel({
  projection,
  presentation,
}: {
  readonly projection: FamiliarProjection;
  readonly presentation: MissionPresentation;
}): ReactElement {
  if (presentation.layout === 'compact' || !presentation.roomy) {
    return (
      <Box marginTop={presentation.roomy ? 1 : 0}>
        <Text bold {...missionColor(presentation, projection.color)}>
          {presentation.layout === 'compact' ? '' : 'FAMILIAR · '}
          {projection.face} · {projection.compactStatus}
        </Text>
      </Box>
    );
  }

  if (presentation.layout === 'stacked') {
    return (
      <Box
        {...missionBorderColor(presentation, STAR_COMMAND_COLORS.pink)}
        borderStyle={presentation.panelBorder}
        marginTop={1}
        paddingX={1}
      >
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.pink)}>
          YOUR FAMILIAR ·{' '}
        </Text>
        <Text {...missionColor(presentation, projection.color)}>
          {projection.face} · {projection.callout}
        </Text>
      </Box>
    );
  }

  return (
    <Box
      alignItems="center"
      {...missionBorderColor(presentation, STAR_COMMAND_COLORS.pink)}
      borderStyle={presentation.panelBorder}
      flexDirection="column"
      flexShrink={0}
      marginLeft={1}
      paddingX={1}
      width={30}
    >
      <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.pink)}>
        YOUR FAMILIAR
      </Text>
      <Box marginTop={1}>
        <Text {...missionColor(presentation, projection.color)}>{projection.face}</Text>
      </Box>
      <Text bold {...missionColor(presentation, projection.color)}>
        {projection.callout}
      </Text>
    </Box>
  );
}

function MissionInput({
  draft,
  presentation,
  runtimeState,
  sessionState,
}: {
  readonly draft: string;
  readonly presentation: MissionPresentation;
  readonly runtimeState: RuntimeState;
  readonly sessionState: SessionState;
}): ReactElement {
  const heading = taskInputHeading(runtimeState, sessionState, presentation);

  return (
    <Box flexDirection="column" marginTop={presentation.roomy ? 1 : 0}>
      <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.cyan)}>
        {heading}
      </Text>
      <Box
        {...missionBorderColor(presentation, STAR_COMMAND_COLORS.cyan)}
        borderStyle={presentation.panelBorder}
        paddingX={1}
      >
        {draft.length === 0 ? (
          <Text>
            <Text {...missionColor(presentation, STAR_COMMAND_COLORS.cyan)}>&gt; </Text>
            <Text dimColor>Type a task and press Enter</Text>
          </Text>
        ) : (
          <Text>
            <Text {...missionColor(presentation, STAR_COMMAND_COLORS.cyan)}>&gt; </Text>
            {draft}
          </Text>
        )}
      </Box>
    </Box>
  );
}

function SessionStatus({
  state,
  canCancel,
  presentation,
}: {
  readonly state: SessionState;
  readonly canCancel: boolean;
  readonly presentation: MissionPresentation;
}): ReactElement {
  switch (state.status) {
    case 'idle':
      return <Text>Session status: idle · ready for a task</Text>;
    case 'starting':
      return <Text>Session status: starting · waiting for Python</Text>;
    case 'running':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.pink)}>
          Session status: running · streaming response{canCancel ? ' · Esc to cancel' : ''}
        </Text>
      );
    case 'awaiting_approval':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Session status: awaiting approval · waiting for a decision
          {canCancel ? ' · Esc to cancel' : ''}
        </Text>
      );
    case 'cancelling':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Session status: cancelling · waiting for Python
        </Text>
      );
    case 'completed':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.mint)}>
          Session status: completed · ready for another task
        </Text>
      );
    case 'cancelled':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Session status: cancelled · ready for another task
        </Text>
      );
    case 'failed': {
      const failure = state.turns.at(-1)?.sessionFailure;
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Session status: failed
          {failure === undefined ? '' : ` (${failure.code}) · ${failure.message}`} · ready for
          another task
        </Text>
      );
    }
    case 'protocol-failed':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Session status: protocol failed · {state.protocolFailure}
        </Text>
      );
  }
}

function RuntimeStatus({
  state,
  presentation,
}: {
  readonly state: RuntimeState;
  readonly presentation: MissionPresentation;
}): ReactElement {
  switch (state.status) {
    case 'starting':
      return <Text>Status: starting Python runtime · workspace: {state.workspace}</Text>;
    case 'running':
      if (presentation.layout === 'compact') {
        return (
          <Box flexDirection="column">
            <Text {...missionColor(presentation, STAR_COMMAND_COLORS.mint)}>
              Status: runtime running
            </Text>
            <Text>workspace: {state.workspace}</Text>
            <Text>Ctrl+C to exit</Text>
          </Box>
        );
      }
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.mint)}>
          Status: runtime running · workspace: {state.workspace} · Ctrl+C to exit
        </Text>
      );
    case 'failed-to-start':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Status: runtime failed to start · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'protocol-failed':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Status: runtime protocol failed ({state.code}) · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'unexpectedly-exited':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Status: runtime failed · {state.message} · Ctrl+C to exit
        </Text>
      );
    case 'stopping':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Status: stopping Python runtime…
        </Text>
      );
    case 'stopped':
      return <Text>Status: Python runtime stopped.</Text>;
  }
}

function assistantText(
  turn: ConversationTurn,
  presentation: MissionPresentation,
): ReactElement | string {
  if (turn.assistantText.length > 0) {
    return turn.assistantText;
  }
  switch (turn.status) {
    case 'starting':
      return <Text dimColor>Starting…</Text>;
    case 'running':
      return <Text dimColor>Waiting for response…</Text>;
    case 'awaiting_approval':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Waiting for approval…
        </Text>
      );
    case 'cancelling':
      return (
        <Text bold {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Cancelling…
        </Text>
      );
    case 'cancelled':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.gold)}>
          Cancelled before a response.
        </Text>
      );
    case 'completed':
      return <Text dimColor>No response text.</Text>;
    case 'failed':
      return (
        <Text {...missionColor(presentation, STAR_COMMAND_COLORS.red)}>
          Failed before a response.
        </Text>
      );
  }
}

function familiar(
  face: string,
  callout: string,
  compactStatus: string,
  color: string,
): FamiliarProjection {
  return {face, callout, compactStatus, color};
}

function missionColor(
  presentation: MissionPresentation,
  color: string,
): {readonly color?: string} {
  return presentation.colorEnabled ? {color} : {};
}

function missionBorderColor(
  presentation: MissionPresentation,
  borderColor: string,
): {readonly borderColor?: string} {
  return presentation.colorEnabled ? {borderColor} : {};
}

function runtimeFailureAlert(state: RuntimeState): string | undefined {
  switch (state.status) {
    case 'failed-to-start':
      return `Runtime failed to start: ${state.message}`;
    case 'protocol-failed':
      return `Runtime protocol failed (${state.code}): ${state.message}`;
    case 'unexpectedly-exited':
      return `Runtime failed: ${state.message}`;
    case 'starting':
    case 'running':
    case 'stopping':
    case 'stopped':
      return undefined;
  }
}

function sessionFailureAlert(state: SessionState): string | undefined {
  if (state.status === 'protocol-failed') {
    return `Session protocol failed: ${state.protocolFailure ?? 'Restart required.'}`;
  }
  if (state.status !== 'failed') {
    return undefined;
  }
  const failure = state.turns.at(-1)?.sessionFailure;
  return failure === undefined
    ? 'Session failed before a bounded reason was available.'
    : `Session failed (${failure.code}): ${failure.message}`;
}

function showCelebration(
  runtimeState: RuntimeState,
  sessionState: SessionState,
  presentation: MissionPresentation,
): boolean {
  return (
    presentation.showEmoji &&
    runtimeState.status === 'running' &&
    runtimeState.warning === undefined &&
    runtimeState.recordingWarning === undefined &&
    (sessionState.status === 'idle' ||
      sessionState.status === 'running' ||
      sessionState.status === 'completed')
  );
}

function taskInputHeading(
  runtimeState: RuntimeState,
  sessionState: SessionState,
  presentation: MissionPresentation,
): string {
  if (presentation.layout === 'compact') {
    return 'Task input';
  }
  if (runtimeState.status !== 'running') {
    return 'TASK DRAFT · Task input · waiting for runtime';
  }
  if (sessionState.status === 'protocol-failed') {
    return 'TASK DRAFT · Task input · restart required before submission';
  }
  if (isActiveSessionStatus(sessionState.status)) {
    return 'NEXT COMMAND · Task input · draft preserved while mission runs';
  }
  return `CAST YOUR NEXT COMMAND${presentation.showEmoji ? ' 🎀' : ''} · Task input`;
}

function runtimePower(state: RuntimeState): string {
  switch (state.status) {
    case 'running':
      return 'READY';
    case 'starting':
      return 'WAKING';
    case 'stopping':
      return 'STOPPING';
    case 'stopped':
      return 'OFFLINE';
    case 'failed-to-start':
    case 'protocol-failed':
    case 'unexpectedly-exited':
      return 'ALERT';
  }
}

function statusLabel(value: string): string {
  return value.replaceAll('-', ' ').replaceAll('_', ' ').toUpperCase();
}
