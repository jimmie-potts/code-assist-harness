const LINE_FEED = 0x0a;
const CARRIAGE_RETURN = 0x0d;

/** Default maximum bytes in one protocol JSON object, excluding its LF delimiter. */
export const DEFAULT_MAX_LINE_BYTES = MAX_PROTOCOL_LINE_BYTES;

/** Framing and decoding failures produced before JSON parsing begins. */
export type ProtocolLineErrorCode =
  | 'invalid_framing'
  | 'invalid_utf8'
  | 'line_too_long';

/** A bounded, input-independent line-reader failure. */
export interface ProtocolLineError {
  /** Machine-readable framing or decoding failure class. */
  readonly code: ProtocolLineErrorCode;
  /** Safe explanation that does not quote retained bytes. */
  readonly message: string;
}

/** One complete decoded line, or one contained physical-line failure. */
export type ProtocolLineResult =
  | {readonly ok: true; readonly line: string}
  | {readonly ok: false; readonly error: ProtocolLineError};

const LINE_ERROR_MESSAGES: Readonly<Record<ProtocolLineErrorCode, string>> = {
  invalid_framing: 'Protocol input must be one complete JSON object terminated by LF.',
  invalid_utf8: 'Protocol line is not valid UTF-8.',
  line_too_long: 'Protocol line exceeds the byte limit.',
};

/**
 * Incrementally frame a byte stream into bounded UTF-8 NDJSON lines.
 *
 * The reader retains at most `maxLineBytes` for the active line. A line that exceeds the bound is
 * discarded through its next LF, produces one immediate `line_too_long` result, and does not
 * prevent later lines in the same chunk from being read. UTF-8 is decoded only after framing with
 * fatal error handling, so arbitrary chunk and multibyte boundaries are safe. Blank lines, CRLF,
 * and bare carriage returns are rejected. `finish()` transitions the reader permanently to its
 * closed state; later pushes are caller errors and repeated finishes are harmless.
 */
export class NdjsonLineReader {
  readonly #maxLineBytes: number;
  // Preserve a leading BOM so JSON validation rejects it instead of silently changing wire bytes.
  readonly #decoder = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true});
  #lineBytes: number[] = [];
  #discardingOversizeLine = false;
  #finished = false;

  /**
   * Create a line reader with an exact per-line byte bound, excluding the LF delimiter.
   *
   * @param maxLineBytes - Positive, JavaScript-safe maximum bytes retained for one line.
   * @throws RangeError If the configured bound is not a positive safe integer.
   */
  public constructor(maxLineBytes = DEFAULT_MAX_LINE_BYTES) {
    if (!Number.isSafeInteger(maxLineBytes) || maxLineBytes <= 0) {
      throw new RangeError('The protocol line byte limit must be a positive safe integer.');
    }
    this.#maxLineBytes = maxLineBytes;
  }

  /**
   * Consume an arbitrary byte chunk and return every completed line outcome in arrival order.
   *
   * @param chunk - Raw bytes from one stdout or stdin read.
   * @returns Complete decoded lines and contained failures produced by this chunk.
   * @throws Error If called after `finish()`.
   */
  public push(chunk: Uint8Array): readonly ProtocolLineResult[] {
    this.#assertOpen();
    const results: ProtocolLineResult[] = [];

    for (const byte of chunk) {
      if (byte === LINE_FEED) {
        const result = this.#completeLine();
        if (result !== undefined) {
          results.push(result);
        }
        continue;
      }

      if (this.#discardingOversizeLine) {
        continue;
      }

      if (this.#lineBytes.length === this.#maxLineBytes) {
        this.#lineBytes = [];
        this.#discardingOversizeLine = true;
        results.push(lineFailure('line_too_long'));
        continue;
      }

      this.#lineBytes.push(byte);
    }

    return results;
  }

  /**
   * Close the reader and report a retained unterminated line.
   *
   * An oversize line was already reported when it crossed the bound, so EOF does not report it
   * twice. A bounded incomplete line is classified as `invalid_framing`. A stream ending
   * immediately after LF has no final result. Repeated calls return no additional results.
   *
   * @returns Zero or one final framing failure.
   */
  public finish(): readonly ProtocolLineResult[] {
    if (this.#finished) {
      return [];
    }
    this.#finished = true;

    if (this.#discardingOversizeLine) {
      this.#resetLine();
      return [];
    }

    if (this.#lineBytes.length > 0) {
      this.#resetLine();
      return [lineFailure('invalid_framing')];
    }

    return [];
  }

  #completeLine(): ProtocolLineResult | undefined {
    if (this.#discardingOversizeLine) {
      this.#resetLine();
      return undefined;
    }

    const bytes = Uint8Array.from(this.#lineBytes);
    this.#resetLine();

    if (bytes.length === 0 || bytes.includes(CARRIAGE_RETURN)) {
      return lineFailure('invalid_framing');
    }

    try {
      return {ok: true, line: this.#decoder.decode(bytes)};
    } catch {
      return lineFailure('invalid_utf8');
    }
  }

  #resetLine(): void {
    this.#lineBytes = [];
    this.#discardingOversizeLine = false;
  }

  #assertOpen(): void {
    if (this.#finished) {
      throw new Error('The NDJSON line reader is already finished.');
    }
  }
}

function lineFailure(code: ProtocolLineErrorCode): ProtocolLineResult {
  return {ok: false, error: {code, message: LINE_ERROR_MESSAGES[code]}};
}
import {MAX_PROTOCOL_LINE_BYTES} from './protocol.js';
