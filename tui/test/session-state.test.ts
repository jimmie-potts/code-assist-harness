import {describe, expect, it} from 'vitest';

import {
  INITIAL_SESSION_STATE,
  reduceSessionState,
  type SessionEvent,
  type SessionState,
} from '../src/session-state.js';

const TIMESTAMP = '2026-07-30T12:00:00.000Z';

describe('reduceSessionState', () => {
  it('projects ordered deltas, authoritative completion, and a distinct second session', () => {
    let state = submit(INITIAL_SESSION_STATE, 'cmd_first', 'First task');
    expect(state.status).toBe('starting');

    state = receive(state, event('session.started', 'cmd_first', 'ses_first', 1, {}));
    expect(state.status).toBe('running');

    for (const [sequence, text, accumulated] of [
      [2, 'One ', 'One '],
      [3, 'mocked ', 'One mocked '],
      [4, 'answer.', 'One mocked answer.'],
    ] as const) {
      state = receive(
        state,
        event('assistant.delta', 'cmd_first', 'ses_first', sequence, {text}),
      );
      expect(state.turns.at(-1)?.assistantText).toBe(accumulated);
      expect(state.status).toBe('running');
    }

    state = receive(
      state,
      event('assistant.completed', 'cmd_first', 'ses_first', 5, {
        text: 'One mocked answer.',
      }),
    );
    expect(state.status).toBe('running');
    state = receive(state, event('session.completed', 'cmd_first', 'ses_first', 6, {}));
    expect(state.status).toBe('completed');

    state = submit(state, 'cmd_second', 'Second task');
    state = receive(state, event('session.started', 'cmd_second', 'ses_second', 1, {}));

    expect(state.status).toBe('running');
    expect(state.turns).toHaveLength(2);
    expect(state.turns[0]).toMatchObject({
      commandId: 'cmd_first',
      sessionId: 'ses_first',
      status: 'completed',
      assistantText: 'One mocked answer.',
      lastSequence: 6,
    });
    expect(state.turns[1]).toMatchObject({
      commandId: 'cmd_second',
      sessionId: 'ses_second',
      status: 'running',
      lastSequence: 1,
    });
  });

  it('projects cancelling until an authoritative cancelled terminal event arrives', () => {
    let state = runningState();
    state = receive(
      state,
      event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'partial'}),
    );
    state = cancel(state, 'cmd_cancel', 'ses_active');

    expect(state).toMatchObject({
      status: 'cancelling',
      turns: [
        {
          status: 'cancelling',
          assistantText: 'partial',
          cancelCommandId: 'cmd_cancel',
        },
      ],
    });

    // A delta already in flight remains legal until Python acknowledges cancellation.
    state = receive(
      state,
      event('assistant.delta', 'cmd_active', 'ses_active', 3, {text: ' output'}),
    );
    expect(state.status).toBe('cancelling');
    state = receive(state, event('session.cancelled', 'cmd_cancel', 'ses_active', 4, {}));

    expect(state).toMatchObject({
      status: 'cancelled',
      turns: [
        {
          status: 'cancelled',
          assistantText: 'partial output',
          lastSequence: 4,
        },
      ],
    });

    state = submit(state, 'cmd_next', 'Continue after cancellation');
    expect(state.status).toBe('starting');
    expect(state.turns).toHaveLength(2);
  });

  it('allows normal completion to win while cancellation is pending', () => {
    let state = runningState();
    state = receive(
      state,
      event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'complete'}),
    );
    state = cancel(state, 'cmd_cancel', 'ses_active');
    state = receive(
      state,
      event('assistant.completed', 'cmd_active', 'ses_active', 3, {text: 'complete'}),
    );
    state = receive(
      state,
      event('session.completed', 'cmd_active', 'ses_active', 4, {}),
    );

    expect(state.status).toBe('completed');
    expect(state.turns.at(-1)?.status).toBe('completed');

    const duplicateTerminal = receive(
      state,
      event('session.cancelled', 'cmd_cancel', 'ses_active', 5, {}),
    );
    expect(duplicateTerminal.status).toBe('protocol-failed');
    expect(duplicateTerminal.protocolFailureDetails).toEqual({
      code: 'terminal_state_absorbing',
      priorStatus: 'completed',
      eventType: 'session.cancelled',
    });
  });

  it('fails closed on cancellation without a matching local request', () => {
    const unsolicited = receive(
      runningState(),
      event('session.cancelled', 'cmd_cancel', 'ses_active', 2, {}),
    );
    expect(unsolicited.status).toBe('protocol-failed');
    expect(unsolicited.protocolFailureDetails?.code).toBe('illegal_transition');

    let mismatched = cancel(runningState(), 'cmd_cancel', 'ses_active');
    mismatched = receive(
      mismatched,
      event('session.cancelled', 'cmd_other_cancel', 'ses_active', 2, {}),
    );
    expect(mismatched.status).toBe('protocol-failed');
    expect(mismatched.protocolFailure).toContain('did not correlate');
  });

  it.each([
    {
      name: 'wrong correlation',
      mutate: (value: SessionEvent): SessionEvent => ({...value, correlation_id: 'cmd_wrong'}),
      expected: 'did not correlate',
    },
    {
      name: 'session ID mismatch',
      mutate: (value: SessionEvent): SessionEvent => ({...value, session_id: 'ses_wrong'}),
      expected: 'did not belong',
    },
    {
      name: 'sequence gap',
      mutate: (value: SessionEvent): SessionEvent => ({...value, sequence: 3}),
      expected: 'next session sequence',
    },
    {
      name: 'sequence duplicate',
      mutate: (value: SessionEvent): SessionEvent => ({...value, sequence: 1}),
      expected: 'next session sequence',
    },
  ])('fails closed on a $name', ({mutate, expected}) => {
    let state = runningState();
    const delta = event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'partial'});

    state = receive(state, mutate(delta));

    expect(state.status).toBe('protocol-failed');
    expect(state.protocolFailure).toContain(expected);
  });

  it('fails closed when assistant completion disagrees with accepted deltas', () => {
    let state = runningState();
    state = receive(
      state,
      event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'accepted'}),
    );

    state = receive(
      state,
      event('assistant.completed', 'cmd_active', 'ses_active', 3, {text: 'different'}),
    );

    expect(state.status).toBe('protocol-failed');
    expect(state.protocolFailure).toContain('exactly confirm');
  });

  it('fails closed on early session completion and a delta after assistant completion', () => {
    const early = receive(
      runningState(),
      event('session.completed', 'cmd_active', 'ses_active', 2, {}),
    );
    expect(early.status).toBe('protocol-failed');
    expect(early.protocolFailure).toContain('before assistant completion');

    let late = runningState();
    late = receive(
      late,
      event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'complete'}),
    );
    late = receive(
      late,
      event('assistant.completed', 'cmd_active', 'ses_active', 3, {text: 'complete'}),
    );
    late = receive(
      late,
      event('assistant.delta', 'cmd_active', 'ses_active', 4, {text: 'late'}),
    );
    expect(late.status).toBe('protocol-failed');
    expect(late.protocolFailure).toContain('after assistant completion');
  });

  it('fails closed when a second terminal event arrives after completion', () => {
    let state = runningState();
    state = receive(
      state,
      event('assistant.delta', 'cmd_active', 'ses_active', 2, {text: 'complete'}),
    );
    state = receive(
      state,
      event('assistant.completed', 'cmd_active', 'ses_active', 3, {text: 'complete'}),
    );
    state = receive(
      state,
      event('session.completed', 'cmd_active', 'ses_active', 4, {}),
    );

    state = receive(
      state,
      event('session.completed', 'cmd_active', 'ses_active', 5, {}),
    );

    expect(state.status).toBe('protocol-failed');
    expect(state.protocolFailureDetails?.code).toBe('terminal_state_absorbing');
  });

  it('projects approval waiting and permits cancellation from the waiting state', () => {
    let state = runningState();
    state = reduceSessionState(state, {
      type: 'approval.requested',
      sessionId: 'ses_active',
    });

    expect(state.status).toBe('awaiting_approval');
    expect(state.turns.at(-1)?.status).toBe('awaiting_approval');

    state = cancel(state, 'cmd_cancel', 'ses_active');
    expect(state.status).toBe('cancelling');
    expect(state.turns.at(-1)).toMatchObject({
      status: 'cancelling',
      cancelCommandId: 'cmd_cancel',
    });
  });

  it('preserves an authoritative failed turn and starts a fresh lifecycle for the next task', () => {
    let state = runningState();
    state = receive(
      state,
      event('session.failed', 'cmd_active', 'ses_active', 2, {
        code: 'mock.failure',
        message: 'The mock session failed safely.',
      }),
    );

    expect(state).toMatchObject({
      status: 'failed',
      turns: [
        {
          status: 'failed',
          sessionFailure: {
            code: 'mock.failure',
            message: 'The mock session failed safely.',
          },
        },
      ],
    });

    state = submit(state, 'cmd_next', 'Try a safer path');
    expect(state.status).toBe('starting');
    expect(state.turns).toHaveLength(2);
    expect(state.turns[0]?.status).toBe('failed');
    expect(state.turns[1]).toMatchObject({
      commandId: 'cmd_next',
      task: 'Try a safer path',
      status: 'starting',
      lastSequence: 0,
    });
  });

  it('reports bounded invariant metadata without leaking rejected payloads or identities', () => {
    const state = receive(
      runningState(),
      event('assistant.delta', 'cmd_secret', 'ses_secret', 9, {
        text: 'TOP-SECRET-PAYLOAD',
      }),
    );

    expect(state.status).toBe('protocol-failed');
    expect(state.protocolFailureDetails).toEqual({
      code: 'correlation_mismatch',
      priorStatus: 'running',
      eventType: 'assistant.delta',
    });
    expect(state.protocolFailure).not.toContain('TOP-SECRET-PAYLOAD');
    expect(state.protocolFailure).not.toContain('cmd_secret');
    expect(state.protocolFailure).not.toContain('ses_secret');
    expect(state.protocolFailure?.length).toBeLessThan(220);
  });

  it('ignores all later updates after a projection failure', () => {
    const failed = receive(
      runningState(),
      event('assistant.delta', 'cmd_active', 'ses_wrong', 2, {text: 'rejected'}),
    );

    expect(
      reduceSessionState(failed, {
        type: 'task.submitted',
        commandId: 'cmd_later',
        task: 'Later task',
      }),
    ).toBe(failed);
  });
});

function runningState(): SessionState {
  return receive(
    submit(INITIAL_SESSION_STATE, 'cmd_active', 'Active task'),
    event('session.started', 'cmd_active', 'ses_active', 1, {}),
  );
}

function submit(state: SessionState, commandId: string, task: string): SessionState {
  return reduceSessionState(state, {type: 'task.submitted', commandId, task});
}

function cancel(state: SessionState, commandId: string, sessionId: string): SessionState {
  return reduceSessionState(state, {type: 'cancel.requested', commandId, sessionId});
}

function receive(state: SessionState, value: SessionEvent): SessionState {
  return reduceSessionState(state, {type: 'event.received', event: value});
}

function event(
  type: SessionEvent['type'],
  correlationId: string,
  sessionId: string,
  sequence: number,
  payload: Record<string, string>,
): SessionEvent {
  return {
    protocol_version: 1,
    type,
    session_id: sessionId,
    sequence,
    timestamp: TIMESTAMP,
    correlation_id: correlationId,
    payload,
  } as SessionEvent;
}
