import {z} from 'zod';

/** Protocol version implemented by this process boundary. */
export const PROTOCOL_VERSION = 1 as const;

/** Largest encoded JSON object accepted on either stream, excluding its LF delimiter. */
export const MAX_PROTOCOL_LINE_BYTES = 64 * 1024;

const COMMAND_ID_PATTERN = /^cmd_[A-Za-z0-9_-]{1,64}$/u;
const SESSION_ID_PATTERN = /^ses_[A-Za-z0-9_-]{1,64}$/u;
const ISO_TIMESTAMP_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/u;

const nonEmptyStringSchema = z.string().min(1);
const errorCodeSchema = z.string().regex(/^[a-z][a-z0-9_.-]{0,63}$/u);
const safeMessageSchema = z.string().min(1).max(1024).refine(hasNoTerminalControls);
const commandIdSchema = z.string().regex(COMMAND_ID_PATTERN);
const sessionIdSchema = z.string().regex(SESSION_ID_PATTERN);
const sequenceSchema = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const timestampSchema = z.string().refine(isExactIsoTimestamp);

const runtimeInitializeCommandSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('runtime.initialize'),
  command_id: commandIdSchema,
  timestamp: timestampSchema,
  payload: z.strictObject({workspace: nonEmptyStringSchema}),
});

const sessionStartCommandSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.start'),
  command_id: commandIdSchema,
  timestamp: timestampSchema,
  payload: z.strictObject({task: nonEmptyStringSchema}),
});

const sessionCancelCommandSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.cancel'),
  command_id: commandIdSchema,
  timestamp: timestampSchema,
  payload: z.strictObject({session_id: sessionIdSchema}),
});

const runtimeShutdownCommandSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('runtime.shutdown'),
  command_id: commandIdSchema,
  timestamp: timestampSchema,
  payload: z.strictObject({}),
});

/**
 * Strict version 1 command schema at the TypeScript process boundary.
 *
 * This schema describes wire data, not local UI state. Unknown envelope or payload fields are
 * rejected so additions require an intentional compatibility decision.
 */
export const protocolCommandSchema = z.discriminatedUnion('type', [
  runtimeInitializeCommandSchema,
  sessionStartCommandSchema,
  sessionCancelCommandSchema,
  runtimeShutdownCommandSchema,
]);

const runtimeReadyEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('runtime.ready'),
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({workspace: nonEmptyStringSchema}),
});

const sessionStartedEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.started'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({}),
});

const assistantDeltaEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('assistant.delta'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({text: nonEmptyStringSchema}),
});

const assistantCompletedEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('assistant.completed'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({text: nonEmptyStringSchema}),
});

const sessionCompletedEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.completed'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({}),
});

const sessionCancelledEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.cancelled'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({}),
});

const sessionFailedEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('session.failed'),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({
    code: errorCodeSchema,
    message: safeMessageSchema,
  }),
});

const runtimeErrorEventSchema = z.strictObject({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.literal('runtime.error'),
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.strictObject({
    code: errorCodeSchema,
    message: safeMessageSchema,
    recoverable: z.boolean(),
  }),
});

/**
 * Strict version 1 event schema at the TypeScript process boundary.
 *
 * Runtime events may carry command correlation but never session ordering fields. Session events
 * always carry a session identifier and positive, JavaScript-safe sequence number. The schema is a
 * wire contract and must be validated before an event is converted to local UI state.
 */
export const protocolEventSchema = z.discriminatedUnion('type', [
  runtimeReadyEventSchema,
  sessionStartedEventSchema,
  assistantDeltaEventSchema,
  assistantCompletedEventSchema,
  sessionCompletedEventSchema,
  sessionCancelledEventSchema,
  sessionFailedEventSchema,
  runtimeErrorEventSchema,
]);

/** A validated command wire object accepted by the Python runtime. */
export type ProtocolCommand = z.infer<typeof protocolCommandSchema>;

/** A validated event wire object accepted by the TypeScript parent. */
export type ProtocolEvent = z.infer<typeof protocolEventSchema>;

/** Discriminator values supported for version 1 commands. */
export type ProtocolCommandType = ProtocolCommand['type'];

/** Discriminator values supported for version 1 events. */
export type ProtocolEventType = ProtocolEvent['type'];

/** Stable, sanitized classifications returned by the two-stage message parser. */
export type ProtocolParseErrorCode =
  | 'malformed_json'
  | 'malformed_envelope'
  | 'unsupported_version'
  | 'unknown_type'
  | 'invalid_payload';

/** A safe parse failure that never contains input bytes or validator internals. */
export interface ProtocolParseError {
  /** Machine-readable failure class. */
  readonly code: ProtocolParseErrorCode;
  /** Bounded, input-independent explanation suitable for a structured failure. */
  readonly message: string;
}

