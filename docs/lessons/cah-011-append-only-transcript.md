# CAH-011 lesson: Append-only transcript

- **Unit:** CAH-011
- **Milestone:** M1 - Conversational core
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; focused transcript/runtime and TUI checks pass
- **Story:** [CAH-011](../../user-stories/cah-011-append-only-transcript.md)
- **Visual companion:**
  [A flight recorder, not a time machine](assets/cah-011-append-only-transcript.pptx)
- **Related architecture:** [Architecture](../architecture.md),
  [Safety model](../safety-model.md), and [Evaluation](../evaluation.md)

> This lesson describes the shipped CAH-011 path. The code samples below are excerpts from the
> implementation and tests, not aspirational pseudocode.

## Quick summary

CAH-011 adds a privacy-aware local flight recorder for each session. Python observes trusted
reducer inputs, writes their redacted and bounded forms as append-only JSONL, derives an honest
terminal summary, and can validate and fold the tape back through the same reducer without
re-running any effect.

The transcript is evidence, not authority. A storage failure produces one recoverable warning and
disables later recording attempts for that process; it never changes the live session result.

## Learning objectives

After completing this unit, you should be able to:

- distinguish authoritative lifecycle state from a durable projection of that state;
- preserve physical record order separately from protocol event sequence;
- apply stateful streaming redaction and cumulative content bounds before persistence;
- explain what per-record `fsync`, restrictive permissions, and strict replay do and do not prove;
- design a non-recursive failure path that keeps the user session usable; and
- compare a single-user JSONL recorder with a governed production audit platform.

## Why this unit matters

An in-memory conversation disappears when the process exits. That makes cancellation races,
provider failures, and state-machine defects difficult to study. Recording raw SDK traffic would
solve the wrong problem: it would persist untrusted structures and increase secret exposure.

CAH-011 instead records the facts the reducer already trusted. Later evaluation work can inspect a
complete tape or a safely terminated prefix, while privacy controls remain explicit and users can
choose `--no-transcript` before Python reads a state location or discovers configured secrets.

## Key concepts

- **Append-only JSONL:** one compact JSON object and one LF per accepted input. Earlier records are
  never edited during the session.
- **Two orders:** `record_order` covers domain facts and events together; protocol `sequence`
  remains authoritative only within validated session events.
- **Safe projection:** the persisted state may contain `[REDACTED]`, `[TRUNCATED]`, or `~` instead
  of the original text. Replay reconstructs that stored projection, not removed content.
- **Pseudonymous workspace ID:** `ws1_` plus 24 hexadecimal SHA-256 characters keeps the canonical
  path and repository name out of filenames. Someone who can guess a path can still hash it, so the
  ID is not anonymous.
- **Strict replay:** framing, UTF-8, schema, version, bounds, record order, identity, reducer
  invariants, and optional workspace scope are validated before a tape is trusted.
- **Honest summary:** changed files and check results are reported as unavailable because CAH-011
  has no tools that can produce those facts yet.

## Architecture and design

```text
trusted local fact / validated event
                 |
                 v
       live reducer accepts it  <---- lifecycle authority
                 |
                 v
       transcript observer
                 |
        redact + bound content
                 |
        append one JSONL record
        flush + fsync that record
                 |
       strict replay folds safely  ----> evidence only
```

Python owns the recorder in `persistence/transcript.py`. `MockSession` calls its lifecycle observer
only after the reducer accepts an update. `runtime.py` converts the recorder's first payload-free
failure into a recoverable protocol event. The TypeScript supervisor keeps that recording warning
visible without granting it session-state authority.

Artifacts live at:

```text
$XDG_STATE_HOME/code-assist-harness/transcripts/
└── ws1_<workspace>--ses_<session>--tr_<random>.jsonl
    ws1_<workspace>--ses_<session>--tr_<random>.summary.txt
```

When `XDG_STATE_HOME` is absent or relative, the root falls back to
`~/.local/state/code-assist-harness/`. Application directories are forced to `0700`; transcript and
summary files are forced to `0600`. Exclusive leaf creation and `O_NOFOLLOW` reject common
collisions and final-component symlinks, but the path setup is not a production-grade `dirfd`
defense against every same-user replacement race.

