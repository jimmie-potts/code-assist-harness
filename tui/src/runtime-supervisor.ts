import {spawn} from 'node:child_process';
import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {accessSync, constants, realpathSync, statSync} from 'node:fs';
import {delimiter, isAbsolute, join, resolve} from 'node:path';

import {RuntimeDiagnostics} from './runtime-diagnostics.js';

const DEFAULT_GRACE_PERIOD_MS = 1000;
const DEFAULT_TERMINATE_PERIOD_MS = 1000;
const PYTHON_RUNTIME_OVERRIDE_NAMES = new Set(['PYTHONHOME', 'PYTHONPATH']);
const VIRTUAL_ENVIRONMENT_NAME = 'VIRTUAL_ENV';

/**
 * A projection-only description of the Python child lifecycle.
 *
 * Legal transitions are `starting` to `running`, `failed-to-start`, `stopping`, or `stopped`;
 * `running` to `unexpectedly-exited` or `stopping`; `failed-to-start` to `stopping` or `stopped`
 * during owner teardown; `unexpectedly-exited` directly to `stopped`; and `stopping` to `stopped`.
 * `stopped` is terminal. Once stop is requested, a subsequent close is cleanup evidence and can
 * never become `unexpectedly-exited`. These values are local UI state, not protocol wire shapes or
 * evidence of protocol readiness.
 */
export type RuntimeState =
  | {readonly status: 'starting'; readonly workspace: string}
  | {readonly status: 'running'; readonly workspace: string}
  | {readonly status: 'failed-to-start'; readonly workspace: string; readonly message: string}
  | {readonly status: 'unexpectedly-exited'; readonly workspace: string; readonly message: string}
  | {readonly status: 'stopping'; readonly workspace: string}
  | {readonly status: 'stopped'; readonly workspace: string};

/** Shell-free request whose command is canonicalized by preflight before Python is spawned. */
export interface RuntimeLaunchRequest {
  readonly command: string;
  readonly arguments: readonly string[];
  readonly options: {
    readonly cwd: string;
    readonly shell: false;
    readonly stdio: readonly ['pipe', 'pipe', 'pipe'];
    readonly detached: true;
    /** Parent environment snapshot without Python, virtual-environment, or uv selectors. */
    readonly env: NodeJS.ProcessEnv;
  };
}

/** Minimal supervisor contract consumed by the Ink lifecycle owner. */
export interface RuntimeSupervisor {
  /** Return the current immutable child state. */
  getState(): RuntimeState;
  /** Observe state transitions; returns an unsubscribe function. */
  subscribe(listener: (state: RuntimeState) => void): () => void;
  /** Start this supervisor's only child at most once. */
  start(): Promise<void>;
  /** Stop and reap the child; repeated calls share the same cleanup. */
  stop(): Promise<void>;
}

/** Configuration that fixes one supervisor to one repository and one workspace. */
export interface PythonRuntimeSupervisorConfiguration {
  readonly repositoryRoot: string;
  readonly workspace: string;
  readonly command?: string;
}

/** Injectable process and timing seams for deterministic lifecycle tests. */
export interface PythonRuntimeSupervisorDependencies {
  readonly spawnProcess?: (request: RuntimeLaunchRequest) => ChildProcessWithoutNullStreams;
  /** Validate local runtime prerequisites and return the exact request that may be spawned. */
  readonly prepareLaunch?: (request: RuntimeLaunchRequest) => RuntimeLaunchRequest;
  readonly signalProcessGroup?: (
    child: ChildProcessWithoutNullStreams,
    signal: NodeJS.Signals,
  ) => void;
  readonly wait?: (milliseconds: number) => Promise<void>;
  readonly gracePeriodMs?: number;
  readonly terminatePeriodMs?: number;
  /** Parent environment used for deterministic child filtering and diagnostic redaction. */
  readonly environment?: NodeJS.ProcessEnv;
}

