# Safety Model

> Status: proposed overall MVP design with implemented incremental controls. CAH-022 hard-bounds the
> provider-session path, and CAH-023 makes that path available only through explicit, validated OpenAI
> selection. The launch still defaults to `MockSession`; this is not a sandbox or a claim that
> untrusted code can be executed safely.

Code Assist Harness places a model between a user and a local repository. Model output and
repository content are untrusted inputs. Safety therefore comes from defense in depth: bounded
capabilities, deterministic policy, informed approval, precondition checks, cancellation, and an
auditable event stream.

## Supported trust boundary

The MVP will run inside Ubuntu under WSL and operate on one explicitly selected workspace. It is a
personal, interactive tool. It does not initially provide container isolation, network tools,
unattended execution, Git mutation, native Windows support, or protection equivalent to an OS
sandbox.

The trusted computing base includes the installed harness, its user-level configuration, and the
person granting approvals. The model, provider output, repository instructions, file content, and
workspace configuration are untrusted. A repository may narrow permissions but may not declare its
own commands safe or broaden filesystem access.

## Approval model

| Requested action | Default behavior |
| --- | --- |
| Native bounded repository read | Automatic after validation and path policy |
| Structured edit batch | Show generated diff; require one batch approval |
| Subprocess command | Require one approval for that exact command |
| Network or privileged tool | Unavailable in the MVP |

Approval communicates user intent but is not the only defense. A prohibited command or
outside-workspace edit is denied before an approval prompt appears. The prompt must show the exact
normalized action, working directory, affected paths or diff, capability, and relevant risk.

Approvals are single-use and bound to an action digest. Any change to arguments, working directory,
edit content, paths, or preconditions requires a new decision. Rejection and cancellation are
explicit results returned to the agent loop; neither is treated as permission to retry silently.

## Policy evaluation order

Side-effect requests follow a fail-closed sequence:

1. Validate the tool name and Pydantic input model.
2. Normalize paths, arguments, and working directory.
3. Classify capabilities and reject unavailable classes.
4. Enforce workspace, symlink, and command policy.
5. Construct the exact review representation.
6. Obtain approval when required and bind it to the normalized action.
7. Recheck paths, file hashes, policy, and deadlines immediately before execution.
8. Execute through a bounded, cancellable executor.
9. Validate, redact, emit, and persist the audit result.

Unexpected conditions deny or fail the action. Policy code must not ask a model whether a request is
safe.

## Workspace and path safety

The runtime will receive its workspace explicitly; the launch directory is only the default
selected by the CLI. All model-facing paths are workspace-relative. Before access, the harness
resolves and normalizes the requested path, checks the closest existing ancestor, and rejects
traversal or symlink resolution outside the workspace.

Path checks must be repeated at execution time because files and symlinks can change after a
proposal. Edit operations also use content-hash or exact-content preconditions. A stale proposal
returns a conflict and never overwrites newer content. Tests must cover `..`, absolute paths,
symlinked files and directories, missing descendants under symlinks, and replacement races.

The host filesystem still has race conditions that path checks alone cannot eliminate. The design
should prefer descriptor-relative or atomic operations where practical and document residual risk.
Container-backed execution remains a future strengthening step.

## Command policy

The initial built-in policy permits only narrowly described validation command shapes. User-level
configuration may broaden or narrow those candidates. Workspace configuration may only narrow the
effective set. Every effective command still requires individual approval.

Commands use argument arrays and an explicit working directory. Shell strings, shell interpolation,
redirection, pipelines, and `shell=True` are prohibited. Policy compares normalized executable and
argument shapes, not a display string. Prohibited families, Git-mutating operations, network
clients, and privilege escalation remain denied even if the model asks and the user would otherwise
approve the presented request.

Approved tool subprocesses, unlike the TUI-supervised Python runtime, start from a minimal
environment allowlist rather than inheriting all parent variables. Provider credentials, tokens,
and unrelated secrets are removed. Output, runtime, and process count are bounded, and cancellation
terminates the launched process tree.

## Edit safety

Structured create, exact-replacement, and delete operations are collected into one batch. The
harness validates every operation and generates the unified diff. The user approves that whole diff,
not a model-authored summary. Before application, hashes and absence/existence preconditions are
checked again. The audit trail distinguishes proposed paths, approved paths, changed paths, and any
conflict or partial failure.

Git commits, branches, pushes, index changes, and other Git-state mutation are outside the MVP even
when they could technically be expressed as file or command operations.

## Cancellation and bounded work

Cancellation will be checked before provider calls, tool execution, edit application, and another
loop step. Since external work may finish concurrently, the session terminal-state guard ensures
exactly one completed, cancelled, or failed event wins.

CAH-022 implements four hard limits for provider-backed sessions: model-turn admission,
provider-work time, cumulative accepted UTF-8 output, and observed provider tool calls. The immutable
configuration is validated before use, while every allocated session owns a fresh tracker. Admission
is charged before `Provider.start()`, output before publication, and tool requests before parsing or
handling. The stable safe failure codes are `model_turn_limit_exceeded`,
`provider_work_deadline_exceeded`, `assistant_output_limit_exceeded`, and
`tool_call_limit_exceeded`; none includes configured values or provider content.

The monotonic provider-work deadline is captured at session allocation, before transcript setup and
observer attachment, and an independent watcher can start provider cancellation while an admitted
publication is blocked. An exact event/deadline tie belongs to the deadline. The already-admitted,
ordered, non-interleaved publication transaction still completes its wire/reducer/observer work; an
ordinary later failure does not roll back an earlier accepted view. The deadline is not a local
sink-latency bound.

