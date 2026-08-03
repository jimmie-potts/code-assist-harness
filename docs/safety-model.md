# Safety Model

> Status: proposed overall MVP design with implemented incremental controls. CAH-022 hard-bounds the
> provider-session path, and CAH-023 makes that path available only through explicit, validated OpenAI
> selection. CAH-024 through CAH-037 refine the read-only M2 boundaries but have not implemented
> them. The launch still defaults to `MockSession`; this is not a sandbox or a claim that untrusted
> code can be executed safely.

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
selected by the CLI. All model-facing paths are workspace-relative. CAH-024 will turn that existing
canonical root into an immutable Python boundary, resolve one relative target against a filesystem
snapshot, and reject absolute paths, traversal, or symlink resolution outside the workspace. It will
report an accepted target with a workspace-relative label and will not itself read the target.

That planned snapshot check is necessary but not execution-time authorization. Path checks must be
repeated when a later tool accesses a target because files and symlinks can change after validation
or a proposal. Edit operations also use content-hash or exact-content preconditions. A stale
proposal returns a conflict and never overwrites newer content. CAH-026 plans the non-overridable
deny/ignore policy, and CAH-027 through CAH-029 require access-time re-admission for listing, reads,
and search. Their tests cover missing descendants under symlinks and observable replacement races in
addition to the CAH-024 containment matrix.

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
five-second local grace. A completed cleanup wins an exact cleanup/grace tie. Otherwise the local
barrier task is cancelled and reaped, and the required provider force-reap hook cancels and awaits
every provider-owned local cleanup or SDK task without shielding. `provider_cleanup_failed` is emitted
at most once without replacing the selected terminal outcome. No local provider task remains after
force-reap, but resource release stays unconfirmed: this requires cancellation-responsive provider
code and does not prove remote cleanup succeeded. File-size, search-result, provider-request, and
multi-turn bounds are refined in CAH-026 through CAH-036 but remain unimplemented; command-duration
and side-effecting tool limits remain later controls.

CAH-023 adds a narrower provider-network boundary, not a network tool. TypeScript and Python both
validate the explicit `openai` provider plus exact `gpt-5.6-luna` model, while Python
remains authoritative before SDK import. `OPENAI_API_KEY` is inspected only after that selection;
every other `OPENAI_*` setting is rejected so ambient routing, headers, or logging cannot silently
alter the request. Both the supervised child and canonical `scripts/check` gate remove
`SSLKEYLOGFILE`; the child starts Python with `-E`, and direct adapter construction independently
rejects that TLS secret-export selector before client creation. The adapter
fixes the official endpoint, disables environment proxy trust, redirects, SDK retries, and background
mode, and sets `store=false` for the request. Its closed failure table never exposes SDK exceptions,
bodies, headers, request IDs, model candidates, or credentials. Assistant text preserves TAB/LF
layout but rejects every other C0/C1 control at the provider-domain boundary; the Python and
TypeScript wire validators repeat that check before text can enter terminal state.

M2 keeps tool-aware provider turns atomic: the harness buffers and validates the entire closed
response grammar before publishing text or dispatching a tool. Invalid or incomplete grammar has
no partial effect. Local native read handlers remain bounded synchronous calls, so cancellation and
deadline checks bracket execution rather than pretending to preempt and reap a running handler; a
result is discarded when cancellation wins. Provider-facing tool outcomes are canonical compact
JSON success-or-error envelopes capped at 65,536 bytes inclusive; oversize output is rejected rather
than truncated.

Explicit OpenAI selection authorizes bounded, policy-admitted repository context and read-tool
results to leave the local machine for that session. Deny/ignore policy is path-oriented, not
content-level secret scanning, so an otherwise admitted source file may contain sensitive text. The
user-facing selection path must state that residual risk; the mock path remains local and
network-free.

Each OpenAI operation lazily owns one client and stream. Natural termination and cancellation share
one shielded adapter cleanup task that attempts both closes, beneath the harness's five-second local
cleanup grace. A bounded cleanup failure records that release is unconfirmed; it does not claim remote
cleanup succeeded or replace the selected session outcome. An independently raised `CancelledError`
from a close coroutine is recorded as that bounded failure while both closes are still attempted;
cancellation of the cleanup owner itself remains control flow and stops the remaining sequential
closes. Ordinary joiners shield this owner, while grace expiry causes the session to cancel and reap it
through the required authoritative hook. Default validation uses SDK fakes with network denied, and
the live smoke requires explicit flags, the exact model, and a credential.

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

### Planned CAH-024 — Establish snapshot workspace containment

> As a user, I want every repository target interpreted relative to one canonical workspace so that
> a context operation cannot begin with an outside-workspace path.

CAH-024 introduces the immutable Python boundary and deterministic containment tests. It does not
perform filesystem access or eliminate time-of-check-to-time-of-use races.

### Planned CAH-026 through CAH-029 — Recheck workspace targets at read execution

> As a user, I want containment, symlinks, deny/ignore policy, type, and bounds rechecked at read time
> so that a prior path snapshot cannot silently authorize changed content.

[CAH-026](../user-stories/cah-026-define-repository-read-contracts.md) owns the shared admission
policy. It applies Git-compatible ignore rules independently to the normalized supplied path and the
resolved canonical target; each view requires every parent directory to remain traversable before a
leaf negation or nested policy can apply. Either view's ignored ancestor or target denies, so a
symlink alias cannot bypass policy on either name. [CAH-027](../user-stories/cah-027-list-files-and-stat-path.md),
[CAH-028](../user-stories/cah-028-read-bounded-text-file.md), and
[CAH-029](../user-stories/cah-029-search-repository-text.md) reuse it immediately before access and
return only fixed safe failures or bounded workspace-relative results. Edit-target preconditions
remain M3 work.

### Planned CAH-031 through CAH-037 — Keep tool authority in the harness

> As a user, I want model tool requests admitted through one typed registry and explicit bounded loop
> so that neither the provider nor an MCP transport can execute or continue work directly.

CAH-031 limits registration to four read capabilities and attaches harness-owned target-scope
metadata to successful reads. CAH-032 defines strict context/tool exchange
values, including a bounded positional opaque-continuation item type, without dispatch. CAH-033
admits a complete response before either publication or dispatch,
CAH-034 discovers and atomically admits applicable instructions for the successful target before its
follow-up, and CAH-035 generalizes that monotonic context rule only to four model
turns and three sequential calls with cumulative limits. CAH-036 requests
`reasoning.encrypted_content` on every stateless OpenAI turn so replay is available, but keeps that
opaque payload out of policy and evidence. CAH-037 explicitly composes the four-turn, 120-second,
4,096-byte, three-call M2 profile instead of inheriting defaults. A future MCP client must enter
through a generalized registry and separate remote-trust design; the local M2 registry is not a
direct MCP compatibility claim.

Repository instructions remain untrusted guidance. A discovered `AGENTS.md` can neither broaden read
policy nor turn a failed target into an admitted scope; discovery or context-budget failure stops
before result replay and another provider start.

### Implemented in CAH-011 — Persist redacted lifecycle evidence

> As a learner, I want a local append-only record with a privacy opt-out so that I can study
> behavior without retaining raw provider or environment data.

The current implementation is described in [Transcripts and privacy](#transcripts-and-privacy).
Search, export, automated retention, tamper evidence, and centralized governance remain future work.

Each story is complete only with a meaningful no-side-effect failure test, actionable fixed errors,
and the bounded event or transcript evidence required by the boundary it actually changes.
