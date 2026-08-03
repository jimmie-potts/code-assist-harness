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

import type {ProtocolCommand} from '../src/protocol.js';
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
  type SessionEvent,
  type SessionState,
} from '../src/session-state.js';

const repositoryRoot = realpathSync(fileURLToPath(new URL('../../', import.meta.url)));
const scenarioFixtureRoot = new URL('../../protocol/fixtures/v1/scenarios/', import.meta.url);
const successScenarioCommands = readScenarioFixture<ProtocolCommand>(
  'walking-skeleton-success.commands.ndjson',
);
const successScenarioEvents = readScenarioFixture<SessionEvent>(
  'walking-skeleton-success.events.ndjson',
);
const cancellationScenarioCommands = readScenarioFixture<ProtocolCommand>(
  'walking-skeleton-cancel.commands.ndjson',
);
const cancellationScenarioEvents = readScenarioFixture<SessionEvent>(
  'walking-skeleton-cancel.events.ndjson',
);
// A broken cancellation path would finish the three 500 ms mock checkpoints inside this window.
const POST_CANCELLATION_OBSERVATION_MS = 2000;
const FAKE_RUNTIME_SECRET = 'FAKE_CAH_RUNTIME_BOUNDARY_SECRET_011';

interface IsolatedRuntimeEnvironment {
  readonly directory: string;
  readonly values: NodeJS.ProcessEnv;
}

function createIsolatedRuntimeEnvironment(): IsolatedRuntimeEnvironment {
  const directory = mkdtempSync(join(tmpdir(), 'cah-real-runtime-environment-'));
  const home = join(directory, 'home');
  mkdirSync(home, {mode: 0o700});
  const environment: NodeJS.ProcessEnv = {};
  for (const name of ['LANG', 'LC_ALL', 'PATH', 'TERM', 'TMPDIR'] as const) {
    const value = process.env[name];
    if (value !== undefined) {
      environment[name] = value;
    }
  }
  return {directory, values: {...environment, HOME: home}};
}

interface TranscriptRecordFixture {
  readonly record_order: number;
  readonly input: {readonly type: string};
}

