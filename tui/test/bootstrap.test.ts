import {describe, expect, it, vi} from 'vitest';

import {bootstrapApplication} from '../src/bootstrap.js';

describe('bootstrapApplication', () => {
  it('loads and runs Ink only after runtime validation succeeds', async () => {
    const runApplication = vi.fn<() => Promise<void>>().mockResolvedValue(undefined);
    const loadApplication = vi.fn().mockResolvedValue({runApplication});

    await bootstrapApplication('22.22.1', loadApplication);

    expect(loadApplication).toHaveBeenCalledOnce();
    expect(runApplication).toHaveBeenCalledOnce();
  });

  it('does not load Ink when the runtime is unsupported', async () => {
    const loadApplication = vi.fn();

    await expect(bootstrapApplication('20.19.0', loadApplication)).rejects.toThrow(
      'Required: Node.js >=22.13.0 <23',
    );
    expect(loadApplication).not.toHaveBeenCalled();
  });
});
