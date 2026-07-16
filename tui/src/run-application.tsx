import {render} from 'ink';
import type {ReactElement} from 'react';

import {App} from './app.js';
import type {RuntimeSupervisor} from './runtime-supervisor.js';

/** Minimal Ink instance contract needed by the application lifecycle. */
export interface RunningApplication {
  /** Replace the rendered projection after a supervised runtime transition. */
  rerender(tree: ReactElement): void;
  /** Unmount Ink so a process termination signal can enter the shared cleanup path. */
  unmount(): void;
  /** Settle when Ink has unmounted and restored terminal state. */
  waitUntilExit(): Promise<unknown>;
}

/** Render options that make Ctrl+C an Ink-owned clean exit. */
export interface ApplicationRenderOptions {
  /** Ask Ink to intercept Ctrl+C and unmount its terminal tree. */
  readonly exitOnCtrlC: true;
}

/** Injectable rendering seam used to verify lifecycle configuration without a physical TTY. */
export type ApplicationRenderer = (
  tree: ReactElement,
  options: ApplicationRenderOptions,
) => RunningApplication;

/** Process signals that request normal TUI-owned child cleanup. */
export type ApplicationTerminationSignal = 'SIGHUP' | 'SIGTERM';

/**
 * Register one termination listener and return an unsubscribe function.
 *
 * The production subscriber preserves conventional signal exit codes while routing SIGHUP and
 * SIGTERM through Ink unmount and the supervisor's asynchronous `finally` cleanup.
 */
export type ApplicationTerminationSubscriber = (
  listener: (signal: ApplicationTerminationSignal) => void,
) => () => void;

/**
 * Mount the terminal shell, supervise Python, and clean it up after every Ink exit path.
 *
 * @param supervisor - Lifecycle owner for the one Python child and workspace.
 * @param renderApplication - Renderer used to mount the root component.
 * @param subscribeToTermination - Process-signal seam used to request an Ink exit.
 */
export async function runApplication(
  supervisor: RuntimeSupervisor,
  renderApplication: ApplicationRenderer = render,
  subscribeToTermination: ApplicationTerminationSubscriber = subscribeToProcessTermination,
): Promise<void> {
  let unsubscribe = (): void => undefined;
  let unsubscribeFromTermination = (): void => undefined;

  try {
    const application = renderApplication(<App runtimeState={supervisor.getState()} />, {
      exitOnCtrlC: true,
    });
    unsubscribeFromTermination = subscribeToTermination(() => {
      application.unmount();
    });
    unsubscribe = supervisor.subscribe((runtimeState) => {
      application.rerender(<App runtimeState={runtimeState} />);
    });
    const startup = supervisor.start().then(() => 'started' as const);
    const inkExit = application.waitUntilExit().then(() => 'exited' as const);
    const firstTransition = await Promise.race([startup, inkExit]);
    if (firstTransition === 'started') {
      await inkExit;
    }
  } finally {
    unsubscribe();
    try {
      await supervisor.stop();
    } finally {
      unsubscribeFromTermination();
    }
  }
}

function subscribeToProcessTermination(
  listener: (signal: ApplicationTerminationSignal) => void,
): () => void {
  let handled = false;
  const handle = (signal: ApplicationTerminationSignal): void => {
    if (handled) {
      return;
    }
    handled = true;
    process.exitCode = signal === 'SIGTERM' ? 143 : 129;
    listener(signal);
  };
  const handleHangup = (): void => handle('SIGHUP');
  const handleTermination = (): void => handle('SIGTERM');

  process.on('SIGHUP', handleHangup);
  process.on('SIGTERM', handleTermination);
  return () => {
    process.removeListener('SIGHUP', handleHangup);
    process.removeListener('SIGTERM', handleTermination);
  };
}