/** Result of validating one already-framed command or event line. */
export type ProtocolParseResult<Message> =
  | {readonly ok: true; readonly value: Message}
  | {readonly ok: false; readonly error: ProtocolParseError};

/**
 * An input-independent error raised when local code attempts to encode an invalid wire object.
 *
 * Validation details and the attempted object are deliberately omitted so callers cannot
 * accidentally surface secrets through a diagnostic channel.
 */
export class ProtocolEncodingError extends Error {
  /** Whether the rejected object was intended for stdin or stdout. */
  public readonly direction: 'command' | 'event';
  /** Stable reason the candidate could not be placed on the wire. */
  public readonly code: 'invalid_message' | 'line_too_long';

  /** Create a sanitized encoder error for one protocol direction. */
  public constructor(
    direction: 'command' | 'event',
    code: 'invalid_message' | 'line_too_long' = 'invalid_message',
  ) {
    super(
      code === 'line_too_long'
        ? `Cannot encode a protocol ${direction} that exceeds the line byte limit.`
        : `Cannot encode an invalid protocol ${direction}.`,
    );
    this.name = 'ProtocolEncodingError';
    this.direction = direction;
    this.code = code;
  }
}

// Probes intentionally ignore unrelated fields. The selected strict schema remains authoritative
// and classifies every undeclared field as invalid message data instead of a routing failure.
const commandEnvelopeProbeSchema = z.object({
  protocol_version: z.number().int(),
  type: nonEmptyStringSchema,
  command_id: commandIdSchema,
  timestamp: timestampSchema,
  payload: z.unknown(),
});

const versionProbeSchema = z.object({protocol_version: z.number().int()});

const eventEnvelopeProbeSchema = z.object({
  protocol_version: z.number().int(),
  type: nonEmptyStringSchema,
  timestamp: timestampSchema,
  session_id: sessionIdSchema.optional(),
  sequence: sequenceSchema.optional(),
  correlation_id: commandIdSchema.optional(),
  payload: z.unknown(),
});

const runtimeEventEnvelopeSchema = z.object({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.enum(['runtime.ready', 'runtime.error']),
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.unknown(),
});

const sessionEventEnvelopeSchema = z.object({
  protocol_version: z.literal(PROTOCOL_VERSION),
  type: z.enum([
    'session.started',
    'assistant.delta',
    'assistant.completed',
    'session.completed',
    'session.cancelled',
    'session.failed',
  ]),
  session_id: sessionIdSchema,
  sequence: sequenceSchema,
  timestamp: timestampSchema,
  correlation_id: commandIdSchema.optional(),
  payload: z.unknown(),
});

const COMMAND_TYPES = new Set<ProtocolCommandType>([
  'runtime.initialize',
  'session.start',
  'session.cancel',
  'runtime.shutdown',
]);
const RUNTIME_EVENT_TYPES = new Set<ProtocolEventType>(['runtime.ready', 'runtime.error']);
const SESSION_EVENT_TYPES = new Set<ProtocolEventType>([
  'session.started',
  'assistant.delta',
  'assistant.completed',
  'session.completed',
  'session.cancelled',
  'session.failed',
]);

const PARSE_ERROR_MESSAGES: Readonly<Record<ProtocolParseErrorCode, string>> = {
  malformed_json: 'Protocol line is not valid JSON.',
  malformed_envelope: 'Protocol message envelope is invalid.',
  unsupported_version: 'Protocol version is not supported.',
  unknown_type: 'Protocol message type is not supported.',
  invalid_payload: 'Protocol message payload is invalid.',
};

/**
 * Parse and validate one command after an LF reader has removed its delimiter.
 *
 * An integer version is inspected before version 1-specific fields, allowing a future envelope to
 * fail as unsupported rather than accidentally malformed. The common version 1 envelope is then
 * validated before type dispatch, and payload validation happens only for a known command type.
 *
 * @param line - One decoded physical line without its terminating LF.
 * @returns A trusted command or a sanitized failure classification.
 */
export function parseCommandLine(line: string): ProtocolParseResult<ProtocolCommand> {
  const jsonResult = parseJson(line);
  if (!jsonResult.ok) {
    return jsonResult;
  }

  const versionResult = versionProbeSchema.safeParse(jsonResult.value);
  if (!versionResult.success) {
    return parseFailure('malformed_envelope');
  }
  if (versionResult.data.protocol_version !== PROTOCOL_VERSION) {
    return parseFailure('unsupported_version');
  }

  const envelopeResult = commandEnvelopeProbeSchema.safeParse(jsonResult.value);
  if (!envelopeResult.success) {
    return parseFailure('malformed_envelope');
  }
  if (!isCommandType(envelopeResult.data.type)) {
    return parseFailure('unknown_type');
  }

  const messageResult = protocolCommandSchema.safeParse(jsonResult.value);
  return messageResult.success
    ? {ok: true, value: messageResult.data}
    : parseFailure('invalid_payload');
}

