import {describe, expect, it} from 'vitest';

import {
  MAX_PROTOCOL_LINE_BYTES,
  ProtocolEncodingError,
  encodeCommandLine,
  encodeEventLine,
  parseCommandLine,
  parseEventLine,
} from '../src/protocol.js';

const TIMESTAMP = '2026-07-16T13:00:00.000Z';

describe('version 1 protocol schemas', () => {
  it('accepts every strict command shape', () => {
    const commands = [
      command('runtime.initialize', {workspace: '/tmp/example'}),
      command('session.start', {task: 'Explain this repository.'}),
      command('session.cancel', {session_id: 'ses_example'}),
      command('runtime.shutdown', {}),
    ];

    for (const candidate of commands) {
      const result = parseCommandLine(JSON.stringify(candidate));
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.value.type).toBe(candidate.type);
      }
    }
  });

  it('accepts every strict event shape and optional command correlation', () => {
    const events = [
      runtimeEvent('runtime.ready', {workspace: '/tmp/example'}),
      sessionEvent('session.started', 1, {}),
      sessionEvent('assistant.delta', 2, {text: 'Partial'}),
      sessionEvent('assistant.completed', 3, {text: 'Complete'}),
      sessionEvent('session.completed', 4, {}),
      sessionEvent('session.cancelled', 5, {}),
      sessionEvent('session.failed', 6, {code: 'failed', message: 'Safe failure.'}),
      runtimeEvent('runtime.error', {
        code: 'malformed_json',
        message: 'A command line was not valid JSON.',
        recoverable: true,
      }),
    ];

    for (const candidate of events) {
      const result = parseEventLine(JSON.stringify(candidate));
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(result.value.type).toBe(candidate.type);
      }
    }

    const uncorrelated = runtimeEvent('runtime.error', {
      code: 'startup_failed',
      message: 'Runtime startup failed.',
      recoverable: false,
    });
    delete uncorrelated.correlation_id;
    expect(parseEventLine(JSON.stringify(uncorrelated)).ok).toBe(true);
  });

  it('classifies JSON, envelope, version, type, and payload failures separately', () => {
    const cases = [
      ['{"protocol_version":1', 'malformed_json'],
      [
        JSON.stringify({
          protocol_version: 1,
          type: 'runtime.shutdown',
          timestamp: TIMESTAMP,
          payload: {},
        }),
        'malformed_envelope',
      ],
      [JSON.stringify({...command('runtime.shutdown', {}), protocol_version: 2}), 'unsupported_version'],
      [JSON.stringify({...command('runtime.shutdown', {}), type: 'runtime.pause'}), 'unknown_type'],
      [JSON.stringify(command('session.start', {task: 42})), 'invalid_payload'],
    ] as const;

    for (const [line, expectedCode] of cases) {
      const result = parseCommandLine(line);
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.error.code).toBe(expectedCode);
      }
    }
  });

  it('rejects a future integer version before requiring version 1 envelope fields', () => {
    const result = parseCommandLine(JSON.stringify({protocol_version: 999, future: 'shape'}));
    expect(parseFailureCode(result)).toBe('unsupported_version');
  });

  it('uses JSON numeric semantics for integral version and sequence spellings', () => {
    const commandLine =
      '{"protocol_version":1.0,"type":"runtime.shutdown","command_id":"cmd_numeric",' +
      `"timestamp":"${TIMESTAMP}","payload":{}}`;
    const eventLine =
      '{"protocol_version":1.0,"type":"session.started","session_id":"ses_numeric",' +
      `"sequence":1.0,"timestamp":"${TIMESTAMP}","payload":{}}`;

    expect(parseCommandLine(commandLine).ok).toBe(true);
    expect(parseEventLine(eventLine).ok).toBe(true);
  });

  it('classifies overflowing JSON numbers consistently as malformed JSON', () => {
    expect(parseFailureCode(parseCommandLine('{"protocol_version":1e9999}'))).toBe(
      'malformed_json',
    );
  });

  it('treats undeclared envelope and payload fields as invalid payloads', () => {
    const extraEnvelopeField = {
      ...runtimeEvent('runtime.ready', {workspace: '/tmp/example'}),
      debug: true,
    };
    const extraPayloadField = command('runtime.shutdown', {debug: true});

    expect(parseFailureCode(parseEventLine(JSON.stringify(extraEnvelopeField)))).toBe(
      'invalid_payload',
    );
    expect(parseFailureCode(parseCommandLine(JSON.stringify(extraPayloadField)))).toBe(
      'invalid_payload',
    );
  });

  it('enforces identifier, timestamp, and session ordering invariants in the envelope', () => {
    const invalidCandidates = [
      {...command('runtime.shutdown', {}), command_id: 'command_1'},
      {...command('runtime.shutdown', {}), command_id: `cmd_${'a'.repeat(65)}`},
      {...command('runtime.shutdown', {}), timestamp: '2026-07-16T13:00:00Z'},
      {...command('runtime.shutdown', {}), timestamp: '2026-02-30T13:00:00.000Z'},
      {...command('runtime.shutdown', {}), timestamp: '0000-01-01T00:00:00.000Z'},
    ];

    for (const candidate of invalidCandidates) {
      expect(parseFailureCode(parseCommandLine(JSON.stringify(candidate)))).toBe(
        'malformed_envelope',
      );
    }

    const invalidEvents = [
      {...sessionEvent('session.started', 1, {}), session_id: 'session_1'},
      {...sessionEvent('session.started', 1, {}), sequence: 0},
      {...sessionEvent('session.started', 1, {}), sequence: Number.MAX_SAFE_INTEGER + 1},
      {...sessionEvent('session.started', 1, {}), correlation_id: 'request_1'},
    ];

    for (const candidate of invalidEvents) {
      expect(parseFailureCode(parseEventLine(JSON.stringify(candidate)))).toBe(
        'malformed_envelope',
      );
    }
  });

  it('validates session identifiers inside cancellation payloads', () => {
    const result = parseCommandLine(
      JSON.stringify(command('session.cancel', {session_id: 'session_example'})),
    );
    expect(parseFailureCode(result)).toBe('invalid_payload');
  });

  it('accepts documented timestamp and identifier boundaries', () => {
    for (const timestamp of ['0001-01-01T00:00:00.000Z', '9999-12-31T23:59:59.999Z']) {
      const candidate = {...command('runtime.shutdown', {}), timestamp};
      expect(parseCommandLine(JSON.stringify(candidate)).ok).toBe(true);
    }

    const candidate = {
      ...command('session.cancel', {session_id: `ses_${'s'.repeat(64)}`}),
      command_id: `cmd_${'c'.repeat(64)}`,
    };
    expect(parseCommandLine(JSON.stringify(candidate)).ok).toBe(true);
  });

  it('rejects empty semantic strings and primitive coercion', () => {
    const invalidPayloads = [
      command('runtime.initialize', {workspace: ''}),
      command('session.start', {task: ''}),
      sessionEvent('assistant.delta', 1, {text: ''}),
      sessionEvent('session.failed', 1, {code: '', message: 'Failure'}),
      runtimeEvent('runtime.error', {code: 'failed', message: '', recoverable: true}),
      runtimeEvent('runtime.error', {
        code: 'failed',
        message: 'Failure',
        recoverable: 'true',
      }),
    ];

    for (const candidate of invalidPayloads) {
      const result =
        'command_id' in candidate
          ? parseCommandLine(JSON.stringify(candidate))
          : parseEventLine(JSON.stringify(candidate));
      expect(parseFailureCode(result)).toBe('invalid_payload');
    }

    expect(
      parseFailureCode(
        parseCommandLine(JSON.stringify({...command('runtime.shutdown', {}), protocol_version: true})),
      ),
    ).toBe('malformed_envelope');
    expect(
      parseFailureCode(
        parseEventLine(
          JSON.stringify({...runtimeEvent('runtime.ready', {workspace: '/tmp/example'}), correlation_id: null}),
        ),
      ),
    ).toBe('malformed_envelope');
  });

  it('rejects terminal controls in user-visible failure fields', () => {
    const unsafe = runtimeEvent('runtime.error', {
      code: 'unsafe_error',
      message: 'unsafe\u001b[31m',
      recoverable: false,
    });

    expect(parseFailureCode(parseEventLine(JSON.stringify(unsafe)))).toBe('invalid_payload');
  });

  it('requires session envelope fields only on session events', () => {
    const missingSequence = sessionEvent('session.started', 1, {});
    delete missingSequence.sequence;

    expect(parseFailureCode(parseEventLine(JSON.stringify(missingSequence)))).toBe(
      'malformed_envelope',
    );

    const runtimeWithSessionField = {
      ...runtimeEvent('runtime.ready', {workspace: '/tmp/example'}),
      session_id: 'ses_example',
    };
    expect(parseFailureCode(parseEventLine(JSON.stringify(runtimeWithSessionField)))).toBe(
      'invalid_payload',
    );
  });

  it('returns input-independent errors without raw values or Zod details', () => {
    const secret = 'fake-secret-that-must-not-escape';
    const result = parseCommandLine(
      JSON.stringify(command('session.start', {task: {secret}})),
    );

    expect(result.ok).toBe(false);
    expect(JSON.stringify(result)).not.toContain(secret);
    expect(JSON.stringify(result)).not.toContain('issues');
    expect(JSON.stringify(result)).not.toContain('path');
  });
});

