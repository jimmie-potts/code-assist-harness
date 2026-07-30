import type {ProtocolEvent} from './protocol.js';

/** Lifecycle states shared by the Python authority and TypeScript boundary projection. */
export type SessionLifecycleStatus =
  | 'idle'
  | 'starting'
  | 'running'
  | 'awaiting_approval'
  | 'cancelling'
  | 'completed'
  | 'cancelled'
  | 'failed';

/** Safe failure details supplied by an authoritative `session.failed` event. */
export interface SessionFailure {
  /** Stable machine-readable failure classification. */
  readonly code: string;
  /** Bounded, validated message that is safe for display. */
  readonly message: string;
}

/**
 * Immutable state for exactly one session lifecycle.
 *
 * `idle` is the only reusable state. Terminal states are absorbing, sequence zero means no Python
 * event has been accepted, and nullable identities are populated only by their owning transition.
 * This type is local domain state rather than a wire shape.
 */
export interface SessionLifecycleState {
  /** Current state in the closed lifecycle. */
  readonly status: SessionLifecycleStatus;
  /** Command that submitted the task, once known. */
  readonly startCommandId: string | null;
  /** Exact submitted task text, retained for the conversation projection. */
  readonly task: string | null;
  /** Python-owned session identity, assigned by `session.started`. */
  readonly sessionId: string | null;
  /** Command that requested cancellation, once accepted locally. */
  readonly cancelCommandId: string | null;
  /** Last accepted authoritative sequence, or zero before `session.started`. */
  readonly lastSequence: number;
  /** Assistant deltas accepted in strict sequence order. */
  readonly assistantText: string;
  /** Whether `assistant.completed` confirmed the accumulated text. */
  readonly assistantCompleted: boolean;
  /** Authoritative safe failure, present only in `failed`. */
  readonly sessionFailure: SessionFailure | null;
}

/** Empty state used before one task is submitted. */
export const INITIAL_SESSION_LIFECYCLE_STATE: SessionLifecycleState = {
  status: 'idle',
  startCommandId: null,
  task: null,
  sessionId: null,
  cancelCommandId: null,
  lastSequence: 0,
  assistantText: '',
  assistantCompleted: false,
  sessionFailure: null,
};

/** Local fact that a validated task command was sent to Python. */
export interface TaskSubmitted {
  readonly type: 'task.submitted';
  readonly commandId: string;
  readonly task: string;
}

/** Local fact that a validated cancellation command was sent to Python. */
export interface CancelRequested {
  readonly type: 'cancel.requested';
  readonly commandId: string;
  readonly sessionId: string;
}

/** Domain-only fact that the active session is waiting for a future approval decision. */
export interface ApprovalRequested {
  readonly type: 'approval.requested';
  readonly sessionId: string;
}

/** Domain-only fact that a future approval interaction returned control to the active session. */
export interface ApprovalResolved {
  readonly type: 'approval.resolved';
  readonly sessionId: string;
}

/** Validated version 1 wire event that participates in the session lifecycle. */
export type SessionLifecycleEvent = Extract<
  ProtocolEvent,
  {
    readonly type:
      | 'session.started'
      | 'assistant.delta'
      | 'assistant.completed'
      | 'session.completed'
      | 'session.cancelled'
      | 'session.failed';
  }
>;

/** One trusted local fact or validated wire event accepted by the pure reducer. */
export type SessionLifecycleInput =
  | TaskSubmitted
  | CancelRequested
  | ApprovalRequested
  | ApprovalResolved
  | SessionLifecycleEvent;

/** Stable, payload-free classifications for rejected lifecycle transitions. */
export type SessionInvariantFailureCode =
  | 'illegal_transition'
  | 'correlation_mismatch'
  | 'session_mismatch'
  | 'sequence_regression'
  | 'sequence_gap'
  | 'assistant_after_completion'
  | 'assistant_already_completed'
  | 'assistant_completion_mismatch'
  | 'session_completion_before_assistant'
  | 'terminal_state_absorbing';

