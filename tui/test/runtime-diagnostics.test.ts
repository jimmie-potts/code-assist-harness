import {describe, expect, it} from 'vitest';

import {RuntimeDiagnostics} from '../src/runtime-diagnostics.js';

describe('RuntimeDiagnostics', () => {
  it('redacts known and recognizable secrets while removing terminal controls', () => {
    const diagnostics = new RuntimeDiagnostics({API_TOKEN: 'top-secret-value'}, 4096, 1200);

    diagnostics.append('failure token=top-');
    diagnostics.append('secret-value OPENAI_API_KEY=sk-visible-secret ');
    diagnostics.append('Authorization: Bearer bearer-value \u001B[31mred\u001B[0m\u0000');

    const summary = diagnostics.summary();
    expect(summary).toContain('failure token=[REDACTED]');
    expect(summary).toContain('OPENAI_API_KEY=[REDACTED]');
    expect(summary).toContain('Authorization=[REDACTED]');
    expect(summary).toContain('red');
    expect(summary).not.toContain('top-secret-value');
    expect(summary).not.toContain('sk-visible-secret');
    expect(summary).not.toContain('\u001B');
    expect(summary).not.toContain('\u0000');
  });

  it('bounds retained bytes before decoding and marks omitted context', () => {
    const diagnostics = new RuntimeDiagnostics({}, 24, 48);
    diagnostics.append('an earlier diagnostic that must disappear ');
    diagnostics.append('useful ending');

    const summary = diagnostics.summary();
    expect(summary).toContain('[earlier diagnostics omitted]');
    expect(summary).toContain('useful ending');
    expect(summary?.length).toBeLessThanOrEqual(48);
    expect(summary).not.toContain('an earlier diagnostic');
  });

  it('redacts a known secret when the tail begins inside its value', () => {
    const diagnostics = new RuntimeDiagnostics({SERVICE_PASSWORD: 'prefix-sensitive-value'}, 18, 80);
    diagnostics.append('noise prefix-sensitive-value');

    const summary = diagnostics.summary();
    expect(summary).toContain('[REDACTED]');
    expect(summary).not.toContain('sensitive-value');
  });

  it('redacts distinctive inherited values and complete quoted assignments', () => {
    const diagnostics = new RuntimeDiagnostics({
      CONNECTION_STRING: 'postgres://user:password@database/private',
    });
    diagnostics.append('connection postgres://user:password@database/private ');
    diagnostics.append('PASSWORD="correct horse battery staple" after');

    const summary = diagnostics.summary();
    expect(summary).toContain('connection [REDACTED]');
    expect(summary).toContain('PASSWORD=[REDACTED]');
    expect(summary).toContain('after');
    expect(summary).not.toContain('postgres');
    expect(summary).not.toContain('correct horse');
    expect(summary).not.toContain('battery staple');
  });
});
