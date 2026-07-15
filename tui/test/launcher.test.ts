import {spawnSync} from 'node:child_process';
import {mkdtempSync, rmSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

const launcherPath = fileURLToPath(new URL('../../scripts/run-tui', import.meta.url));

describe('run-tui launcher', () => {
  it('reports an actionable error when Node.js is missing', () => {
    const emptyPath = mkdtempSync(join(tmpdir(), 'code-assist-harness-empty-path-'));

    try {
      const result = spawnSync(launcherPath, [], {
        encoding: 'utf8',
        env: {PATH: emptyPath},
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain('Node.js was not found inside Ubuntu WSL');
      expect(result.stderr).toContain('npm --prefix tui ci');
      expect(result.stderr).toContain('./scripts/run-tui');
    } finally {
      rmSync(emptyPath, {recursive: true, force: true});
    }
  });

  it('rejects an unsupported Node.js version before invoking npm', () => {
    const fakePath = mkdtempSync(join(tmpdir(), 'code-assist-harness-fake-path-'));
    const fakeNode = join(fakePath, 'node');
    const fakeNpm = join(fakePath, 'npm');

    writeFileSync(fakeNode, "#!/bin/sh\nprintf '%s\\n' 'v20.19.0'\n", {mode: 0o755});
    writeFileSync(fakeNpm, "#!/bin/sh\nprintf '%s\\n' 'npm must not run' >&2\nexit 99\n", {
      mode: 0o755,
    });

    try {
      const result = spawnSync(launcherPath, [], {
        encoding: 'utf8',
        env: {PATH: fakePath},
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain('cannot start with Node.js v20.19.0');
      expect(result.stderr).toContain('Required: Node.js >=22.13.0 <23');
      expect(result.stderr).toContain('Install or select the pinned version inside Ubuntu WSL');
      expect(result.stderr).not.toContain('npm must not run');
    } finally {
      rmSync(fakePath, {recursive: true, force: true});
    }
  });
});
