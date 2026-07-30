import {spawn} from 'node:child_process';
import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, join} from 'node:path';
import {fileURLToPath} from 'node:url';

import {render as renderInk} from 'ink-testing-library';
import {describe, expect, it} from 'vitest';

import {
  runApplication,
  type ApplicationRenderer,
  type ApplicationTerminationSubscriber,
} from '../src/run-application.js';
import {
  PythonRuntimeSupervisor,
  type RuntimeLaunchRequest,
  type RuntimeState,
} from '../src/runtime-supervisor.js';
import {
  INITIAL_SESSION_STATE,
  reduceSessionState,
  type SessionState,
} from '../src/session-state.js';

const repositoryRoot = realpathSync(fileURLToPath(new URL('../../', import.meta.url)));

describe('real Node to uv to Python boundary', () => {
  it('starts the genuine runtime with filtered overrides and reaps the process group', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-runtime-workspace-'));
    const poisonPythonPath = mkdtempSync(join(tmpdir(), 'cah-poison-python-path-'));
    const poisonPackage = join(poisonPythonPath, 'code_assist_harness');
    const poisonMarker = join(poisonPythonPath, 'poison-runtime-imported');
    mkdirSync(poisonPackage);
    writeFileSync(join(poisonPackage, '__init__.py'), '');
    writeFileSync(
      join(poisonPackage, 'runtime.py'),
      [
        'from pathlib import Path',
        'import sys',
        `Path(${JSON.stringify(poisonMarker)}).write_text("imported")`,
        'sys.stdin.buffer.read()',
        '',
      ].join('\n'),
    );
    let uvPid: number | undefined;
    let pythonPid: number | undefined;

    const spawnProcess = (request: RuntimeLaunchRequest): ChildProcessWithoutNullStreams => {
      const child = spawn(request.command, [...request.arguments], {
        cwd: request.options.cwd,
        detached: request.options.detached,
        env: request.options.env,
        shell: request.options.shell,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      uvPid = child.pid;
      return child;
    };
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace},
      {
        spawnProcess,
        gracePeriodMs: 2000,
        terminatePeriodMs: 2000,
        environment: {
          ...process.env,
          PYTHONHOME: join(workspace, 'missing-python-home'),
          PYTHONPATH: poisonPythonPath,
          UV_ISOLATED: '1',
          UV_PROJECT_ENVIRONMENT: join(workspace, 'poison-uv-project-environment'),
          VIRTUAL_ENV: join(workspace, 'poison-active-environment'),
        },
      },
    );
    const states: RuntimeState[] = [];
    const sessionProjections: SessionState[] = [];
    let sessionState = INITIAL_SESSION_STATE;
    const unsubscribe = supervisor.subscribe((state) => states.push(state));
    const unsubscribeFromSession = supervisor.subscribeToSessionUpdates((update) => {
      sessionState = reduceSessionState(sessionState, update);
      sessionProjections.push(sessionState);
    });

    try {
      expect(supervisor.getState().status).toBe('starting');
      await withTimeout(
        supervisor.start(),
        5000,
        'runtime did not return a validated runtime.ready event',
      );
      expect(supervisor.getState().status).toBe('running');
      expect(states.map((state) => state.status)).toEqual(['running']);
      expect(uvPid).toBeDefined();
      if (uvPid === undefined) {
        throw new Error('uv spawned without a process ID.');
      }

      pythonPid = await findRuntimeProcess(uvPid);
      expect(readCommandLine(pythonPid)).toContain('code_assist_harness.runtime');
      expect(readExecutableName(pythonPid)).toMatch(/^python(?:\d+(?:\.\d+)*)?$/u);

      const firstCommandId = supervisor.submitTask('Explain the real boundary.');
      await waitForCondition(
        () => sessionState.status === 'completed',
        5000,
        'first mocked session did not complete',
      );
      const firstTurn = sessionState.turns[0];
      expect(firstTurn).toMatchObject({
        commandId: firstCommandId,
        sessionId: 'ses_mock_1',
        status: 'completed',
        assistantText:
          'Mock response: the task crossed the process boundary and streamed back successfully.',
        lastSequence: 6,
      });
      expect(
        sessionProjections
          .filter((projection) => projection.turns.length === 1)
          .map((projection) => projection.turns[0]?.assistantText)
          .filter((text, index, values) => text !== '' && text !== values[index - 1]),
      ).toEqual([
        'Mock response: ',
        'Mock response: the task crossed the process boundary ',
        'Mock response: the task crossed the process boundary and streamed back successfully.',
      ]);

      const secondCommandId = supervisor.submitTask('Prove a second session.');
      await waitForCondition(
        () => sessionState.status === 'completed' && sessionState.turns.length === 2,
        5000,
        'second mocked session did not complete',
      );
      expect(secondCommandId).not.toBe(firstCommandId);
      expect(sessionState.turns[1]).toMatchObject({
        commandId: secondCommandId,
        sessionId: 'ses_mock_2',
        status: 'completed',
        lastSequence: 6,
      });
      expect(sessionState.turns[1]?.sessionId).not.toBe(firstTurn?.sessionId);

      await withTimeout(supervisor.stop(), 5000, 'runtime cleanup did not finish');

      expect(supervisor.getState().status).toBe('stopped');
      expect(existsSync(`/proc/${uvPid}`)).toBe(false);
      expect(existsSync(`/proc/${pythonPid}`)).toBe(false);
      expect(existsSync(poisonMarker)).toBe(false);
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      if (supervisor.getState().status !== 'stopped') {
        await supervisor.stop();
      }
      unsubscribe();
      unsubscribeFromSession();
      rmSync(workspace, {recursive: true, force: true});
      rmSync(poisonPythonPath, {recursive: true, force: true});
    }
  }, 10_000);

  it('renders every genuine mocked delta before completion and accepts a second task', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-render-workspace-'));
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace},
      {gracePeriodMs: 2000, terminatePeriodMs: 2000},
    );
    const frames: string[] = [];
    let terminal: ReturnType<typeof renderInk> | undefined;
    let requestExit = (): void => undefined;
    const renderApplication: ApplicationRenderer = (tree, options) => {
      expect(options).toEqual({exitOnCtrlC: true});
      const view = renderInk(tree);
      terminal = view;
      let exited = false;
      let resolveExit = (): void => undefined;
      const exit = new Promise<void>((resolve) => {
        resolveExit = resolve;
      });
      const capture = (): void => {
        const frame = view.lastFrame();
        if (frame !== undefined && frame !== frames.at(-1)) {
          frames.push(frame);
        }
      };
      const captureTree = (nextTree: Parameters<ApplicationRenderer>[0]): void => {
        const snapshot = renderInk(nextTree);
        const frame = snapshot.lastFrame();
        if (frame !== undefined && frame !== frames.at(-1)) {
          frames.push(frame);
        }
        snapshot.unmount();
      };
      capture();
      requestExit = () => {
        if (!exited) {
          exited = true;
          view.unmount();
          resolveExit();
        }
      };
      return {
        rerender: (nextTree) => {
          captureTree(nextTree);
          view.rerender(nextTree);
          capture();
          setImmediate(capture);
        },
        unmount: requestExit,
        waitUntilExit: () => exit,
      };
    };
    const ignoreTerminationSignals: ApplicationTerminationSubscriber = () => () => undefined;
    const running = runApplication(supervisor, renderApplication, ignoreTerminationSignals);

    try {
      await waitForCondition(
        () => supervisor.getState().status === 'running' && terminal !== undefined,
        5000,
        'application did not render a ready runtime',
      );
      if (terminal === undefined) {
        throw new Error('application renderer did not expose its terminal');
      }

      terminal.stdin.write('Explain the rendered boundary.');
      terminal.stdin.write('\r');
      await waitForCondition(
        () => frames.some((frame) => frame.includes('Session status: completed')),
        5000,
        'first rendered session did not complete',
      );

      const firstDelta = frames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          !frame.includes('the task crossed the process boundary') &&
          frame.includes('Session status: running'),
      );
      const secondDelta = frames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          frame.includes('the task crossed the process boundary') &&
          !frame.includes('successfully.') &&
          frame.includes('Session status: running'),
      );
      const thirdDelta = frames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          frame.includes('the task crossed the process boundary') &&
          frame.includes('streamed') &&
          frame.includes('successfully.') &&
          frame.includes('Session status: running'),
      );
      const firstCompletion = frames.findIndex(
        (frame) =>
          frame.includes('Explain the rendered boundary.') &&
          frame.includes('streamed') &&
          frame.includes('successfully.') &&
          frame.includes('Session status: completed'),
      );
      expect(firstDelta).toBeGreaterThanOrEqual(0);
      expect(secondDelta).toBeGreaterThan(firstDelta);
      expect(thirdDelta).toBeGreaterThan(secondDelta);
      expect(firstCompletion).toBeGreaterThan(thirdDelta);

      terminal.stdin.write('Prove the rendered boundary again.');
      terminal.stdin.write('\r');
      await waitForCondition(
        () =>
          frames.some(
            (frame) =>
              frame.includes('Prove the rendered boundary again.') &&
              (frame.match(/Mock response:/gu)?.length ?? 0) === 2 &&
              frame.includes('Session status: completed'),
          ),
        5000,
        'second rendered session did not complete',
      );
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      requestExit();
      try {
        await running;
      } finally {
        rmSync(workspace, {recursive: true, force: true});
      }
    }

    expect(supervisor.getState().status).toBe('stopped');
  }, 10_000);
});