describe('protocol line encoders', () => {
  it('validates and writes exactly one compact command object followed by LF', () => {
    const candidate = command('session.start', {task: 'Line one\nLine two'});
    const encoded = encodeCommandLine(candidate);

    expect(encoded.endsWith('\n')).toBe(true);
    expect(encoded.slice(0, -1)).not.toContain('\n');
    expect(encoded).not.toContain('\r');
    expect(parseCommandLine(encoded.slice(0, -1))).toEqual({ok: true, value: candidate});
  });

  it('validates and writes exactly one compact event object followed by LF', () => {
    const candidate = sessionEvent('assistant.delta', 1, {text: 'Hello'});
    const encoded = encodeEventLine(candidate);

    expect(encoded.match(/\n/gu)).toHaveLength(1);
    expect(encoded.endsWith('\n')).toBe(true);
    expect(parseEventLine(encoded.slice(0, -1))).toEqual({ok: true, value: candidate});
  });

  it('rejects invalid objects with sanitized encoder errors', () => {
    const secret = 'fake-secret-that-must-not-escape';
    const invalid = {...command('session.start', {task: secret}), debug: secret};

    expect(() => encodeCommandLine(invalid)).toThrow(ProtocolEncodingError);
    expect(() => encodeCommandLine(invalid)).toThrow('Cannot encode an invalid protocol command.');

    try {
      encodeCommandLine(invalid);
    } catch (error: unknown) {
      expect(String(error)).not.toContain(secret);
    }
  });

  it('rejects valid command and event objects that exceed the wire byte limit', () => {
    const oversizedCommand = command('session.start', {task: 'é'.repeat(MAX_PROTOCOL_LINE_BYTES)});
    const oversizedEvent = sessionEvent('assistant.delta', 1, {
      text: 'x'.repeat(MAX_PROTOCOL_LINE_BYTES),
    });

    for (const [direction, encode] of [
      ['command', () => encodeCommandLine(oversizedCommand)],
      ['event', () => encodeEventLine(oversizedEvent)],
    ] as const) {
      try {
        encode();
        throw new Error('Expected oversized protocol encoding to fail.');
      } catch (error: unknown) {
        expect(error).toBeInstanceOf(ProtocolEncodingError);
        expect(error).toMatchObject({direction, code: 'line_too_long'});
        expect(String(error)).not.toContain('é'.repeat(100));
      }
    }
  });
});

function command(type: string, payload: Record<string, unknown>): Record<string, unknown> {
  return {
    protocol_version: 1,
    type,
    command_id: 'cmd_example',
    timestamp: TIMESTAMP,
    payload,
  };
}

function runtimeEvent(type: string, payload: Record<string, unknown>): Record<string, unknown> {
  return {
    protocol_version: 1,
    type,
    timestamp: TIMESTAMP,
    correlation_id: 'cmd_example',
    payload,
  };
}

function sessionEvent(
  type: string,
  sequence: number,
  payload: Record<string, unknown>,
): Record<string, unknown> {
  return {
    protocol_version: 1,
    type,
    session_id: 'ses_example',
    sequence,
    timestamp: TIMESTAMP,
    correlation_id: 'cmd_example',
    payload,
  };
}

function parseFailureCode(
  result: ReturnType<typeof parseCommandLine> | ReturnType<typeof parseEventLine>,
): string | undefined {
  return result.ok ? undefined : result.error.code;
}
