import {readFileSync} from 'node:fs';

import {describe, expect, it} from 'vitest';

import {NdjsonLineReader} from '../src/protocol-stream.js';
import {parseCommandLine, parseEventLine} from '../src/protocol.js';

interface ValidFixtureEntry {
  readonly id: string;
  readonly direction: 'command' | 'event';
  readonly type: string;
  readonly path: string;
}

interface InvalidFixtureEntry {
  readonly id: string;
  readonly direction: 'command' | 'event';
  readonly classification: string;
  readonly path: string;
}

interface FixtureManifest {
  readonly valid: readonly ValidFixtureEntry[];
  readonly invalid: readonly InvalidFixtureEntry[];
}

const fixtureRoot = new URL('../../protocol/fixtures/v1/', import.meta.url);
const manifest = JSON.parse(
  readFileSync(new URL('manifest.json', fixtureRoot), 'utf8'),
) as FixtureManifest;

describe('shared protocol version 1 fixtures', () => {
  for (const entry of manifest.valid) {
    it(`accepts ${entry.id} in the ${entry.direction} validator`, () => {
      const results = readFixture(entry.path);
      expect(results).toHaveLength(1);
      const lineResult = results[0];
      expect(lineResult?.ok).toBe(true);
      if (!lineResult?.ok) {
        return;
      }

      const parseResult =
        entry.direction === 'command'
          ? parseCommandLine(lineResult.line)
          : parseEventLine(lineResult.line);
      expect(parseResult.ok).toBe(true);
      if (parseResult.ok) {
        expect(parseResult.value.type).toBe(entry.type);
      }
    });
  }

  for (const entry of manifest.invalid) {
    it(`classifies ${entry.id} as ${entry.classification}`, () => {
      const results = readFixture(entry.path);
      expect(results).toHaveLength(1);
      const lineResult = results[0];

      if (!lineResult?.ok) {
        expect(lineResult?.error.code).toBe(entry.classification);
        return;
      }

      const parseResult =
        entry.direction === 'command'
          ? parseCommandLine(lineResult.line)
          : parseEventLine(lineResult.line);
      expect(parseResult.ok).toBe(false);
      if (!parseResult.ok) {
        expect(parseResult.error.code).toBe(entry.classification);
      }
    });
  }
});

function readFixture(path: string): ReturnType<NdjsonLineReader['push']> {
  const bytes = readFileSync(new URL(path, fixtureRoot));
  const reader = new NdjsonLineReader(64 * 1024);
  const results = [...reader.push(bytes), ...reader.finish()];
  return results;
}
