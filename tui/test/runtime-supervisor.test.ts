import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {EventEmitter} from 'node:events';
import {PassThrough} from 'node:stream';

import {describe, expect, it, vi} from 'vitest';

import {
  buildRuntimeLaunchRequest,
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
    expect(buildRuntimeLaunchRequest('/repo', '/workspace')).toEqual({
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
      },
    });
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
    child.stderr.write('API_TOKEN=hidden-value useful diagnostic');
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
      {spawnProcess},
    );

    await supervisor.start();

    expect(capturedRequest?.options.shell).toBe(false);
    expect(supervisor.getState()).toMatchObject({status: 'failed-to-start'});
    await supervisor.stop();
  });
});