describe('real Node to uv to Python boundary', () => {
  it('starts the genuine runtime with filtered overrides and reaps the process group', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-runtime-workspace-'));
    const stateRoot = mkdtempSync(join(tmpdir(), 'cah-real-runtime-state-'));
    const isolatedEnvironment = createIsolatedRuntimeEnvironment();
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
    const successCommand = successScenarioCommands[0];
    if (successScenarioCommands.length !== 1 || successCommand?.type !== 'session.start') {
      throw new Error('successful walking-skeleton fixture must contain one session.start');
    }
    const commandIds = [
      'cmd_walk_success_initialize_001',
      successCommand.command_id,
      'cmd_walk_success_second_001',
      'cmd_walk_success_shutdown_001',
    ];
    const commandTimestamps = [
      '2026-07-30T13:59:59.000Z',
      successCommand.timestamp,
      '2026-07-30T14:00:02.000Z',
      '2026-07-30T14:00:04.000Z',
    ];
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace},
      {
        spawnProcess,
        gracePeriodMs: 2000,
        terminatePeriodMs: 2000,
        createCommandId: nextFixtureValue(commandIds, 'success command ID'),
        now: nextFixtureValue(commandTimestamps, 'success command timestamp'),
        environment: {
          ...isolatedEnvironment.values,
          OPENAI_API_KEY: FAKE_RUNTIME_SECRET,
          PYTHONHOME: join(workspace, 'missing-python-home'),
          PYTHONPATH: poisonPythonPath,
          UV_ISOLATED: '1',
          UV_PROJECT_ENVIRONMENT: join(workspace, 'poison-uv-project-environment'),
          VIRTUAL_ENV: join(workspace, 'poison-active-environment'),
          XDG_STATE_HOME: stateRoot,
        },
      },
    );
    const states: RuntimeState[] = [];
    const sessionProjections: SessionState[] = [];
    const receivedEvents: SessionEvent[] = [];
    let sessionState = INITIAL_SESSION_STATE;
    const unsubscribe = supervisor.subscribe((state) => states.push(state));
    const unsubscribeFromSession = supervisor.subscribeToSessionUpdates((update) => {
      sessionState = reduceSessionState(sessionState, update);
      sessionProjections.push(sessionState);
      if (update.type === 'event.received') {
        receivedEvents.push(update.event);
      }
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
      const runtimeCommandLine = readCommandLine(pythonPid);
      expect(runtimeCommandLine).toContain('code_assist_harness.runtime');
      expect(runtimeCommandLine).toContain('--provider mock');
      expect(runtimeCommandLine).not.toContain('--model');
      expect(readExecutableName(pythonPid)).toMatch(/^python(?:\d+(?:\.\d+)*)?$/u);

      const firstCommandId = supervisor.submitTask(successCommand.payload.task);
      expect(firstCommandId).toBe(successCommand.command_id);
      await waitForCondition(
        () => sessionState.status === 'completed',
        7000,
        'first mocked session did not complete',
      );
      const firstTurn = sessionState.turns[0];
      expect(firstTurn).toMatchObject({
        commandId: firstCommandId,
        task: successCommand.payload.task,
        sessionId: 'ses_mock_1',
        status: 'completed',
        assistantText:
          'Mock response: the task crossed the process boundary and streamed back successfully.',
        lastSequence: 6,
      });
      expect(normalizeEventTimestamps(receivedEvents, successScenarioEvents)).toEqual(
        successScenarioEvents,
      );
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
        7000,
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
      const transcriptDirectory = join(stateRoot, 'code-assist-harness', 'transcripts');
      const artifacts = readdirSync(transcriptDirectory);
      const transcripts = artifacts.filter((name) => name.endsWith('.jsonl'));
      const summaries = artifacts.filter((name) => name.endsWith('.summary.txt'));
      expect(transcripts).toHaveLength(2);
      expect(summaries).toHaveLength(2);
      for (const artifact of artifacts) {
        expect(readFileSync(join(transcriptDirectory, artifact), 'utf8')).not.toContain(
          FAKE_RUNTIME_SECRET,
        );
      }
      for (const transcript of transcripts) {
        const contents = readFileSync(join(transcriptDirectory, transcript), 'utf8');
        expect(contents.endsWith('\n')).toBe(true);
        expect(contents).not.toContain(workspace);
        const records = contents
          .trimEnd()
          .split('\n')
          .map((line) => JSON.parse(line) as TranscriptRecordFixture);
        expect(records.map((record) => record.record_order)).toEqual(
          records.map((_record, index) => index + 1),
        );
        expect(records.at(-1)?.input.type).toBe('session.completed');
      }
    } finally {
      if (supervisor.getState().status !== 'stopped') {
        await supervisor.stop();
      }
      unsubscribe();
      unsubscribeFromSession();
      rmSync(workspace, {recursive: true, force: true});
      rmSync(stateRoot, {recursive: true, force: true});
      rmSync(isolatedEnvironment.directory, {recursive: true, force: true});
      rmSync(poisonPythonPath, {recursive: true, force: true});
    }
  }, 15_000);

  it('cancels genuine sessions before the first delta and between later deltas', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-cancel-workspace-'));
    const isolatedEnvironment = createIsolatedRuntimeEnvironment();
    const [cancelStartCommand, cancelCommand] = cancellationScenarioCommands;
    if (
      cancellationScenarioCommands.length !== 2 ||
      cancelStartCommand?.type !== 'session.start' ||
      cancelCommand?.type !== 'session.cancel'
    ) {
      throw new Error('cancellation walking-skeleton fixture must contain start then cancel');
    }
    const commandIds = [
      'cmd_walk_cancel_initialize_001',
      cancelStartCommand.command_id,
      cancelCommand.command_id,
      'cmd_walk_cancel_start_002',
      'cmd_walk_cancel_002',
      'cmd_walk_cancel_shutdown_001',
    ];
    const commandTimestamps = [
      '2026-07-30T14:00:59.000Z',
      cancelStartCommand.timestamp,
      cancelCommand.timestamp,
      '2026-07-30T14:01:01.000Z',
      '2026-07-30T14:01:01.700Z',
      '2026-07-30T14:01:02.000Z',
    ];
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace, transcriptEnabled: false},
      {
        gracePeriodMs: 2000,
        terminatePeriodMs: 2000,
        createCommandId: nextFixtureValue(commandIds, 'cancellation command ID'),
        now: nextFixtureValue(commandTimestamps, 'cancellation command timestamp'),
        environment: isolatedEnvironment.values,
      },
    );
    let sessionState = INITIAL_SESSION_STATE;
    const updates: string[] = [];
    const receivedEvents: SessionEvent[] = [];
    const unsubscribe = supervisor.subscribeToSessionUpdates((update) => {
      sessionState = reduceSessionState(sessionState, update);
      if (update.type === 'event.received') {
        receivedEvents.push(update.event);
      }
      updates.push(
        update.type === 'event.received'
          ? `${update.event.type}:${update.event.sequence}`
          : update.type,
      );
    });

    try {
      await withTimeout(supervisor.start(), 5000, 'runtime did not become ready for cancellation');

      expect(supervisor.submitTask(cancelStartCommand.payload.task)).toBe(
        cancelStartCommand.command_id,
      );
      await waitForCondition(
        () => sessionState.status === 'running',
        3000,
        'first session never became addressable',
      );
      expect(sessionState.turns.at(-1)?.assistantText).toBe('');
      expect(supervisor.cancelSession()).toBe(true);
      expect(supervisor.cancelSession()).toBe(false);
      await waitForCondition(
        () => sessionState.status === 'cancelled',
        3000,
        'first session did not acknowledge cancellation',
      );
      expect(sessionState.turns[0]).toMatchObject({
        commandId: cancelStartCommand.command_id,
        cancelCommandId: cancelCommand.command_id,
        task: cancelStartCommand.payload.task,
        sessionId: cancelCommand.payload.session_id,
        status: 'cancelled',
        assistantText: '',
        lastSequence: 2,
      });
      expect(normalizeEventTimestamps(receivedEvents, cancellationScenarioEvents)).toEqual(
        cancellationScenarioEvents,
      );
      const firstTerminalUpdates = [...updates];
      await delay(POST_CANCELLATION_OBSERVATION_MS);
      expect(updates).toEqual(firstTerminalUpdates);
      expect(sessionState.status).toBe('cancelled');
      expect(supervisor.getState().status).toBe('running');

      supervisor.submitTask('Cancel between deltas.');
      await waitForCondition(
        () =>
          sessionState.status === 'running' &&
          sessionState.turns.length === 2 &&
          sessionState.turns[1]?.assistantText === 'Mock response: ',
        3000,
        'second session did not expose its first delta',
      );
      expect(supervisor.cancelSession()).toBe(true);
      await waitForCondition(
        () => sessionState.status === 'cancelled',
        3000,
        'second session did not acknowledge cancellation',
      );
      expect(sessionState.turns[1]).toMatchObject({
        status: 'cancelled',
        assistantText: 'Mock response: ',
        lastSequence: 3,
      });
      const secondTerminalUpdates = [...updates];
      await delay(POST_CANCELLATION_OBSERVATION_MS);
      expect(updates).toEqual(secondTerminalUpdates);
      expect(sessionState.status).toBe('cancelled');
      expect(supervisor.getState().status).toBe('running');
      expect(updates.filter((update) => update.startsWith('session.cancelled'))).toEqual([
        'session.cancelled:2',
        'session.cancelled:3',
      ]);
      expect(sessionState.status).not.toBe('protocol-failed');
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      unsubscribe();
      await supervisor.stop();
      rmSync(workspace, {recursive: true, force: true});
      rmSync(isolatedEnvironment.directory, {recursive: true, force: true});
    }

    expect(supervisor.getState().status).toBe('stopped');
  }, 15_000);

  it('stops and reaps genuine uv and Python processes during active session work', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-active-stop-workspace-'));
    const isolatedEnvironment = createIsolatedRuntimeEnvironment();
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
      {repositoryRoot, workspace, transcriptEnabled: false},
      {
        spawnProcess,
        gracePeriodMs: 2500,
        terminatePeriodMs: 2000,
        environment: isolatedEnvironment.values,
      },
    );
    let sessionState = INITIAL_SESSION_STATE;
    const unsubscribe = supervisor.subscribeToSessionUpdates((update) => {
      sessionState = reduceSessionState(sessionState, update);
    });

    try {
      await withTimeout(supervisor.start(), 5000, 'runtime did not become ready for active stop');
      expect(uvPid).toBeDefined();
      if (uvPid === undefined) {
        throw new Error('uv spawned without a process ID.');
      }
      pythonPid = await findRuntimeProcess(uvPid);

      supervisor.submitTask('Remain active while the application exits.');
      await waitForCondition(
        () => sessionState.status === 'running',
        3000,
        'session never became active before stop',
      );
      expect(sessionState.turns.at(-1)).toMatchObject({
        status: 'running',
        assistantCompleted: false,
      });

      const stopping = supervisor.stop();
      expect(supervisor.getState().status).toBe('stopping');
      await withTimeout(stopping, 6000, 'active runtime cleanup did not finish');

      expect(supervisor.getState().status).toBe('stopped');
      expect(existsSync(`/proc/${uvPid}`)).toBe(false);
      expect(existsSync(`/proc/${pythonPid}`)).toBe(false);
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      unsubscribe();
      if (supervisor.getState().status !== 'stopped') {
        await supervisor.stop();
      }
      rmSync(workspace, {recursive: true, force: true});
      rmSync(isolatedEnvironment.directory, {recursive: true, force: true});
    }
  }, 12_000);

  it('renders every genuine mocked delta before completion and accepts a second task', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-render-workspace-'));
    const isolatedEnvironment = createIsolatedRuntimeEnvironment();
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace, transcriptEnabled: false},
      {
        gracePeriodMs: 2000,
        terminatePeriodMs: 2000,
        environment: isolatedEnvironment.values,
      },
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
        7000,
        'first rendered session did not complete',
      );
      const semanticFrames = frames.map(semanticTerminalText);

      const firstDelta = semanticFrames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          !frame.includes('the task crossed the process boundary') &&
          frame.includes('Session status: running'),
      );
      const secondDelta = semanticFrames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          frame.includes('the task crossed the process boundary') &&
          !frame.includes('successfully.') &&
          frame.includes('Session status: running'),
      );
      const thirdDelta = semanticFrames.findIndex(
        (frame) =>
          frame.includes('Mock response:') &&
          frame.includes('the task crossed the process boundary') &&
          frame.includes('streamed') &&
          frame.includes('successfully.') &&
          frame.includes('Session status: running'),
      );
      const firstCompletion = semanticFrames.findIndex(
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
            (frame) => {
              const semanticFrame = semanticTerminalText(frame);
              return (
                semanticFrame.includes('Prove the rendered boundary again.') &&
                (semanticFrame.match(/Mock response:/gu)?.length ?? 0) === 2 &&
                semanticFrame.includes('Session status: completed')
              );
            },
          ),
        7000,
        'second rendered session did not complete',
      );
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      requestExit();
      try {
        await running;
      } finally {
        rmSync(workspace, {recursive: true, force: true});
        rmSync(isolatedEnvironment.directory, {recursive: true, force: true});
      }
    }

    expect(supervisor.getState().status).toBe('stopped');
  }, 15_000);
});

function semanticTerminalText(frame: string): string {
  // Responsive Ink panels may wrap one sentence between vertical border cells. Boundary evidence
  // compares the visible text and its frame order rather than treating layout glyphs as content.
  return frame.replace(/[|\u2500-\u257f]/gu, ' ').replace(/\s+/gu, ' ').trim();
}

function readScenarioFixture<T>(filename: string): readonly T[] {
  const contents = readFileSync(new URL(filename, scenarioFixtureRoot), 'utf8');
  return contents
    .trimEnd()
    .split('\n')
    .map((line) => JSON.parse(line) as T);
}

function nextFixtureValue(values: string[], label: string): () => string {
  return () => {
    const value = values.shift();
    if (value === undefined) {
      throw new Error(`real-boundary test exhausted its ${label} values`);
    }
    return value;
  };
}

function normalizeEventTimestamps(
  events: readonly SessionEvent[],
  expectedEvents: readonly SessionEvent[],
): readonly SessionEvent[] {
  return events.map((event, index) => {
    const expected = expectedEvents[index];
    if (expected === undefined) {
      throw new Error('real boundary emitted more session events than its teaching fixture');
    }
    return {...event, timestamp: expected.timestamp};
  });
}

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
