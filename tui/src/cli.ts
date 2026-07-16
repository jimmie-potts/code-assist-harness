import {realpathSync} from 'node:fs';
import {fileURLToPath} from 'node:url';

import {bootstrapApplication} from './bootstrap.js';
import type {ApplicationModule} from './bootstrap.js';

const repositoryRoot = realpathSync(fileURLToPath(new URL('../../', import.meta.url)));

async function loadApplication(): Promise<ApplicationModule> {
  const [{runApplication}, {PythonRuntimeSupervisor}, {resolveWorkspace}] = await Promise.all([
    import('./run-application.js'),
    import('./runtime-supervisor.js'),
    import('./workspace.js'),
  ]);
  const launchDirectory =
    process.env.CODE_ASSIST_LAUNCH_DIRECTORY ?? process.env.INIT_CWD ?? process.cwd();
  const workspace = resolveWorkspace(process.argv.slice(2), launchDirectory);
  const supervisor = new PythonRuntimeSupervisor({
    repositoryRoot,
    workspace: workspace.path,
  });

  return {
    runApplication: () => runApplication(supervisor),
  };
}

try {
  await bootstrapApplication(process.versions.node, loadApplication);
} catch (error: unknown) {
  const message = error instanceof Error ? error.message : 'The TUI failed to start unexpectedly.';
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}
