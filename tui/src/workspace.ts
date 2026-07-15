import {realpathSync, statSync} from 'node:fs';
import {resolve} from 'node:path';

/** The one canonical repository workspace assigned to a runtime process. */
export interface WorkspaceSelection {
  /** Canonical, symlink-resolved directory passed to the Python child. */
  readonly path: string;
  /** Whether the workspace came from the launch directory or an explicit CLI option. */
  readonly source: 'launch-directory' | 'command-line';
}

/** An actionable error raised before a child is started with an unusable workspace. */
export class WorkspaceConfigurationError extends Error {
  /** Create a workspace configuration error suitable for the CLI error channel. */
  public constructor(message: string) {
    super(message);
    this.name = 'WorkspaceConfigurationError';
  }
}

/**
 * Resolve the single workspace selected for this TUI process.
 *
 * Relative overrides are interpreted from the directory in which the launcher was invoked, not
 * npm's package directory. The returned path exists, is a directory, and has all symlinks removed.
 *
 * @param arguments_ - TUI arguments after the Node entry point.
 * @param launchDirectory - Directory from which the repository launcher was invoked.
 * @returns The one canonical workspace and the source of that selection.
 * @throws WorkspaceConfigurationError If arguments are invalid or the path is unusable.
 */
export function resolveWorkspace(
  arguments_: readonly string[],
  launchDirectory: string,
): WorkspaceSelection {
  const configuredPath = parseWorkspaceArgument(arguments_);
  const candidate =
    configuredPath === undefined ? launchDirectory : resolve(launchDirectory, configuredPath);
  const description =
    configuredPath === undefined ? 'launch directory' : `workspace path ${JSON.stringify(configuredPath)}`;

  let canonicalPath: string;
  try {
    canonicalPath = realpathSync(candidate);
  } catch {
    throw new WorkspaceConfigurationError(
      `Code Assist Harness cannot use ${description} because it does not exist or cannot be resolved.`,
    );
  }

  try {
    if (!statSync(canonicalPath).isDirectory()) {
      throw new WorkspaceConfigurationError(
        `Code Assist Harness cannot use ${description} because it is not a directory.`,
      );
    }
  } catch (error: unknown) {
    if (error instanceof WorkspaceConfigurationError) {
      throw error;
    }
    throw new WorkspaceConfigurationError(
      `Code Assist Harness cannot inspect ${description}. Check its permissions and retry.`,
    );
  }

  return {
    path: canonicalPath,
    source: configuredPath === undefined ? 'launch-directory' : 'command-line',
  };
}

function parseWorkspaceArgument(arguments_: readonly string[]): string | undefined {
  if (arguments_.length === 0) {
    return undefined;
  }

  if (arguments_[0] !== '--workspace') {
    throw new WorkspaceConfigurationError(
      `Unknown argument ${JSON.stringify(arguments_[0])}. Usage: ./scripts/run-tui [--workspace PATH]`,
    );
  }

  if (arguments_.length !== 2 || arguments_[1] === undefined || arguments_[1].length === 0) {
    throw new WorkspaceConfigurationError(
      'The --workspace option requires exactly one path. Usage: ./scripts/run-tui [--workspace PATH]',
    );
  }

  return arguments_[1];
}