/** An actionable local setup failure detected before any child process is spawned. */
export class RuntimeLaunchPreparationError extends Error {
  /** Create a safe failure message suitable for the TUI status region. */
  public constructor(message: string) {
    super(message);
    this.name = 'RuntimeLaunchPreparationError';
  }
}

/**
 * Build the offline uv invocation that {@link prepareRuntimeLaunch} must approve before spawn.
 *
 * The uv project root is the harness repository while the target workspace is a separate explicit
 * Python argument. Python, virtual-environment, and uv selectors are removed from the inherited
 * environment. stdin/stdout/stderr are all pipes; stdout remains opaque until CAH-004.
 */
export function buildRuntimeLaunchRequest(
  repositoryRoot: string,
  workspace: string,
  command = 'uv',
  environment: NodeJS.ProcessEnv = process.env,
): RuntimeLaunchRequest {
  const pythonExecutable = join(repositoryRoot, '.venv', 'bin', 'python');
  return {
    command,
    arguments: [
      'run',
      '--project',
      repositoryRoot,
      '--frozen',
      '--no-cache',
      '--no-sync',
      '--offline',
      '--no-env-file',
      '--no-progress',
      '--no-python-downloads',
      '--python',
      pythonExecutable,
      '--',
      'python',
      '-m',
      'code_assist_harness.runtime',
      '--workspace',
      workspace,
    ],
    options: {
      cwd: repositoryRoot,
      shell: false,
      stdio: ['pipe', 'pipe', 'pipe'],
      detached: true,
      env: buildRuntimeEnvironment(environment),
    },
  };
}

/**
 * Validate the prepared Python environment and resolve uv to one absolute Linux executable.
 *
 * This preflight runs before spawn so a missing project environment cannot cause `uv run` to
 * create `.venv`. Path checks reject raw or symlink-resolved Windows executables without claiming
 * to inspect the executable file format.
 *
 * @param request - Candidate request whose working directory is the harness repository.
 * @returns A copy whose command is the canonical Linux uv executable.
 * @throws RuntimeLaunchPreparationError When uv or the prepared project environment is unusable.
 */
export function prepareRuntimeLaunch(request: RuntimeLaunchRequest): RuntimeLaunchRequest {
  const command = resolveUvExecutable(
    request.command,
    request.options.cwd,
    request.options.env,
  );
  assertPreparedPythonEnvironment(request.options.cwd);
  return {...request, command};
}

/**
 * Own exactly one uv/Python child from spawn through close and bounded shutdown escalation.
 *
 * A successful OS spawn is CAH-003's temporary running boundary; protocol readiness arrives in
 * CAH-004. Any close not requested by {@link stop} is a visible failure, including exit code zero.
 * Normal cleanup closes protocol stdin first, then signals the detached WSL process group only if
 * the child does not close within bounded grace periods.
 */
