import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {EventEmitter} from 'node:events';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {PassThrough} from 'node:stream';

import {describe, expect, it, vi} from 'vitest';

import {
  buildRuntimeLaunchRequest,
  prepareRuntimeLaunch,
  PythonRuntimeSupervisor,
  type RuntimeLaunchRequest,
  type RuntimeState,
} from '../src/runtime-supervisor.js';

class FakeChild extends EventEmitter {
  public readonly stdin = new PassThrough();
  public readonly stdout = new PassThrough();
  public readonly stderr = new PassThrough();
  public readonly pid = 4242;
  public exitCode: number | null = null;
  public signalCode: NodeJS.Signals | null = null;

  public close(code: number | null, signal: NodeJS.Signals | null = null): void {
    this.exitCode = code;
    this.signalCode = signal;
    this.emit('close', code, signal);
  }
}

function asChild(child: FakeChild): ChildProcessWithoutNullStreams {
  return child as unknown as ChildProcessWithoutNullStreams;
}

function createSupervisor(
  child: FakeChild,
  overrides: {
    readonly command?: string;
    readonly environment?: NodeJS.ProcessEnv;
    readonly wait?: (milliseconds: number) => Promise<void>;
    readonly prepareLaunch?: (request: RuntimeLaunchRequest) => RuntimeLaunchRequest;
    readonly signalProcessGroup?: (
      child: ChildProcessWithoutNullStreams,
      signal: NodeJS.Signals,
    ) => void;
    readonly captureRequest?: (request: RuntimeLaunchRequest) => void;
  } = {},
): PythonRuntimeSupervisor {
  return new PythonRuntimeSupervisor(
    {
      repositoryRoot: '/harness root',
      workspace: '/workspace with spaces',
      ...(overrides.command === undefined ? {} : {command: overrides.command}),
    },
    {
      spawnProcess: (request) => {
        overrides.captureRequest?.(request);
        return asChild(child);
      },
      prepareLaunch: overrides.prepareLaunch ?? ((request) => request),
      ...(overrides.environment === undefined ? {} : {environment: overrides.environment}),
      ...(overrides.wait === undefined ? {} : {wait: overrides.wait}),
      ...(overrides.signalProcessGroup === undefined
        ? {}
        : {signalProcessGroup: overrides.signalProcessGroup}),
      gracePeriodMs: 1,
      terminatePeriodMs: 1,
    },
  );
}

