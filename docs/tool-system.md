# Tool System

> Status: proposed design with the read-only M2 seam refined through CAH-039 in documented dependency
> order. No model-callable workspace or subprocess tool is implemented yet.

Tools are typed capabilities exposed by the Python harness. The model may request a tool, but the
harness validates, authorizes, executes, bounds, and records it. This separation keeps model output
from becoming direct filesystem or process authority.

## Generalized tool documentation target

Every production tool must document the following operational contract. A later generalized registry
may encode the normalized parts needed for provider schemas, policy decisions, audit events, and TUI
help; the table is not the exact CAH-031 descriptor shape.

| Field | Required meaning |
| --- | --- |
| Name | Stable model-facing identifier |
| Purpose | Narrow behavior and when the model should use it |
| Input schema | Strict portable model schema plus native Pydantic v2 request model |
| Output schema | Structured success and failure result model |
| Capability | M2 uses exact `read_workspace`; later side-effect/network classes require their own design |
| Approval | Whether and at what granularity approval is required |
| Filesystem access | Allowed roots, path behavior, and mutation behavior |
| Process/network behavior | Whether a subprocess or network can be reached |
| Timeout | Hard execution deadline and timeout result |
| Output limits | Byte, item, line, or match bounds |
| Cancellation | How cooperative and forced cancellation work |
| Expected failures | Stable codes for common invalid or failed operations |
| Security considerations | Trust boundaries and known residual risks |

CAH-031 intentionally encodes only `name`, `description`, `input_model`, `result_type`, and exact
`read_workspace` capability. The closed native read contracts document filesystem behavior, limits,
cancellation, failures, and security considerations without expanding that implementation unit into
the future generalized policy registry. Documentation remains part of the tool contract rather than
a best-effort page.

## Registration and dispatch

A registry maps a unique name to its definition and executor. Model-provided dispatch follows a
fixed order; unknown-tool lookup deliberately wins before any argument decoding:

1. Reject an unknown tool name.
2. Iteratively preflight the complete, at-most-16,384-byte argument payload with a
   quote-and-escape-aware delimiter scanner. Count the root object as structural depth 1, reject
   mismatched containers or depth above 64, and admit numeric tokens only when they use signed 64-bit
   JSON integer grammar without a fraction or exponent, all before Python integer conversion.
3. Pair-decode exactly one JSON object with a rejecting `parse_constant` callback for `NaN`,
   `Infinity`, and `-Infinity`.
4. Walk the preserved pairs iteratively and reject a repeated decoded member name at every admitted
   object depth before constructing a dictionary.
5. Require its exact advertised key set before a native model can apply defaults.
6. Validate native field types and constraints with Pydantic.
7. Verify the prepared catalog and exact registry-entry object identities without running a handler.
8. Classify the requested capability.
9. Evaluate workspace and command policy.
10. Create an approval request when the action requires one.
11. Bind approval to the exact normalized action.
12. Revalidate mutable preconditions immediately before execution.
13. Call the registry's provider-independent `dispatch_bound(entry, validated_input)` exactly once;
    that is the execution point and it retains cancellation, time, and output bounds.
14. Cross the post-dispatch guard, then validate and emit the structured result and audit events.

For M2 provider calls, CAH-039 alone owns steps 1 through 6 and returns either one
content-suppressed, catalog-entry-bound prepared invocation or one fixed safe error. Its immutable
catalog factory accepts only the CAH-031 registry and calls CAH-038's definition bridge internally;
callers cannot inject a second definition tuple. The catalog owns that exact CAH-031 registry identity and
re-exposes the bridge-produced definitions advertised in every request. CAH-034 consumes that same
catalog, crosses the cooperative pre-dispatch guard, performs step 7, and reaches step 13 exactly
once through `dispatch_bound`; there is no earlier or second execution. Catalog construction has
already fixed step 8 to `read_workspace`. CAH-026 and the closed native handler own repository policy
and access-time revalidation for steps 9 and 12, while approval steps 10-11 are not applicable to M2
reads. CAH-034 then crosses the post-dispatch guard and owns result/enrichment/replay. Future
write/command units must fill the explicit capability, policy, approval, and precondition stages
before the same single execution point. Neither orchestration nor a provider adapter imports a
second registry, scanner, decoder, duplicate walk, exact-key gate, or Pydantic argument path.
CAH-032 construction and provider adapters first enforce the carrier's tool-name shape and 16-KiB
argument byte bound. A malformed or above-limit carrier never invokes CAH-039; its tests begin with
admitted carriers and still exercise the exact at-limit value.

