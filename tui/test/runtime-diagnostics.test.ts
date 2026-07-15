import {describe, expect, it} from 'vitest';

import {RuntimeDiagnostics} from '../src/runtime-diagnostics.js';

describe('RuntimeDiagnostics', () => {
  it('redacts known and recognizable secrets while removing terminal controls', () => {
    const diagnostics = new RuntimeDiagnostics({API_TOKEN: 'top-secret-value'}, 4096, 1200);

    diagnostics.append('failure token=top-');
    diagnostics.append('secret-value\nOPENAI_API_KEY=sk-visible-secret\n');
    diagnostics.append('Authorization: Bearer bearer-value\n\u001B[31mred\u001B[0m\u0000');

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

  it('redacts complete multi-part credential headers without hiding later diagnostics', () => {
    const diagnostics = new RuntimeDiagnostics({});
    diagnostics.append('Status: failed\n');
    diagnostics.append('Keyboard: unavailable\nmonkey=banana\n');
    diagnostics.append('runtime error: Authorization: Basic ZmFrZS11c2VyOmZha2UtcGFzcw==\n');
    diagnostics.append('Authorization=Basic ZmFrZS1vdGhlci1mYWtlLXBhc3M=\n');
    diagnostics.append('Cookie: session=fake-session; preference=dark\n');
    diagnostics.append('Set-Cookie: session=fake-set-cookie; HttpOnly\n');
    diagnostics.append('Proxy-Authorization: Basic ZmFrZS1wcm94eQ==\n');
    diagnostics.append('X-Authorization: Basic ZmFrZS1wcmVmaXhlZA==\n');
    diagnostics.append('useful diagnostic');

    const summary = diagnostics.summary();
    expect(summary).toContain('Status: failed');
    expect(summary).toContain('Keyboard: unavailable');
    expect(summary).toContain('monkey=banana');
    expect(summary).toContain('runtime error: Authorization=[REDACTED]');
    expect(summary).toContain('Authorization=[REDACTED]');
    expect(summary).toContain('Cookie=[REDACTED]');
    expect(summary).toContain('Set-Cookie=[REDACTED]');
    expect(summary).toContain('Proxy-Authorization=[REDACTED]');
    expect(summary).toContain('X-Authorization=[REDACTED]');
    expect(summary).toContain('useful diagnostic');
    expect(summary).not.toContain('ZmFrZS11c2VyOmZha2UtcGFzcw==');
    expect(summary).not.toContain('ZmFrZS1vdGhlci1mYWtlLXBhc3M=');
    expect(summary).not.toContain('fake-session');
    expect(summary).not.toContain('fake-set-cookie');
    expect(summary).not.toContain('preference=dark');
    expect(summary).not.toContain('ZmFrZS1wcm94eQ==');
    expect(summary).not.toContain('ZmFrZS1wcmVmaXhlZA==');
  });

  it('recognizes credential lines before inherited-value redaction can erase the header', () => {
    const diagnostics = new RuntimeDiagnostics({DISPLAY_MODE: 'Authorization'});
    diagnostics.append('Authorization: Basic ZmFrZS1vcmRlcmluZy1wYXNzd29yZA==');

    const summary = diagnostics.summary();
    expect(summary).toContain('[REDACTED]');
    expect(summary).not.toContain('ZmFrZS1vcmRlcmluZy1wYXNzd29yZA==');
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

  it('redacts a known secret when stderr ends inside its value', () => {
    const exactEnding = new RuntimeDiagnostics({SERVICE_TOKEN: 'prefix-sensitive-value'});
    exactEnding.append('failure prefix-sensit');

    const lineEnding = new RuntimeDiagnostics({SERVICE_TOKEN: 'prefix-sensitive-value'});
    lineEnding.append('failure prefix-sensit\n');

    expect(exactEnding.summary()).toBe('failure [REDACTED]');
    expect(lineEnding.summary()).toBe('failure [REDACTED]');
  });

  it('redacts distinctive inherited values and complete quoted assignments', () => {
    const diagnostics = new RuntimeDiagnostics({
      CONNECTION_STRING: 'postgres://user:password@database/private',
    });
    diagnostics.append('connection postgres://user:password@database/private ');
    diagnostics.append('PASSWORD="correct horse battery staple"\nafter');

    const summary = diagnostics.summary();
    expect(summary).toContain('connection [REDACTED]');
    expect(summary).toContain('PASSWORD=[REDACTED]');
    expect(summary).toContain('after');
    expect(summary).not.toContain('postgres');
    expect(summary).not.toContain('correct horse');
    expect(summary).not.toContain('battery staple');
  });
});
