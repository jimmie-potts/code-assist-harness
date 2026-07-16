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

const WORKSPACE = '/workspace with spaces';
const COMMAND_TIMESTAMP = '2026-07-16T13:00:00.000Z';
const EVENT_TIMESTAMP = '2026-07-16T13:00:00.100Z';
const INITIALIZATION_COMMAND_ID = 'cmd_initialize_001';
const SHUTDOWN_COMMAND_ID = 'cmd_shutdown_001';

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
    readonly readinessTimeoutMs?: number;
    readonly createCommandId?: () => string;
    readonly now?: () => string;
    readonly prepareLaunch?: (request: RuntimeLaunchRequest) => RuntimeLaunchRequest;
    readonly signalProcessGroup?: (
      child: ChildProcessWithoutNullStreams,
      signal: NodeJS.Signals,
    ) => void;
    readonly captureRequest?: (request: RuntimeLaunchRequest) => void;
  } = {},
): PythonRuntimeSupervisor {
  const commandIds = [INITIALIZATION_COMMAND_ID, SHUTDOWN_COMMAND_ID];
  return new PythonRuntimeSupervisor(
    {
      repositoryRoot: '/harness root',
      workspace: WORKSPACE,
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
      readinessTimeoutMs: overrides.readinessTimeoutMs ?? 1000,
      createCommandId:
        overrides.createCommandId ?? (() => commandIds.shift() ?? 'cmd_additional_001'),
      now: overrides.now ?? (() => COMMAND_TIMESTAMP),
    },
  );
}

function initializationCommandLine(): string {
  return `${JSON.stringify({
    protocol_version: 1,
    type: 'runtime.initialize',
    command_id: INITIALIZATION_COMMAND_ID,
    timestamp: COMMAND_TIMESTAMP,
    payload: {workspace: WORKSPACE},
  })}\n`;
}

function shutdownCommandLine(): string {
  return `${JSON.stringify({
    protocol_version: 1,
    type: 'runtime.shutdown',
    command_id: SHUTDOWN_COMMAND_ID,
    timestamp: COMMAND_TIMESTAMP,
    payload: {},
  })}\n`;
}

function readyEventLine(
  correlationId = INITIALIZATION_COMMAND_ID,
  workspace = WORKSPACE,
): string {
  return `${JSON.stringify({
    protocol_version: 1,
    type: 'runtime.ready',
    timestamp: EVENT_TIMESTAMP,
    correlation_id: correlationId,
    payload: {workspace},
  })}\n`;
}

function sessionStartedEventLine(): string {
  return `${JSON.stringify({
    protocol_version: 1,
    type: 'session.started',
    session_id: 'ses_unexpected_001',
    sequence: 1,
    timestamp: EVENT_TIMESTAMP,
    payload: {},
  })}\n`;
}

function nextInputLine(child: FakeChild): Promise<string> {
  return new Promise((resolve) => {
    child.stdin.once('data', (chunk: Buffer | string) => {
      resolve(chunk.toString());
    });
  });
}

async function startReady(
  child: FakeChild,
  supervisor: PythonRuntimeSupervisor,
): Promise<void> {
  const initializationLine = nextInputLine(child);
  const start = supervisor.start();
  child.emit('spawn');
  expect(await initializationLine).toBe(initializationCommandLine());
  child.stdout.write(readyEventLine());
  await start;
  expect(supervisor.getState().status).toBe('running');
}

