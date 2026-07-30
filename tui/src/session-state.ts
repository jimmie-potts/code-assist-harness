import type {ProtocolEvent} from './protocol.js';

/** CAH-005 mocked-session event accepted by the local conversation projection. */
export type SessionEvent = Extract<
  ProtocolEvent,
  {
    readonly type:
      | 'session.started'
      | 'assistant.delta'
      | 'assistant.completed'
      | 'session.completed';
  }
>;

/** One local command or validated event in the ordered session projection stream. */
export type SessionUpdate =
  | {
      readonly type: 'task.submitted';
      readonly commandId: string;
      readonly task: string;
    }
  | {readonly type: 'event.received'; readonly event: SessionEvent};

/** Visible state for one submitted task and its authoritative Python session. */
export interface ConversationTurn {
  /** Command that caused this turn. */
  readonly commandId: string;
  /** Exact user text sent in the `session.start` payload. */
  readonly task: string;
  /** Python-owned session identity, available after `session.started`. */
  readonly sessionId?: string;
  /** Session-local lifecycle projected from validated events. */
  readonly status: 'starting' | 'running' | 'completed';
  /** Accepted assistant deltas in sequence order. */
  readonly assistantText: string;
  /** Last accepted Python sequence, or zero before the session starts. */
  readonly lastSequence: number;
  /** Whether Python has confirmed the accumulated assistant text. */
  readonly assistantCompleted: boolean;
}

/**
 * Local, immutable conversation projection rendered by Ink.
 *
 * `idle` has no turns. A local submission enters `starting`; only `session.started` enters
 * `running`, and only a terminal Python event enters a terminal state. `protocol-failed` is a local
 * fail-closed state for an event that violates correlation, sequence, identity, or completion
 * invariants. Turns remain visible after runtime exit because runtime lifecycle changes are reduced
 * separately.
 */
export interface SessionState {
  /** Status of the newest turn, or `idle` before the first submission. */
  readonly status:
    | 'idle'
    | 'starting'
    | 'running'
    | 'completed'
    | 'protocol-failed';
  /** Completed turns plus the optional active turn in submission order. */
  readonly turns: readonly ConversationTurn[];
  /** Safe invariant failure displayed when an event cannot enter trusted UI state. */
  readonly protocolFailure?: string;
}

/** Empty projection used when the TUI first mounts. */
export const INITIAL_SESSION_STATE: SessionState = {status: 'idle', turns: []};

/**
 * Reduce one ordered local/session update into visible conversation state.
 *
 * The reducer is pure. It never guesses around duplicate, out-of-order, mismatched, or unknown
 * transitions: the first violation produces `protocol-failed`, and later updates are ignored.
 * `assistant.completed` must exactly equal accepted deltas, and `session.completed` is legal only
 * after that confirmation. Runtime lifecycle changes are intentionally outside this reducer.
 *
 * @param state - Current immutable conversation projection.
 * @param update - Local submission or validated session event in arrival order.
 * @returns A new projection, or the existing terminal protocol-failure projection.
 */
export function reduceSessionState(state: SessionState, update: SessionUpdate): SessionState {
  if (state.status === 'protocol-failed') {
    return state;
  }
  if (update.type === 'task.submitted') {
    return reduceSubmission(state, update);
  }
  return reduceEvent(state, update.event);
}

function reduceSubmission(
  state: SessionState,
  update: Extract<SessionUpdate, {readonly type: 'task.submitted'}>,
): SessionState {
  if (state.status === 'starting' || state.status === 'running') {
    return failProjection(state, 'A second task was submitted while a session was active.');
  }
  const turn: ConversationTurn = {
    commandId: update.commandId,
    task: update.task,
    status: 'starting',
    assistantText: '',
    lastSequence: 0,
    assistantCompleted: false,
  };
  return {status: 'starting', turns: [...state.turns, turn]};
}

function reduceEvent(state: SessionState, event: SessionEvent): SessionState {
  const turn = state.turns.at(-1);
  if (turn === undefined || (turn.status !== 'starting' && turn.status !== 'running')) {
    return failProjection(state, `Received ${event.type} without an active submitted task.`);
  }
  if (event.correlation_id !== turn.commandId) {
    return failProjection(state, `${event.type} did not correlate to the active task.`);
  }

  if (event.type === 'session.started') {
    if (turn.status !== 'starting' || event.sequence !== 1) {
      return failProjection(state, 'session.started must be the first event for a submitted task.');
    }
    return replaceNewestTurn(state, {
      ...turn,
      sessionId: event.session_id,
      status: 'running',
      lastSequence: event.sequence,
    });
  }

  const mismatch = sessionEventMismatch(turn, event);
  if (mismatch !== undefined) {
    return failProjection(state, mismatch);
  }

  switch (event.type) {
    case 'assistant.delta':
      if (turn.assistantCompleted) {
        return failProjection(state, 'assistant.delta arrived after assistant completion.');
      }
      return replaceNewestTurn(state, {
        ...turn,
        assistantText: turn.assistantText + event.payload.text,
        lastSequence: event.sequence,
      });
    case 'assistant.completed':
      if (turn.assistantCompleted || event.payload.text !== turn.assistantText) {
        return failProjection(
          state,
          'assistant.completed did not exactly confirm the accumulated deltas.',
        );
      }
      return replaceNewestTurn(state, {
        ...turn,
        assistantCompleted: true,
        lastSequence: event.sequence,
      });
    case 'session.completed':
      if (!turn.assistantCompleted) {
        return failProjection(state, 'session.completed arrived before assistant completion.');
      }
      return replaceNewestTurn(
        state,
        {...turn, status: 'completed', lastSequence: event.sequence},
        'completed',
      );
  }
}

function sessionEventMismatch(
  turn: ConversationTurn,
  event: Exclude<SessionEvent, {readonly type: 'session.started'}>,
): string | undefined {
  if (turn.status !== 'running' || turn.sessionId === undefined) {
    return `${event.type} arrived before session.started.`;
  }
  if (event.session_id !== turn.sessionId) {
    return `${event.type} did not belong to the active session.`;
  }
  if (event.sequence !== turn.lastSequence + 1) {
    return `${event.type} did not carry the next session sequence.`;
  }
  return undefined;
}

function replaceNewestTurn(
  state: SessionState,
  turn: ConversationTurn,
  status: SessionState['status'] = 'running',
): SessionState {
  return {status, turns: [...state.turns.slice(0, -1), turn]};
}

function failProjection(state: SessionState, message: string): SessionState {
  return {...state, status: 'protocol-failed', protocolFailure: message};
}
