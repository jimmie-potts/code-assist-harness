import {describe, expect, it, vi} from 'vitest';

import type {ApplicationRenderer} from '../src/run-application.js';
import {runApplication} from '../src/run-application.js';

describe('runApplication', () => {
  it('enables Ctrl+C cleanup and waits until Ink exits', async () => {
    const waitUntilExit = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const renderApplication = vi.fn<ApplicationRenderer>(() => ({waitUntilExit}));

    await runApplication(renderApplication);

    expect(renderApplication).toHaveBeenCalledOnce();
    expect(renderApplication.mock.calls[0]?.[1]).toEqual({exitOnCtrlC: true});
    expect(waitUntilExit).toHaveBeenCalledOnce();
  });
});