### Code sample: observe only accepted state

The reducer commits first. The recorder sees the accepted update and resulting state afterward:

```python
async def _reduce_lifecycle(self, update: SessionUpdate) -> None:
    """Accept one integration fact or raise a bounded payload-free invariant error."""
    reduction = reduce_session_state(self._lifecycle_state, update)
    if not reduction.ok:
        raise _lifecycle_invariant_error(reduction.failure)
    self._lifecycle_state = reduction.state
    await self._notify_lifecycle(update)

async def _notify_lifecycle(self, update: SessionUpdate) -> None:
    """Publish one accepted update without granting the observer lifecycle authority."""
    if self._lifecycle_observer is not None:
        await self._lifecycle_observer(update, self._lifecycle_state)
```

That ordering prevents invalid wire input, raw provider values, and rejected transitions from
becoming evidence merely because they reached the process.

### Code sample: completion comes from stored-safe deltas

Streaming redaction is stateful. Each safe delta is accumulated, and the stored completion is
rebuilt from that safe projection rather than independently sanitizing a raw final response:

```python
if isinstance(update, AssistantDeltaEvent):
    safe_delta = self._redact_stream_fragment(update.payload.text)
    safe_delta = self._bounded_assistant_fragment(safe_delta)
    self.safe_assistant_text += safe_delta
    return update.model_copy(update={"payload": AssistantTextPayload(text=safe_delta)})
if isinstance(update, AssistantCompletedEvent):
    completed = self.safe_assistant_text or _OMISSION_MARKER
    return update.model_copy(update={"payload": AssistantTextPayload(text=completed)})
```

This matters for secrets split across several deltas. Possible secret prefixes are masked before
they can be appended. The global assistant-content budget is 16 KiB by default; after it is spent,
later non-empty deltas use the one-byte `~` structural sentinel so reducer cardinality remains valid
without unbounded marker growth.

### Code sample: commit order only after durability work

The in-memory safe projection and next record number advance only after the bounded line is written
and `fsync` returns:

```python
line = _encode_record(record)
if (
    self._next_record_order > _MAX_TRANSCRIPT_RECORDS
    or self._committed_bytes + len(line) > _MAX_TRANSCRIPT_BYTES
):
    raise TranscriptPersistenceError("transcript_write_failed")
self._append_and_flush(line)
self._state = reduction.state
self._next_record_order += 1
self._committed_bytes += len(line)
```

The writer caps one line at 128 KiB, a tape at 16 MiB, a tape at 10,000 records, and cumulative
assistant replay text at the line ceiling plus one structural byte per possible record. Replay
enforces the same assistant-cost ceiling before the reducer can perform quadratic string growth on
a crafted tape. A partial write or failed flush attempts to truncate back to the last committed byte
and then latches recording unavailable. If truncation itself also fails, replay safely rejects the
damaged final line; arbitrary disk failure cannot guarantee that every visible byte is a valid
record.

### Code sample: fail recording, not the turn

The runtime reports the first failure once and leaves the authoritative mock session running:

```python
async def _record_lifecycle(
    update: SessionUpdate,
    accepted_state: SessionState,
) -> None:
    """Persist one accepted input or emit the one safe warning."""
    nonlocal transcript_available
    failure = await transcript.record(update, accepted_state)
    if failure is None:
        return
    transcript_available = False
    await writer.emit_runtime(
        "runtime.error",
        {
            "code": "transcript_persistence_failed",
            "message": failure.message,
            "recoverable": True,
        },
        correlation_id=start_command_id,
    )
```

The error contains a fixed safe message, never the failed path, exception text, record payload, or
secret. Recording its own warning would recurse, so runtime warnings are deliberately outside the
session transcript.

### Code sample: validate, then fold

Replay treats stored bytes as untrusted. Only a strict record with the expected physical order,
stable identities, and a legal reducer transition enters reconstructed state:

