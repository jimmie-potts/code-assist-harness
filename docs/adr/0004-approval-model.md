# ADR 0004: Separate read, edit, and command approval behavior

- **Status:** Accepted
- **Date:** 2026-07-13
- **Decision scope:** Human approval, policy, and workspace side effects

## Context

The MVP must inspect a repository fluently while preventing a model from silently changing files
or running programs. Requiring approval for every bounded file read would make ordinary repository
discovery unusable. Treating one broad approval as permission for later edits or commands would
hide material changes from the user. Approval alone is also insufficient: a model or an untrusted
repository should not be able to make an unrelated or destructive command acceptable merely by
asking persuasively.

File edits present an additional race. The user must review the exact proposed outcome, and an
approval must not overwrite content changed after the proposal was created.

## Decision

The policy model distinguishes native repository reads, edit batches, and subprocess commands.

### Native repository reads

Bounded native Python tools such as `list_files`, `read_file`, `search_text`, and `stat_path` may
run automatically. They are still subject to schema validation, workspace-boundary checks,
symlink-safe path resolution, ignored-directory rules, file-size limits, and output limits.

Filesystem inspection is not implemented by invoking shell utilities. A request that uses a
subprocess, including `git status`, follows the subprocess rules even when its purpose is read-only.

### Edit batches

The model proposes structured exact-replacement, create, or delete operations. It does not supply
an authoritative patch for direct application. The harness:

1. validates every operation and path;
2. captures file hashes and other preconditions;
3. computes the unified diff for the complete batch;
4. presents that unchanged batch for one approval decision;
5. verifies all preconditions immediately before any write; and
6. follows a documented multi-file failure contract or reports a conflict without overwriting
   newer content.

One approval covers the displayed edit batch only. Any change to paths, operations, expected
content, or resulting diff creates a new action and requires a new approval. Rejection causes no
filesystem mutation and is returned to the loop as a structured result.

### Subprocess commands

Every subprocess invocation requires an individual approval, including familiar validation and
read-only commands. Before it may be presented for approval, it must satisfy the effective command
policy.

- Commands are executable-and-argument arrays, never shell strings.
- Built-in policy defines the initial safe candidates.
- User configuration may broaden or narrow those candidates.
- Workspace configuration may narrow policy but cannot silently broaden it.
- Prohibited command families remain denied even if the user attempts to approve them through the
  ordinary approval interaction.
- The prompt shows exact arguments, working directory, and risk classification.

The initial allowlist is small and centered on documented Python and TUI validation commands. Git
state mutation, network access, shell interpolation, and privileged execution are prohibited in
the MVP.

## Approval identity and audit

Each approval request is bound to a stable digest or equivalent identity of the fully normalized
action. A response can authorize only that identity and active session. Stale, repeated, or
mismatched responses cannot authorize changed work.

The transcript records the proposed action metadata, policy classification, approval request,
decision, and executed outcome. Sensitive values and unbounded tool results are redacted or
bounded before becoming events. Approval presentation is owned by the TUI; authorization and
identity checks are owned by Python.

## Consequences

### Benefits

- Repository inspection remains fluid while side effects remain visible.
- The user approves the exact generated diff rather than a model's description of it.
- Hash preconditions prevent approved proposals from overwriting newer changes silently.
- A strict allowlist provides defense even when the model asks for a dangerous command and the user
  is inattentive.
- Configuration owned by an untrusted workspace cannot grant itself more authority.

### Costs and risks

- Frequent command approvals add friction to validation-heavy workflows.
- Structured edit operations require careful conflict, encoding, and partial-failure handling.
- Path and symlink validation is security-sensitive and needs adversarial tests.
- Approval identity and normalization must be stable across rendering and execution.

The friction is accepted for the learning-first MVP. Broader or remembered approvals may be
considered only after audit evidence demonstrates a safe, comprehensible design.

## Alternatives considered

### Require approval for every tool

Rejected because repeated approval for bounded native reads would obstruct context discovery
without controlling a meaningful side effect.

### Approve all commands for a session or command family

Rejected because a broad approval would conceal changed arguments and reduce the user's control.

### Rely on approval without an allowlist

Rejected because human confirmation is only one defense and an untrusted repository must not be
able to redefine arbitrary commands as safe.

### Accept arbitrary patch text from the model

Rejected for the MVP because structured operations are easier to validate, bind to file
preconditions, render consistently, and explain educationally.

## Implementation status

This is an accepted target decision. At acceptance time, the repository had no tools, policy
engine, approvals, edit representation, or command executor. CAH-004 introduces only the protocol
foundation; approval and side-effect behavior arrives in the controlled coding-agent milestones.