Native path fields use one earlier contract rather than a CAH-039-specific parser:
CAH-024 admits at most 4,095 strict-UTF-8 bytes, 256 normalized non-dot components, and 255 UTF-8
bytes per component, and CAH-026 maps that failure for repository consumers. For a known call this
check occurs at CAH-039's existing strict-Pydantic stage and becomes `invalid_read_tool_input` before
dispatch. Unknown lookup, raw JSON admission, duplicate rejection, and exact-key precedence remain
unchanged. A CAH-038 `maxLength: 4095` is only a coarse character hint because JSON Schema length is
not a UTF-8-byte count.

Unsupported or duplicate arguments are errors rather than ignored hints. Duplicate equality is exact
after JSON escape decoding, without case folding or Unicode normalization. Provider-supplied JSON
never reaches an executor as an unvalidated dictionary. An invalid request yields a structured result
the loop can return to the model; it does not crash the session. Trusted direct Python callers may
still use the unchanged native request models and their defaults; that does not make an advertised model-facing
field optional. The 16,384-byte ceiling is one aggregate bound for the complete serialized argument,
not a fresh allowance per subtree; quote-contained braces and brackets do not consume structural
depth, while objects and arrays both do. Structural or numeric preflight failure, rejected constants,
and defensive decoder `RecursionError`/`ValueError` all become `invalid_read_tool_input` without
parser or interpreter text.

## Read tools

`list_files`, `read_file`, `search_text`, and `stat_path` are native Python tools. They are
classified as reads and may execute automatically after policy validation. They never invoke a
shell, access the network, or escape the workspace. Their outputs are bounded and carry source
provenance. More detail appears in [Context Engineering](context-engineering.md).

Each registered M2 read tool also owns one pure, typed `instruction_scopes` extractor over its exact
validated success result. The execution-time canonical request scope captured by final native
admission is first; it survives empty-list and no-match success. In provider-visible result order,
`list_files` then adds each directory or file parent, `stat_path` adds the returned directory or file
parent, `read_file` adds the returned file parent, and `search_text` adds every match-file parent.
Exact labels are deduplicated by first occurrence; later CAH-025 admission and CAH-030 merge handle
repeated owner snapshots. This ordered tuple and the dedicated list/search canonical-scope fields are
content-suppressed harness control-plane metadata, never model-facing result JSON. The original
request alias is not consulted after dispatch. A known failure carries no scopes. The loop must
discover every scope and require each returned instruction bundle's `canonical_scope` to exactly
equal that captured scope before atomic merge and successful-result replay. There is no alias
fallback; one unsafe, invalid, changed, or over-budget scope rejects the whole candidate transaction.
CAH-030 retains each binding's canonical-depth precedence rank, and CAH-032 copies that exact value
instead of deriving it from tuple position or closing legal gaps. Native result limits bound
extraction to 501 candidates for listing and 201 for search before exact deduplication.

CAH-031's canonical model-facing result projection admits a finite, acyclic JSON tree and restricts
every integer to the signed 64-bit range before decimal conversion. The complete wrapped envelope
admits at most 64 object/list levels, with the outer `result` object at depth 1. An iterative walk
detects cycles and, before sorting or serialization, charges every visited value/container,
object-member name, and Unicode scalar against one 65,536-unit work budget; it stops at the first
over-limit contribution rather than traversing the rest of a wide value. Canonical output is
separately capped at 65,536 UTF-8 bytes inclusive. Only an admitted tree reaches canonical
serialization. A defensive serializer `RecursionError` or `ValueError` maps to
`invalid_read_tool_result`; it cannot expose interpreter text or partially emit the result envelope.

CAH-038's flat portable schema boundary is bounded before copying or serialization. It checks fixed
mapping/list cardinalities in O(1), caps each enum at 256 values, constructs a new shape-directed copy
under one non-resetting 16,384-unit visit/scalar budget, and incrementally emits at most 16,384 UTF-8
bytes. It never applies a generic `deepcopy` or serialize-then-measure pass to an untrusted direct/fake
schema; cyclic, deep, huge-string, and over-wide values fail before sorting or encoding. Production
schema generation is restricted to the exact four native Pydantic model identities. Expected root or
property `title` and property `default` annotations are charged and omitted only inside the bounded
shape-directed pass—never by a generic recursive pre-pass—and all other generator drift fails closed.

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
native read operations through an immutable typed registry and derives their complete ordered local
instruction scopes only after exact success-result validation. Duplicate registration candidates,
unknown names, wrong inputs, wrong results, and raising or invalid scope extraction fail with fixed
non-leaking errors. The four production extractors are a closed trusted set whose purity is checked
statically and through interaction tests; runtime validation does not claim it can detect or undo an
arbitrary side effect. General E4 policy and dynamic extension remain M3 or later.

