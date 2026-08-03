# Tool System

> Status: proposed design with the read-only M2 seam refined through CAH-026 to CAH-036. No
> model-callable workspace or subprocess tool is implemented yet.

Tools are typed capabilities exposed by the Python harness. The model may request a tool, but the
harness validates, authorizes, executes, bounds, and records it. This separation keeps model output
from becoming direct filesystem or process authority.

## Tool definition contract

Every registered tool must document and encode:

| Field | Required meaning |
| --- | --- |
| Name | Stable model-facing identifier |
| Purpose | Narrow behavior and when the model should use it |
| Input schema | Strict portable model schema plus native Pydantic v2 request model |
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

A registry maps a unique name to its definition and executor. Model-provided dispatch follows a
fixed order:

1. Reject an unknown tool name.
2. Decode exactly one JSON object without performing work.
3. Require its exact advertised key set before a native model can apply defaults.
4. Validate native field types and constraints with Pydantic.
5. Classify the requested capability.
6. Evaluate workspace and command policy.
7. Create an approval request when the action requires one.
8. Bind approval to the exact normalized action.
9. Revalidate mutable preconditions immediately before execution.
10. Execute with cancellation, time, and output bounds.
11. Validate and emit the structured result and audit events.

Unsupported arguments are errors rather than ignored hints. Provider-supplied JSON never reaches an
executor as an unvalidated dictionary. An invalid request yields a structured result the loop can
return to the model; it does not crash the session. Trusted direct Python callers may still use the
unchanged native request models and their defaults; that does not make an advertised model-facing
field optional.

## Read tools

`list_files`, `read_file`, `search_text`, and `stat_path` are native Python tools. They are
classified as reads and may execute automatically after policy validation. They never invoke a
shell, access the network, or escape the workspace. Their outputs are bounded and carry source
provenance. More detail appears in [Context Engineering](context-engineering.md).

## Function calling and MCP

Function calling is the model-facing loop grammar: advertise tool definitions, receive a typed call,
run harness-owned dispatch, return one correlated result, and ask the model to continue. The
provider adapter translates this exchange but never executes the tool or decides whether it is safe.
M2 keeps the first grammar deliberately serial: a model turn may request exactly one tool, and the
next admitted turn receives that one result. Multiple, parallel, or mixed text-and-tool responses
fail closed until a later unit defines their ordering and accounting.

The Model Context Protocol (MCP) solves a related but different problem: discovering and invoking
tools offered by another process or service. The deliberately narrow M2 registry is not directly
MCP-compatible: it admits four local synchronous read handlers, a strict schema subset, and one
canonical JSON result envelope. A later generalized registry port may let an MCP client snapshot
and re-admit a trusted server catalog, filter or translate broader schemas and result shapes, and
classify remote network authority. M2 does not connect to an MCP server. Server trust,
authentication, network policy, dynamic catalogs, structured or multimodal result validation, and
remote cancellation require their own threat model and implementation stories.

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

### Planned CAH-031 — Register typed read tools

> As a harness developer, I want every model-callable tool registered with validated schemas and
> capability metadata so that dispatch and policy are predictable.

The [implementation-ready story](../user-stories/cah-031-register-read-tools.md) admits exactly four
native read operations through an immutable typed registry. Duplicate or side-effecting candidates,
unknown names, wrong inputs, and wrong results fail with fixed non-leaking errors. General E4 policy
and dynamic extension remain M3 or later.

### Planned CAH-032 — Define the provider-neutral tool contract

> As an agent-loop developer, I want selected context, definitions, calls, and results represented
> without provider or MCP types so that adapters cannot become the orchestrator.

The [implementation-ready story](../user-stories/cah-032-define-provider-tool-contract.md) defines
the strict portable schema subset, exact call/result history, context projection, request bounds,
registry-to-definition bridge, pre-Pydantic exact-key gate, and strict-fake behavior. It does not
parse or dispatch a call.

### Planned CAH-033 — Admit one complete tool-aware response

The [response-admission story](../user-stories/cah-033-stage-and-validate-tool-aware-response.md)
buffers a provider turn and validates its complete closed grammar before exposing final text or one
tool-call request. A normalized provider failure can end any valid nonterminal prefix while
discarding its stage and preserving only its bounded classification. Premature EOF, mixed output,
and multiple calls cause neither text publication nor tool dispatch.

### Planned CAH-034 and CAH-035 — Prove one exchange, then iterate

The [one-round-trip story](../user-stories/cah-034-run-one-read-tool-round-trip.md) makes the entire
request/call/validate/dispatch/result/response flow visible using one canonical compact JSON result
envelope capped at 65,536 bytes inclusive. Model-facing keys are admitted before Pydantic defaults;
oversize output fails instead of being truncated. The
[bounded-loop story](../user-stories/cah-035-run-bounded-agent-loop.md) replaces
that teaching branch with a sequential four-turn, three-call state machine. Synchronous native tools
are bounded and non-preemptive: cancellation and deadline checks bracket execution, and a result is
discarded if cancellation wins while the handler runs. CAH-037's planned composition root supplies
that four-turn/three-call profile explicitly while retaining the 120-second and 4,096-byte CAH-022
values; it does not inherit bare `LoopLimits()` defaults.

### Planned CAH-036 — Map OpenAI Responses function calls

The [implementation-ready story](../user-stories/cah-036-map-openai-tool-calls.md) maps the same
definitions, full stateless history, calls, results, and selected context through the strict OpenAI
adapter. Full replay under `store=false` reconstructs every required field from each accepted
canonical reasoning-item envelope—even with `current_turn` reasoning context—and applies the one
reviewed null-content-to-omitted-input mapping. Every request sets exactly
`include=["reasoning.encrypted_content"]`, including turn one, so the API returns the opaque payload
needed for any later replay. It disables parallel calls,
rejects hosted/MCP tool types, and leaves dispatch and continuation decisions in the harness. Explicit
OpenAI selection authorizes
bounded admitted repository-content egress for that session; it is not content-level secret
scanning.

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
