import {mkdtempSync, mkdirSync, realpathSync, rmSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

import {describe, expect, it} from 'vitest';

import {OPENAI_TEXT_STREAM_MODEL} from '../src/provider-configuration.js';
import {
  resolveApplicationConfiguration,
  resolveWorkspace,
  WorkspaceConfigurationError,
} from '../src/workspace.js';

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
    ['--no-transcript', '--workspace', '.'],
    ['--workspace', '.', '--no-transcript'],
  ])('accepts transcript opt-out before or after the workspace: %s %s %s', (...arguments_) => {
    const configuration = resolveApplicationConfiguration(arguments_, process.cwd());

    expect(configuration).toEqual({
      workspace: {path: realpathSync(process.cwd()), source: 'command-line'},
      transcriptEnabled: false,
      provider: 'mock',
    });
  });

  it('enables local transcripts by default', () => {
    expect(resolveApplicationConfiguration([], process.cwd())).toEqual({
      workspace: {path: realpathSync(process.cwd()), source: 'launch-directory'},
      transcriptEnabled: true,
      provider: 'mock',
    });
  });

  it.each([
    ['--provider', 'openai', '--model', OPENAI_TEXT_STREAM_MODEL, '--no-transcript'],
    ['--no-transcript', '--model', OPENAI_TEXT_STREAM_MODEL, '--provider', 'openai'],
  ])('accepts the explicit OpenAI provider/model pair in either order', (...arguments_) => {
    expect(resolveApplicationConfiguration(arguments_, process.cwd())).toEqual({
      workspace: {path: realpathSync(process.cwd()), source: 'launch-directory'},
      transcriptEnabled: false,
      provider: 'openai',
      model: OPENAI_TEXT_STREAM_MODEL,
    });
  });

  it.each([
    {arguments_: ['--unknown'], message: 'Unknown command-line argument'},
    {arguments_: ['--workspace'], message: 'requires exactly one path'},
    {arguments_: ['--workspace', '.', '--workspace', '.'], message: 'provided only once'},
    {arguments_: ['--no-transcript', '--no-transcript'], message: 'provided only once'},
    {arguments_: ['--provider'], message: 'requires exactly one value'},
    {arguments_: ['--provider', 'mock', '--provider', 'mock'], message: 'provided only once'},
    {arguments_: ['--model'], message: 'requires exactly one value'},
    {
      arguments_: ['--model', OPENAI_TEXT_STREAM_MODEL, '--model', OPENAI_TEXT_STREAM_MODEL],
      message: 'provided only once',
    },
    {arguments_: ['--provider', 'invalid'], message: 'must be either mock or openai'},
    {arguments_: ['--model', OPENAI_TEXT_STREAM_MODEL], message: 'only with --provider openai'},
    {arguments_: ['--provider', 'openai'], message: 'requires --model MODEL'},
    {
      arguments_: ['--provider', 'openai', '--model', 'secret-model-value'],
      message: 'Unsupported OpenAI model',
    },
  ])('rejects invalid arguments: $arguments_', ({arguments_, message}) => {
    expect(() => resolveWorkspace(arguments_, process.cwd())).toThrow(message);
  });

  it('does not echo rejected provider or model values in configuration diagnostics', () => {
    const provider = 'provider-value-that-must-not-be-echoed';
    const model = 'model-value-that-must-not-be-echoed';

    expect(configurationErrorMessage(['--provider', provider])).not.toContain(provider);
    expect(
      configurationErrorMessage(['--provider', 'openai', '--model', model]),
    ).not.toContain(model);
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

function configurationErrorMessage(arguments_: readonly string[]): string {
  try {
    resolveApplicationConfiguration(arguments_, process.cwd());
  } catch (error: unknown) {
    if (error instanceof Error) {
      return error.message;
    }
  }
  throw new Error('Expected application configuration to fail.');
}