```python
record = _TRANSCRIPT_RECORD_ADAPTER.validate_json(encoded_record, strict=True)
if record.record_order != line_number:
    raise TranscriptReplayError("record_order_mismatch", line_number)
if record.workspace_id != expected_workspace_id:
    raise TranscriptReplayError("workspace_mismatch", line_number)
if record.session_id != expected_session_id or not _record_matches_session(record):
    raise TranscriptReplayError("session_mismatch", line_number)
update = _record_update(record)
reduction = reduce_session_state(state, update)
if not reduction.ok:
    raise TranscriptReplayError("lifecycle_invariant_failed", line_number)
state = reduction.state
```

Validation failures expose only a bounded code and line number. Underlying Pydantic, decoding, and
path exceptions are suppressed so secret-bearing input excerpts and local paths do not enter normal
tracebacks.

## Practical walkthrough

1. Launch normally or pass `--no-transcript`; the TUI forwards the option as a separate shell-free
   child argument.
2. On `session.start`, Python derives `TranscriptSettings`, canonicalizes the workspace, creates a
   pseudonymous ID, and exclusively opens the owner-only JSONL outside the target repository.
3. Attaching the observer immediately records the already-accepted `task.submitted` fact.
4. Each later accepted domain fact or validated event crosses the single stateful sanitizer, strict
   transcript schema, byte/record caps, append, flush, and `fsync` boundary.
5. A terminal record triggers a summary written to a `0600` temporary file, flushed, and atomically
   replaced. The containing directory is not fsynced, so this is atomic publication in the normal
   local process model, not a claim of power-loss durability.
6. `replay_transcript()` opens only a bounded regular file, validates one LF-delimited record at a
   time, and folds from `idle`. An incomplete valid prefix is inspectable with `complete=False`; it
   is never resumable work.
7. Inspect the JSONL and summary under the XDG state root. Verify that the target repository remains
   unchanged and that a guessed workspace path is required to correlate its pseudonymous ID.

The mock writes protocol stdout before it reduces and notifies persistence. Therefore the newest
visible event may be ahead of durable evidence. The interruption regression waits for the next
event before terminating the process, which proves the previous delta's awaited `fsync` returned.
The guarantee is a frequently flushed accepted prefix, not perfect capture of the last displayed
event under every crash.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and test evidence |
| --- | --- | --- |
| Write or `fsync` fails mid-session | One durable recording warning appears | The live session still reaches its authoritative terminal event; the prior replayable prefix remains inspectable |
| Summary write fails | Recording warning after the terminal JSONL record | The complete tape still replays; the partial temporary summary is removed and no final summary is claimed |
| Secret spans streamed deltas | Prefix and suffix arrive separately | Individual stored fragments omit the seeded token; completion equals the joined stored-safe deltas |
| Content or tape cap is crossed | Persistence reports a safe write failure | Recording stops before writer output exceeds its own replay limits; session work continues |
| Process is terminated | No terminal record or summary exists | The previously awaited prefix replays with `complete=False`; no work is resumed |
| Corrupt, huge, FIFO, or identity-swapped input is replayed | A classified replay error identifies the first unsafe line | Replay performs no effect, does not echo record contents, and stops before accepting later bytes |
| `--no-transcript` is selected | No XDG transcript paths are inspected or created | Normalized protocol payloads, correlations, sequences, and terminal state match an enabled run |

Focused regressions use temporary XDG roots, isolated fake homes, fake credentials, and injected
write/flush/summary failures. The genuine Node-to-`uv`-to-Python boundary also checks generated
JSONL and summary artifacts without giving the child a developer credential or real home state.

## Production expansion

### Example enterprise scenario

Imagine an internal coding service used by 250 engineers across regulated repositories. Security
needs tenant access controls, encryption-key rotation, retention schedules, legal holds, integrity
proofs, cross-region recovery, and searchable correlation. A laptop JSONL file with `0600`
permissions cannot provide those governance or durability guarantees.

### Typical production capabilities and tools

These are representative comparisons, not approved dependencies:

- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
  illustrates structured correlation across centralized collectors. The benefit is shared
  observability; the cost is schema governance, pipeline operation, indexing spend, and broader
  privacy exposure.
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
  illustrates write-once retention and legal holds. The benefit is policy-enforced immutability; the
  cost is retention administration, recovery drills, storage versions, and difficult deletion
  exceptions.