Every provider cleanup await uses the session's one shared supervised cleanup task and a fixed
five-second local grace. A completed cleanup wins an exact cleanup/grace tie; otherwise the local
awaitable is cancelled and reaped and `provider_cleanup_failed` is emitted at most once without
replacing the selected terminal outcome. This requires provider awaitables to propagate task
cancellation and does not prove remote cleanup succeeded. File-size, search-result,
command-duration, whole-session, and later tool-execution limits remain future controls.

CAH-023 adds a narrower provider-network boundary, not a network tool. TypeScript and Python both
validate the explicit `openai` provider plus exact `gpt-5.6-luna` model, while Python
remains authoritative before SDK import. `OPENAI_API_KEY` is inspected only after that selection;
every other `OPENAI_*` setting is rejected so ambient routing, headers, or logging cannot silently
alter the request. The adapter fixes the official endpoint, disables environment proxy trust,
redirects, SDK retries, and background mode, and sets `store=false` for the request. Its closed failure
table never exposes SDK exceptions, bodies, headers, request IDs, model candidates, or credentials.

Each OpenAI operation lazily owns one client and stream. Natural termination and cancellation share
one shielded adapter cleanup task that attempts both closes, beneath the harness's five-second local
cleanup grace. A bounded cleanup failure records that release is unconfirmed; it does not claim remote
cleanup succeeded or replace the selected session outcome. Default validation uses SDK fakes with
network denied, and the live smoke requires explicit flags, the exact model, and a credential.

## Transcripts and privacy

Trusted lifecycle inputs—application-owned domain facts and validated session events—and explicitly
typed non-lifecycle evidence are append-only evidence, not raw debug capture. By default, session
transcripts live under the WSL XDG state directory, normally
`~/.local/state/code-assist-harness/transcripts/`, indexed by a stable workspace hash, session ID,
and random transcript ID rather than a personal path in the filename. Application directories are
`0700`; transcript and summary files are `0600`; each accepted record is flushed and fsynced.

Lifecycle records include user tasks, assistant text, validated session events, cancellation intent,
and the approval wait/resume facts introduced by CAH-010. The current writer emits transcript version
3, while replay accepts internally consistent versions 1, 2, and 3. Provider-backed tapes may contain
one `model.usage_observed` record with bounded JavaScript-safe token counts and, with healthy
persistence through terminal publication, exactly one `loop.limits_observed` record immediately
before the terminal session event. Loop evidence contains the four configured limits, harness-owned
counters, and an optional exhausted-limit enum, but no monotonic timestamp or raw provider value.
Writer and replay cross-check that enum against the exact adjacent terminal failure code, preventing
contradictory summaries; version 3 also rejects a reserved limit-failure code without the record. A
version-3 mock tape may omit it because `MockSession` does not use the provider path.

These typed observations are bounded local evidence, not protocol events, lifecycle inputs, billing
proof, or authority to admit more work; replay exposes them separately from session state, and
`--no-transcript` suppresses them with the rest of the local record. Typed tool metadata, tool
results, approval decision details, changed-file paths, and validation outcomes remain future fields;
the current summary reports those unavailable rather than inventing them. Raw provider payloads and
environment mappings are excluded. Values discovered under recognized secret-like environment names
and recognized credential syntax are redacted before a lifecycle input is persisted. Redaction is a
safety net, so producers should avoid emitting secrets in the first place.

The CLI implements `--no-transcript`, which disables local JSONL and summary files without changing
the event tape. It does not govern the adapter's separate `store=false` request setting or broader
provider-account retention controls. A first transcript failure becomes
one sanitized recoverable TUI warning, disables later persistence attempts for that process, and
cannot silently corrupt or rewrite session state.

These controls reduce accidental disclosure; they do not make the record encrypted, tamper-evident,
anonymous, or inaccessible to another process running as the same WSL user. User text can itself
contain identifying paths even when filenames do not. Redaction is a safety net rather than proof
that arbitrary encoded or transformed secrets are absent, and local retention/deletion remains the
user's responsibility.

## Threat-driven tests

At minimum, safety tests cover:

- Traversal and symlink escape before filesystem access.
- A workspace configuration attempting to broaden command policy.
- Shell metacharacters or unsupported command arguments.
- An approval replayed against a changed command or edit batch.
- A file changed between diff review and application.
- Rejected approval producing no side effect.
- Command timeout and cancellation terminating child processes.
- Secret-like values omitted or redacted from events, diagnostics, fixtures, and transcripts.
- Provider/model/environment/key rejection before SDK import, with fixed non-echoing diagnostics.

Passing these tests demonstrates the specified controls; it does not turn restricted host execution
into secure execution of arbitrary untrusted code.

## Implementation stories

### Future story — Enforce layered command policy

> As a user, I want built-in and user policy to bound commands while repositories may only narrow
> access so that untrusted workspace content cannot grant itself authority.

### Future story — Bind approvals to exact actions

> As a user, I want each decision tied to the command or edit I reviewed so that stale approvals
> cannot authorize changed work.

### Future story — Protect the workspace boundary

> As a user, I want traversal, symlinks, and stale edit targets checked at execution time so that
> tools cannot escape or overwrite newer content.

### Implemented in CAH-011 — Persist redacted lifecycle evidence

> As a learner, I want a local append-only record with a privacy opt-out so that I can study
> behavior without retaining raw provider or environment data.

The current implementation is described in [Transcripts and privacy](#transcripts-and-privacy).
Search, export, automated retention, tamper evidence, and centralized governance remain future work.

Each story is complete only with a no-side-effect failure test, actionable user-facing errors, and
validated transcript events for decisions and outcomes.