/**
 * Parse and validate one event after an LF reader has removed its delimiter.
 *
 * Version support is decided before version 1-specific fields. Runtime and session envelope shapes
 * are then checked before payload validation. An unknown type never enters trusted UI state, and
 * no failure result includes the offending line or Zod issue details.
 *
 * @param line - One decoded physical line without its terminating LF.
 * @returns A trusted event or a sanitized failure classification.
 */
export function parseEventLine(line: string): ProtocolParseResult<ProtocolEvent> {
  const jsonResult = parseJson(line);
  if (!jsonResult.ok) {
    return jsonResult;
  }

  const versionResult = versionProbeSchema.safeParse(jsonResult.value);
  if (!versionResult.success) {
    return parseFailure('malformed_envelope');
  }
  if (versionResult.data.protocol_version !== PROTOCOL_VERSION) {
    return parseFailure('unsupported_version');
  }

  const envelopeResult = eventEnvelopeProbeSchema.safeParse(jsonResult.value);
  if (!envelopeResult.success) {
    return parseFailure('malformed_envelope');
  }

  const {type} = envelopeResult.data;
  if (!isEventType(type)) {
    return parseFailure('unknown_type');
  }

  const selectedEnvelopeSchema = RUNTIME_EVENT_TYPES.has(type)
    ? runtimeEventEnvelopeSchema
    : sessionEventEnvelopeSchema;
  if (!selectedEnvelopeSchema.safeParse(jsonResult.value).success) {
    return parseFailure('malformed_envelope');
  }

  const messageResult = protocolEventSchema.safeParse(jsonResult.value);
  return messageResult.success
    ? {ok: true, value: messageResult.data}
    : parseFailure('invalid_payload');
}

/**
 * Validate and serialize one command as compact NDJSON.
 *
 * @param command - Candidate wire command.
 * @returns Exactly one validated JSON object followed by one LF.
 * @throws ProtocolEncodingError If the candidate is not an exact version 1 command.
 */
export function encodeCommandLine(command: unknown): string {
  return encodeLine(command, protocolCommandSchema, 'command');
}

/**
 * Validate and serialize one event as compact NDJSON.
 *
 * @param event - Candidate wire event.
 * @returns Exactly one validated JSON object followed by one LF.
 * @throws ProtocolEncodingError If the candidate is not an exact version 1 event.
 */
export function encodeEventLine(event: unknown): string {
  return encodeLine(event, protocolEventSchema, 'event');
}

function isExactIsoTimestamp(value: string): boolean {
  if (!ISO_TIMESTAMP_PATTERN.test(value) || value.startsWith('0000-')) {
    return false;
  }
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && date.toISOString() === value;
}

function hasNoTerminalControls(value: string): boolean {
  for (const character of value) {
    const codePoint = character.codePointAt(0) ?? 0;
    if (codePoint < 32 || (codePoint >= 127 && codePoint <= 159)) {
      return false;
    }
  }
  return true;
}

function parseJson(
  line: string,
): {readonly ok: true; readonly value: unknown} | {readonly ok: false; readonly error: ProtocolParseError} {
  try {
    const value = JSON.parse(line) as unknown;
    return containsNonFiniteNumber(value)
      ? parseFailure('malformed_json')
      : {ok: true, value};
  } catch {
    return parseFailure('malformed_json');
  }
}

function containsNonFiniteNumber(value: unknown): boolean {
  const pending: unknown[] = [value];
  while (pending.length > 0) {
    const current = pending.pop();
    if (typeof current === 'number' && !Number.isFinite(current)) {
      return true;
    }
    if (Array.isArray(current)) {
      pending.push(...current);
    } else if (typeof current === 'object' && current !== null) {
      pending.push(...Object.values(current));
    }
  }
  return false;
}

function parseFailure(
  code: ProtocolParseErrorCode,
): {readonly ok: false; readonly error: ProtocolParseError} {
  return {ok: false, error: {code, message: PARSE_ERROR_MESSAGES[code]}};
}

function isCommandType(type: string): type is ProtocolCommandType {
  return COMMAND_TYPES.has(type as ProtocolCommandType);
}

function isEventType(type: string): type is ProtocolEventType {
  return RUNTIME_EVENT_TYPES.has(type as ProtocolEventType) ||
    SESSION_EVENT_TYPES.has(type as ProtocolEventType);
}

function encodeLine<Message>(
  candidate: unknown,
  schema: z.ZodType<Message>,
  direction: 'command' | 'event',
): string {
  const result = schema.safeParse(candidate);
  if (!result.success) {
    throw new ProtocolEncodingError(direction);
  }
  const document = JSON.stringify(result.data);
  if (new TextEncoder().encode(document).byteLength > MAX_PROTOCOL_LINE_BYTES) {
    throw new ProtocolEncodingError(direction, 'line_too_long');
  }
  return `${document}\n`;
}
