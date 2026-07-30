import type {
  ApprovalRequested,
  ApprovalResolved,
  CancelRequested,
  SessionFailure,
  SessionInvariantFailure,
  SessionLifecycleEvent,
  SessionLifecycleInput,
  SessionLifecycleState,
  SessionLifecycleStatus,
  TaskSubmitted,
} from './session-lifecycle.js';
import {
  INITIAL_SESSION_LIFECYCLE_STATE,
  isTerminalSessionStatus,
  reduceSessionLifecycle,
} from './session-lifecycle.js';

/** Validated protocol event accepted by the local conversation projection. */
export type SessionEvent = SessionLifecycleEvent;

/**
 * One local domain fact or validated event in the ordered conversation projection stream.
 *
 * Approval updates are internal domain facts, not protocol-v1 wire messages. They reserve the
 * projection seam for the later approval unit without inventing an unvalidated wire contract.
 */
export type SessionUpdate =
  | TaskSubmitted
  | CancelRequested
  | ApprovalRequested
  | ApprovalResolved
  | {readonly type: 'event.received'; readonly event: SessionEvent};

/** Visible immutable projection of one submitted task and its authoritative Python session. */
export interface ConversationTurn {
  /** Command that caused this turn. */
  readonly commandId: string;
  /** Exact user text sent in the `session.start` payload. */
  readonly task: string;
  /** Python-owned session identity, available after `session.started`. */
  readonly sessionId?: string;
  /** Session-local lifecycle projected from trusted facts and validated events. */
  readonly status: Exclude<SessionLifecycleStatus, 'idle'>;
  /** Accepted assistant deltas in sequence order. */
  readonly assistantText: string;
  /** Last accepted Python sequence, or zero before the session starts. */
  readonly lastSequence: number;
  /** Whether Python has confirmed the accumulated assistant text. */
  readonly assistantCompleted: boolean;
  /** Command that requested cancellation, present only after a validated local request. */
  readonly cancelCommandId?: string;
  /** Validated and bounded authoritative failure, present only for `failed`. */
  readonly sessionFailure?: SessionFailure;
}

/**
 * Local, immutable multi-turn conversation projection rendered by Ink.
 *
 * `lifecycle` represents exactly the newest turn and delegates every transition to the shared
 * pure lifecycle reducer. Terminal lifecycle states stay absorbing for diagnostics; submitting a
 * later task explicitly starts a fresh lifecycle while preserving prior turns. `protocol-failed`
 * is a local fail-closed projection whose diagnostic contains only stable invariant metadata.
 */
export interface SessionState {
  /** Status of the newest turn, or `idle` before the first submission. */
  readonly status: SessionLifecycleStatus | 'protocol-failed';
  /** Completed turns plus the optional active turn in submission order. */
  readonly turns: readonly ConversationTurn[];
  /** One-session reducer state for the newest turn. */
  readonly lifecycle: SessionLifecycleState;
  /** Bounded, payload-free invariant summary displayed after a rejected update. */
  readonly protocolFailure?: string;
  /** Structured payload-free invariant details retained for tests and diagnostics. */
  readonly protocolFailureDetails?: SessionInvariantFailure;
}

/** Empty projection used when the TUI first mounts. */
export const INITIAL_SESSION_STATE: SessionState = {
  status: 'idle',
  turns: [],
  lifecycle: INITIAL_SESSION_LIFECYCLE_STATE,
};

/**
 * Reduce one ordered local/session update into visible multi-turn conversation state.
 *
 * The adapter is pure and delegates all lifecycle legality, correlation, identity, ordering, and
 * completion checks to {@link reduceSessionLifecycle}. A terminal turn is retained when the next
 * task creates a fresh lifecycle. Rejected updates leave the trusted turns and lifecycle exactly
 * unchanged and expose only bounded invariant metadata, never command IDs or event payloads.
 *
 * @param state - Current immutable conversation projection.
 * @param update - Trusted local fact or validated session event in arrival order.
 * @returns The next projection, or the existing terminal protocol-failure projection.
 */
export function reduceSessionState(state: SessionState, update: SessionUpdate): SessionState {
  if (state.status === 'protocol-failed') {
    return state;
  }

  const input = lifecycleInput(update);
  const lifecycle =
    input.type === 'task.submitted' && isTerminalSessionStatus(state.lifecycle.status)
      ? INITIAL_SESSION_LIFECYCLE_STATE
      : state.lifecycle;
  const result = reduceSessionLifecycle(lifecycle, input);
  if (!result.ok) {
    return failProjection(state, result.failure);
  }

  if (input.type === 'task.submitted') {
    return {
      status: result.state.status,
      turns: [...state.turns, projectTurn(result.state)],
      lifecycle: result.state,
    };
  }

  if (state.turns.length === 0) {
    // This guard should be unreachable because the lifecycle reducer rejects non-submission input
    // from idle, but it keeps the adapter total if its representation changes independently.
    return failProjection(state, {
      code: 'illegal_transition',
      priorStatus: state.lifecycle.status,
      eventType: input.type,
    });
  }

  return {
    status: result.state.status,
    turns: [...state.turns.slice(0, -1), projectTurn(result.state)],
    lifecycle: result.state,
  };
}

/** Format structured reducer failure metadata without including rejected input payloads. */
export function formatSessionInvariantFailure(failure: SessionInvariantFailure): string {
  const explanation = INVARIANT_EXPLANATIONS[failure.code];
  return `${explanation} [${failure.code}; prior=${failure.priorStatus}; event=${failure.eventType}]`;
}

const INVARIANT_EXPLANATIONS: Readonly<Record<SessionInvariantFailure['code'], string>> = {
  illegal_transition: 'The session update is not legal from the current lifecycle state.',
  correlation_mismatch: 'The session event did not correlate to the active command.',
  session_mismatch: 'The session event did not belong to the active session.',
  sequence_regression: 'The session event did not carry the next session sequence.',
  sequence_gap: 'The session event did not carry the next session sequence.',
  assistant_after_completion: 'Assistant output arrived after assistant completion.',
  assistant_already_completed: 'Assistant completion was reported more than once.',
  assistant_completion_mismatch:
    'Assistant completion did not exactly confirm the accumulated deltas.',
  session_completion_before_assistant:
    'Session completion arrived before assistant completion.',
  terminal_state_absorbing: 'A session update arrived after the terminal outcome.',
};

function lifecycleInput(update: SessionUpdate): SessionLifecycleInput {
  return update.type === 'event.received' ? update.event : update;
}

function projectTurn(state: SessionLifecycleState): ConversationTurn {
  if (state.status === 'idle' || state.startCommandId === null || state.task === null) {
    throw new Error('A conversation turn requires a submitted lifecycle.');
  }
  return {
    commandId: state.startCommandId,
    task: state.task,
    ...(state.sessionId === null ? {} : {sessionId: state.sessionId}),
    status: state.status,
    assistantText: state.assistantText,
    lastSequence: state.lastSequence,
    assistantCompleted: state.assistantCompleted,
    ...(state.cancelCommandId === null ? {} : {cancelCommandId: state.cancelCommandId}),
    ...(state.sessionFailure === null ? {} : {sessionFailure: state.sessionFailure}),
  };
}

function failProjection(
  state: SessionState,
  failure: SessionInvariantFailure,
): SessionState {
  return {
    ...state,
    status: 'protocol-failed',
    protocolFailure: formatSessionInvariantFailure(failure),
    protocolFailureDetails: failure,
  };
}
