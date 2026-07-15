import {spawnSync} from 'node:child_process';
import {mkdtempSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {delimiter, join} from 'node:path';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

const launcherPath = fileURLToPath(new URL('../../scripts/run-tui', import.meta.url));
const systemPath = ['/usr/bin', '/bin'].join(delimiter);

function testPath(fakePath: string): string {
  return [fakePath, systemPath].join(delimiter);
}

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
        env: {PATH: testPath(fakePath)},
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

  it('rejects npm when its resolved executable is a Windows path', () => {
    const fakePath = mkdtempSync(join(tmpdir(), 'code-assist-harness-windows-npm-'));
    const fakeNode = join(fakePath, 'node');
    const fakeNpm = join(fakePath, 'npm');
    const windowsNpm = join(fakePath, 'npm.exe');

    writeFileSync(fakeNode, "#!/bin/sh\nprintf '%s\\n' 'v22.22.1'\n", {mode: 0o755});
    writeFileSync(windowsNpm, "#!/bin/sh\nprintf '%s\\n' 'npm must not run' >&2\nexit 99\n", {
      mode: 0o755,
    });
    symlinkSync(windowsNpm, fakeNpm);

    try {
      const result = spawnSync(launcherPath, [], {
        encoding: 'utf8',
        env: {PATH: testPath(fakePath)},
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain('found a Windows npm executable');
      expect(result.stderr).toContain(windowsNpm);
      expect(result.stderr).toContain('Install npm for Node.js 22.22.1 inside Ubuntu WSL');
      expect(result.stderr).not.toContain('npm must not run');
    } finally {
      rmSync(fakePath, {recursive: true, force: true});
    }
  });

  it('rejects Node.js when a Linux path resolves to a Windows executable', () => {
    const fakePath = mkdtempSync(join(tmpdir(), 'code-assist-harness-windows-node-'));
    const fakeNode = join(fakePath, 'node');
    const windowsNode = join(fakePath, 'node.exe');
    const fakeNpm = join(fakePath, 'npm');

    writeFileSync(
      windowsNode,
      "#!/bin/sh\nprintf '%s\\n' 'node must not run' >&2\nprintf '%s\\n' 'v22.22.1'\n",
      {mode: 0o755},
    );
    symlinkSync(windowsNode, fakeNode);
    writeFileSync(fakeNpm, "#!/bin/sh\nprintf '%s\\n' 'npm must not run' >&2\nexit 99\n", {
      mode: 0o755,
    });

    try {
      const result = spawnSync(launcherPath, [], {
        encoding: 'utf8',
        env: {PATH: testPath(fakePath)},
      });

      expect(result.status).toBe(1);
      expect(result.stderr).toContain('found a Windows Node.js executable');
      expect(result.stderr).toContain(windowsNode);
      expect(result.stderr).toContain('Install and select Node.js 22.22.1 inside Ubuntu WSL');
      expect(result.stderr).not.toContain('node must not run');
      expect(result.stderr).not.toContain('npm must not run');
    } finally {
      rmSync(fakePath, {recursive: true, force: true});
    }
  });

  it('preserves the launch directory and forwards a workspace path as one argument', () => {
    const fakePath = mkdtempSync(join(tmpdir(), 'code-assist-harness-forwarding-'));
    const launchDirectory = mkdtempSync(join(tmpdir(), 'code-assist-harness-launch-directory-'));
    const fakeNode = join(fakePath, 'node');
    const fakeNpm = join(fakePath, 'npm');

    writeFileSync(fakeNode, "#!/bin/sh\nprintf '%s\\n' 'v22.22.1'\n", {mode: 0o755});
    writeFileSync(
      fakeNpm,
      [
        '#!/bin/sh',
        'printf \'launch=%s\\n\' "$CODE_ASSIST_LAUNCH_DIRECTORY"',
        'for argument in "$@"; do',
        '  printf \'argument=<%s>\\n\' "$argument"',
        'done',
        '',
      ].join('\n'),
      {mode: 0o755},
    );

    try {
      const result = spawnSync(launcherPath, ['--workspace', 'target with spaces'], {
        cwd: launchDirectory,
        encoding: 'utf8',
        env: {PATH: testPath(fakePath)},
      });

      expect(result.status).toBe(0);
      expect(result.stdout).toContain(`launch=${launchDirectory}`);
      expect(result.stdout).toContain('argument=<start>');
      expect(result.stdout).toContain('argument=<-->');
      expect(result.stdout).toContain('argument=<--workspace>');
      expect(result.stdout).toContain('argument=<target with spaces>');
    } finally {
      rmSync(fakePath, {recursive: true, force: true});
      rmSync(launchDirectory, {recursive: true, force: true});
    }
  });
});
