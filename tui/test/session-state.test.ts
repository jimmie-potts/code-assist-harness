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
    expect(state.protocolFailure).toContain('without an active submitted task');
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