async function closeOnInputEnd(child: FakeChild, supervisor: PythonRuntimeSupervisor): Promise<void> {
  child.stdin.once('finish', () => child.close(0));
  await supervisor.stop();
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

  it('writes exact initialization and remains starting until matching runtime.ready', async () => {
    const child = new FakeChild();
    let request: RuntimeLaunchRequest | undefined;
    const supervisor = createSupervisor(child, {captureRequest: (value) => (request = value)});
    const states: RuntimeState[] = [];
    supervisor.subscribe((state) => states.push(state));

    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    expect(supervisor.getState().status).toBe('starting');
    child.emit('spawn');

    expect(await initializationLine).toBe(initializationCommandLine());
    expect(request?.arguments.at(-1)).toBe(WORKSPACE);
    expect(supervisor.getState().status).toBe('starting');
    expect(states).toEqual([]);

    child.stdout.write(readyEventLine());
    await start;

    expect(supervisor.getState().status).toBe('running');
    expect(states.map((state) => state.status)).toEqual(['running']);

    await closeOnInputEnd(child, supervisor);
  });

  it.each([
    {
      name: 'wrong correlation ID',
      readyLine: readyEventLine('cmd_different_001'),
    },
    {
      name: 'wrong canonical workspace',
      readyLine: readyEventLine(INITIALIZATION_COMMAND_ID, '/different-workspace'),
    },
  ])('fails closed when runtime.ready has the $name', async ({readyLine}) => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child);
    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    child.emit('spawn');
    expect(await initializationLine).toBe(initializationCommandLine());

    child.stdout.write(readyLine);
    await start;

    expect(supervisor.getState()).toMatchObject({
      status: 'protocol-failed',
      code: 'readiness_mismatch',
    });
    expect(child.stdin.writableEnded).toBe(true);
    child.close(0);
    await supervisor.stop();
  });

  it('surfaces a correlated runtime.error as an initialization failure', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child);
    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    child.emit('spawn');
    await initializationLine;

    child.stdout.write(
      `${JSON.stringify({
        protocol_version: 1,
        type: 'runtime.error',
        timestamp: EVENT_TIMESTAMP,
        correlation_id: INITIALIZATION_COMMAND_ID,
        payload: {
          code: 'workspace_mismatch',
          message: 'Initialization workspace does not match.',
          recoverable: false,
        },
      })}\n`,
    );
    await start;

    expect(supervisor.getState()).toMatchObject({
      status: 'failed-to-start',
      message: expect.stringContaining('workspace_mismatch'),
    });
    expect(supervisor.getState()).toMatchObject({
      message: expect.stringContaining('Initialization workspace does not match.'),
    });
    expect(child.stdin.writableEnded).toBe(true);
    child.close(0);
    await supervisor.stop();
  });

  it.each([
    {
      name: 'malformed known event',
      line: `${JSON.stringify({
        protocol_version: 1,
        type: 'runtime.ready',
        timestamp: EVENT_TIMESTAMP,
        correlation_id: INITIALIZATION_COMMAND_ID,
        payload: {workspace: 7},
      })}\n`,
      code: 'invalid_payload',
    },
    {
      name: 'unknown event',
      line: `${JSON.stringify({
        protocol_version: 1,
        type: 'runtime.future',
        timestamp: EVENT_TIMESTAMP,
        correlation_id: INITIALIZATION_COMMAND_ID,
        payload: {},
      })}\n`,
      code: 'unknown_type',
    },
  ])('keeps $name distinct before readiness', async ({line, code}) => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child);
    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    child.emit('spawn');
    await initializationLine;

    child.stdout.write(line);
    await start;

    expect(supervisor.getState()).toMatchObject({status: 'protocol-failed', code});
    expect(child.stdin.writableEnded).toBe(true);
    child.close(0);
    await supervisor.stop();
  });

  it('fails closed when a valid session event arrives before readiness', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child);
    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    child.emit('spawn');
    await initializationLine;

    child.stdout.write(sessionStartedEventLine());
    await start;

    expect(supervisor.getState()).toMatchObject({
      status: 'protocol-failed',
      code: 'unexpected_event',
      message: expect.stringContaining('before runtime.ready'),
    });
    child.close(0);
    await supervisor.stop();
  });

  it('fails closed when runtime.ready misses the readiness deadline', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child, {readinessTimeoutMs: 1});
    const initializationLine = nextInputLine(child);
    const start = supervisor.start();
    child.emit('spawn');
    expect(await initializationLine).toBe(initializationCommandLine());

    await start;

    expect(supervisor.getState()).toMatchObject({
      status: 'protocol-failed',
      code: 'readiness_timeout',
    });
    expect(child.stdin.writableEnded).toBe(true);
    child.close(0);
    await supervisor.stop();
  });

  it('starts the readiness deadline even when the initialization write callback never fires', async () => {
    const child = new FakeChild();
    vi.spyOn(child.stdin, 'write').mockImplementation((() => true) as typeof child.stdin.write);
    const supervisor = createSupervisor(child, {readinessTimeoutMs: 1});

    const start = supervisor.start();
    child.emit('spawn');
    await start;

    expect(supervisor.getState()).toMatchObject({
      status: 'protocol-failed',
      code: 'readiness_timeout',
    });
    expect(child.stdin.writableEnded).toBe(true);
    child.close(0);
    await supervisor.stop();
  });

  it('fails closed and sanitizes a runtime error received after readiness', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child, {environment: {API_TOKEN: 'hidden-value'}});
    await startReady(child, supervisor);

    child.stdout.write(
      `${JSON.stringify({
        protocol_version: 1,
        type: 'runtime.error',
        timestamp: EVENT_TIMESTAMP,
        payload: {
          code: 'provider_failed',
          message: 'Provider exposed hidden-value',
          recoverable: false,
        },
      })}\n`,
    );

    expect(supervisor.getState()).toMatchObject({
      status: 'protocol-failed',
      code: 'unexpected_event',
      message: expect.stringContaining('[REDACTED]'),
    });
    const state = supervisor.getState();
    expect(state.status === 'protocol-failed' ? state.message : '').not.toContain('hidden-value');
    child.close(0);
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

  it('treats any unrequested close as failure and sanitizes stderr secrets', async () => {
    const child = new FakeChild();
    const supervisor = createSupervisor(child, {environment: {API_TOKEN: 'hidden-value'}});
    await startReady(child, supervisor);

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
    expect(state.message).not.toContain('hidden-value');
  });

  it('writes shutdown before closing stdin and escalating idempotent cleanup', async () => {
    const child = new FakeChild();
    const signals: NodeJS.Signals[] = [];
    const inputLines: string[] = [];
    const shutdownWritten = vi.fn();
    child.stdin.on('data', (chunk: Buffer | string) => {
      const line = chunk.toString();
      inputLines.push(line);
      if (line.includes('runtime.shutdown')) {
        shutdownWritten();
      }
    });
    const endInput = vi.spyOn(child.stdin, 'end');
    const signalProcessGroup = vi.fn(
      (_child: ChildProcessWithoutNullStreams, signal: NodeJS.Signals) => {
        signals.push(signal);
        if (signal === 'SIGKILL') {
          child.close(null, signal);
        }
      },
    );
    const supervisor = createSupervisor(child, {
      wait: async () => undefined,
      signalProcessGroup,
    });
    await startReady(child, supervisor);

    const firstStop = supervisor.stop();
    const secondStop = supervisor.stop();
    expect(firstStop).toBe(secondStop);
    await firstStop;

    expect(child.stdin.writableEnded).toBe(true);
    expect(inputLines).toEqual([initializationCommandLine(), shutdownCommandLine()]);
    expect(shutdownWritten).toHaveBeenCalledOnce();
    expect(endInput).toHaveBeenCalledOnce();
    expect(signalProcessGroup).toHaveBeenCalledTimes(2);
    expect(shutdownWritten.mock.invocationCallOrder[0]).toBeLessThan(
      endInput.mock.invocationCallOrder[0] ?? Number.POSITIVE_INFINITY,
    );
    expect(endInput.mock.invocationCallOrder[0]).toBeLessThan(
      signalProcessGroup.mock.invocationCallOrder[0] ?? Number.POSITIVE_INFINITY,
    );
    expect(signals).toEqual(['SIGTERM', 'SIGKILL']);
    expect(supervisor.getState().status).toBe('stopped');
  });

  it('does not let a missing shutdown write callback delay bounded signal escalation', async () => {
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
    await startReady(child, supervisor);
    vi.spyOn(child.stdin, 'write').mockImplementation((() => true) as typeof child.stdin.write);

    await supervisor.stop();

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
      await startReady(child, supervisor);
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