export class PythonRuntimeSupervisor implements RuntimeSupervisor {
  readonly #request: RuntimeLaunchRequest;
  readonly #spawnProcess: (request: RuntimeLaunchRequest) => ChildProcessWithoutNullStreams;
  readonly #prepareLaunch: (request: RuntimeLaunchRequest) => RuntimeLaunchRequest;
  readonly #signalProcessGroup: (
    child: ChildProcessWithoutNullStreams,
    signal: NodeJS.Signals,
  ) => void;
  readonly #wait: (milliseconds: number) => Promise<void>;
  readonly #gracePeriodMs: number;
  readonly #terminatePeriodMs: number;
  readonly #diagnostics: RuntimeDiagnostics;
  readonly #workspace: string;
  readonly #listeners = new Set<(state: RuntimeState) => void>();
  readonly #closed: Promise<void>;
  #resolveClosed: () => void = () => undefined;
  #state: RuntimeState;
  #child: ChildProcessWithoutNullStreams | undefined;
  #startPromise: Promise<void> | undefined;
  #stopPromise: Promise<void> | undefined;
  #didSpawn = false;
  #didClose = false;
  #stopRequested = false;

  /** Create a supervisor fixed to one canonical workspace. */
  public constructor(
    configuration: PythonRuntimeSupervisorConfiguration,
    dependencies: PythonRuntimeSupervisorDependencies = {},
  ) {
    this.#request = buildRuntimeLaunchRequest(
      configuration.repositoryRoot,
      configuration.workspace,
      configuration.command,
      dependencies.environment,
    );
    this.#spawnProcess = dependencies.spawnProcess ?? spawnRuntimeProcess;
    this.#prepareLaunch = dependencies.prepareLaunch ?? prepareRuntimeLaunch;
    this.#signalProcessGroup = dependencies.signalProcessGroup ?? signalRuntimeProcessGroup;
    this.#wait = dependencies.wait ?? waitFor;
    this.#gracePeriodMs = dependencies.gracePeriodMs ?? DEFAULT_GRACE_PERIOD_MS;
    this.#terminatePeriodMs = dependencies.terminatePeriodMs ?? DEFAULT_TERMINATE_PERIOD_MS;
    this.#diagnostics = new RuntimeDiagnostics(dependencies.environment);
    this.#workspace = configuration.workspace;
    this.#state = {status: 'starting', workspace: configuration.workspace};
    this.#closed = new Promise((resolveClosed) => {
      this.#resolveClosed = resolveClosed;
    });
  }

  /** Return the current immutable child state. */
  public getState(): RuntimeState {
    return this.#state;
  }

  /** Observe future state transitions. */
  public subscribe(listener: (state: RuntimeState) => void): () => void {
    this.#listeners.add(listener);
    return () => {
      this.#listeners.delete(listener);
    };
  }

  /** Start this supervisor's single child and settle after spawn success or startup failure. */
  public start(): Promise<void> {
    if (this.#startPromise !== undefined) {
      return this.#startPromise;
    }

    if (this.#stopRequested) {
      this.#transition({status: 'stopped', workspace: this.#requestWorkspace()});
      this.#startPromise = Promise.resolve();
      return this.#startPromise;
    }

    this.#startPromise = new Promise((resolveStart) => {
      let startSettled = false;
      const settleStart = (): void => {
        if (!startSettled) {
          startSettled = true;
          resolveStart();
        }
      };

      let child: ChildProcessWithoutNullStreams;
      try {
        child = this.#spawnProcess(this.#prepareLaunch(this.#request));
      } catch (error: unknown) {
        this.#transitionToStartupFailure(error);
        this.#markClosed();
        settleStart();
        return;
      }

      this.#child = child;
      child.stdout.resume();
      child.stderr.on('data', (chunk: Buffer | string) => {
        this.#diagnostics.append(chunk);
      });
      child.once('spawn', () => {
        this.#didSpawn = true;
        if (!this.#stopRequested) {
          this.#transition({status: 'running', workspace: this.#requestWorkspace()});
        }
        settleStart();
      });
      child.once('error', (error: Error) => {
        if (!this.#didSpawn && !this.#stopRequested) {
          this.#transitionToStartupFailure(error);
        }
        settleStart();
      });
      child.once('close', (code: number | null, signal: NodeJS.Signals | null) => {
        this.#markClosed();
        if (!this.#stopRequested) {
          if (this.#didSpawn) {
            this.#transition({
              status: 'unexpectedly-exited',
              workspace: this.#requestWorkspace(),
              message: this.#unexpectedExitMessage(code, signal),
            });
          } else if (this.#state.status === 'starting') {
            this.#transitionToStartupFailure(undefined);
          }
        }
        settleStart();
      });
    });

    return this.#startPromise;
  }

  /** Close stdin, escalate to process-group signals when needed, and await the close event. */
  public stop(): Promise<void> {
    if (this.#stopPromise !== undefined) {
      return this.#stopPromise;
    }

    this.#stopRequested = true;
    this.#stopPromise = this.#stopAndReap();
    return this.#stopPromise;
  }

  async #stopAndReap(): Promise<void> {
    const workspace = this.#requestWorkspace();
    if (this.#child === undefined || this.#didClose) {
      this.#markClosed();
      this.#transition({status: 'stopped', workspace});
      return;
    }

    this.#transition({status: 'stopping', workspace});
    this.#child.stdin.end();

    if (!(await this.#closesWithin(this.#gracePeriodMs))) {
      this.#signalProcessGroup(this.#child, 'SIGTERM');
    }
    if (!(await this.#closesWithin(this.#terminatePeriodMs))) {
      this.#signalProcessGroup(this.#child, 'SIGKILL');
    }

    await this.#closed;
    this.#transition({status: 'stopped', workspace});
  }

  async #closesWithin(milliseconds: number): Promise<boolean> {
    if (this.#didClose) {
      return true;
    }
    await Promise.race([this.#closed, this.#wait(milliseconds)]);
    return this.#didClose;
  }

  #transitionToStartupFailure(error: unknown): void {
    if (error instanceof RuntimeLaunchPreparationError) {
      this.#transition({
        status: 'failed-to-start',
        workspace: this.#requestWorkspace(),
        message: error.message,
      });
      return;
    }
    const code = processErrorCode(error);
    const message =
      code === 'ENOENT'
        ? 'Python runtime could not start because uv was not found. Install uv, run "uv sync --dev", and retry.'
        : `Python runtime could not start${code === undefined ? '' : ` (${code})`}. Run "uv sync --dev" and retry.`;
    this.#transition({status: 'failed-to-start', workspace: this.#requestWorkspace(), message});
  }

  #unexpectedExitMessage(code: number | null, signal: NodeJS.Signals | null): string {
    const outcome =
      signal === null
        ? `exit code ${code === null ? 'unknown' : String(code)}`
        : `signal ${signal}`;
    const diagnostic = this.#diagnostics.summary();
    const context = diagnostic === undefined ? '' : ` Diagnostic: ${diagnostic}`;
    return `Python runtime exited unexpectedly with ${outcome}.${context}`;
  }

  #requestWorkspace(): string {
    return this.#workspace;
  }

  #transition(state: RuntimeState): void {
    this.#state = state;
    for (const listener of this.#listeners) {
      listener(state);
    }
  }

  #markClosed(): void {
    if (!this.#didClose) {
      this.#didClose = true;
      this.#resolveClosed();
    }
  }
}

