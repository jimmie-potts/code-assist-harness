import {describe, expect, it} from 'vitest';

import {
  INITIAL_SESSION_LIFECYCLE_STATE,
  isActiveSessionStatus,
  isCancellableSessionStatus,
  isTerminalSessionStatus,
  reduceSessionLifecycle,
  replaySessionLifecycle,
  type SessionLifecycleEvent,
  type SessionLifecycleInput,
  type SessionLifecycleResult,
  type SessionLifecycleState,
} from '../src/session-lifecycle.js';

const TIMESTAMP = '2026-07-30T12:00:00.000Z';

describe('reduceSessionLifecycle', () => {
  it('reduces the complete happy path without mutating earlier states', () => {
    const idle = INITIAL_SESSION_LIFECYCLE_STATE;
    const starting = success(reduceSessionLifecycle(idle, submitted()));
    const running = success(
      reduceSessionLifecycle(starting, event('session.started', 'cmd_start', 'ses_one', 1, {})),
    );
    const withText = success(
      reduceSessionLifecycle(
        running,
        event('assistant.delta', 'cmd_start', 'ses_one', 2, {text: 'Hello'}),
      ),
    );
    const confirmed = success(
      reduceSessionLifecycle(
        withText,
        event('assistant.completed', 'cmd_start', 'ses_one', 3, {text: 'Hello'}),
      ),
    );
    const completed = success(
      reduceSessionLifecycle(
        confirmed,
        event('session.completed', 'cmd_start', 'ses_one', 4, {}),
      ),
    );

    expect(completed).toMatchObject({
      status: 'completed',
      startCommandId: 'cmd_start',
      task: 'Explain reducers',
      sessionId: 'ses_one',
      lastSequence: 4,
      assistantText: 'Hello',
      assistantCompleted: true,
      sessionFailure: null,
    });
    expect(idle).toEqual(INITIAL_SESSION_LIFECYCLE_STATE);
    expect(starting).toMatchObject({status: 'starting', sessionId: null, lastSequence: 0});
    expect(running).toMatchObject({status: 'running', assistantText: ''});
  });

  it('models approval as identity-checked domain facts, not protocol messages', () => {
    const running = runningState();
    const waiting = success(
      reduceSessionLifecycle(running, {type: 'approval.requested', sessionId: 'ses_one'}),
    );
    const resumed = success(
      reduceSessionLifecycle(waiting, {type: 'approval.resolved', sessionId: 'ses_one'}),
    );

    expect(waiting.status).toBe('awaiting_approval');
    expect(resumed.status).toBe('running');

    const mismatch = reduceSessionLifecycle(waiting, {
      type: 'approval.resolved',
      sessionId: 'ses_other',
    });
    expectFailure(mismatch, 'session_mismatch', 'awaiting_approval', 'approval.resolved');
    expect(mismatch.state).toBe(waiting);
  });

  it('allows cancellation while running or awaiting approval', () => {
    const running = runningState();
    const cancelling = success(
      reduceSessionLifecycle(running, {
        type: 'cancel.requested',
        commandId: 'cmd_cancel',
        sessionId: 'ses_one',
      }),
    );
    const cancelled = success(
      reduceSessionLifecycle(
        cancelling,
        event('session.cancelled', 'cmd_cancel', 'ses_one', 2, {}),
      ),
    );
    expect(cancelled).toMatchObject({status: 'cancelled', cancelCommandId: 'cmd_cancel'});

    const waiting = success(
      reduceSessionLifecycle(running, {type: 'approval.requested', sessionId: 'ses_one'}),
    );
    const waitingCancellation = success(
      reduceSessionLifecycle(waiting, {
        type: 'cancel.requested',
        commandId: 'cmd_wait_cancel',
        sessionId: 'ses_one',
      }),
    );
    expect(waitingCancellation.status).toBe('cancelling');
  });

  it('lets authoritative completion win the cancellation race', () => {
    const result = replaySessionLifecycle([
      submitted(),
      event('session.started', 'cmd_start', 'ses_one', 1, {}),
      event('assistant.delta', 'cmd_start', 'ses_one', 2, {text: 'Done'}),
      {
        type: 'cancel.requested',
        commandId: 'cmd_cancel',
        sessionId: 'ses_one',
      },
      event('assistant.completed', 'cmd_start', 'ses_one', 3, {text: 'Done'}),
      event('session.completed', 'cmd_start', 'ses_one', 4, {}),
    ]);

    expect(success(result)).toMatchObject({status: 'completed', cancelCommandId: 'cmd_cancel'});
  });

  it.each(['running', 'awaiting_approval', 'cancelling'] as const)(
    'accepts an authoritative failure while %s',
    (targetStatus) => {
      const inputs: SessionLifecycleInput[] = [
        submitted(),
        event('session.started', 'cmd_start', 'ses_one', 1, {}),
      ];
      if (targetStatus === 'awaiting_approval') {
        inputs.push({type: 'approval.requested', sessionId: 'ses_one'});
      } else if (targetStatus === 'cancelling') {
        inputs.push({
          type: 'cancel.requested',
          commandId: 'cmd_cancel',
          sessionId: 'ses_one',
        });
      }
      inputs.push(
        event('session.failed', 'cmd_start', 'ses_one', 2, {
          code: 'mock.failure',
          message: 'The mock session failed safely.',
        }),
      );

      expect(success(replaySessionLifecycle(inputs))).toMatchObject({
        status: 'failed',
        lastSequence: 2,
        sessionFailure: {code: 'mock.failure', message: 'The mock session failed safely.'},
      });
    },
  );

  it.each([
    {
      name: 'wrong correlation',
      input: event('assistant.delta', 'cmd_wrong', 'ses_one', 2, {text: 'secret'}),
      code: 'correlation_mismatch',
    },
    {
      name: 'wrong session',
      input: event('assistant.delta', 'cmd_start', 'ses_wrong', 2, {text: 'secret'}),
      code: 'session_mismatch',
    },
    {
      name: 'duplicate sequence',
      input: event('assistant.delta', 'cmd_start', 'ses_one', 1, {text: 'secret'}),
      code: 'sequence_regression',
    },
    {
      name: 'sequence gap',
      input: event('assistant.delta', 'cmd_start', 'ses_one', 3, {text: 'secret'}),
      code: 'sequence_gap',
    },
  ] as const)('rejects a $name without changing or leaking state', ({input, code}) => {
    const prior = runningState();
    const result = reduceSessionLifecycle(prior, input);

    expectFailure(result, code, 'running', 'assistant.delta');
    expect(result.state).toBe(prior);
    expect(JSON.stringify(result)).not.toContain('secret');
  });

  it('distinguishes assistant completion invariants', () => {
    const running = runningState();
    const mismatch = reduceSessionLifecycle(
      running,
      event('assistant.completed', 'cmd_start', 'ses_one', 2, {text: 'different'}),
    );
    expectFailure(mismatch, 'assistant_completion_mismatch', 'running', 'assistant.completed');

    const withText = success(
      reduceSessionLifecycle(
        running,
        event('assistant.delta', 'cmd_start', 'ses_one', 2, {text: 'same'}),
      ),
    );
    const confirmed = success(
      reduceSessionLifecycle(
        withText,
        event('assistant.completed', 'cmd_start', 'ses_one', 3, {text: 'same'}),
      ),
    );
    expectFailure(
      reduceSessionLifecycle(
        confirmed,
        event('assistant.completed', 'cmd_start', 'ses_one', 4, {text: 'same'}),
      ),
      'assistant_already_completed',
      'running',
      'assistant.completed',
    );
    expectFailure(
      reduceSessionLifecycle(
        confirmed,
        event('assistant.delta', 'cmd_start', 'ses_one', 4, {text: 'late'}),
      ),
      'assistant_after_completion',
      'running',
      'assistant.delta',
    );
    expectFailure(
      reduceSessionLifecycle(
        running,
        event('session.completed', 'cmd_start', 'ses_one', 2, {}),
      ),
      'session_completion_before_assistant',
      'running',
      'session.completed',
    );
  });

  it.each(['completed', 'cancelled', 'failed'] as const)(
    'keeps %s absorbing and returns its exact state on a late input',
    (status) => {
      const terminal = terminalState(status);
      const result = reduceSessionLifecycle(terminal, submitted());

      expectFailure(result, 'terminal_state_absorbing', status, 'task.submitted');
      expect(result.state).toBe(terminal);
    },
  );

  it('stops replay at the first failure and produces identical deterministic results', () => {
    const inputs: readonly SessionLifecycleInput[] = [
      submitted(),
      event('session.started', 'cmd_start', 'ses_one', 1, {}),
      event('assistant.delta', 'cmd_start', 'ses_one', 3, {text: 'not accepted'}),
      event('assistant.delta', 'cmd_start', 'ses_one', 2, {text: 'never reached'}),
    ];

    const first = replaySessionLifecycle(inputs);
    const second = replaySessionLifecycle(inputs);
    expect(first).toEqual(second);
    expectFailure(first, 'sequence_gap', 'running', 'assistant.delta');
    expect(first.state).toMatchObject({lastSequence: 1, assistantText: ''});
  });

  it('classifies active, terminal, and cancellable statuses without omissions', () => {
    expect(
      (['idle', 'starting', 'running', 'awaiting_approval', 'cancelling', 'completed', 'cancelled', 'failed'] as const).map(
        (status) => [
          status,
          isActiveSessionStatus(status),
          isTerminalSessionStatus(status),
          isCancellableSessionStatus(status),
        ],
      ),
    ).toEqual([
      ['idle', false, false, false],
      ['starting', true, false, false],
      ['running', true, false, true],
      ['awaiting_approval', true, false, true],
      ['cancelling', true, false, false],
      ['completed', false, true, false],
      ['cancelled', false, true, false],
      ['failed', false, true, false],
    ]);
  });
});

