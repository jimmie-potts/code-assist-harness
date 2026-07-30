import {readdirSync, readFileSync} from 'node:fs';

import {describe, expect, it} from 'vitest';

import {protocolEventSchema} from '../src/protocol.js';
import {
  INITIAL_SESSION_LIFECYCLE_STATE,
  reduceSessionLifecycle,
  replaySessionLifecycle,
  type SessionLifecycleEvent,
  type SessionLifecycleInput,
  type SessionLifecycleResult,
  type SessionLifecycleState,
} from '../src/session-lifecycle.js';

interface CanonicalInput {
  readonly type: string;
  readonly [key: string]: unknown;
}

interface FixtureCase {
  readonly id: string;
  readonly initial_state: 'idle';
  readonly setup_inputs?: readonly CanonicalInput[];
  readonly input?: CanonicalInput;
  readonly inputs?: readonly CanonicalInput[];
  readonly expected_result: Readonly<Record<string, unknown>>;
}

interface FixtureDocument {
  readonly fixture_version: number;
  readonly cases: readonly FixtureCase[];
}

interface FixtureFileEntry {
  readonly path: FixturePath;
  readonly case_count: number;
}

interface DomainFactEntry {
  readonly type: string;
  readonly wire_message: boolean;
}

interface LifecycleManifest {
  readonly fixture_version: number;
  readonly canonical_initial_state: Readonly<Record<string, unknown>>;
  readonly input_contract: {
    readonly domain_facts: readonly DomainFactEntry[];
    readonly wire_events: readonly string[];
  };
  readonly files: readonly FixtureFileEntry[];
}

interface ProtocolManifest {
  readonly valid: readonly {readonly type: string}[];
}

type FixturePath =
  | 'legal-transitions.json'
  | 'replay-scenarios.json'
  | 'invariant-failures.json';

const fixtureRoot = new URL('../../protocol/fixtures/session-lifecycle/v1/', import.meta.url);
const protocolManifestUrl = new URL('../../protocol/fixtures/v1/manifest.json', import.meta.url);
const manifest = readJson<LifecycleManifest>(new URL('manifest.json', fixtureRoot));
const protocolManifest = readJson<ProtocolManifest>(protocolManifestUrl);
const expectedCaseCounts: Readonly<Record<FixturePath, number>> = {
  'legal-transitions.json': 16,
  'replay-scenarios.json': 7,
  'invariant-failures.json': 27,
};
const fixturePaths = Object.keys(expectedCaseCounts) as readonly FixturePath[];
const fixtures = Object.fromEntries(
  fixturePaths.map((path) => [path, readJson<FixtureDocument>(new URL(path, fixtureRoot))]),
) as Readonly<Record<FixturePath, FixtureDocument>>;
const wireEventTypes = new Set(manifest.input_contract.wire_events);

describe('shared CAH-010 lifecycle fixtures', () => {
  it('declares the exact fixture file and case contract', () => {
    expect(manifest.fixture_version).toBe(1);
    expect(manifest.canonical_initial_state).toEqual(
      normalizeState(INITIAL_SESSION_LIFECYCLE_STATE),
    );
    expect(readdirSync(fixtureRoot).sort()).toEqual([
      'invariant-failures.json',
      'legal-transitions.json',
      'manifest.json',
      'replay-scenarios.json',
    ]);

    const declaredCounts = Object.fromEntries(
      manifest.files.map((entry) => [entry.path, entry.case_count]),
    );
    expect(declaredCounts).toEqual(expectedCaseCounts);
    expect(Object.values(declaredCounts).reduce((total, count) => total + count, 0)).toBe(50);

    const allIds: string[] = [];
    for (const path of fixturePaths) {
      const document = fixtures[path];
      expect(document.fixture_version).toBe(manifest.fixture_version);
      expect(document.cases).toHaveLength(expectedCaseCounts[path]);
      expect(document.cases.every((fixtureCase) => fixtureCase.initial_state === 'idle')).toBe(
        true,
      );
      allIds.push(...document.cases.map((fixtureCase) => fixtureCase.id));
    }
    expect(new Set(allIds).size).toBe(allIds.length);
  });

  for (const path of ['legal-transitions.json', 'invariant-failures.json'] as const) {
    for (const fixtureCase of fixtures[path].cases) {
      it(`matches ${path}: ${fixtureCase.id}`, () => {
        const setupInputs = fixtureCase.setup_inputs ?? [];
        if (fixtureCase.input === undefined) {
          throw new Error(`${fixtureCase.id} must declare one subject input`);
        }
        const allInputs = [...setupInputs, fixtureCase.input];

        let state = INITIAL_SESSION_LIFECYCLE_STATE;
        for (const rawInput of setupInputs) {
          const setupResult = reduceSessionLifecycle(state, toInput(rawInput));
          expect(setupResult.ok, `fixture setup failed for ${fixtureCase.id}`).toBe(true);
          if (!setupResult.ok) {
            throw new Error(`fixture setup failed for ${fixtureCase.id}`);
          }
          state = setupResult.state;
        }

        const subjectResult = reduceSessionLifecycle(state, toInput(fixtureCase.input));
        expect(normalizeResult(subjectResult)).toEqual(fixtureCase.expected_result);
        assertDeterministicReplay(allInputs, fixtureCase.expected_result);
      });
    }
  }

  for (const fixtureCase of fixtures['replay-scenarios.json'].cases) {
    it(`replays replay-scenarios.json: ${fixtureCase.id}`, () => {
      if (fixtureCase.inputs === undefined) {
        throw new Error(`${fixtureCase.id} must declare replay inputs`);
      }
      assertDeterministicReplay(fixtureCase.inputs, fixtureCase.expected_result);
    });
  }

  it('keeps approval inputs as domain facts outside protocol version 1', () => {
    const approvalTypes = new Set(['approval.requested', 'approval.resolved']);
    const domainFacts = new Map(
      manifest.input_contract.domain_facts.map((entry) => [entry.type, entry.wire_message]),
    );
    const protocolTypes = new Set(protocolManifest.valid.map((entry) => entry.type));

    for (const type of approvalTypes) {
      expect(domainFacts.get(type)).toBe(false);
      expect(wireEventTypes.has(type)).toBe(false);
      expect(protocolTypes.has(type)).toBe(false);
      expect(protocolEventSchema.safeParse({type, session_id: 'ses_domain_only'}).success).toBe(
        false,
      );
    }
  });

  it('does not echo a rejected event payload in an invariant failure', () => {
    const secret = 'PAYLOAD_MUST_NOT_ENTER_THE_DIAGNOSTIC';
    const result = replayCanonicalInputs([
      {
        type: 'task.submitted',
        command_id: 'cmd_fixture_secret',
        task: 'Exercise safe failure output.',
      },
      {
        protocol_version: 1,
        type: 'session.started',
        session_id: 'ses_fixture_secret',
        sequence: 1,
        timestamp: '2026-07-30T17:00:00.000Z',
        correlation_id: 'cmd_fixture_secret',
        payload: {},
      },
      {
        protocol_version: 1,
        type: 'assistant.delta',
        session_id: 'ses_fixture_secret',
        sequence: 2,
        timestamp: '2026-07-30T17:00:00.100Z',
        correlation_id: 'cmd_foreign_secret',
        payload: {text: secret},
      },
    ]);

    expect(result.ok).toBe(false);
    if (result.ok) {
      throw new Error('expected the foreign correlation to fail');
    }
    expect(Object.keys(result.failure).sort()).toEqual(['code', 'eventType', 'priorStatus']);
    expect(JSON.stringify(result.failure)).not.toContain(secret);
  });
});