function spawnRuntimeProcess(request: RuntimeLaunchRequest): ChildProcessWithoutNullStreams {
  return spawn(request.command, [...request.arguments], {
    cwd: request.options.cwd,
    detached: request.options.detached,
    shell: request.options.shell,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: request.options.env,
  });
}

function buildRuntimeEnvironment(environment: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const runtimeEnvironment: NodeJS.ProcessEnv = {};
  for (const [name, value] of Object.entries(environment)) {
    // Python and uv environment selectors can bypass the exact prepared-environment contract.
    const isRuntimeOverride =
      PYTHON_RUNTIME_OVERRIDE_NAMES.has(name) ||
      name === VIRTUAL_ENVIRONMENT_NAME ||
      name.startsWith('UV_');
    if (value !== undefined && !isRuntimeOverride) {
      runtimeEnvironment[name] = value;
    }
  }
  return runtimeEnvironment;
}

function resolveUvExecutable(
  command: string,
  workingDirectory: string,
  environment: NodeJS.ProcessEnv,
): string {
  const hasPathSeparator = command.includes('/') || command.includes('\\');
  if (hasPathSeparator && isWindowsExecutablePath(command)) {
    throw windowsUvError(command);
  }

  const candidates = hasPathSeparator || isAbsolute(command)
    ? [resolve(workingDirectory, command)]
    : (environment.PATH ?? '')
        .split(delimiter)
        .map((entry) => resolve(workingDirectory, entry.length === 0 ? '.' : entry, command));

  for (const candidate of candidates) {
    try {
      accessSync(candidate, constants.X_OK);
      if (!statSync(candidate).isFile()) {
        continue;
      }
    } catch {
      continue;
    }

    if (isWindowsExecutablePath(candidate)) {
      throw windowsUvError(candidate);
    }

    let canonicalPath: string;
    try {
      canonicalPath = realpathSync(candidate);
    } catch {
      continue;
    }
    if (isWindowsExecutablePath(canonicalPath)) {
      throw windowsUvError(canonicalPath);
    }
    return canonicalPath;
  }

  throw new RuntimeLaunchPreparationError(
    'Python runtime could not start because uv was not found inside Ubuntu WSL. Install uv, run "uv sync --dev", and retry.',
  );
}

