import {bootstrapApplication} from './bootstrap.js';

try {
  await bootstrapApplication(process.versions.node, () => import('./run-application.js'));
} catch (error: unknown) {
  const message = error instanceof Error ? error.message : 'The TUI failed to start unexpectedly.';
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
}
