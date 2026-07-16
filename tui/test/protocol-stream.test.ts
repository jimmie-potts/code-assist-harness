import {describe, expect, it} from 'vitest';

import {NdjsonLineReader, type ProtocolLineResult} from '../src/protocol-stream.js';
import {encodeCommandLine, parseCommandLine} from '../src/protocol.js';

const encoder = new TextEncoder();

describe('NdjsonLineReader', () => {
  it('frames multiple lines across arbitrary chunks and split multibyte characters', () => {
    const source = 'first € line\nsecond line\n';
    const bytes = encoder.encode(source);

    for (let split = 0; split <= bytes.length; split += 1) {
      const reader = new NdjsonLineReader(64);
      const results = [
        ...reader.push(bytes.subarray(0, split)),
        ...reader.push(bytes.subarray(split)),
        ...reader.finish(),
      ];
      expect(results).toEqual([
        {ok: true, line: 'first € line'},
        {ok: true, line: 'second line'},
      ]);
    }
  });

  it('accepts a line exactly at the byte bound', () => {
    const reader = new NdjsonLineReader(4);
    expect(reader.push(encoder.encode('four\n'))).toEqual([{ok: true, line: 'four'}]);
    expect(reader.finish()).toEqual([]);
  });

  it('discards one oversize line and recovers at its LF delimiter', () => {
    const reader = new NdjsonLineReader(4);
    const results = reader.push(encoder.encode('12345 bytes that are discarded\nok\n'));

    expect(results).toEqual([
      {
        ok: false,
        error: {
          code: 'line_too_long',
          message: 'Protocol line exceeds the byte limit.',
        },
      },
      {ok: true, line: 'ok'},
    ]);
    expect(reader.finish()).toEqual([]);
  });

  it('rejects CRLF and bare carriage returns without poisoning later lines', () => {
    const reader = new NdjsonLineReader(64);
    const results = reader.push(encoder.encode('first\r\nsec\rond\nthird\n'));

    expect(resultCodes(results)).toEqual(['invalid_framing', 'invalid_framing', 'ok']);
    expect(results.at(-1)).toEqual({ok: true, line: 'third'});
  });

  it('uses fatal UTF-8 decoding and resumes after an invalid line', () => {
    const reader = new NdjsonLineReader(64);
    const invalidThenValid = Uint8Array.from([0xc3, 0x28, 0x0a, 0x6f, 0x6b, 0x0a]);

    const results = reader.push(invalidThenValid);
    expect(resultCodes(results)).toEqual(['invalid_utf8', 'ok']);
    expect(results[1]).toEqual({ok: true, line: 'ok'});
  });

  it('preserves a UTF-8 BOM so JSON validation rejects the altered wire spelling', () => {
    const reader = new NdjsonLineReader(64);
    const line = Uint8Array.from([0xef, 0xbb, 0xbf, 0x7b, 0x7d, 0x0a]);
    const results = reader.push(line);

    expect(results).toHaveLength(1);
    const result = results[0];
    expect(result?.ok).toBe(true);
    if (result?.ok) {
      expect(parseCommandLine(result.line)).toMatchObject({
        ok: false,
        error: {code: 'malformed_json'},
      });
    }
  });

  it('reports invalid framing when a bounded line reaches EOF before LF', () => {
    const reader = new NdjsonLineReader(64);
    expect(reader.push(encoder.encode('{"partial":true}'))).toEqual([]);
    expect(reader.finish()).toEqual([
      {
        ok: false,
        error: {
          code: 'invalid_framing',
          message: 'Protocol input must be one complete JSON object terminated by LF.',
        },
      },
    ]);
  });

  it('reports an oversize line once even when EOF arrives while it is discarded', () => {
    const reader = new NdjsonLineReader(3);
    expect(resultCodes(reader.push(encoder.encode('oversize')))).toEqual(['line_too_long']);
    expect(reader.finish()).toEqual([]);
  });

  it('rejects blank lines and does not report an extra EOF failure after LF', () => {
    const reader = new NdjsonLineReader(16);
    expect(resultCodes(reader.push(encoder.encode('\n')))).toEqual(['invalid_framing']);
    expect(reader.finish()).toEqual([]);
  });

  it('rejects invalid limits and use after the terminal state', () => {
    expect(() => new NdjsonLineReader(0)).toThrow(RangeError);
    expect(() => new NdjsonLineReader(Number.MAX_SAFE_INTEGER + 1)).toThrow(RangeError);

    const reader = new NdjsonLineReader(16);
    reader.finish();
    expect(() => reader.push(new Uint8Array())).toThrow('already finished');
    expect(reader.finish()).toEqual([]);
  });

  it('integrates encoded commands with arbitrary byte chunking', () => {
    const command = {
      protocol_version: 1,
      type: 'runtime.shutdown',
      command_id: 'cmd_shutdown',
      timestamp: '2026-07-16T13:00:00.000Z',
      payload: {},
    };
    const encoded = encoder.encode(encodeCommandLine(command));
    const reader = new NdjsonLineReader(encoded.length);
    const results = [
      ...reader.push(encoded.subarray(0, 2)),
      ...reader.push(encoded.subarray(2, encoded.length - 1)),
      ...reader.push(encoded.subarray(encoded.length - 1)),
    ];

    expect(results).toHaveLength(1);
    const lineResult = results[0];
    expect(lineResult?.ok).toBe(true);
    if (lineResult?.ok) {
      expect(parseCommandLine(lineResult.line)).toEqual({ok: true, value: command});
    }
  });
});

function resultCodes(results: readonly ProtocolLineResult[]): string[] {
  return results.map((result) => (result.ok ? 'ok' : result.error.code));
}