- [Vault Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
  illustrates centralized encryption, signing, and key rotation. The benefit is governed key use;
  the cost is highly available service operation, authentication policy, rotation procedures, and
  latency monitoring.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One WSL user and one Python process | Many users, tenants, workspaces, and regions |
| Authority | Reducer state; transcript is a projection | Versioned event contracts plus governed producers and consumers |
| Durability | Per-record local `fsync`; valid prefix under tested interruption | Replication, backups, integrity checks, and measured recovery objectives |
| Privacy | Heuristic redaction, bounds, `0600`/`0700`, and opt-out | Classification, encryption, access control, consent, deletion, and legal holds |
| Integrity | Strict schema/order replay; no MAC or hash chain | Signed or immutable records with independent verification |
| Operations | Local warning, direct inspection, manual retention | Central alerts, runbooks, cost controls, retention jobs, and audit review |
| Cost | Minimal services and cognitive load | Storage, indexing, key management, governance, and on-call ownership |

### Trade-offs and graduation signals

The learning design is transparent, inspectable, and cheap. Its sanitizer is intentionally
heuristic: recognized configured values and common credential syntax are masked, but encoded,
transformed, or unknown-format secrets can survive. User text can also contain identifying paths.
Permissions are not encryption; replay is not authenticity; and local deletion remains the user's
responsibility.

The synchronous bounded write and `fsync` path keeps the durability boundary easy to reason about,
but a slow state filesystem can delay command reading or cancellation. Move storage behind a
serialized worker or service when measured latency, multi-user access, retention obligations,
tamper evidence, or recovery targets exceed what a single local file can support.

## Practical exercises

1. Split a fake configured token at every possible character boundary and assert that no individual
   stored fragment contains a token prefix.
2. Inject a short write followed by an exception. Replay the retained prefix, then inject a failed
   rollback and observe how strict framing contains the damage.
3. Change a valid tape's outer session ID, nested event session ID, record order, and workspace ID
   one at a time. Record the first safe replay classification for each mutation.
4. Compare enabled and `--no-transcript` runs after removing timestamps. Check event payloads,
   correlations, sequence, reducer state, and absence of state-directory artifacts.
5. Try encoded and transformed fake secrets to map the boundary of heuristic redaction. Propose a
   producer-side rule that avoids relying on the sanitizer as data-loss prevention.
6. Draft an enterprise retention policy and identify data the service should never emit even when
   encryption and immutable storage are available.

## Key takeaways

- The reducer owns truth; the transcript observes only accepted facts and events.
- Redact and bound before bytes exist, then rebuild completion from the exact safe deltas stored.
- Commit record order only after append and `fsync`; on failure, keep the turn alive and report once.
- Replay validates and folds evidence. It never resumes work, repeats effects, restores removed
  content, or proves authenticity.
- A local flight recorder is excellent for learning; production governance arrives with real
  operational and privacy cost.

## Glossary

- **Append-only:** new records are added without intentionally rewriting earlier session records.
- **Domain fact:** a trusted application-owned reducer input, such as task submission or
  cancellation intent, that is not a protocol event.
- **JSONL:** one JSON value per line, suitable for incremental append and prefix recovery.
- **Pseudonymous ID:** a stable derived identifier that hides the source value in ordinary display
  but can still be correlated by someone who knows a candidate.
- **Redaction:** irreversible replacement of recognized sensitive content before persistence.
- **Replay:** deterministic state reconstruction from validated stored inputs without repeating
  side effects.
- **Safe projection:** stored lifecycle state after deliberate redaction and bounding.
- **`fsync`:** a request for the operating system to flush a file's current data to its storage
  durability boundary.

See the shared [project glossary](../glossary.md) for session, event, transcript, and terminal state.

## Further reading

- [CAH-011 user story](../../user-stories/cah-011-append-only-transcript.md)
- [Safety model: transcripts and privacy](../safety-model.md#transcripts-and-privacy)
- [Evaluation: replay and diagnosis](../evaluation.md#replay-and-diagnosis)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Vault Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
