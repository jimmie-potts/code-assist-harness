import type {ProtocolEvent} from './protocol.js';

/** Mocked-session event accepted by the local conversation projection. */
export type SessionEvent = Extract<
  ProtocolEvent,
  {
    readonly type:
      | 'session.started'
      | 'assistant.delta'
      | 'assistant.completed'
      | 'session.completed'
      | 'session.cancelled';
  }
>;

/** One local command or validated event in the ordered session projection stream. */
export type SessionUpdate =
  | {
      readonly type: 'task.submitted';
      readonly commandId: string;
      readonly task: string;
    }
  | {
      readonly type: 'cancel.requested';
      readonly commandId: string;
      readonly sessionId: string;
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
  readonly status: 'starting' | 'running' | 'cancelling' | 'completed' | 'cancelled';
  /** Accepted assistant deltas in sequence order. */
  readonly assistantText: string;
  /** Last accepted Python sequence, or zero before the session starts. */
  readonly lastSequence: number;
  /** Whether Python has confirmed the accumulated assistant text. */
  readonly assistantCompleted: boolean;
  /** Command that requested cancellation, present only after a validated local request. */
  readonly cancelCommandId?: string;
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
    | 'cancelling'
    | 'completed'
    | 'cancelled'
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
 * A local cancellation request enters `cancelling`, but only Python's `session.cancelled` event
 * enters the terminal `cancelled` state. Start-correlated stream and completion events remain legal
 * while cancellation is pending, so whichever valid terminal event arrives first wins.
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
  if (update.type === 'cancel.requested') {
    return reduceCancellationRequest(state, update);
  }
  return reduceEvent(state, update.event);
}

function reduceSubmission(
  state: SessionState,
  update: Extract<SessionUpdate, {readonly type: 'task.submitted'}>,
): SessionState {
  if (
    state.status === 'starting' ||
    state.status === 'running' ||
    state.status === 'cancelling'
  ) {
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

function reduceCancellationRequest(
  state: SessionState,
  update: Extract<SessionUpdate, {readonly type: 'cancel.requested'}>,
): SessionState {
  const turn = state.turns.at(-1);
  if (
    state.status !== 'running' ||
    turn?.status !== 'running' ||
    turn.sessionId === undefined
  ) {
    return failProjection(state, 'Cancellation was requested without an addressable active session.');
  }
  if (update.sessionId !== turn.sessionId) {
    return failProjection(state, 'Cancellation did not target the active session.');
  }
  return replaceNewestTurn(
    state,
    {...turn, status: 'cancelling', cancelCommandId: update.commandId},
    'cancelling',
  );
}

function reduceEvent(state: SessionState, event: SessionEvent): SessionState {
  const turn = state.turns.at(-1);
  if (
    turn === undefined ||
    (turn.status !== 'starting' && turn.status !== 'running' && turn.status !== 'cancelling')
  ) {
    return failProjection(state, `Received ${event.type} without an active submitted task.`);
  }
  const expectedCorrelationId =
    event.type === 'session.cancelled' ? turn.cancelCommandId : turn.commandId;
  if (event.correlation_id !== expectedCorrelationId) {
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
    case 'session.cancelled':
      if (turn.status !== 'cancelling' || turn.cancelCommandId === undefined) {
        return failProjection(state, 'session.cancelled arrived without a cancellation request.');
      }
      return replaceNewestTurn(
        state,
        {...turn, status: 'cancelled', lastSequence: event.sequence},
        'cancelled',
      );
  }
}

function sessionEventMismatch(
  turn: ConversationTurn,
  event: Exclude<SessionEvent, {readonly type: 'session.started'}>,
): string | undefined {
  if (
    (turn.status !== 'running' && turn.status !== 'cancelling') ||
    turn.sessionId === undefined
  ) {
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
  status: SessionState['status'] = turn.status === 'cancelling' ? 'cancelling' : 'running',
): SessionState {
  return {status, turns: [...state.turns.slice(0, -1), turn]};
}

function failProjection(state: SessionState, message: string): SessionState {
  return {...state, status: 'protocol-failed', protocolFailure: message};
}
