import {spawn} from 'node:child_process';
import type {ChildProcessWithoutNullStreams} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {accessSync, constants, realpathSync, statSync} from 'node:fs';
import {delimiter, isAbsolute, join, resolve} from 'node:path';

import {
  encodeCommandLine,
  MAX_PROTOCOL_LINE_BYTES,
  parseEventLine,
  ProtocolEncodingError,
  PROTOCOL_VERSION,
  type ProtocolEvent,
  type ProtocolParseErrorCode,
} from './protocol.js';
import {
  NdjsonLineReader,
  type ProtocolLineErrorCode,
  type ProtocolLineResult,
} from './protocol-stream.js';
import {RuntimeDiagnostics} from './runtime-diagnostics.js';
import {
  INITIAL_SESSION_LIFECYCLE_STATE,
  isActiveSessionStatus,
  isCancellableSessionStatus,
  isTerminalSessionStatus,
  reduceSessionLifecycle,
  type SessionLifecycleState,
} from './session-lifecycle.js';
import {
  formatSessionInvariantFailure,
  type SessionEvent,
  type SessionUpdate,
} from './session-state.js';

const DEFAULT_GRACE_PERIOD_MS = 1000;
const DEFAULT_TERMINATE_PERIOD_MS = 1000;
const DEFAULT_READINESS_TIMEOUT_MS = 5000;
const PYTHON_RUNTIME_OVERRIDE_NAMES = new Set(['PYTHONHOME', 'PYTHONPATH']);
const VIRTUAL_ENVIRONMENT_NAME = 'VIRTUAL_ENV';

/**
 * A projection-only description of the Python child lifecycle.
 *
 * `starting` becomes `running` only after a validated, correlated `runtime.ready`. A malformed,
 * unknown, unexpected, or mismatched stdout event moves either active state to `protocol-failed`
 * and closes command input rather than admitting untrusted state. Startup rejection becomes
 * `failed-to-start`; an unrequested process close becomes `unexpectedly-exited`. Requested cleanup
 * moves any nonterminal state through `stopping` to terminal `stopped`. These values are local UI
 * state, not wire shapes.
 */
export type RuntimeState =
  | {readonly status: 'starting'; readonly workspace: string}
  | {readonly status: 'running'; readonly workspace: string}
  | {readonly status: 'failed-to-start'; readonly workspace: string; readonly message: string}
  | {
      readonly status: 'protocol-failed';
      readonly workspace: string;
      readonly code: RuntimeProtocolFailureCode;
      readonly message: string;
    }
  | {readonly status: 'unexpectedly-exited'; readonly workspace: string; readonly message: string}
  | {readonly status: 'stopping'; readonly workspace: string}
  | {readonly status: 'stopped'; readonly workspace: string};

/** Safe failure categories exposed by the local runtime lifecycle projection. */
export type RuntimeProtocolFailureCode =
  | ProtocolParseErrorCode
  | ProtocolLineErrorCode
  | 'unexpected_event'
  | 'command_write_failed'
  | 'readiness_mismatch'
  | 'readiness_timeout';

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
  /** Observe accepted local submissions and validated session events in projection order. */
  subscribeToSessionUpdates(listener: (update: SessionUpdate) => void): () => void;
  /** Validate and send one task while the runtime is ready and no session is active. */
  submitTask(task: string): string;
  /** Request cancellation once for the addressable active session. */
  cancelSession(): boolean;
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
  readonly readinessTimeoutMs?: number;
  /** Create one unique, already-valid protocol command ID. */
  readonly createCommandId?: () => string;
  /** Return an exact protocol timestamp, normally `Date.prototype.toISOString()`. */
  readonly now?: () => string;
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

/** A safe local rejection raised before an invalid task can reach the protocol stream. */
export class SessionSubmissionError extends Error {
  /** Create an understandable submission failure suitable for the input region. */
  public constructor(message: string) {
    super(message);
    this.name = 'SessionSubmissionError';
  }
}

