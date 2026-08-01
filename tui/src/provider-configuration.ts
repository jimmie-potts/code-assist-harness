/** Provider names accepted by the repository-owned runtime launch path. */
export const SUPPORTED_RUNTIME_PROVIDERS = ['mock', 'openai'] as const;

/** Default provider selected when the user does not supply `--provider`. */
export const DEFAULT_RUNTIME_PROVIDER = 'mock' as const;

/** The one reviewed OpenAI snapshot supported by CAH-023's text-only stream automaton. */
export const OPENAI_TEXT_STREAM_MODEL = 'gpt-4.1-mini-2025-04-14' as const;

/** Exact OpenAI model allowlist kept in parity with the authoritative Python configuration. */
export const SUPPORTED_OPENAI_TEXT_STREAM_MODELS: ReadonlySet<string> = new Set([
  OPENAI_TEXT_STREAM_MODEL,
]);

const MAXIMUM_MODEL_ID_BYTES = 256;
const DISALLOWED_MODEL_CODE_POINT = /[\p{White_Space}\p{C}]/u;

/** A provider name that may cross the shell-free TypeScript-to-Python launch boundary. */
export type RuntimeProvider = (typeof SUPPORTED_RUNTIME_PROVIDERS)[number];

/** The exact OpenAI snapshot whose stream grammar this repository implements. */
export type SupportedOpenAITextStreamModel = typeof OPENAI_TEXT_STREAM_MODEL;

/**
 * Validated provider selection owned by application configuration, not the NDJSON protocol.
 *
 * Mock selection never carries a model. OpenAI selection always carries the one exact snapshot
 * whose event grammar has been reviewed and implemented by the harness.
 */
export type ProviderSelection =
  | {readonly provider: 'mock'}
  | {readonly provider: 'openai'; readonly model: SupportedOpenAITextStreamModel};

/** Safe configuration rejection whose message never contains a supplied provider or model value. */
export class ProviderConfigurationError extends Error {
  /** Create a fixed provider-configuration failure suitable for direct stderr display. */
  public constructor(message: string) {
    super(message);
    this.name = 'ProviderConfigurationError';
  }
}

/**
 * Validate the provider/model pair before a Python child can be constructed.
 *
 * Model identifiers are checked for a bounded UTF-8 representation and unsafe Unicode before
 * exact allowlist membership. Python repeats these checks and remains authoritative before SDK
 * import, client construction, or network access.
 *
 * @param provider - Optional provider value; absence selects the deterministic mock.
 * @param model - Optional model value accepted only with the OpenAI provider.
 * @returns A discriminated selection that cannot represent an invalid provider/model pair.
 * @throws ProviderConfigurationError If either value or their combination is unsupported.
 */
export function resolveProviderSelection(
  provider: string | undefined,
  model: string | undefined,
): ProviderSelection {
  const selectedProvider = provider ?? DEFAULT_RUNTIME_PROVIDER;
  if (!isRuntimeProvider(selectedProvider)) {
    throw new ProviderConfigurationError('--provider must be either mock or openai.');
  }

  if (selectedProvider === 'mock') {
    if (model !== undefined) {
      throw new ProviderConfigurationError(
        '--model is supported only with --provider openai.',
      );
    }
    return {provider: 'mock'};
  }

  if (model === undefined) {
    throw new ProviderConfigurationError(
      '--provider openai requires --model MODEL.',
    );
  }
  if (!isLocallyValidModelId(model) || !isSupportedOpenAITextStreamModel(model)) {
    throw new ProviderConfigurationError(
      'Unsupported OpenAI model. Use gpt-4.1-mini-2025-04-14.',
    );
  }
  return {provider: 'openai', model};
}

function isRuntimeProvider(value: string): value is RuntimeProvider {
  return (SUPPORTED_RUNTIME_PROVIDERS as readonly string[]).includes(value);
}

function isSupportedOpenAITextStreamModel(
  value: string,
): value is SupportedOpenAITextStreamModel {
  return SUPPORTED_OPENAI_TEXT_STREAM_MODELS.has(value);
}

function isLocallyValidModelId(value: string): boolean {
  const byteLength = Buffer.byteLength(value, 'utf8');
  return (
    byteLength >= 1 &&
    byteLength <= MAXIMUM_MODEL_ID_BYTES &&
    !DISALLOWED_MODEL_CODE_POINT.test(value)
  );
}