/**
 * Sanitized rejection from the lifecycle reducer.
 *
 * The diagnostic deliberately omits identifiers, task text, assistant text, and event payloads.
 */
export interface SessionInvariantFailure {
  /** Stable reason the input was rejected. */
  readonly code: SessionInvariantFailureCode;
  /** State from which the invalid transition was attempted. */
  readonly priorStatus: SessionLifecycleStatus;
  /** Discriminator of the rejected trusted input. */
  readonly eventType: SessionLifecycleInput['type'];
}

/** Result of reducing one input or replaying an ordered input sequence. */
export type SessionLifecycleResult =
  | {readonly ok: true; readonly state: SessionLifecycleState}
  | {
      readonly ok: false;
      /** Exact state object supplied to the rejected transition. */
      readonly state: SessionLifecycleState;
      readonly failure: SessionInvariantFailure;
    };

const TERMINAL_STATUSES: ReadonlySet<SessionLifecycleStatus> = new Set([
  'completed',
  'cancelled',
  'failed',
]);

const ACTIVE_STATUSES: ReadonlySet<SessionLifecycleStatus> = new Set([
  'starting',
  'running',
  'awaiting_approval',
  'cancelling',
]);

const CANCELLABLE_STATUSES: ReadonlySet<SessionLifecycleStatus> = new Set([
  'running',
  'awaiting_approval',
]);

/** Return whether a status represents live work that blocks another submission. */
export function isActiveSessionStatus(status: SessionLifecycleStatus): boolean {
  return ACTIVE_STATUSES.has(status);
}

