import {realpathSync, statSync} from 'node:fs';
import {resolve} from 'node:path';

import {
  resolveProviderSelection,
  type ProviderSelection,
} from './provider-configuration.js';

/** The one canonical repository workspace assigned to a runtime process. */
export interface WorkspaceSelection {
  /** Canonical, symlink-resolved directory passed to the Python child. */
  readonly path: string;
  /** Whether the workspace came from the launch directory or an explicit CLI option. */
  readonly source: 'launch-directory' | 'command-line';
}

/** User-facing launch configuration parsed before the Python child is constructed. */
export type ApplicationConfiguration = {
  /** The one canonical target repository assigned to this application process. */
  readonly workspace: WorkspaceSelection;
  /** Whether Python should create local transcript and summary artifacts. */
  readonly transcriptEnabled: boolean;
} & ProviderSelection;

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
 * @throws ProviderConfigurationError If provider/model arguments are unsupported.
 */
export function resolveWorkspace(
  arguments_: readonly string[],
  launchDirectory: string,
): WorkspaceSelection {
  return resolveApplicationConfiguration(arguments_, launchDirectory).workspace;
}

/**
 * Resolve workspace, persistence, and provider selection from order-independent CLI arguments.
 *
 * @param arguments_ - TUI arguments after the Node entry point.
 * @param launchDirectory - Directory from which the repository launcher was invoked.
 * @returns Canonical workspace, persistence choice, and validated provider/model selection.
 * @throws WorkspaceConfigurationError If an option is unknown, repeated, or incomplete.
 * @throws ProviderConfigurationError If the provider/model pair is unsupported.
 */
export function resolveApplicationConfiguration(
  arguments_: readonly string[],
  launchDirectory: string,
): ApplicationConfiguration {
  const parsed = parseApplicationArguments(arguments_);
  const configuredPath = parsed.workspace;
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
    workspace: {
      path: canonicalPath,
      source: configuredPath === undefined ? 'launch-directory' : 'command-line',
    },
    transcriptEnabled: !parsed.noTranscript,
    ...resolveProviderSelection(parsed.provider, parsed.model),
  };
}

function parseApplicationArguments(arguments_: readonly string[]): {
  readonly workspace: string | undefined;
  readonly noTranscript: boolean;
  readonly provider: string | undefined;
  readonly model: string | undefined;
} {
  let workspace: string | undefined;
  let noTranscript = false;
  let provider: string | undefined;
  let model: string | undefined;
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === '--no-transcript') {
      if (noTranscript) {
        throw new WorkspaceConfigurationError(
          `The --no-transcript option may be provided only once. ${usage()}`,
        );
      }
      noTranscript = true;
      continue;
    }
    if (argument === '--workspace') {
      if (workspace !== undefined) {
        throw new WorkspaceConfigurationError(
          `The --workspace option may be provided only once. ${usage()}`,
        );
      }
      const value = arguments_[index + 1];
      if (value === undefined || value.length === 0 || value.startsWith('--')) {
        throw new WorkspaceConfigurationError(
          `The --workspace option requires exactly one path. ${usage()}`,
        );
      }
      workspace = value;
      index += 1;
      continue;
    }
    if (argument === '--provider') {
      if (provider !== undefined) {
        throw new WorkspaceConfigurationError(
          `The --provider option may be provided only once. ${usage()}`,
        );
      }
      const value = arguments_[index + 1];
      if (value === undefined || value.length === 0 || value.startsWith('--')) {
        throw new WorkspaceConfigurationError(
          `The --provider option requires exactly one value. ${usage()}`,
        );
      }
      provider = value;
      index += 1;
      continue;
    }
    if (argument === '--model') {
      if (model !== undefined) {
        throw new WorkspaceConfigurationError(
          `The --model option may be provided only once. ${usage()}`,
        );
      }
      const value = arguments_[index + 1];
      if (value === undefined || value.length === 0 || value.startsWith('--')) {
        throw new WorkspaceConfigurationError(
          `The --model option requires exactly one value. ${usage()}`,
        );
      }
      model = value;
      index += 1;
      continue;
    }
    throw new WorkspaceConfigurationError(
      `Unknown command-line argument. ${usage()}`,
    );
  }
  return {workspace, noTranscript, provider, model};
}

function usage(): string {
  return 'Usage: ./scripts/run-tui [--workspace PATH] [--no-transcript] [--provider mock|openai] [--model MODEL]';
}
