# Safety Model

> Status: proposed design. These controls describe the intended MVP and are not yet a sandbox or a
> claim that untrusted code can be executed safely.

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

The child environment starts from a minimal allowlist rather than inheriting all parent variables.
Provider credentials, tokens, and unrelated secrets are removed. Output, runtime, and process count
are bounded, and cancellation terminates the launched process tree.

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
loop step. Provider calls and executors will receive cancellation signals and deadlines. Since
external work may finish concurrently, the session terminal-state guard ensures exactly one
completed, cancelled, or failed event wins.

Turn, tool-call, output, file-size, search-result, command-duration, and session-duration limits
constrain both mistakes and deliberate abuse. A limit failure identifies the exact limit without
including sensitive data.

## Transcripts and privacy

Validated events will be append-only evidence, not raw debug capture. By default, session
transcripts will live under the WSL XDG state directory, normally
`~/.local/state/code-assist-harness/`, indexed by a stable workspace identifier rather than a
personal path in the filename. Files should use restrictive local permissions.

The event stream may include user tasks, assistant text, bounded tool metadata and results, approval
decisions, changed-file paths, and validation outcomes. It excludes raw provider payloads and
environment values. Configured sensitive values and recognized credentials are redacted before an
event is persisted. Redaction is a safety net, so producers should avoid emitting secrets in the
first place.

Before the first real-provider release, the CLI must offer a documented `--no-transcript` mode.
Transcript failure is visible to the user and cannot silently corrupt or rewrite session state.

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

### Future story — Persist redacted audit evidence

> As a learner, I want a local append-only record with a privacy opt-out so that I can study
> behavior without retaining raw provider or environment data.

Each story is complete only with a no-side-effect failure test, actionable user-facing errors, and
validated transcript events for decisions and outcomes.