/**
 * Build the offline uv invocation that {@link prepareRuntimeLaunch} must approve before spawn.
 *
 * The uv project root is the harness repository while the target workspace is a separate explicit
 * Python argument. Python, virtual-environment, and uv selectors are removed from the inherited
 * environment. stdin/stdout/stderr are all pipes; CAH-004 validates stdout as protocol events
 * before any child output can enter trusted lifecycle state.
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
 * OS spawn establishes only a writable physical process. The supervisor sends one validated
 * `runtime.initialize` command and enters `running` only after the child returns the matching
 * `runtime.ready` event for this supervisor's canonical workspace. Unknown or invalid stdout fails
 * closed. Normal cleanup sends a validated `runtime.shutdown`, closes stdin, and then signals the
 * detached WSL process group only if bounded grace periods expire.
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
  readonly #readinessTimeoutMs: number;
  readonly #createCommandId: () => string;
  readonly #now: () => string;
  readonly #diagnostics: RuntimeDiagnostics;
  readonly #eventReader = new NdjsonLineReader(MAX_PROTOCOL_LINE_BYTES);
  readonly #workspace: string;
  readonly #listeners = new Set<(state: RuntimeState) => void>();
  readonly #sessionListeners = new Set<(update: SessionUpdate) => void>();
  readonly #closed: Promise<void>;
  #resolveClosed: () => void = () => undefined;
  #state: RuntimeState;
  #child: ChildProcessWithoutNullStreams | undefined;
  #startPromise: Promise<void> | undefined;
  #stopPromise: Promise<void> | undefined;
  #resolveStart: () => void = () => undefined;
  #startSettled = false;
  #didSpawn = false;
  #didClose = false;
  #stopRequested = false;
  #failureShutdownRequested = false;
  #initializationCommandId: string | undefined;
  #readinessTimer: NodeJS.Timeout | undefined;
  #sessionValidationState: SessionLifecycleState = INITIAL_SESSION_LIFECYCLE_STATE;

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
    this.#readinessTimeoutMs = dependencies.readinessTimeoutMs ?? DEFAULT_READINESS_TIMEOUT_MS;
    this.#createCommandId = dependencies.createCommandId ?? createCommandId;
    this.#now = dependencies.now ?? currentTimestamp;
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

  /** Observe accepted submissions and session events after local semantic validation. */
  public subscribeToSessionUpdates(listener: (update: SessionUpdate) => void): () => void {
    this.#sessionListeners.add(listener);
    return () => {
      this.#sessionListeners.delete(listener);
    };
  }

  /**
   * Send one `session.start` command and synchronously announce its local projection update.
   *
   * Whitespace-only input, an unavailable runtime, concurrent work, and commands that cannot fit
   * the wire contract are rejected before local state changes or bytes are written. After the exact
   * command line is validated, the local update is published before the asynchronous write so a
   * very fast child can never deliver `session.started` before the projection knows the cause.
   *
   * @param task - Exact user task; surrounding whitespace is preserved when non-empty.
   * @returns The unique command ID written in the protocol envelope.
   * @throws SessionSubmissionError When the runtime cannot legally accept a new task.
   */
  public submitTask(task: string): string {
    if (task.trim().length === 0) {
      throw new SessionSubmissionError('Enter a non-empty task before submitting.');
    }
    if (this.#state.status !== 'running') {
      throw new SessionSubmissionError('Wait for the Python runtime to become ready.');
    }
    if (isActiveSessionStatus(this.#sessionValidationState.status)) {
      throw new SessionSubmissionError('Wait for the active session to finish.');
    }

    const commandId = this.#createCommandId();
    const command = {
      protocol_version: PROTOCOL_VERSION,
      type: 'session.start',
      command_id: commandId,
      timestamp: this.#now(),
      payload: {task},
    } as const;
    let commandLine: string;
    try {
      commandLine = encodeCommandLine(command);
    } catch (error) {
      if (error instanceof ProtocolEncodingError) {
        throw new SessionSubmissionError(
          error.code === 'line_too_long'
            ? 'The task is too large to submit.'
            : 'The task could not be encoded for the Python runtime.',
        );
      }
      throw error;
    }

    const update: SessionUpdate = {type: 'task.submitted', commandId, task};
    // The supervisor validates only the active tape; conversation history remains solely in the
    // application projection that consumes the published updates.
    const validationState = isTerminalSessionStatus(this.#sessionValidationState.status)
      ? INITIAL_SESSION_LIFECYCLE_STATE
        : this.#sessionValidationState;
    const result = reduceSessionLifecycle(validationState, update);
    if (!result.ok) {
      throw new SessionSubmissionError('The task could not enter a valid local session state.');
    }
    this.#sessionValidationState = result.state;
    this.#publishSessionUpdate(update);

    void this.#writeEncodedCommandLine(commandLine).catch(() => {
      this.#transitionToProtocolFailure(
        'command_write_failed',
        'The task could not be written to the Python runtime.',
      );
    });
    return commandId;
  }

  /**
   * Request cancellation for the active Python-owned session at most once.
   *
   * Cancellation is addressable only after `session.started` supplies a session ID. The validated
   * local request is published before its asynchronous write so a fast `session.cancelled` cannot
   * outrun the projection. Repeated requests, startup races, and requests after a terminal event
   * are harmless local no-ops. Python remains authoritative for whether cancellation or completion
   * wins and emits the only terminal event.
   *
   * @returns `true` when one command was accepted for writing, otherwise `false`.
   */
  public cancelSession(): boolean {
    if (
      this.#state.status !== 'running' ||
      !isCancellableSessionStatus(this.#sessionValidationState.status)
    ) {
      return false;
    }
    const sessionId = this.#sessionValidationState.sessionId;
    if (sessionId === null) {
      return false;
    }

    const commandId = this.#createCommandId();
    let commandLine: string;
    try {
      commandLine = encodeCommandLine({
        protocol_version: PROTOCOL_VERSION,
        type: 'session.cancel',
        command_id: commandId,
        timestamp: this.#now(),
        payload: {session_id: sessionId},
      });
    } catch {
      this.#transitionToProtocolFailure(
        'command_write_failed',
        'The cancellation request could not be encoded for the Python runtime.',
      );
      return false;
    }

    const update: SessionUpdate = {
      type: 'cancel.requested',
      commandId,
      sessionId,
    };
    const result = reduceSessionLifecycle(this.#sessionValidationState, update);
    if (!result.ok) {
      this.#transitionToProtocolFailure(
        'unexpected_event',
        formatSessionInvariantFailure(result.failure),
      );
      return false;
    }
    this.#sessionValidationState = result.state;
    this.#publishSessionUpdate(update);

    void this.#writeEncodedCommandLine(commandLine).catch(() => {
      this.#transitionToProtocolFailure(
        'command_write_failed',
        'The cancellation request could not be written to the Python runtime.',
      );
    });
    return true;
  }

  /** Start this supervisor's single child and settle after protocol readiness or startup failure. */
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
      this.#resolveStart = resolveStart;
      let child: ChildProcessWithoutNullStreams;
      try {
        child = this.#spawnProcess(this.#prepareLaunch(this.#request));
      } catch (error: unknown) {
        this.#transitionToStartupFailure(error);
        this.#markClosed();
        this.#settleStart();
        return;
      }

      this.#child = child;
      child.stdout.on('data', (chunk: Buffer | string) => {
        this.#acceptStdoutChunk(chunk);
      });
      child.stdout.once('end', () => {
        this.#acceptLineResults(this.#eventReader.finish());
      });
      child.stderr.on('data', (chunk: Buffer | string) => {
        this.#diagnostics.append(chunk);
      });
      child.once('spawn', () => {
        this.#didSpawn = true;
        if (this.#stopRequested) {
          this.#settleStart();
          return;
        }
        void this.#beginProtocolInitialization();
      });
      child.once('error', (error: Error) => {
        if (!this.#didSpawn && !this.#stopRequested) {
          this.#transitionToStartupFailure(error);
        }
        this.#settleStart();
      });
      child.once('close', (code: number | null, signal: NodeJS.Signals | null) => {
        this.#clearReadinessTimer();
        this.#markClosed();
        if (!this.#stopRequested && !this.#failureShutdownRequested) {
          if (this.#didSpawn && this.#state.status === 'starting') {
            this.#transition({
              status: 'failed-to-start',
              workspace: this.#requestWorkspace(),
              message: this.#unexpectedExitMessage(code, signal),
            });
          } else if (this.#didSpawn) {
            this.#transition({
              status: 'unexpectedly-exited',
              workspace: this.#requestWorkspace(),
              message: this.#unexpectedExitMessage(code, signal),
            });
          } else if (this.#state.status === 'starting') {
            this.#transitionToStartupFailure(undefined);
          }
        }
        this.#settleStart();
      });
    });

    return this.#startPromise;
  }

  /** Send shutdown, close stdin, escalate when needed, and await the close event. */
  public stop(): Promise<void> {
    if (this.#stopPromise !== undefined) {
      return this.#stopPromise;
    }

    this.#stopRequested = true;
    this.#clearReadinessTimer();
    this.#settleStart();
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
    // Node queues `end` after the preceding write, preserving protocol-first ordering without
    // allowing a missing write callback or a backpressured pipe to delay signal escalation.
    void this.#sendShutdownCommand();
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

  async #beginProtocolInitialization(): Promise<void> {
    if (this.#stopRequested || this.#failureShutdownRequested) {
      return;
    }
    const commandId = this.#createCommandId();
    this.#initializationCommandId = commandId;
    this.#readinessTimer = setTimeout(() => {
      this.#transitionToProtocolFailure(
        'readiness_timeout',
        'Python runtime did not send runtime.ready before the startup deadline.',
      );
    }, this.#readinessTimeoutMs);
    this.#readinessTimer.unref();
    try {
      await this.#writeCommand({
        protocol_version: PROTOCOL_VERSION,
        type: 'runtime.initialize',
        command_id: commandId,
        timestamp: this.#now(),
        payload: {workspace: this.#requestWorkspace()},
      });
    } catch (error: unknown) {
      if (!this.#stopRequested && !this.#failureShutdownRequested) {
        this.#clearReadinessTimer();
        this.#transitionToStartupFailure(error);
        this.#requestFailureShutdown();
        this.#settleStart();
      }
      return;
    }

    if (
      this.#stopRequested ||
      this.#failureShutdownRequested ||
      this.#state.status !== 'starting'
    ) {
      return;
    }
  }

  async #sendShutdownCommand(): Promise<void> {
    const child = this.#child;
    if (child === undefined || child.stdin.destroyed || child.stdin.writableEnded) {
      return;
    }
    try {
      await this.#writeCommand({
        protocol_version: PROTOCOL_VERSION,
        type: 'runtime.shutdown',
        command_id: this.#createCommandId(),
        timestamp: this.#now(),
        payload: {},
      });
    } catch {
      // Closing stdin and bounded process-group escalation remain the reliable cleanup fallback.
    }
  }

  async #writeCommand(command: unknown): Promise<void> {
    await this.#writeEncodedCommandLine(encodeCommandLine(command));
  }

  async #writeEncodedCommandLine(line: string): Promise<void> {
    const child = this.#child;
    if (child === undefined || child.stdin.destroyed || child.stdin.writableEnded) {
      throw new Error('Python runtime command input is unavailable.');
    }
    await new Promise<void>((resolveWrite, rejectWrite) => {
      child.stdin.write(line, 'utf8', (error: Error | null | undefined) => {
        if (error === null || error === undefined) {
          resolveWrite();
        } else {
          rejectWrite(error);
        }
      });
    });
  }

  #acceptStdoutChunk(chunk: Buffer | string): void {
    if (this.#stopRequested || this.#failureShutdownRequested) {
      return;
    }
    const bytes = typeof chunk === 'string' ? Buffer.from(chunk, 'utf8') : chunk;
    this.#acceptLineResults(this.#eventReader.push(bytes));
  }

  #acceptLineResults(results: readonly ProtocolLineResult[]): void {
    for (const result of results) {
      if (this.#stopRequested || this.#failureShutdownRequested) {
        return;
      }
      if (!result.ok) {
        this.#transitionToProtocolFailure(result.error.code, result.error.message);
        return;
      }
      const parsed = parseEventLine(result.line);
      if (!parsed.ok) {
        this.#transitionToProtocolFailure(parsed.error.code, parsed.error.message);
        return;
      }
      this.#acceptEvent(parsed.value);
    }
  }

  #acceptEvent(event: ProtocolEvent): void {
    if (this.#state.status === 'running') {
      if (isSessionEvent(event)) {
        this.#acceptSessionEvent(event);
        return;
      }
      const reportedCode = event.type === 'runtime.error' ? event.payload.code : undefined;
      const reportedMessage =
        event.type === 'runtime.error'
          ? (this.#diagnostics.sanitize(event.payload.message) ?? 'No safe details were provided.')
          : undefined;
      const detail =
        event.type === 'runtime.error'
          ? `Python runtime reported ${reportedCode}: ${reportedMessage}`
          : `Python runtime sent unexpected ${event.type} after readiness.`;
      this.#transitionToProtocolFailure('unexpected_event', detail);
      return;
    }
    if (this.#state.status !== 'starting') {
      return;
    }
    if (event.type === 'runtime.error') {
      const correlation = event.correlation_id;
      if (correlation !== this.#initializationCommandId) {
        this.#transitionToProtocolFailure(
          'readiness_mismatch',
          'Python runtime returned an initialization error with the wrong correlation ID.',
        );
        return;
      }
      this.#clearReadinessTimer();
      const reportedCode = event.payload.code;
      const reportedMessage =
        this.#diagnostics.sanitize(event.payload.message) ?? 'No safe details were provided.';
      this.#transition({
        status: 'failed-to-start',
        workspace: this.#requestWorkspace(),
        message: `Python runtime rejected initialization (${reportedCode}): ${reportedMessage}`,
      });
      this.#requestFailureShutdown();
      this.#settleStart();
      return;
    }
    if (event.type !== 'runtime.ready') {
      this.#transitionToProtocolFailure(
        'unexpected_event',
        `Python runtime sent ${event.type} before runtime.ready.`,
      );
      return;
    }
    if (
      event.correlation_id !== this.#initializationCommandId ||
      event.payload.workspace !== this.#requestWorkspace()
    ) {
      this.#transitionToProtocolFailure(
        'readiness_mismatch',
        'Python runtime.ready did not match the initialization command and canonical workspace.',
      );
      return;
    }

    this.#clearReadinessTimer();
    this.#transition({status: 'running', workspace: this.#requestWorkspace()});
    this.#settleStart();
  }

  #acceptSessionEvent(event: SessionEvent): void {
    const update: SessionUpdate = {type: 'event.received', event};
    const result = reduceSessionLifecycle(this.#sessionValidationState, event);
    if (!result.ok) {
      this.#transitionToProtocolFailure(
        'unexpected_event',
        formatSessionInvariantFailure(result.failure),
      );
      return;
    }
    this.#sessionValidationState = result.state;
    this.#publishSessionUpdate(update);
  }

  #transitionToProtocolFailure(code: RuntimeProtocolFailureCode, message: string): void {
    if (this.#stopRequested || this.#failureShutdownRequested) {
      return;
    }
    this.#clearReadinessTimer();
    this.#transition({
      status: 'protocol-failed',
      workspace: this.#requestWorkspace(),
      code,
      message,
    });
    this.#requestFailureShutdown();
    this.#settleStart();
  }

  #requestFailureShutdown(): void {
    this.#failureShutdownRequested = true;
    if (this.#child !== undefined && !this.#child.stdin.destroyed) {
      this.#child.stdin.end();
    }
  }

  #clearReadinessTimer(): void {
    if (this.#readinessTimer !== undefined) {
      clearTimeout(this.#readinessTimer);
      this.#readinessTimer = undefined;
    }
  }

  #settleStart(): void {
    if (!this.#startSettled) {
      this.#startSettled = true;
      this.#resolveStart();
    }
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

  #publishSessionUpdate(update: SessionUpdate): void {
    for (const listener of this.#sessionListeners) {
      listener(update);
    }
  }

  #markClosed(): void {
    if (!this.#didClose) {
      this.#didClose = true;
      this.#resolveClosed();
    }
  }
}

function isSessionEvent(event: ProtocolEvent): event is SessionEvent {
  return (
    event.type === 'session.started' ||
    event.type === 'assistant.delta' ||
    event.type === 'assistant.completed' ||
    event.type === 'session.completed' ||
    event.type === 'session.cancelled' ||
    event.type === 'session.failed'
  );
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

function createCommandId(): string {
  return `cmd_${randomUUID().replaceAll('-', '')}`;
}

function currentTimestamp(): string {
  return new Date().toISOString();
}
