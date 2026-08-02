import {readFileSync} from 'node:fs';

import {describe, expect, it} from 'vitest';

import {
  DEFAULT_RUNTIME_PROVIDER,
  OPENAI_TEXT_STREAM_MODEL,
  ProviderConfigurationError,
  resolveProviderSelection,
  SUPPORTED_OPENAI_TEXT_STREAM_MODELS,
  SUPPORTED_RUNTIME_PROVIDERS,
} from '../src/provider-configuration.js';

interface ProviderModelsFixture {
  readonly default_provider: string;
  readonly supported_providers: readonly string[];
  readonly supported_openai_text_stream_models: readonly string[];
}

const fixture = JSON.parse(
  readFileSync(
    new URL(
      '../../protocol/fixtures/runtime-configuration/v1/provider-models.json',
      import.meta.url,
    ),
    'utf8',
  ),
) as ProviderModelsFixture;

describe('provider configuration', () => {
  it('defaults to the deterministic mock without a model', () => {
    expect(resolveProviderSelection(undefined, undefined)).toEqual({provider: 'mock'});
    expect(resolveProviderSelection('mock', undefined)).toEqual({provider: 'mock'});
  });

  it('accepts only the exact reviewed OpenAI model ID', () => {
    expect(resolveProviderSelection('openai', OPENAI_TEXT_STREAM_MODEL)).toEqual({
      provider: 'openai',
      model: OPENAI_TEXT_STREAM_MODEL,
    });
  });

  it.each([
    {
      provider: 'another-provider',
      model: undefined,
      message: '--provider must be either mock or openai.',
    },
    {
      provider: 'mock',
      model: 'model-value-that-must-not-be-echoed',
      message: '--model is supported only with --provider openai.',
    },
    {
      provider: 'openai',
      model: undefined,
      message: '--provider openai requires --model MODEL.',
    },
  ])('rejects an invalid provider/model pair without echoing values', ({provider, model, message}) => {
    expect(() => resolveProviderSelection(provider, model)).toThrow(
      new ProviderConfigurationError(message),
    );
    expect(message).not.toContain('another-provider');
    expect(message).not.toContain('model-value-that-must-not-be-echoed');
  });

  it.each([
    'gpt-5.6',
    'o4-mini-2025-04-16',
    'ft:gpt-5.6-luna:organization:custom',
    'model-value-that-must-not-be-echoed',
    'a'.repeat(257),
    'gpt-4.1 mini',
    'gpt-4.1\u00a0mini',
    'gpt-4.1\nmini',
    'gpt-4.1\u200dmini',
    '\ud800',
  ])('rejects an unsupported or malformed OpenAI model safely', (model) => {
    const expectedMessage = 'Unsupported OpenAI model. Use gpt-5.6-luna.';

    expect(() => resolveProviderSelection('openai', model)).toThrow(
      new ProviderConfigurationError(expectedMessage),
    );
    if (model === 'model-value-that-must-not-be-echoed') {
      expect(expectedMessage).not.toContain(model);
    }
  });

  it('keeps TypeScript provider and model constants aligned with the shared fixture', () => {
    expect(DEFAULT_RUNTIME_PROVIDER).toBe(fixture.default_provider);
    expect(SUPPORTED_RUNTIME_PROVIDERS).toEqual(fixture.supported_providers);
    expect([...SUPPORTED_OPENAI_TEXT_STREAM_MODELS]).toEqual(
      fixture.supported_openai_text_stream_models,
    );
  });
});
