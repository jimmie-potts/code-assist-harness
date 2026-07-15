import {assertSupportedNodeVersion} from './node-version.js';

/** TUI module loaded only after the local Node.js runtime passes validation. */
export interface ApplicationModule {
  /** Render the application and settle after the terminal UI exits. */
  runApplication(): Promise<void>;
}

/** Deferred import seam that keeps Ink out of the pre-render runtime check. */
export type ApplicationLoader = () => Promise<ApplicationModule>;

/**
 * Validate the runtime before loading or rendering the terminal application.
 *
 * @param nodeVersion - The detected Node.js version.
 * @param loadApplication - Dynamic loader for the Ink-owning module.
 */
export async function bootstrapApplication(
  nodeVersion: string | undefined,
  loadApplication: ApplicationLoader,
): Promise<void> {
  assertSupportedNodeVersion(nodeVersion);
  const application = await loadApplication();
  await application.runApplication();
}