describe('PythonRuntimeSupervisor', () => {
  it('builds an exact shell-free, offline uv request with separate workspace argument', () => {
    expect(buildRuntimeLaunchRequest('/repo', '/workspace', 'uv', {})).toEqual({
      command: 'uv',
      arguments: [
        'run',
        '--project',
        '/repo',
        '--frozen',
        '--no-cache',
        '--no-sync',
        '--offline',
        '--no-env-file',
        '--no-progress',
        '--no-python-downloads',
        '--python',
        '/repo/.venv/bin/python',
        '--',
        'python',
        '-m',
        'code_assist_harness.runtime',
        '--workspace',
        '/workspace',
      ],
      options: {
        cwd: '/repo',
        shell: false,
        stdio: ['pipe', 'pipe', 'pipe'],
        detached: true,
        env: {},
      },
    });
  });

  it('strips runtime-selection overrides while preserving the remaining child environment', () => {
    const environment = {
      PATH: '/usr/bin',
      PYTHONHOME: '',
      PYTHONPATH: '/tmp/fake-python-path',
      UV_PROJECT_ENVIRONMENT: '/tmp/other-environment',
      UV_ISOLATED: '1',
      VIRTUAL_ENV: '/tmp/active-environment',
      CUSTOM_SETTING: 'kept',
    };
    const request = buildRuntimeLaunchRequest('/repo', '/workspace', 'uv', environment);

    expect(request.options.env).toEqual({PATH: '/usr/bin', CUSTOM_SETTING: 'kept'});
    expect(environment).toEqual({
      PATH: '/usr/bin',
      PYTHONHOME: '',
      PYTHONPATH: '/tmp/fake-python-path',
      UV_PROJECT_ENVIRONMENT: '/tmp/other-environment',
      UV_ISOLATED: '1',
      VIRTUAL_ENV: '/tmp/active-environment',
      CUSTOM_SETTING: 'kept',
    });
  });

  it('resolves uv to an absolute Linux path after validating the prepared environment', () => {
    const repositoryRoot = mkdtempSync(join(tmpdir(), 'cah-prepared-runtime-'));
    const executableDirectory = mkdtempSync(join(tmpdir(), 'cah-linux-uv-'));
    const uvExecutable = join(executableDirectory, 'uv');
    const pythonDirectory = join(repositoryRoot, '.venv', 'bin');
    const pythonExecutable = join(pythonDirectory, 'python');
    mkdirSync(pythonDirectory, {recursive: true});
    writeFileSync(join(repositoryRoot, '.venv', 'pyvenv.cfg'), 'home = /usr/bin\n');
    writeExecutable(pythonExecutable);
    writeExecutable(uvExecutable);

    try {
      const request = buildRuntimeLaunchRequest(repositoryRoot, '/workspace', 'uv', {
        PATH: executableDirectory,
      });
      const prepared = prepareRuntimeLaunch(request);

      expect(prepared.command).toBe(realpathSync(uvExecutable));
      expect(prepared.arguments).toContain(pythonExecutable);
    } finally {
      rmSync(repositoryRoot, {recursive: true, force: true});
      rmSync(executableDirectory, {recursive: true, force: true});
    }
  });

  it('reports an unprepared environment without spawning or creating .venv', async () => {
    const repositoryRoot = mkdtempSync(join(tmpdir(), 'cah-missing-runtime-environment-'));
    const executableDirectory = mkdtempSync(join(tmpdir(), 'cah-preflight-uv-'));
    writeExecutable(join(executableDirectory, 'uv'));
    const child = new FakeChild();
    const spawnProcess = vi.fn((): ChildProcessWithoutNullStreams => asChild(child));
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace: '/workspace'},
      {environment: {PATH: executableDirectory}, spawnProcess},
    );

    try {
      await supervisor.start();

      expect(spawnProcess).not.toHaveBeenCalled();
      expect(supervisor.getState()).toMatchObject({
        status: 'failed-to-start',
        message: expect.stringContaining('is not prepared'),
      });
      expect(supervisor.getState()).toMatchObject({
        message: expect.stringContaining('uv sync --dev'),
      });
      expect(existsSync(join(repositoryRoot, '.venv'))).toBe(false);
      await supervisor.stop();
    } finally {
      rmSync(repositoryRoot, {recursive: true, force: true});
      rmSync(executableDirectory, {recursive: true, force: true});
    }
  });

  it('rejects missing and Windows uv executables before spawn', () => {
    const repositoryRoot = mkdtempSync(join(tmpdir(), 'cah-invalid-uv-'));
    const executableDirectory = mkdtempSync(join(tmpdir(), 'cah-windows-uv-'));
    const windowsUv = join(executableDirectory, 'uv.exe');
    writeExecutable(windowsUv);
    symlinkSync(windowsUv, join(executableDirectory, 'uv'));

    try {
      expect(() =>
        prepareRuntimeLaunch(
          buildRuntimeLaunchRequest(repositoryRoot, '/workspace', 'uv', {
            PATH: join(repositoryRoot, 'empty-path'),
          }),
        ),
      ).toThrow(/uv was not found inside Ubuntu WSL/u);
      expect(() =>
        prepareRuntimeLaunch(
          buildRuntimeLaunchRequest(repositoryRoot, '/workspace', 'uv', {
            PATH: executableDirectory,
          }),
        ),
      ).toThrow(/Windows executable/u);
      expect(() =>
        prepareRuntimeLaunch(
          buildRuntimeLaunchRequest(repositoryRoot, '/workspace', '/mnt/c/tools/uv.exe', {}),
        ),
      ).toThrow(/Windows executable/u);
    } finally {
      rmSync(repositoryRoot, {recursive: true, force: true});
      rmSync(executableDirectory, {recursive: true, force: true});
    }
  });

  it('rejects an extensionless uv path under a Windows mount without spawning', async () => {
    const child = new FakeChild();
    const spawnProcess = vi.fn((): ChildProcessWithoutNullStreams => asChild(child));
    const supervisor = new PythonRuntimeSupervisor(
      {
        repositoryRoot: '/repo',
        workspace: '/workspace',
        command: '/mnt/c/tools/uv',
      },
      {environment: {}, spawnProcess},
    );

    await supervisor.start();

    expect(spawnProcess).not.toHaveBeenCalled();
    expect(supervisor.getState()).toMatchObject({
      status: 'failed-to-start',
      message: expect.stringContaining('Windows executable'),
    });
    expect(supervisor.getState()).toMatchObject({
      message: expect.stringContaining('Install uv inside Ubuntu WSL'),
    });
    await supervisor.stop();
  });

  it('moves from starting to running only after spawn', async () => {
    const child = new FakeChild();
    let request: RuntimeLaunchRequest | undefined;
    const supervisor = createSupervisor(child, {captureRequest: (value) => (request = value)});
    const states: RuntimeState[] = [];
    supervisor.subscribe((state) => states.push(state));

    const start = supervisor.start();
    expect(supervisor.getState().status).toBe('starting');
    child.emit('spawn');
    await start;

    expect(request?.arguments.at(-1)).toBe('/workspace with spaces');
    expect(supervisor.getState().status).toBe('running');
    expect(states.map((state) => state.status)).toEqual(['running']);

    child.stdin.once('finish', () => child.close(0));
    await supervisor.stop();
  });

  it('reports an actionable startup failure without entering running', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child);
    const start = supervisor.start();
    const error = Object.assign(new Error('spawn uv ENOENT'), {code: 'ENOENT'});

    child.emit('error', error);
    await start;
    child.close(null);

    expect(supervisor.getState()).toMatchObject({
      status: 'failed-to-start',
      message: expect.stringContaining('uv was not found'),
    });
    expect(supervisor.getState()).toMatchObject({message: expect.stringContaining('uv sync --dev')});
  });

  it('treats any unrequested close as failure and excludes stdout and secrets', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child, {environment: {API_TOKEN: 'hidden-value'}});
    const start = supervisor.start();
    child.emit('spawn');
    await start;

    child.stdout.write('{"future":"protocol secret hidden-value"}\n');
    child.stderr.write('API_TOKEN=hidden-value\nuseful diagnostic');
    child.close(0);

    expect(supervisor.getState()).toMatchObject({
      status: 'unexpectedly-exited',
      message: expect.stringContaining('exit code 0'),
    });
    const state = supervisor.getState();
    if (state.status !== 'unexpectedly-exited') {
      throw new Error('Expected an unexpected-exit state.');
    }
    expect(state.message).toContain('useful diagnostic');
    expect(state.message).toContain('[REDACTED]');
    expect(state.message).not.toContain('future');
    expect(state.message).not.toContain('hidden-value');
  });

  it('closes stdin, escalates the detached group, and shares idempotent cleanup', async () => {
    const child = new FakeChild();
    const signals: NodeJS.Signals[] = [];
    const supervisor = createSupervisor(child, {
      wait: async () => undefined,
      signalProcessGroup: (_child, signal) => {
        signals.push(signal);
        if (signal === 'SIGKILL') {
          child.close(null, signal);
        }
      },
    });
    const start = supervisor.start();
    child.emit('spawn');
    await start;

    const firstStop = supervisor.stop();
    const secondStop = supervisor.stop();
    expect(firstStop).toBe(secondStop);
    await firstStop;

    expect(child.stdin.writableEnded).toBe(true);
    expect(signals).toEqual(['SIGTERM', 'SIGKILL']);
    expect(supervisor.getState().status).toBe('stopped');
  });

  it('signals the process group after the uv leader exits but before inherited pipes close', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child, {wait: async () => undefined});
    const kill = vi.spyOn(process, 'kill').mockImplementation((pid, signal) => {
      expect(pid).toBe(-child.pid);
      expect(signal).toBe('SIGTERM');
      child.close(0);
      return true;
    });

    try {
      const start = supervisor.start();
      child.emit('spawn');
      await start;
      child.exitCode = 0;

      await supervisor.stop();

      expect(kill).toHaveBeenCalledOnce();
      expect(supervisor.getState().status).toBe('stopped');
    } finally {
      kill.mockRestore();
    }
  });

  it('does not use a shell even when a custom command cannot be spawned synchronously', async () => {
    let capturedRequest: RuntimeLaunchRequest | undefined;
    const spawnProcess = (request: RuntimeLaunchRequest): ChildProcessWithoutNullStreams => {
      capturedRequest = request;
      throw Object.assign(new Error('blocked'), {code: 'EACCES'});
    };
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot: '/repo', workspace: '/workspace', command: 'custom uv'},
      {prepareLaunch: (request) => request, spawnProcess},
    );

    await supervisor.start();

    expect(capturedRequest?.options.shell).toBe(false);
    expect(supervisor.getState()).toMatchObject({status: 'failed-to-start'});
    await supervisor.stop();
  });
});

function writeExecutable(path: string): void {
  writeFileSync(path, '#!/bin/sh\nexit 0\n', {mode: 0o755});
}
