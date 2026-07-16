import {render} from 'ink-testing-library';
import {describe, expect, it} from 'vitest';

import {App} from '../src/app.js';

describe('App', () => {
  it('renders the conversation-first shell with a running workspace', () => {
    const view = render(
      <App runtimeState={{status: 'running', workspace: '/home/user/project'}} />,
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
      expect(frame).toContain('Input is not connected in this static shell.');
      expect(frame).toContain('Status: runtime running');
      expect(frame).toContain('/home/user/project');
      expect(frame).toContain('Ctrl+C to exit');

      expect(frame.indexOf('Conversation')).toBeLessThan(frame.indexOf('Task input'));
      expect(frame.indexOf('Task input')).toBeLessThan(frame.indexOf('Status: runtime running'));
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
        status: 'unexpectedly-exited' as const,
        workspace: '/workspace',
        message: 'Python runtime exited unexpectedly with exit code 7.',
      },
      expected: 'runtime failed',
    },
  ])('renders an actionable $runtimeState.status state', ({runtimeState, expected}) => {
    const view = render(<App runtimeState={runtimeState} />);

    try {
      expect(view.lastFrame()).toContain(expected);
      expect(view.lastFrame()).toContain(runtimeState.message);
      expect(view.lastFrame()).toContain('Ctrl+C to exit');
    } finally {
      view.unmount();
    }
  });
});
