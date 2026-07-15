import {render} from 'ink';
import type {ReactElement} from 'react';

import {App} from './app.js';

/** Minimal Ink instance contract needed by the application lifecycle. */
export interface RunningApplication {
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

/**
 * Mount the terminal shell and wait for Ink to complete its exit lifecycle.
 *
 * @param renderApplication - Renderer used to mount the root component.
 */
export async function runApplication(
  renderApplication: ApplicationRenderer = render,
): Promise<void> {
  const application = renderApplication(<App />, {exitOnCtrlC: true});
  await application.waitUntilExit();
}
