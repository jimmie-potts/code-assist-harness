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

interface TeachingScenarioEntry {
  readonly id: string;
  readonly command_path: string;
  readonly event_path: string;
}

interface FixtureManifest {
  readonly valid: readonly ValidFixtureEntry[];
  readonly teaching_scenarios: readonly TeachingScenarioEntry[];
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

  for (const scenario of manifest.teaching_scenarios) {
    for (const [direction, path] of [
      ['command', scenario.command_path],
      ['event', scenario.event_path],
    ] as const) {
      it(`accepts every ${direction} line in ${scenario.id}`, () => {
        const results = readFixture(path);
        expect(results.length).toBeGreaterThan(0);

        for (const lineResult of results) {
          expect(lineResult.ok).toBe(true);
          if (!lineResult.ok) {
            continue;
          }

          const parseResult =
            direction === 'command'
              ? parseCommandLine(lineResult.line)
              : parseEventLine(lineResult.line);
          expect(parseResult.ok).toBe(true);
        }
      });
    }
  }

  it('keeps the walking-skeleton guide NDJSON blocks identical to the teaching scenarios', () => {
    const guide = readFileSync(
      new URL('../../docs/walking-skeleton.md', import.meta.url),
      'utf8',
    );
    const documentedBlocks = [...guide.matchAll(/```ndjson\n([\s\S]*?)```/gu)].map(
      (match) => match[1],
    );
    const documentedFixtureBlocks = [
      ...guide.matchAll(/<!-- fixture: ([^\n]+) -->\n```ndjson\n([\s\S]*?)```/gu),
    ].map((match) => [match[1], match[2]] as const);
    const fixtureBlocks = manifest.teaching_scenarios.flatMap((scenario) =>
      [scenario.command_path, scenario.event_path].map((path) =>
        [path, readFileSync(new URL(path, fixtureRoot), 'utf8')] as const,
      ),
    );

    expect(documentedFixtureBlocks.map((fixtureBlock) => fixtureBlock[1])).toEqual(
      documentedBlocks,
    );
    expect(documentedFixtureBlocks).toEqual(fixtureBlocks);
  });

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
