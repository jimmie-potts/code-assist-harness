/** Exact Node.js release selected for local development in `.node-version`. */
export const PINNED_NODE_VERSION = '22.22.1';

/** Node.js versions supported by the TUI and declared in `package.json`. */
export const SUPPORTED_NODE_RANGE = '>=22.13.0 <23';

const SUPPORTED_MAJOR = 22;
const MINIMUM_MINOR = 13;
const VERSION_PATTERN = /^(\d+)\.(\d+)\.(\d+)$/u;

function startupMessage(version: string | undefined): string {
  const detectedVersion = version === undefined || version.length === 0 ? 'not detected' : version;

  return [
    `Code Assist Harness cannot start with Node.js ${detectedVersion}.`,
    `Required: Node.js ${SUPPORTED_NODE_RANGE} (pinned: ${PINNED_NODE_VERSION}).`,
    'Install or select the pinned version inside Ubuntu WSL, run `npm --prefix tui ci`,',
    'then retry `./scripts/run-tui`.',
  ].join('\n');
}

/**
 * Reject a missing, malformed, or unsupported Node.js version.
 *
 * This function has no renderer imports so callers can run it before loading Ink. It accepts an
 * explicit value to keep unsupported-runtime tests isolated from the developer's active Node.js
 * installation.
 *
 * @param version - The runtime version, normally `process.versions.node`.
 * @throws Error when the version is absent, malformed, or outside the supported range.
 */
export function assertSupportedNodeVersion(version: string | undefined): asserts version is string {
  const match = version?.match(VERSION_PATTERN);

  if (match === undefined || match === null) {
    throw new Error(startupMessage(version));
  }

  const major = Number(match[1]);
  const minor = Number(match[2]);

  if (major !== SUPPORTED_MAJOR || minor < MINIMUM_MINOR) {
    throw new Error(startupMessage(version));
  }
}
