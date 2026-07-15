# CAH-011 lesson: Append-only transcript

- **Unit:** CAH-011
- **Milestone:** M1 - Conversational core
- **Lesson status:** Planned
- **Implementation status:** Planned; no transcript writer or session summary exists yet
- **Story:** [CAH-011](../../user-stories/cah-011-append-only-transcript.md)
- **Related architecture:** [Architecture](../architecture.md),
  [Safety model](../safety-model.md), and [Evaluation](../evaluation.md)

> This lesson combines accepted persistence and privacy decisions with a planned implementation.
> It does not describe behavior currently available in the repository.

## Quick summary

This unit plans a local JSONL transcript that appends each validated session event after redaction.
It teaches the difference between authoritative in-memory state, durable evidence, and a readable
summary while preserving an explicit privacy opt-out.

## Learning objectives

After completing this unit, you should be able to:

- explain why validated domain events, rather than raw provider data, form the audit record;
- preserve event order without making persistence the owner of session state;
- design redaction, restrictive permissions, flushing, and failure reporting as one boundary; and
- compare a local append-only file with durable, governed production event storage.

## Why this unit matters

Later evaluation and replay work needs evidence of what the harness accepted and displayed. Without
a transcript, an unexpected exit erases the diagnostic trail; without redaction and opt-out, that
trail can become a privacy problem. CAH-011 also proves that persisted lifecycle data can
reconstruct the same terminal reducer state without re-running a provider or tool. Content
intentionally redacted or bounded before storage is not recoverable through replay.

## Key concepts

- **Append-only JSONL:** one complete validated event is added per line; earlier lines are never
  rewritten during the session.
- **Event evidence:** the transcript records harness-domain facts, not SDK responses, environment
  dumps, or arbitrary stderr output.
- **Redaction boundary:** every persistable value crosses one policy that removes configured secrets
  and bounds large content before bytes are written.
- **Replay:** validating stored events and applying them to the reducer reconstructs the terminal
  lifecycle state and persisted safe fields. Replay never repeats side effects or recovers content
  removed by redaction or bounding.
- **Human-readable summary:** a derived artifact reports task, outcome, changed files, and checks,
  using honest empty values when a capability is not yet available.

## Architecture and design

```text
validated ordered event
        |
        +--> session reducer (authoritative live state)
        |
        +--> redaction and bounding --> JSONL append --> flush
                                      --> final summary
```

Python owns validation, redaction, file creation, append order, and storage errors. The TUI may
display a persistence error, but it does not write or reinterpret the record. Planned files live
under `$XDG_STATE_HOME/code-assist-harness/`, falling back to the documented WSL XDG location.
A stable workspace identifier avoids exposing a personal path in the filename.

Important invariants:

- only validated session events are eligible for persistence;
- file order matches accepted session-event order;
- files use restrictive local permissions and never contain raw provider payloads or environment
  values;
- `--no-transcript` changes persistence only, not session behavior;
- a write failure is visible but cannot recursively try to record itself or rewrite the session's
  terminal outcome; and
- a complete transcript replays deterministically to the same terminal lifecycle state, while
  intentionally redacted or bounded fields retain their stored safe representation.

## Practical walkthrough

1. Define an injected transcript configuration with enabled state and XDG state root. Tests should
   use a temporary root rather than a real home directory.
2. Derive a stable workspace identifier from the canonical workspace path, but place only the
   identifier and session ID in filenames.
3. Create the transcript with owner-only permissions before accepting appends. Make file-opening
   semantics explicit so a race cannot silently relax them.
4. Pass each validated event through one pure redaction-and-bounding function. Seed tests with fake
   keys and assert that neither exact values nor raw payload containers survive.
5. Serialize one compact JSON object plus `\n`, append in sequence, and flush at a documented
   cadence. A killed test process should leave a valid JSONL prefix.
6. Derive the completion summary from validated state after a terminal event. Do not infer changed
   files or checks that no story has produced.
7. Route storage exceptions to a non-recursive structured error path while leaving the reducer's
   valid terminal result untouched.
8. Run replay, permissions, redaction, failure-injection, summary, and opt-out tests from the story.

