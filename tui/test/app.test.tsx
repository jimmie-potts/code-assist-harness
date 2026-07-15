import {render} from 'ink-testing-library';
import {describe, expect, it} from 'vitest';

import {App} from '../src/app.js';

describe('App', () => {
  it('renders the initial conversation-first shell', () => {
    const view = render(<App />);

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
      expect(frame).toContain('Status: idle');
      expect(frame).toContain('Ctrl+C to exit');

      expect(frame.indexOf('Conversation')).toBeLessThan(frame.indexOf('Task input'));
      expect(frame.indexOf('Task input')).toBeLessThan(frame.indexOf('Status: idle'));
    } finally {
      view.unmount();
    }
  });
});