### Planned CAH-032 — Define the provider-neutral tool contract

> As an agent-loop developer, I want selected context, definitions, opaque continuation, calls, and
> results represented without provider or MCP types so that adapters cannot become the orchestrator.

The [implementation-ready story](../user-stories/cah-032-define-provider-tool-contract.md) defines
exact positional continuation/call/result history, context projection, request bounds, and strict-fake
behavior. Before decoding a result, it iteratively preflights the complete envelope with
a quote-and-escape-aware scanner, one incremental 65,536-byte/work budget, and a 64-level structural
ceiling whose outer object is depth 1. An iterative decoded-value walk and guarded canonical
serialization map defensive decoder or serializer `RecursionError`/`ValueError` to a fixed,
content-suppressed failure. Each continuation is one bounded item in the same ordered history, not an
adapter side channel; multiple call turns may each contribute one. The story does not parse or
dispatch a call. Every directly projected provider string must be an exact built-in `str` and pass an
O(1) character ceiling before UTF-8, escaping, or JSON-encoder entry; exact tuple counts for
conversation, legacy instructions, repository context, and tools are likewise gated before
iteration. Only that shape-admitted request reaches the incremental
512-KiB projection, so an encoder cannot first materialize an unbounded caller string.

### Planned CAH-038 and CAH-039 — Bound definitions and admit arguments

The [definition-canonicalization story](../user-stories/cah-038-canonicalize-provider-tool-definitions.md)
owns the strict portable schema subset, signed-64-bit schema integers, bounded shape-directed copying,
canonical serialization, and registry-to-definition bridge. The
[argument-admission story](../user-stories/cah-039-admit-provider-tool-arguments.md) owns exact-name
lookup and the complete ordered raw-JSON/preflight/pair-decode/duplicate/exact-key/Pydantic boundary.
Its registry-only factory invokes CAH-038 internally, binds one exact CAH-031 registry to the
resulting definition tuple, supplies those definitions to requests, and returns a same-entry
prepared invocation or fixed error without
dispatching.

### Planned CAH-033 — Admit one complete tool-aware response

The [response-admission story](../user-stories/cah-033-stage-and-validate-tool-aware-response.md)
buffers a provider turn and validates its complete closed grammar before exposing final text or one
tool-call request. A normalized provider failure can end any valid nonterminal prefix while
discarding its stage and preserving only its bounded classification. Premature EOF, mixed output,
and multiple calls cause neither text publication nor tool dispatch.

### Planned CAH-034 and CAH-035 — Prove one exchange, then iterate

The [one-round-trip story](../user-stories/cah-034-run-one-read-tool-round-trip.md) makes the entire
request/call/validate/dispatch/result/response flow visible using one canonical compact JSON result
envelope already bounded by CAH-031/032 to 65,536 bytes, 64 complete-envelope object/list levels, and
one non-resetting traversal-work budget. It consumes CAH-039's prepared-or-error handoff once, then
owns guarded native dispatch, result validation, instruction enrichment, compact replay, and the
follow-up transition. Oversize output fails instead of being truncated. Every execution-time
canonical request or result-derived instruction scope is discovered, scope-matched, merged, guarded,
and budgeted before successful-result replay. The
[bounded-loop story](../user-stories/cah-035-run-bounded-agent-loop.md) replaces
that teaching branch with a sequential four-turn, three-call state machine. Synchronous native tools
are bounded and non-preemptive. Before dispatch, after each synchronous dispatch/discovery/merge
stage, and before provider start, one shared seam unconditionally yields outside locks and then runs
the existing cancellation/deadline guard. Candidate results, context, history, and requests remain
uncommitted until the final guard; the seam makes pending cancellation observable but does not reap
an in-flight handler. CAH-037's planned composition root supplies
that four-turn/three-call profile explicitly while retaining the 120-second and 4,096-byte CAH-022
values; it does not inherit bare `LoopLimits()` defaults.

### Planned CAH-036 — Map OpenAI Responses function calls

The [implementation-ready story](../user-stories/cah-036-map-openai-tool-calls.md) maps the same
definitions, full stateless history, calls, results, and selected context through the strict OpenAI
adapter. Full replay under `store=false` reconstructs every required field from each accepted
canonical reasoning-item envelope—even with `current_turn` reasoning context—and applies the
reviewed null-to-omitted-input mapping for each optional `content` and `status` field. Every request
sets exactly `include=["reasoning.encrypted_content"]`, including turn one, so the API returns the
opaque payload needed for any later replay. It disables parallel calls,
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