The useful observation is not merely that a file exists. It is that stored bytes correspond to
accepted events, survive a controlled interruption, omit seeded secrets, and reproduce the expected
terminal lifecycle state without claiming to recover removed content.

## Failure scenarios to study

| Scenario | Observable symptom | Safe outcome and evidence |
| --- | --- | --- |
| Disk fills during append | Persistence reports a write or flush failure | Prior JSONL lines remain valid; one non-recursive error is visible; reducer outcome is unchanged |
| Secret appears in tool output | Raw value approaches the persistence boundary | Generated transcript and snapshots contain no seeded secret; bounded replacement is recorded |
| Process exits between events | Transcript ends before the session terminal event | The retained prefix parses line by line and is never presented as a complete session |
| Transcript disabled | No state artifacts are created | Session event sequence and terminal state match the enabled run |
| Corrupt line is replayed | Validation fails at a known line | Replay stops explicitly and does not trust or execute later content |

## Production expansion

### Example enterprise scenario

Imagine an internal coding service used by 250 engineers across regulated repositories. Security
needs role-based access, legal holds, regional retention, encryption-key rotation, searchable audit
events, and proof that records were not overwritten. A laptop JSONL file cannot supply those
durability and governance guarantees.

### Typical production capabilities and tools

These links illustrate capabilities, not endorsed dependencies:

- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
  represents a common structured event model for central collection and correlation.
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
  illustrates write-once retention and legal-hold capabilities for immutable archives.
- [Vault Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
  illustrates centrally governed encryption, signing, and key rotation without storing plaintext
  application data in the key service.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | One user and one WSL process | Many users, workspaces, regions, and support teams |
| Durability | Flushed local JSONL prefix | Replicated storage, backups, integrity checks, recovery objectives |
| Privacy | Local redaction and `--no-transcript` | Data classification, access control, consent, deletion, and legal holds |
| Search | Direct file inspection and replay | Indexed queries with tenant and retention boundaries |
| Operations | Structured local error and tests | Central telemetry, alerts, runbooks, and audit review |
| Cost | Minimal services and cognitive load | Storage, indexing, key management, governance, and on-call ownership |

### Trade-offs and graduation signals

Central storage improves durability, discovery, and governance but increases privacy exposure,
operational responsibility, and cost. Graduate when multiple users need shared history, a retention
or compliance requirement exceeds local control, transcript loss violates a recovery objective, or
support cannot diagnose incidents from user-owned files. Do not graduate merely because a hosted
logging product exists.

## Practical exercises

1. Write a test that appends three fake validated events, replays them, and compares reducer state.
2. Inject a writer that fails on the third flush; prove the first two lines parse and no recursive
   persistence attempt occurs.
3. Seed user text and tool metadata with a fake token in several encodings and inspect the resulting
   transcript and summary.
4. Run equivalent enabled and disabled configurations and compare all non-persistence events.
5. Draft a retention policy for the enterprise scenario and identify data the application should
   avoid emitting even when encryption is available.

## Key takeaways

- Python owns transcript validation and persistence; the transcript does not own session truth.
- Store ordered, redacted domain events and preserve an explicit no-storage path.
- Local JSONL is inspectable and sufficient for learning; centralized immutable storage is justified
  only by measured sharing, durability, or governance needs.

## Glossary

- **Append-only:** new records are added without changing earlier session records.
- **JSONL:** one JSON value per line, suitable for incremental writes and line-by-line recovery.
- **Redaction:** removal or replacement of sensitive values before persistence.
- **Replay:** deterministic state reconstruction from validated events without repeating effects.
- **Retention:** rules governing how long records remain available and when they may be deleted.
- **WORM:** write-once-read-many storage that prevents protected versions from being overwritten.

See the shared [project glossary](../glossary.md) for session, event, transcript, and terminal state.

## Further reading

- [CAH-011 user story](../../user-stories/cah-011-append-only-transcript.md)
- [Safety model: transcripts and privacy](../safety-model.md#transcripts-and-privacy)
- [Evaluation: replay and diagnosis](../evaluation.md#replay-and-diagnosis)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)
- [Vault Transit secrets engine](https://developer.hashicorp.com/vault/docs/secrets/transit)
