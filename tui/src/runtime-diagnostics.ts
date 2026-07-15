const DEFAULT_BYTE_LIMIT = 4096;
const DEFAULT_DISPLAY_LIMIT = 1200;
const REDACTION = '[REDACTED]';
const MINIMUM_SECRET_FRAGMENT_LENGTH = 4;
const SECRET_NAME = /(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE|AUTH|DSN|DATABASE_URL)/iu;
const ENVIRONMENT_ASSIGNMENT =
  /\b([A-Z][A-Z0-9_]*)\s*[:=]\s*(?:Bearer\s+[^\s,;]+|"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;]+)/giu;
const BEARER_TOKEN = /\bBearer\s+[^\s,;]+/giu;
const OPENAI_STYLE_TOKEN = /\bsk-[A-Za-z0-9_-]{8,}/gu;
const ESCAPE = String.fromCodePoint(27);
const ANSI_SEQUENCE = new RegExp(`${ESCAPE}\\[[0-?]*[ -/]*[@-~]`, 'gu');

/**
 * Retain a bounded stderr tail and convert it into secret-safe display text.
 *
 * Raw stderr never enters UI state. Bytes are bounded before decoding, known secret environment
 * values and common credential shapes are redacted, terminal controls are removed, and display
 * text receives a second character limit.
 */
export class RuntimeDiagnostics {
  readonly #byteLimit: number;
  readonly #displayLimit: number;
  readonly #secretValues: readonly string[];
  #tail: Buffer<ArrayBufferLike> = Buffer.alloc(0);
  #truncated = false;

  /**
   * Create a diagnostic collector.
   *
   * @param environment - Environment whose values of at least eight characters, plus secret-named
   * values of at least four characters, must be redacted.
   * @param byteLimit - Maximum raw stderr tail retained in memory.
   * @param displayLimit - Maximum sanitized characters returned to the UI.
   */
  public constructor(
    environment: NodeJS.ProcessEnv = process.env,
    byteLimit = DEFAULT_BYTE_LIMIT,
    displayLimit = DEFAULT_DISPLAY_LIMIT,
  ) {
    this.#byteLimit = byteLimit;
    this.#displayLimit = displayLimit;
    this.#secretValues = Object.entries(environment)
      .filter(
        ([name, value]) =>
          value !== undefined &&
          (value.length >= 8 || (SECRET_NAME.test(name) && value.length >= 4)),
      )
      .map(([, value]) => value as string)
      .sort((left, right) => right.length - left.length);
  }

  /** Add one stderr chunk while retaining only the configured tail. */
  public append(chunk: string | Buffer): void {
    const bytes = typeof chunk === 'string' ? Buffer.from(chunk) : chunk;
    if (bytes.length >= this.#byteLimit) {
      this.#truncated = this.#truncated || this.#tail.length > 0 || bytes.length > this.#byteLimit;
      this.#tail = bytes.subarray(bytes.length - this.#byteLimit);
      return;
    }
    const combined = Buffer.concat([this.#tail, bytes]);
    if (combined.length > this.#byteLimit) {
      this.#truncated = true;
      this.#tail = combined.subarray(combined.length - this.#byteLimit);
      return;
    }
    this.#tail = combined;
  }

  /**
   * Return bounded, sanitized context for a visible failure.
   *
   * @returns Safe single-line context, or undefined when stderr contained no useful text.
   */
  public summary(): string | undefined {
    let text = this.#tail.toString('utf8').replace(ANSI_SEQUENCE, '').trimEnd();
    text = redactKnownValues(text, this.#secretValues);
    text = text
      .replace(ENVIRONMENT_ASSIGNMENT, (match, name: string) =>
        SECRET_NAME.test(name) ? `${name}=${REDACTION}` : match,
      )
      .replace(BEARER_TOKEN, `Bearer ${REDACTION}`)
      .replace(OPENAI_STYLE_TOKEN, REDACTION);
    text = removeControlCharacters(text).replace(/\s+/gu, ' ').trim();

    if (text.length === 0) {
      return undefined;
    }

    const truncationMarker = this.#truncated ? '[earlier diagnostics omitted] ' : '';
    const available = Math.max(0, this.#displayLimit - truncationMarker.length);
    const bounded =
      text.length > available ? `…${text.slice(-Math.max(0, available - 1))}` : text;
    return `${truncationMarker}${bounded}`;
  }
}

function redactKnownValues(text: string, secretValues: readonly string[]): string {
  let redacted = text;
  for (const value of secretValues) {
    redacted = redacted.split(value).join(REDACTION);

    // A tail buffer can begin in the middle of a secret. Redact that matching suffix as well.
    for (let offset = 1; offset <= value.length - MINIMUM_SECRET_FRAGMENT_LENGTH; offset += 1) {
      const suffix = value.slice(offset);
      if (redacted.startsWith(suffix)) {
        redacted = `${REDACTION}${redacted.slice(suffix.length)}`;
        break;
      }
    }

    // stderr can end before a secret is fully written. Redact that leading fragment too.
    for (
      let length = value.length - 1;
      length >= MINIMUM_SECRET_FRAGMENT_LENGTH;
      length -= 1
    ) {
      const prefix = value.slice(0, length);
      if (redacted.endsWith(prefix)) {
        redacted = `${redacted.slice(0, -prefix.length)}${REDACTION}`;
        break;
      }
    }
  }
  return redacted;
}

function removeControlCharacters(text: string): string {
  let clean = '';
  for (const character of text) {
    const codePoint = character.codePointAt(0) ?? 0;
    const isAllowedWhitespace = character === '\n' || character === '\r' || character === '\t';
    const isControl = codePoint < 32 || (codePoint >= 127 && codePoint <= 159);
    clean += isControl && !isAllowedWhitespace ? ' ' : character;
  }
  return clean;
}