function runningState(): SessionLifecycleState {
  return success(
    replaySessionLifecycle([
      submitted(),
      event('session.started', 'cmd_start', 'ses_one', 1, {}),
    ]),
  );
}

function terminalState(
  status: 'completed' | 'cancelled' | 'failed',
): SessionLifecycleState {
  if (status === 'cancelled') {
    return success(
      replaySessionLifecycle([
        submitted(),
        event('session.started', 'cmd_start', 'ses_one', 1, {}),
        {type: 'cancel.requested', commandId: 'cmd_cancel', sessionId: 'ses_one'},
        event('session.cancelled', 'cmd_cancel', 'ses_one', 2, {}),
      ]),
    );
  }
  if (status === 'failed') {
    return success(
      replaySessionLifecycle([
        submitted(),
        event('session.started', 'cmd_start', 'ses_one', 1, {}),
        event('session.failed', 'cmd_start', 'ses_one', 2, {
          code: 'mock.failure',
          message: 'Safe failure.',
        }),
      ]),
    );
  }
  return success(
    replaySessionLifecycle([
      submitted(),
      event('session.started', 'cmd_start', 'ses_one', 1, {}),
      event('assistant.delta', 'cmd_start', 'ses_one', 2, {text: 'Done'}),
      event('assistant.completed', 'cmd_start', 'ses_one', 3, {text: 'Done'}),
      event('session.completed', 'cmd_start', 'ses_one', 4, {}),
    ]),
  );
}

function submitted(): SessionLifecycleInput {
  return {type: 'task.submitted', commandId: 'cmd_start', task: 'Explain reducers'};
}

function success(result: SessionLifecycleResult): SessionLifecycleState {
  expect(result.ok).toBe(true);
  if (!result.ok) {
    throw new Error(`Unexpected lifecycle failure: ${result.failure.code}`);
  }
  return result.state;
}

function expectFailure(
  result: SessionLifecycleResult,
  code: string,
  priorStatus: SessionLifecycleState['status'],
  eventType: SessionLifecycleInput['type'],
): void {
  expect(result.ok).toBe(false);
  if (result.ok) {
    throw new Error('Expected lifecycle failure.');
  }
  expect(result.failure).toEqual({code, priorStatus, eventType});
}

function event(
  type: SessionLifecycleEvent['type'],
  correlationId: string,
  sessionId: string,
  sequence: number,
  payload: Record<string, string>,
): SessionLifecycleEvent {
  return {
    protocol_version: 1,
    type,
    session_id: sessionId,
    sequence,
    timestamp: TIMESTAMP,
    correlation_id: correlationId,
    payload,
  } as SessionLifecycleEvent;
}
