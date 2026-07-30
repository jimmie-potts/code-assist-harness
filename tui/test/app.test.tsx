import {render} from 'ink-testing-library';
import type {ReactElement} from 'react';
import {describe, expect, it, vi} from 'vitest';

import {App} from '../src/app.js';
import {SessionSubmissionError} from '../src/runtime-supervisor.js';
import {
  INITIAL_SESSION_STATE,
  reduceSessionState,
  type SessionEvent,
  type SessionState,
} from '../src/session-state.js';

const TIMESTAMP = '2026-07-30T12:00:00.000Z';
const COMMAND_ID = 'cmd_stream_001';
const SESSION_ID = 'ses_stream_001';

describe('App', () => {
  it('renders the conversation-first shell with an idle running workspace', () => {
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/home/user/project'}}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={() => undefined}
        onCancelSession={() => false}
      />,
    );

    try {
      const frame = view.lastFrame();

      expect(frame).toBeDefined();
      if (frame === undefined) {
        throw new Error('Ink did not render an initial frame.');
      }

      expect(frame).toContain('Code Assist Harness');
      expect(frame).toContain('Conversation');
      expect(frame).toContain('No messages yet.');
      expect(frame).toContain('Task input');
      expect(frame).toContain('Type a task and press Enter');
      expect(frame).toContain('Session status: idle');
      expect(frame).toContain('Status: runtime running');
      expect(frame).toContain('/home/user/project');
      expect(frame).toContain('Ctrl+C to exit');

      expect(frame.indexOf('Conversation')).toBeLessThan(frame.indexOf('Task input'));
      expect(frame.indexOf('Task input')).toBeLessThan(frame.indexOf('Session status: idle'));
      expect(frame.indexOf('Session status: idle')).toBeLessThan(
        frame.indexOf('Status: runtime running'),
      );
    } finally {
      view.unmount();
    }
  });

  it('rejects whitespace-only input locally with understandable feedback', async () => {
    const onSubmitTask = vi.fn();
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={onSubmitTask}
        onCancelSession={() => false}
      />,
    );

    try {
      view.stdin.write('   ');
      view.stdin.write('\r');

      await vi.waitFor(() => {
        expect(view.lastFrame()).toContain('Enter a non-empty task before submitting.');
      });
      expect(onSubmitTask).not.toHaveBeenCalled();
    } finally {
      view.unmount();
    }
  });

  it('submits exact non-empty input and clears the editable buffer', async () => {
    const onSubmitTask = vi.fn();
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={onSubmitTask}
        onCancelSession={() => false}
      />,
    );

    try {
      view.stdin.write('  Explain this repository.  ');
      view.stdin.write('\r');

      await vi.waitFor(() => {
        expect(onSubmitTask).toHaveBeenCalledWith('  Explain this repository.  ');
      });
      expect(view.lastFrame()).toContain('Type a task and press Enter');
    } finally {
      view.unmount();
    }
  });

  it('preserves the editable buffer when submission is rejected synchronously', async () => {
    const onSubmitTask = vi.fn(() => {
      throw new SessionSubmissionError('The task is too large to submit.');
    });
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={onSubmitTask}
        onCancelSession={() => false}
      />,
    );

    try {
      view.stdin.write('Keep this task');
      view.stdin.write('\r');

      await vi.waitFor(() => {
        expect(onSubmitTask).toHaveBeenCalledWith('Keep this task');
        expect(view.lastFrame()).toContain('> Keep this task');
        expect(view.lastFrame()).toContain('The task is too large to submit.');
        expect(view.lastFrame()).toContain('No messages yet.');
      });
    } finally {
      view.unmount();
    }
  });

  it('backspaces one complete Unicode code point', async () => {
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={() => undefined}
        onCancelSession={() => false}
      />,
    );

    try {
      view.stdin.write('A😀');
      await vi.waitFor(() => expect(view.lastFrame()).toContain('A😀'));

      view.stdin.write('\u007F');

      await vi.waitFor(() => {
        expect(view.lastFrame()).toContain('> A');
        expect(view.lastFrame()).not.toContain('😀');
        expect(view.lastFrame()).not.toContain('�');
      });
    } finally {
      view.unmount();
    }
  });

  it('renders every accepted delta before completion and preserves a draft during rerenders', async () => {
    let state = submittedState('Explain streaming.');
    const view = render(
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={state}
        onSubmitTask={() => undefined}
        onCancelSession={() => false}
      />,
    );

    try {
      state = receive(state, 'session.started', 1, {});
      view.rerender(
        <App
          runtimeState={{status: 'running', workspace: '/workspace'}}
          sessionState={state}
          onSubmitTask={() => undefined}
          onCancelSession={() => false}
        />,
      );
      expect(view.lastFrame()).toContain('Session status: running');

      view.stdin.write('my next task');
      await vi.waitFor(() => expect(view.lastFrame()).toContain('my next task'));
      view.stdin.write('\r');
      await vi.waitFor(() => {
        expect(view.lastFrame()).toContain('Wait for the active session to finish.');
      });

      for (const [sequence, text, accumulated] of [
        [2, 'Mocked ', 'Mocked '],
        [3, 'output ', 'Mocked output '],
        [4, 'streams.', 'Mocked output streams.'],
      ] as const) {
        state = receive(state, 'assistant.delta', sequence, {text});
        view.rerender(
          <App
            runtimeState={{status: 'running', workspace: '/workspace'}}
            sessionState={state}
            onSubmitTask={() => undefined}
            onCancelSession={() => false}
          />,
        );
        expect(view.lastFrame()).toContain(accumulated);
        expect(view.lastFrame()).toContain('my next task');
        expect(view.lastFrame()).toContain('Session status: running');
      }

      state = receive(state, 'assistant.completed', 5, {text: 'Mocked output streams.'});
      state = receive(state, 'session.completed', 6, {});
      view.rerender(
        <App
          runtimeState={{status: 'running', workspace: '/workspace'}}
          sessionState={state}
          onSubmitTask={() => undefined}
          onCancelSession={() => false}
        />,
      );

      await vi.waitFor(() => {
        expect(view.lastFrame()).toContain('Mocked output streams.');
        expect(view.lastFrame()).toContain('my next task');
        expect(view.lastFrame()).toContain('Session status: completed');
        expect(view.lastFrame()).toContain('ready for another task');
        expect(view.lastFrame()).not.toContain('Wait for the active session to finish.');
      });
    } finally {
      view.unmount();
    }
  });

  it('requests cancellation with Escape once and renders the authoritative cancelled outcome', async () => {
    const onCancelSession = vi.fn(() => true);
    let state = receive(submittedState('Stop this task.'), 'session.started', 1, {});
    const renderApp = (): ReactElement => (
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={state}
        onSubmitTask={() => undefined}
        onCancelSession={onCancelSession}
      />
    );
    const view = render(renderApp());

    try {
      expect(view.lastFrame()).toContain('Esc to cancel');
      view.stdin.write('keep this draft');
      view.stdin.write('\u001B');
      await vi.waitFor(() => expect(onCancelSession).toHaveBeenCalledOnce());

      state = reduceSessionState(state, {
        type: 'cancel.requested',
        commandId: 'cmd_cancel_001',
        sessionId: SESSION_ID,
      });
      view.rerender(renderApp());
      expect(view.lastFrame()).toContain('Session status: cancelling');
      expect(view.lastFrame()).toContain('waiting for Python');
      expect(view.lastFrame()).not.toContain('Esc to cancel');
      expect(view.lastFrame()).toContain('keep this draft');

      view.stdin.write('\u001B');
      await new Promise((resolve) => setImmediate(resolve));
      expect(onCancelSession).toHaveBeenCalledOnce();

      state = receive(state, 'session.cancelled', 2, {}, 'cmd_cancel_001');
      view.rerender(renderApp());
      expect(view.lastFrame()).toContain('Session status: cancelled');
      expect(view.lastFrame()).toContain('ready for another task');
      expect(view.lastFrame()).toContain('Cancelled before a response.');
      expect(view.lastFrame()).toContain('keep this draft');
      expect(view.lastFrame()).not.toContain('protocol failed');
    } finally {
      view.unmount();
    }
  });

  it('keeps a draft cancellable while awaiting approval and renders session failure safely', async () => {
    const onCancelSession = vi.fn(() => true);
    let state = receive(submittedState('Review this change.'), 'session.started', 1, {});
    const renderApp = (): ReactElement => (
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={state}
        onSubmitTask={() => undefined}
        onCancelSession={onCancelSession}
      />
    );
    const view = render(renderApp());

    try {
      view.stdin.write('preserve this next task');
      state = reduceSessionState(state, {
        type: 'approval.requested',
        sessionId: SESSION_ID,
      });
      view.rerender(renderApp());

      await vi.waitFor(() => {
        expect(view.lastFrame()).toContain('Session status: awaiting approval');
        expect(view.lastFrame()).toContain('Esc to cancel');
        expect(view.lastFrame()).toContain('preserve this next task');
      });
      view.stdin.write('\u001B');
      await vi.waitFor(() => expect(onCancelSession).toHaveBeenCalledOnce());

      state = receive(state, 'session.failed', 2, {
        code: 'approval.unavailable',
        message: 'Approval could not be completed safely.',
      });
      view.rerender(renderApp());

      await vi.waitFor(() => {
        const frame = view.lastFrame()?.replace(/\s+/g, ' ');
        expect(frame).toContain('Session status: failed (approval.unavailable)');
        expect(frame).toContain('Approval could not be completed safely.');
        expect(frame).toContain('ready for another task');
        expect(frame).toContain('preserve this next task');
        expect(frame).not.toContain('Esc to cancel');
      });
    } finally {
      view.unmount();
    }
  });

  it('renders a cancelled outcome distinctly from a session protocol failure', () => {
    let cancelled = receive(submittedState('Compare terminal states.'), 'session.started', 1, {});
    cancelled = reduceSessionState(cancelled, {
      type: 'cancel.requested',
      commandId: 'cmd_cancel_001',
      sessionId: SESSION_ID,
    });
    cancelled = receive(cancelled, 'session.cancelled', 2, {}, 'cmd_cancel_001');
    const protocolFailed = receive(
      cancelled,
      'session.cancelled',
      3,
      {},
      'cmd_cancel_001',
    );
    const renderState = (sessionState: SessionState): ReactElement => (
      <App
        runtimeState={{status: 'running', workspace: '/workspace'}}
        sessionState={sessionState}
        onSubmitTask={() => undefined}
        onCancelSession={() => false}
      />
    );
    const view = render(renderState(cancelled));

    try {
      expect(view.lastFrame()).toContain('Session status: cancelled · ready for another task');
      expect(view.lastFrame()).not.toContain('Session status: protocol failed');

      view.rerender(renderState(protocolFailed));
      expect(view.lastFrame()).toContain('Session status: protocol failed');
      expect(view.lastFrame()).toContain('terminal_state_absorbing');
      expect(view.lastFrame()).not.toContain('Session status: cancelled · ready for another task');
    } finally {
      view.unmount();
    }
  });

  it.each([
    {
      runtimeState: {
        status: 'failed-to-start' as const,
        workspace: '/workspace',
        message: 'Install uv and retry.',
      },
      expected: 'runtime failed to start',
    },
    {
      runtimeState: {
        status: 'protocol-failed' as const,
        workspace: '/workspace',
        code: 'unknown_type' as const,
        message: 'Protocol message type is not supported.',
      },
      expected: 'runtime protocol failed (unknown_type)',
    },
    {
      runtimeState: {
        status: 'unexpectedly-exited' as const,
        workspace: '/workspace',
        message: 'Python runtime exited unexpectedly with exit code 7.',
      },
      expected: 'runtime failed',
    },
  ])('renders an actionable $runtimeState.status state', ({runtimeState, expected}) => {
    const view = render(
      <App
        runtimeState={runtimeState}
        sessionState={INITIAL_SESSION_STATE}
        onSubmitTask={() => undefined}
        onCancelSession={() => false}
      />,
    );

    try {
      expect(view.lastFrame()).toContain(expected);
      expect(view.lastFrame()).toContain(runtimeState.message);
      expect(view.lastFrame()).toContain('Ctrl+C');
      expect(view.lastFrame()).toContain('to exit');
    } finally {
      view.unmount();
    }
  });
});

function submittedState(task: string): SessionState {
  return reduceSessionState(INITIAL_SESSION_STATE, {
    type: 'task.submitted',
    commandId: COMMAND_ID,
    task,
  });
}

function receive(
  state: SessionState,
  type:
    | 'session.started'
    | 'assistant.delta'
    | 'assistant.completed'
    | 'session.completed'
    | 'session.cancelled'
    | 'session.failed',
  sequence: number,
  payload: Record<string, string>,
  correlationId = COMMAND_ID,
): SessionState {
  return reduceSessionState(state, {
    type: 'event.received',
    event: {
      protocol_version: 1,
      type,
      session_id: SESSION_ID,
      sequence,
      timestamp: TIMESTAMP,
      correlation_id: correlationId,
      payload,
    } as SessionEvent,
  });
}