function assertPreparedPythonEnvironment(repositoryRoot: string): void {
  const environmentRoot = join(repositoryRoot, '.venv');
  const configurationPath = join(environmentRoot, 'pyvenv.cfg');
  const pythonExecutable = join(environmentRoot, 'bin', 'python');

  try {
    accessSync(configurationPath, constants.R_OK);
    if (!statSync(configurationPath).isFile()) {
      throw new Error('pyvenv.cfg is not a file');
    }
    accessSync(pythonExecutable, constants.X_OK);
    if (!statSync(pythonExecutable).isFile()) {
      throw new Error('python is not a file');
    }
  } catch {
    throw new RuntimeLaunchPreparationError(
      `Python runtime could not start because ${JSON.stringify(environmentRoot)} is not prepared. Run "uv sync --dev" in the harness repository and retry.`,
    );
  }

  let canonicalPython: string;
  try {
    canonicalPython = realpathSync(pythonExecutable);
  } catch {
    throw new RuntimeLaunchPreparationError(
      `Python runtime could not resolve the prepared interpreter at ${JSON.stringify(pythonExecutable)}. Run "uv sync --dev" and retry.`,
    );
  }
  if (isWindowsExecutablePath(pythonExecutable) || isWindowsExecutablePath(canonicalPython)) {
    throw new RuntimeLaunchPreparationError(
      `Python runtime found a Windows interpreter at ${JSON.stringify(canonicalPython)}. Recreate .venv with "uv sync --dev" inside Ubuntu WSL and retry.`,
    );
  }
}

function isWindowsExecutablePath(path: string): boolean {
  const normalizedPath = path.replaceAll('\\', '/');
  return (
    normalizedPath.startsWith('/mnt/') ||
    /^[A-Za-z]:\//u.test(normalizedPath) ||
    normalizedPath.toLowerCase().endsWith('.exe')
  );
}

function windowsUvError(path: string): RuntimeLaunchPreparationError {
  return new RuntimeLaunchPreparationError(
    `Python runtime could not start because uv resolved to a Windows executable at ${JSON.stringify(path)}. Install uv inside Ubuntu WSL, run "uv sync --dev", and retry.`,
  );
}

function signalRuntimeProcessGroup(
  child: ChildProcessWithoutNullStreams,
  signal: NodeJS.Signals,
): void {
  if (child.pid === undefined) {
    return;
  }

  // The uv leader may have exited while its Python descendant still owns inherited pipes. The
  // detached process group remains signalable until every member exits, so `close` is the guard.
  try {
    process.kill(-child.pid, signal);
  } catch (error: unknown) {
    const code = processErrorCode(error);
    if (code !== 'ESRCH') {
      throw error;
    }
  }
}

function processErrorCode(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('code' in error)) {
    return undefined;
  }
  return typeof error.code === 'string' ? error.code : undefined;
}

function waitFor(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, milliseconds);
    timer.unref();
  });
}