/** Return whether a status is absorbing for a single-session lifecycle. */
export function isTerminalSessionStatus(status: SessionLifecycleStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

/** Return whether the user can request cancellation in this status. */
export function isCancellableSessionStatus(status: SessionLifecycleStatus): boolean {
  return CANCELLABLE_STATUSES.has(status);
}

/**
 * Reduce one trusted input into one immutable session lifecycle.
 *
 * The reducer is strict and pure. It accepts only the documented transition matrix, checks
 * correlation before identity and sequence, and never mutates or replaces state on failure.
 * Duplicate terminal events are diagnostic failures because terminal states are absorbing.
 * Callers must validate wire events before invoking this function.
 *
 * @param state - Current state for exactly one task/session.
 * @param input - Trusted local fact or validated version 1 session event.
 * @returns A new state on success, or the exact prior state plus a sanitized failure.
 */
export function reduceSessionLifecycle(
  state: SessionLifecycleState,
  input: SessionLifecycleInput,
): SessionLifecycleResult {
  if (isTerminalSessionStatus(state.status)) {
    return reject(state, input, 'terminal_state_absorbing');
  }
  if (!isLegalTransition(state.status, input.type)) {
    return reject(state, input, 'illegal_transition');
  }

  switch (input.type) {
    case 'task.submitted':
      return accept({
        ...INITIAL_SESSION_LIFECYCLE_STATE,
        status: 'starting',
        startCommandId: input.commandId,
        task: input.task,
      });
    case 'cancel.requested':
      if (input.sessionId !== state.sessionId) {
        return reject(state, input, 'session_mismatch');
      }
      return accept({
        ...state,
        status: 'cancelling',
        cancelCommandId: input.commandId,
      });
    case 'approval.requested':
      if (input.sessionId !== state.sessionId) {
        return reject(state, input, 'session_mismatch');
      }
      return accept({...state, status: 'awaiting_approval'});
    case 'approval.resolved':
      if (input.sessionId !== state.sessionId) {
        return reject(state, input, 'session_mismatch');
      }
      return accept({...state, status: 'running'});
    default:
      return reduceSessionEvent(state, input);
  }
}

/**
 * Replay trusted inputs deterministically, stopping at the first invariant failure.
 *
 * @param inputs - Ordered local facts and validated wire events.
 * @param initialState - Starting state; defaults to a fresh idle lifecycle.
 * @returns The final success or the first failure with its exact prior state.
 */
export function replaySessionLifecycle(
  inputs: readonly SessionLifecycleInput[],
  initialState: SessionLifecycleState = INITIAL_SESSION_LIFECYCLE_STATE,
): SessionLifecycleResult {
  let state = initialState;
  for (const input of inputs) {
    const result = reduceSessionLifecycle(state, input);
    if (!result.ok) {
      return result;
    }
    state = result.state;
  }
  return accept(state);
}

function reduceSessionEvent(
  state: SessionLifecycleState,
  event: SessionLifecycleEvent,
): SessionLifecycleResult {
  const expectedCorrelationId =
    event.type === 'session.cancelled' ? state.cancelCommandId : state.startCommandId;
  if (event.correlation_id !== expectedCorrelationId) {
    return reject(state, event, 'correlation_mismatch');
  }

  if (event.type === 'session.started') {
    const sequenceFailure = sequenceFailureCode(state.lastSequence, event.sequence);
    if (sequenceFailure !== null) {
      return reject(state, event, sequenceFailure);
    }
    return accept({
      ...state,
      status: 'running',
      sessionId: event.session_id,
      lastSequence: event.sequence,
    });
  }

  if (event.session_id !== state.sessionId) {
    return reject(state, event, 'session_mismatch');
  }
  const sequenceFailure = sequenceFailureCode(state.lastSequence, event.sequence);
  if (sequenceFailure !== null) {
    return reject(state, event, sequenceFailure);
  }

  switch (event.type) {
    case 'assistant.delta':
      if (state.assistantCompleted) {
        return reject(state, event, 'assistant_after_completion');
      }
      return accept({
        ...state,
        assistantText: state.assistantText + event.payload.text,
        lastSequence: event.sequence,
      });
    case 'assistant.completed':
      if (state.assistantCompleted) {
        return reject(state, event, 'assistant_already_completed');
      }
      if (event.payload.text !== state.assistantText) {
        return reject(state, event, 'assistant_completion_mismatch');
      }
      return accept({...state, assistantCompleted: true, lastSequence: event.sequence});
    case 'session.completed':
      if (!state.assistantCompleted) {
        return reject(state, event, 'session_completion_before_assistant');
      }
      return accept({...state, status: 'completed', lastSequence: event.sequence});
    case 'session.cancelled':
      return accept({...state, status: 'cancelled', lastSequence: event.sequence});
    case 'session.failed':
      return accept({
        ...state,
        status: 'failed',
        lastSequence: event.sequence,
        sessionFailure: {...event.payload},
      });
  }
}

function isLegalTransition(
  status: SessionLifecycleStatus,
  type: SessionLifecycleInput['type'],
): boolean {
  switch (type) {
    case 'task.submitted':
      return status === 'idle';
    case 'session.started':
      return status === 'starting';
    case 'assistant.delta':
    case 'assistant.completed':
    case 'session.completed':
      return status === 'running' || status === 'cancelling';
    case 'approval.requested':
      return status === 'running';
    case 'approval.resolved':
      return status === 'awaiting_approval';
    case 'cancel.requested':
      return status === 'running' || status === 'awaiting_approval';
    case 'session.cancelled':
      return status === 'cancelling';
    case 'session.failed':
      return status === 'running' || status === 'awaiting_approval' || status === 'cancelling';
  }
}

function sequenceFailureCode(
  lastSequence: number,
  sequence: number,
): 'sequence_regression' | 'sequence_gap' | null {
  const expected = lastSequence + 1;
  if (sequence < expected) {
    return 'sequence_regression';
  }
  if (sequence > expected) {
    return 'sequence_gap';
  }
  return null;
}

function accept(state: SessionLifecycleState): SessionLifecycleResult {
  return {ok: true, state};
}

function reject(
  state: SessionLifecycleState,
  input: SessionLifecycleInput,
  code: SessionInvariantFailureCode,
): SessionLifecycleResult {
  return {
    ok: false,
    state,
    failure: {code, priorStatus: state.status, eventType: input.type},
  };
}
