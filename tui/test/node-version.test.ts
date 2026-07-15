import {describe, expect, it} from 'vitest';

import {assertSupportedNodeVersion} from '../src/node-version.js';

describe('assertSupportedNodeVersion', () => {
  it.each(['22.13.0', '22.22.1'])('accepts supported version %s', (version) => {
    expect(() => assertSupportedNodeVersion(version)).not.toThrow();
  });

  it.each([undefined, '', 'not-a-version', '22.12.9', '23.0.0', '24.0.0'])(
    'rejects unsupported version %s with setup guidance',
    (version) => {
      expect(() => assertSupportedNodeVersion(version)).toThrow(
        /Install or select the pinned version inside Ubuntu WSL/u,
      );
    },
  );
});
