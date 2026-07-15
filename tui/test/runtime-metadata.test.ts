import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

import {
  assertSupportedNodeVersion,
  PINNED_NODE_VERSION,
  SUPPORTED_NODE_RANGE,
} from '../src/node-version.js';

interface PackageMetadata {
  readonly engines?: {
    readonly node?: string;
  };
}

const packagePath = fileURLToPath(new URL('../package.json', import.meta.url));
const versionPinPath = fileURLToPath(new URL('../../.node-version', import.meta.url));

describe('Node.js runtime metadata', () => {
  it('keeps the version pin, npm engine, and bootstrap guard aligned', () => {
    const packageMetadata = JSON.parse(readFileSync(packagePath, 'utf8')) as PackageMetadata;
    const versionPin = readFileSync(versionPinPath, 'utf8').trim();

    expect(versionPin).toBe(PINNED_NODE_VERSION);
    expect(packageMetadata.engines?.node).toBe(SUPPORTED_NODE_RANGE);
    expect(() => assertSupportedNodeVersion(versionPin)).not.toThrow();
  });
});
