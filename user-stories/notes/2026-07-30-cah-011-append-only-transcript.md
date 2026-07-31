# 2026-07-30 CAH-011 append-only transcript

## Outcome

CAH-011 adds one privacy-aware append-only JSONL transcript per accepted session, plus an honest
human-readable summary after a successfully persisted terminal record. The Python harness owns
storage, sanitization, failure classification, and strict reducer replay; the TUI exposes opt-out
and preserves one recoverable recording warning without taking lifecycle authority.

CAH-020 is now the next dependency-ready unit.

## Locked decisions

- The transcript records trusted application-owned domain facts and validated session events only
  after the authoritative reducer accepts them. Raw provider structures, invalid wire input,
  diagnostics, and runtime warnings are never transcript inputs.
- Transcript `record_order` spans facts and events, while protocol event `sequence` retains its
  session-local meaning. Replay validates both rather than conflating them.
- Storage defaults to `$XDG_STATE_HOME/code-assist-harness/transcripts/` and falls back to
  `~/.local/state/code-assist-harness/transcripts/`. State never belongs in the target repository.
- Artifact basenames contain a stable pseudonymous workspace hash, session ID, and random transcript
  ID. A known candidate path can still be hashed for comparison, so this is not anonymity.
- Directories are owner-only `0700`; JSONL, temporary summary, and final summary files are `0600`.
  Leaf creation is exclusive and rejects final-component symlinks. Same-user path replacement and
  full `dirfd` hardening remain production-expansion concerns.
- Configured values discovered under recognized secret-like environment names and common pasted
  credential forms are redacted before persistence, including split streamed tokens. Text is
  cumulatively byte-bounded; assistant completion is rebuilt from the exact stored-safe deltas.
- One record is appended, flushed, and fsynced before the persisted safe state and record order
  advance. A short write or failed flush attempts to truncate the partial record back to the prior
  committed offset.
- The first persistence failure latches recording unavailable, produces one payload-free recoverable
  runtime warning, and disables later transcript attempts for that process. It never changes the
  authoritative session terminal outcome and is not recursively recorded.
- Replay opens a bounded regular file, validates LF framing, UTF-8, strict schema/version, record and
  byte limits, cumulative assistant cost, workspace/session identity, and reducer invariants. It
  folds stored-safe inputs without resuming work or repeating a side effect.
- `--no-transcript` short-circuits XDG/home and secret discovery as well as file creation. Its
  normalized protocol tape remains equivalent to an enabled run.

## Security and failure discoveries

Streaming redaction cannot wait for a future fragment after already writing a possible secret
prefix. The sanitizer therefore masks current suffixes that are prefixes of configured or
recognized credentials. This deliberately favors false positives over partial token disclosure.
Fine-grained GitHub PATs and common database credential variables are included in the recognized
forms, while encoded, transformed, or novel formats remain outside this heuristic safety net.

A byte and record cap alone did not bound replay cost because repeated string concatenation in the
shared reducer could be quadratic. A crafted 16 MiB, 9,999-record tape originally exceeded a
15-second audit timeout. Replay now enforces the writer's cumulative assistant-cost ceiling before
folding; the same tape rejects as `transcript_too_large` at record 115 in about 0.1 seconds.

Summary publication writes and fsyncs a restrictive temporary file, then atomically replaces the
final name and removes partial temporary output on failure. The directory is not fsynced, so the
design does not claim power-loss durability. Likewise, a rollback failure may leave a damaged final
line; strict replay contains that damage rather than pretending the full file is valid.

Filesystem work remains synchronous but strictly bounded inside the single event loop. That keeps
the learning-scale durability boundary explicit, but a slow state filesystem can delay command
reading or cancellation. A serialized worker or persistence service is a graduation path; the local
managed WSL environment used for this unit hangs even on a trivial `asyncio.to_thread` call.

## Lesson evidence

The verified [written lesson](../../docs/lessons/cah-011-append-only-transcript.md) includes exact
implementation excerpts for reducer observation, streaming sanitization, append/fsync commit order,
runtime failure routing, and strict replay. Its
[ten-slide visual companion](../../docs/lessons/assets/cah-011-append-only-transcript.pptx) uses a
privacy-first flight-recorder motif and the line “A flight recorder, not a time machine.”

All ten artifact-tool renders were inspected individually at full resolution. The bundled
presentation overflow test completed successfully with no reported overflow.

## Validation evidence

- Canonical Python stages: 226 core/runtime tests, 30 protocol-fixture tests, and 24 repository-policy
  tests passing.
- Canonical TypeScript stages: 208 core tests, 29 protocol-fixture tests, and 4 genuine
  Node-to-Python boundary tests passing.
- Focused transcript/runtime tests exercise XDG/fallback storage, permissions, collision and symlink
  rejection, environment-derived and streamed credential redaction, Unicode and cumulative bounds,
  exact completion reconstruction, summary success/failure, partial append rollback, creation and
  mid-session `fsync` failure, interruption prefixes, opt-out equivalence, hostile replay, and safe
  tracebacks.
- The genuine Node-to-`uv`-to-Python tests run with isolated temporary homes and allowlisted
  non-secret environment values, seed only fake credentials, and scan both JSONL and summaries.
- Type checking, ESLint, Ruff linting, Ruff formatting, Markdown-link policy, documentation policy,
  protocol fixtures, process guards, and network-source policy are covered by `./scripts/check`.
- `TMPDIR=/tmp ./scripts/check` is the final local and CI gate.

## Deferred work

- CAH-020 defines the provider-neutral interface and programmable fake provider.
- Transcript browsing, export, resume, automated retention, tamper evidence, encryption, centralized
  governance, and shared search remain out of scope.
- Later tool and approval stories can add typed bounded metadata, decision details, changed paths,
  and validation outcomes. CAH-011 summaries report those unavailable until a trusted producer
  exists.
