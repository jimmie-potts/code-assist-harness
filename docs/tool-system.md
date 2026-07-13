# Tool System

> Status: proposed design. No model-callable workspace or subprocess tools are implemented yet.

Tools are typed capabilities exposed by the Python harness. The model may request a tool, but the
harness validates, authorizes, executes, bounds, and records it. This separation keeps model output
from becoming direct filesystem or process authority.

## Tool definition contract

Every registered tool must document and encode:

| Field | Required meaning |
| --- | --- |
| Name | Stable model-facing identifier |
| Purpose | Narrow behavior and when the model should use it |
| Input schema | Pydantic v2 model accepted at the model boundary |
| Output schema | Structured success and failure result model |
| Capability | `read`, `write`, `command`, `network`, or `privileged` |
| Approval | Whether and at what granularity approval is required |
| Filesystem access | Allowed roots, path behavior, and mutation behavior |
| Process/network behavior | Whether a subprocess or network can be reached |
| Timeout | Hard execution deadline and timeout result |
| Output limits | Byte, item, line, or match bounds |
| Cancellation | How cooperative and forced cancellation work |
| Expected failures | Stable codes for common invalid or failed operations |
| Security considerations | Trust boundaries and known residual risks |

The registry will eventually use this metadata for provider schemas, policy decisions, audit events,
and TUI help. Documentation is part of the definition rather than a separate best-effort page.

## Registration and dispatch

A registry maps a unique name to its definition and executor. Dispatch follows a fixed order:

1. Reject an unknown tool name.
2. Parse and validate arguments without performing work.
3. Classify the requested capability.
4. Evaluate workspace and command policy.
5. Create an approval request when the action requires one.
6. Bind approval to the exact normalized action.
7. Revalidate mutable preconditions immediately before execution.
8. Execute with cancellation, time, and output bounds.
9. Validate and emit the structured result and audit events.

Unsupported arguments are errors rather than ignored hints. Provider-supplied JSON never reaches an
executor as an unvalidated dictionary. An invalid request yields a structured result the loop can
return to the model; it does not crash the session.

## Read tools

`list_files`, `read_file`, `search_text`, and `stat_path` are native Python tools. They are
classified as reads and may execute automatically after policy validation. They never invoke a
shell, access the network, or escape the workspace. Their outputs are bounded and carry source
provenance. More detail appears in [Context Engineering](context-engineering.md).

## Edit proposals

The model does not overwrite a file or submit arbitrary patch text in the MVP. It requests a batch
of structured exact operations:

- Create a file with specified content and an absent-file precondition.
- Replace an exact expected region with new content.
- Delete a file with an expected-content or content-hash precondition.

The edit service validates every path and precondition, computes one unified diff for the complete
batch, and emits an approval request. One approval covers exactly that displayed batch. Immediately
before applying, the harness verifies that files still match their proposal hashes. A mismatch
returns a conflict and leaves the changed file untouched. Partial application must not be reported
as full success; the implementation story must choose and document transactional behavior for
multi-file failure.

The generated diff is review material, not executable input. Approval is bound to a digest of the
normalized operations and relevant preconditions so a changed action cannot reuse a stale approval.

## Command execution

Every subprocess command requires its own approval, including apparently safe commands such as
`git status`, `pytest`, and `ruff`. A command must also satisfy the configured allowlist; approval
alone cannot override policy.

Commands are represented as argument arrays, for example:

```json
{
  "argv": ["uv", "run", "pytest"],
  "cwd": "."
}
```

Shell strings, interpolation, `shell=True`, pipelines, redirection, and command substitution are
prohibited. The executor uses an explicit workspace-relative working directory, a minimal sanitized
environment, a deadline, bounded stdout and stderr capture, and cancellation that terminates the
whole launched process tree. Tool results distinguish exit failure, timeout, cancellation, policy
denial, and output truncation.

An executor interface will isolate process lifecycle from tool dispatch. The first executor is a
restricted WSL host process. A future container executor may implement the same interface without
changing the agent loop or tool definitions.

## Result and audit model

Tool results will be data, not formatted console logs. A result contains the tool-call ID, outcome,
stable status or failure code, bounded data, timing, truncation flags, and safe explanatory text.
Sensitive environment values and raw provider payloads are never included.

Audit events record the normalized request, policy decision, approval decision when applicable,
execution start, and result. For edits they also identify proposed and actually changed paths. For
commands they record the exact argument array and working directory. The transcript stores these
validated, redacted events.

## Implementation stories

### Future story — Register typed tools

> As a harness developer, I want every model-callable tool registered with validated schemas and
> capability metadata so that dispatch and policy are predictable.

Complete this story when unknown tools, malformed arguments, duplicate names, and result validation
have deterministic tests.

### Future story — Execute bounded commands

> As a user, I want approved validation commands run without a shell and within strict bounds so
> that I can inspect results without granting arbitrary process authority.

Complete this story when allowlist denial, per-command approval, timeout, cancellation, environment
sanitization, and output truncation are tested.

### Future story — Propose and apply an edit batch

> As a user, I want to review one harness-generated diff before a structured edit batch is applied
> so that file changes are exact and informed.

Complete this story when rejection causes no changes, stale files cause conflicts, approval cannot
authorize a changed batch, and the audit stream matches actual file state.

### Future story — Define an executor port

> As a harness maintainer, I want process execution behind a narrow interface so that stronger
> isolation can be introduced without changing orchestration.

Complete this story with a fake executor and restricted host implementation; a container backend is
explicitly later scope.