async function findRuntimeProcess(uvPid: number): Promise<number> {
  const deadline = Date.now() + 5000;
  let lastObservedProcesses: string[] = [];
  while (Date.now() < deadline) {
    const pending = [uvPid];
    const visited = new Set<number>();
    lastObservedProcesses = [];
    while (pending.length > 0) {
      const candidatePid = pending.shift();
      if (candidatePid === undefined || visited.has(candidatePid)) {
        continue;
      }
      visited.add(candidatePid);
      lastObservedProcesses.push(
        `${candidatePid}:${readExecutableName(candidatePid)}:${readCommandLine(candidatePid)}`,
      );

      if (isPythonRuntime(candidatePid)) {
        return candidatePid;
      }
      pending.push(...readChildProcessIds(candidatePid));
    }
    await delay(10);
  }
  throw new Error(
    `The uv process never launched the Python runtime module. Last observed: ${lastObservedProcesses.join(' | ')}`,
  );
}

async function waitForCondition(
  predicate: () => boolean,
  milliseconds: number,
  message: string,
): Promise<void> {
  const deadline = Date.now() + milliseconds;
  while (Date.now() < deadline) {
    if (predicate()) {
      return;
    }
    await delay(10);
  }
  throw new Error(message);
}

function isPythonRuntime(pid: number): boolean {
  return (
    /^python(?:\d+(?:\.\d+)*)?$/u.test(readExecutableName(pid)) &&
    readCommandLine(pid).includes('code_assist_harness.runtime')
  );
}

function readChildProcessIds(pid: number): number[] {
  try {
    const childProcessIds = new Set<number>();
    for (const threadId of readdirSync(`/proc/${pid}/task`)) {
      try {
        const values = readFileSync(`/proc/${pid}/task/${threadId}/children`, 'utf8')
          .trim()
          .split(/\s+/u)
          .filter((value) => value.length > 0)
          .map(Number);
        for (const value of values) {
          childProcessIds.add(value);
        }
      } catch {
        // Threads may exit while their child list is read; the next poll observes current state.
      }
    }
    return [...childProcessIds];
  } catch {
    return [];
  }
}

function readExecutableName(pid: number): string {
  try {
    return basename(readlinkSync(`/proc/${pid}/exe`));
  } catch {
    return '';
  }
}

function readCommandLine(pid: number): string {
  try {
    return readFileSync(`/proc/${pid}/cmdline`, 'utf8').replaceAll('\0', ' ');
  } catch {
    return '';
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function withTimeout<T>(promise: Promise<T>, milliseconds: number, message: string): Promise<T> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => reject(new Error(message)), milliseconds);
      }),
    ]);
  } finally {
    if (timer !== undefined) {
      clearTimeout(timer);
    }
  }
}
