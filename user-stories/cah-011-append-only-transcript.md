# CAH-011 - Write an append-only transcript

- **Status:** Done
- **Milestone / epic:** M1 - Conversational core / E1 - Session, state, and event model
- **Dependencies:** CAH-010
- **Lesson:** [Append-only transcript](../docs/lessons/cah-011-append-only-transcript.md)
- **Visual lesson:**
  [A flight recorder, not a time machine](../docs/lessons/assets/cah-011-append-only-transcript.pptx)

## User story

> As a user, I want each session recorded so that I can inspect what happened after the application
> exits.

## Scope

- Persist every trusted lifecycle input accepted by the reducer—application-owned domain facts and
  validated session events—as append-only JSONL under the WSL XDG state directory.
- Derive a stable workspace identifier without placing unnecessary personal paths in filenames.
- Redact configured sensitive values and bound stored result content.
- Add human-readable completion summaries and an explicit `--no-transcript` mode.
- Surface storage failures without corrupting the in-memory lifecycle.

## Acceptance criteria

1. Transcript storage defaults to the appropriate XDG state location, with a documented fallback
   when the environment variable is unset.
2. Every trusted lifecycle input is appended in reducer order as one JSON object per line. Session
   events retain their authoritative sequence, while domain facts such as `task.submitted`,
   `cancel.requested`, and future approval facts use an explicit transcript record order. Invalid
   wire input and unvalidated provider payloads are never recorded.
3. Transcript files are created with restrictive local permissions and flushed often enough that an
   unexpected exit preserves previously accepted events.
4. Filenames use session and stable workspace identifiers without exposing the full workspace path
   or repository name unnecessarily.
5. User tasks, assistant output, bounded tool metadata/results when available, and approval decisions
   when available pass through one redaction boundary before persistence.
6. Environment values, configured secrets, API keys, and raw provider responses are excluded.
7. A completed session has a concise human-readable summary containing task, outcome, changed files,
   and check results; unavailable fields are represented honestly rather than fabricated.
8. `--no-transcript` prevents creation of the transcript and summary while leaving session behavior
   otherwise unchanged.
9. A write or flush failure becomes a visible structured persistence error, avoids recursive writes,
   and does not silently mutate the reducer's terminal outcome.
10. Re-reading a complete JSONL file from `idle` and applying its ordered domain facts and validated
    events to the reducer reconstructs the same terminal lifecycle state and the same values for
    persisted safe fields; redacted or bounded content is represented by its stored safe value rather
    than reconstructed.
11. Tests use temporary directories, fake credentials, and injected write failures; no real home
    state or credential is touched.

## Validation

- Run transcript, permission, redaction, failure-injection, summary, opt-out, and replay tests with
  pytest temporary directories.
- Scan generated fixtures and snapshots for seeded fake secrets and assert they are absent.
- Terminate a controlled runtime after several flushed events and verify the retained prefix is valid
  JSONL.
- Run the repository-wide non-live checks.

## Documentation impact

Document transcript contents, XDG location, permissions, workspace identifiers, redaction limits,
failure behavior, retention responsibility, and `--no-transcript`. Update the safety and evaluation
documents with what transcripts can and cannot prove.

## Out of scope

- Session browsing, Markdown export, cross-machine sync, retention automation, or resume.
- Persisting raw provider request/response objects or environment dumps.

## Delivered evidence

- `src/code_assist_harness/persistence/transcript.py` owns the strict transcript-v1 schema,
  pseudonymous workspace IDs, configured-value and recognized-credential redaction, cumulative
  UTF-8 content bounds, exclusive private files, per-record flush/fsync, honest summaries, and
  strict reducer replay.
- `MockSession` notifies persistence only after its authoritative reducer accepts a trusted domain
  fact or successfully written validated session event. Transcript order therefore includes local
  facts without replacing protocol event sequence or live lifecycle truth.
- The Python runtime defaults to `$XDG_STATE_HOME/code-assist-harness/transcripts`, falls back to
  `~/.local/state/code-assist-harness/transcripts`, refuses target-workspace storage, and emits one
  recoverable `transcript_persistence_failed` warning before disabling persistence for the process.
- `--no-transcript` is parsed by the TUI in either order with `--workspace`, forwarded as a separate
  shell-free argument, and short-circuits Python state-location and secret discovery.
- The TUI keeps a recoverable persistence warning visible while runtime command input, active
  session state, cancellation, pending draft text, and later tasks remain usable.
- Python tests cover permissions, collision and symlink rejection, XDG fallback, exact and
  stream-split credential redaction, multibyte bounds, completion/cancellation/failure replay,
  corrupt tapes, injected write/flush/summary failures, opt-out, and a killed-runtime prefix. The
  genuine Node-to-Python test also creates and inspects two independent session artifacts under a
  temporary XDG root.
- The verified lesson includes code excerpts from the shipped writer, runtime observer, and replay
  tests plus the linked visual companion. `./scripts/check` is the final local and CI gate.
