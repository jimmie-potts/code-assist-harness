import {mkdtempSync, mkdirSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

import {describe, expect, it} from 'vitest';

import {resolveWorkspace, WorkspaceConfigurationError} from '../src/workspace.js';

describe('resolveWorkspace', () => {
  it('uses the canonical launch directory by default', () => {
    const root = mkdtempSync(join(tmpdir(), 'cah-workspace-default-'));
    const workspace = join(root, 'workspace');
    const alias = join(root, 'alias');
    mkdirSync(workspace);
    symlinkSync(workspace, alias, 'dir');

    try {
      expect(resolveWorkspace([], alias)).toEqual({
        path: realpathSync(workspace),
        source: 'launch-directory',
      });
    } finally {
      rmSync(root, {recursive: true, force: true});
    }
  });

  it('resolves a relative override with spaces from the launch directory', () => {
    const launchDirectory = mkdtempSync(join(tmpdir(), 'cah-workspace-relative-'));
    const workspace = join(launchDirectory, 'target with spaces');
    mkdirSync(workspace);

    try {
      expect(resolveWorkspace(['--workspace', 'target with spaces'], launchDirectory)).toEqual({
        path: realpathSync(workspace),
        source: 'command-line',
      });
    } finally {
      rmSync(launchDirectory, {recursive: true, force: true});
    }
  });

  it.each([
    {arguments_: ['--unknown'], message: 'Unknown argument'},
    {arguments_: ['--workspace'], message: 'requires exactly one path'},
    {arguments_: ['--workspace', '.', '--workspace', '.'], message: 'requires exactly one path'},
  ])('rejects invalid arguments: $arguments_', ({arguments_, message}) => {
    expect(() => resolveWorkspace(arguments_, process.cwd())).toThrow(message);
  });

  it('rejects missing paths and regular files before spawn', () => {
    const launchDirectory = mkdtempSync(join(tmpdir(), 'cah-workspace-invalid-'));
    const file = join(launchDirectory, 'file.txt');
    writeFileSync(file, 'not a directory', 'utf8');

    try {
      expect(() => resolveWorkspace(['--workspace', 'missing'], launchDirectory)).toThrow(
        WorkspaceConfigurationError,
      );
      expect(() => resolveWorkspace(['--workspace', file], launchDirectory)).toThrow(
        'not a directory',
      );
    } finally {
      rmSync(launchDirectory, {recursive: true, force: true});
    }
  });
});