function assertDeterministicReplay(
  rawInputs: readonly CanonicalInput[],
  expectedResult: Readonly<Record<string, unknown>>,
): void {
  const first = normalizeResult(replayCanonicalInputs(rawInputs));
  const second = normalizeResult(replayCanonicalInputs(rawInputs));

  expect(first).toEqual(expectedResult);
  expect(second).toEqual(expectedResult);
  expect(second).toEqual(first);
}

function replayCanonicalInputs(rawInputs: readonly CanonicalInput[]): SessionLifecycleResult {
  return replaySessionLifecycle(rawInputs.map(toInput));
}

function toInput(rawInput: CanonicalInput): SessionLifecycleInput {
  switch (rawInput.type) {
    case 'task.submitted':
      return {
        type: rawInput.type,
        commandId: requireString(rawInput, 'command_id'),
        task: requireString(rawInput, 'task'),
      };
    case 'cancel.requested':
      return {
        type: rawInput.type,
        commandId: requireString(rawInput, 'command_id'),
        sessionId: requireString(rawInput, 'session_id'),
      };
    case 'approval.requested':
    case 'approval.resolved':
      return {type: rawInput.type, sessionId: requireString(rawInput, 'session_id')};
    default: {
      expect(wireEventTypes.has(rawInput.type)).toBe(true);
      const parsed = protocolEventSchema.safeParse(rawInput);
      expect(parsed.success, `wire fixture ${rawInput.type} must pass Zod`).toBe(true);
      if (!parsed.success || !wireEventTypes.has(parsed.data.type)) {
        throw new Error(`invalid lifecycle wire fixture: ${rawInput.type}`);
      }
      return parsed.data as SessionLifecycleEvent;
    }
  }
}

function requireString(input: CanonicalInput, key: string): string {
  const value = input[key];
  if (typeof value !== 'string') {
    throw new TypeError(`${input.type}.${key} must be a string in the shared fixture`);
  }
  return value;
}

function normalizeState(state: SessionLifecycleState): Readonly<Record<string, unknown>> {
  return {
    status: state.status,
    start_command_id: state.startCommandId,
    task: state.task,
    session_id: state.sessionId,
    cancel_command_id: state.cancelCommandId,
    last_sequence: state.lastSequence,
    assistant_text: state.assistantText,
    assistant_completed: state.assistantCompleted,
    session_failure: state.sessionFailure,
  };
}

function normalizeResult(result: SessionLifecycleResult): Readonly<Record<string, unknown>> {
  return {
    ok: result.ok,
    state: normalizeState(result.state),
    failure: result.ok
      ? null
      : {
          code: result.failure.code,
          prior_status: result.failure.priorStatus,
          event_type: result.failure.eventType,
        },
  };
}

function readJson<T>(url: URL): T {
  return JSON.parse(readFileSync(url, 'utf8')) as T;
}
