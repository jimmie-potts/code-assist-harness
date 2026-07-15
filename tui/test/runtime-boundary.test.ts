import {spawn} from 'node:child_process';
import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {
  existsSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  realpathSync,
  rmSync,
} from 'node:fs';
import {tmpdir} from 'node:os';
import {basename, join} from 'node:path';
import {fileURLToPath} from 'node:url';

import {describe, expect, it} from 'vitest';

import {
  PythonRuntimeSupervisor,
  type RuntimeLaunchRequest,
} from '../src/runtime-supervisor.js';

const repositoryRoot = realpathSync(fileURLToPath(new URL('../../', import.meta.url)));

describe('real Node to uv to Python boundary', () => {
  it('starts the runtime, observes the Python descendant, and reaps the process group', async () => {
    const workspace = mkdtempSync(join(tmpdir(), 'cah-real-runtime-workspace-'));
    let uvPid: number | undefined;
    let pythonPid: number | undefined;

    const spawnProcess = (request: RuntimeLaunchRequest): ChildProcessWithoutNullStreams => {
      const child = spawn(request.command, [...request.arguments], {
        cwd: request.options.cwd,
        detached: request.options.detached,
        shell: request.options.shell,
        stdio: ['pipe', 'pipe', 'pipe'],
      });
      uvPid = child.pid;
      return child;
    };
    const supervisor = new PythonRuntimeSupervisor(
      {repositoryRoot, workspace},
      {spawnProcess, gracePeriodMs: 2000, terminatePeriodMs: 2000},
    );

    try {
      await withTimeout(supervisor.start(), 5000, 'uv did not spawn');
      expect(supervisor.getState().status).toBe('running');
      expect(uvPid).toBeDefined();
      if (uvPid === undefined) {
        throw new Error('uv spawned without a process ID.');
      }

      pythonPid = await findRuntimeProcess(uvPid);
      expect(readCommandLine(pythonPid)).toContain('code_assist_harness.runtime');
      expect(readExecutableName(pythonPid)).toMatch(/^python(?:\d+(?:\.\d+)*)?$/u);

      await withTimeout(supervisor.stop(), 5000, 'runtime cleanup did not finish');

      expect(supervisor.getState().status).toBe('stopped');
      expect(existsSync(`/proc/${uvPid}`)).toBe(false);
      expect(existsSync(`/proc/${pythonPid}`)).toBe(false);
      expect(readdirSync(workspace)).toEqual([]);
    } finally {
      if (supervisor.getState().status !== 'stopped') {
        await supervisor.stop();
      }
      rmSync(workspace, {recursive: true, force: true});
    }
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
