# CAH-031 - Register and dispatch read-only tools

- **Status:** Planned
- **Milestone / epic:** M2 - Read-only coding assistant / E4 - Tool registry and controlled
  execution (read-only kernel only)
- **Dependencies:** CAH-027, CAH-028, CAH-029
- **Lesson:** [Read-tool registry](../docs/lessons/cah-031-read-tool-registry.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** How a harness separates tool capability, typed dispatch, and side-effect policy
  before any model can request a tool.

## User story

> As an agent-loop developer, I want the native repository-read tools behind one typed read-only
> registry so that later model tool calls can select a known capability without gaining an
> unreviewed execution path.

## Single responsibility

CAH-031 owns registration, typed dispatch, and one canonical bounded success-result projection for
the native read tools delivered by CAH-027 through CAH-029. It does not define model-facing input
schemas, parse provider arguments, execute an agent loop, expose tool activity through NDJSON, or
admit any side-effecting capability.

## Scope

- Define one generic, immutable registry of harness-owned read tools.
- Give every registered tool one stable name, description, typed input contract, typed result, and
  explicit `read_workspace` capability classification.
- Pair each tool with an explicit allowlisted native-result projector; after exact result-type
  validation, emit one compact canonical JSON success envelope for the later provider contract.
- Register `list_files`, `stat_path`, `read_file`, and `search_text` in one deterministic order.
- Dispatch an already-typed input to exactly one registered implementation.
- Reject duplicate names, unknown tools, mismatched input types, and every capability other than
  `read_workspace` before implementation code runs.
- Prove registry construction and dispatch with native fakes or temporary workspaces only.

## Locked contract

- The Python harness owns `ReadTool`, `ReadToolDescriptor`, and `ReadToolRegistry`; provider adapters,
  the TUI, and repository files cannot register or dispatch tools.
- A descriptor contains only a stable lower-snake-case name of at most 64 ASCII characters, a
  non-empty description of at most 1,024 UTF-8 bytes, the concrete validated input and result types,
  and the literal capability `read_workspace`. It contains no callable, JSON Schema, provider
  object, approval decision, or environment value.
- A `ReadTool` pairs one descriptor with one synchronous, bounded `execute(validated_input)`
  operation and one explicit `project_result(validated_result)` operation. The input has already
  passed the native tool's Pydantic validation; CAH-031 performs a defensive exact input-type check
  before execution and an exact result-type check before projection. Each of the four projectors
  names the allowed fields from its native result (and nested entry/match values) explicitly. It may
  not use a generic `model_dump`, dataclass reflection, `__dict__`, `repr`, or arbitrary-object JSON
  fallback that could expose a future field accidentally.
- Registry construction consumes an immutable tuple, preserves that order for discovery, and fails
  atomically on an invalid descriptor, duplicate name, or non-read capability. There is no
  last-registration-wins behavior and no mutation after construction.
- Dispatch uses exact, case-sensitive name lookup. Unknown names and input-type mismatches return a
  bounded harness-owned dispatch failure without invoking any tool or echoing the supplied name or
  input. Successful dispatch returns an immutable `ReadToolSuccess` whose content-suppressed
  `output_json` is the canonical envelope specified below; the unprojected native result does not
  cross this registry boundary.
- Tool-domain operational failures remain the native tool's bounded result or exception contract;
  the registry neither catches programmer defects as tool results nor converts filesystem content
  into diagnostics.
- The M2 registry contains exactly the four native operations delivered by CAH-027 through CAH-029.
  Filesystem
  writes, subprocesses, network access, MCP servers, provider-hosted tools, and dynamically imported
  plugins are structurally inadmissible.
- This is the sole intentional E4 overlap in M2: it teaches registry ownership but does not implement
  general policy composition, approvals, executors, write capabilities, or extension loading.

### Canonical bounded success projection

- `project_result` returns a finite, acyclic tree containing only JSON `null`, booleans, integers,
  Unicode-scalar strings, lists, and objects with Unicode-scalar string keys. Floats (including
  finite floats, NaN, and infinities), bytes, tuples, sets, non-string keys, duplicate logical keys,
  arbitrary objects, cycles, and lone surrogates are invalid tool results.
- The registry wraps the projected tree exactly as `{"result": <projected>}` and serializes it with
  Python `json.dumps(..., ensure_ascii=False, separators=(",", ":"), sort_keys=True,
  allow_nan=False)`. A pre-serialization walk enforces the allowlist, so the serializer is not an
  implicit object converter. No Unicode normalization or content redaction occurs at this layer.
- The UTF-8 encoding of the complete wrapped envelope may contain at most 65,536 bytes. The limit is
  inclusive and applies after JSON string escaping, keys, punctuation, and the outer `result`
  wrapper have been added. A value above the bound fails completely; the registry never truncates a
  string, list, object, or serialized envelope.
- Projector failures, unsupported values, non-scalar strings, and result-type drift use
  `invalid_read_tool_result`. An otherwise valid projection above 65,536 bytes uses the distinct
  fixed oversize failure. Ordinary exception and result representations never include the native
  result, projected tree, or serialized output.
- This projection is the model-facing success envelope reused by CAH-032. Native read limits and the
  envelope limit are independent: a valid `ReadFileResult` at its native 65,536-byte text maximum
  can exceed 65,536 bytes after metadata and JSON wrapping and must fail rather than be trimmed.

### Fixed, non-leaking registry failures

`ReadToolRegistryError` contains exactly one stable code and fixed message. It never includes the
candidate name, arguments, result, type representation, workspace path, or implementation error.

| Code | Fixed message | Used when |
| --- | --- | --- |
| `invalid_read_tool_registration` | `Read tool registration is invalid.` | a descriptor, duplicate, or capability candidate is invalid |
| `unknown_read_tool` | `Read tool is not available.` | exact lookup finds no registered name |
| `invalid_read_tool_input` | `Read tool input is invalid.` | the validated input type does not match the descriptor |
| `invalid_read_tool_result` | `Read tool returned an invalid result.` | an implementation violates its declared result type |
| `read_tool_output_too_large` | `Read tool output exceeds the byte limit.` | a valid canonical success envelope exceeds 65,536 UTF-8 bytes |

## Reviewability budget

- **Estimated production-code churn:** 450-600 changed lines.
- **Delivered production-code churn:** Not started.
- **Counted paths:** additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
- If fitting the four operations from the three existing handler stories requires changing their
  filesystem behavior or public result
  contracts, split that work instead of expanding this story.
- **Excluded from count:** tests, documentation, fixtures, lockfiles, and generated artifacts.
- The range is a review estimate, not a quota; do not pad a smaller coherent implementation.

## Acceptance criteria

1. One immutable registry exposes the four native read operations in deterministic order.
2. Every descriptor is typed, documented, bounded, uniquely named, and classified only as
   `read_workspace`.
3. Exact-name dispatch invokes one implementation once with the exact validated input, validates
   its declared result type, runs only that tool's explicit allowlisted projector, and returns the
   exact canonical `{"result":...}` success envelope.
4. Duplicate names, unknown names, wrong input types, wrong result types/projector values,
   side-effecting capability candidates, and oversized projections use fixed non-leaking failures;
   every pre-dispatch rejection executes no implementation and no rejected output escapes.
5. Registry code imports no provider SDK, protocol model, subprocess surface, network client, MCP
   client, or write-tool implementation.
6. Focused tests cover construction, ordering, each dispatch path, exact canonical snapshots,
   scalar/container rejection, and every byte boundary without credentials or network access.

## Acceptance-to-test matrix

| Acceptance | Required evidence |
| --- | --- |
| 1-2 | Unit tests assert exact ordered descriptors, immutability, uniqueness, and capability values. |
| 3 | Parameterized tests dispatch one typed request to each native tool and snapshot the exact UTF-8 `{"result":...}` string, including sorted nested keys, compact separators, unescaped multibyte scalars, and every explicitly projected field. |
| 4 | Spy tools prove duplicate, unknown, wrong-input, and non-read candidates execute zero times; wrong-result/projector spies execute once but leak no value; tables reject floats, bytes, tuples, non-string keys, cycles, and lone surrogates with exact safe failures. |
| 4, 6 | Byte tests accept a complete envelope at 65,536 bytes, reject 65,537 with `read_tool_output_too_large`, and prove that a valid native read at its 65,536-byte text maximum fails when JSON metadata/wrapping pushes the envelope over the bound; no truncation or content appears in the failure. |
| 5 | Repository-policy/import test denies provider, subprocess, network, MCP, and write surfaces from the registry module. |
| 6 | The focused suite and canonical non-live gate pass with the network guard enabled. |

## Validation

- Add focused registry unit tests using deterministic spies and the native tool fixtures.
- Assert exact canonical snapshots for all four operations and prove a different dictionary
  insertion order produces byte-identical output.
- Assert values and failure representations do not reveal supplied arguments, workspace paths,
  native/projected results, or serialized tool output. Include the native-maximum/wrapped-overflow
  regression and exact 65,536/65,537-byte envelope boundaries.
- Run Python type, lint, format, and focused tests, then `TMPDIR=/tmp UV_CACHE_DIR=/tmp/uv-cache
  ./scripts/check`.

## Documentation impact

Update the architecture, safety model, glossary, backlog, story index, and linked Markdown lesson.
The lesson emphasizes the registry as a harness policy boundary and contrasts native registration
with a future MCP registry adapter. Do not add or revise a presentation.

## Exclusions

- Model-facing input definitions, JSON Schema generation, JSON argument parsing, provider error
  envelopes, or provider history messages. This story owns only the shared canonical success
  envelope.
- Agent-loop turns, retries, parallel calls, protocol/TUI tool events, or transcript content.
- Direct MCP compatibility, MCP clients or servers, remote/hosted tools, plugins, dynamic imports,
  writes, subprocesses, approvals, and general E4 policy composition. A future generalized registry
  port must snapshot and re-admit a remote catalog, filter names/schemas, classify remote/network
  capability, map MCP `structuredContent`, `outputSchema`, and `isError`, and own authentication,
  timeouts, and cancellation; an MCP server cannot plug directly into this local read registry.

## Definition of done

- All acceptance criteria have direct automated evidence, including a meaningful no-execution
  failure path, four exact output snapshots, and native-maximum envelope overflow.
- Public APIs are typed and documented; fixed failures and representations are content-safe.
- Production-code churn is at or below 600 lines and the final diff is reviewed for one
  responsibility.
- The story and concise Markdown lesson are verified against implementation, with a compact
  architecture diagram and no presentation changes.
- Focused checks and the canonical repository gate pass; the completed unit is published through
  the repository's review workflow.

## Planned evidence

- A focused registry module and tests proving immutable registration, deterministic discovery, typed
  dispatch, and fail-closed capability admission.
- Repository-policy evidence that registration cannot open a provider, network, subprocess, MCP, or
  write path.
- A lesson that makes the registry-versus-executor and native-tool-versus-MCP distinctions explicit.

## Deferred work

- CAH-032 adds provider-neutral tool definitions, calls, results, and strict fake support.
- CAH-033 admits one complete tool-aware response without parsing or dispatch. CAH-034 is the first
  unit allowed to parse an admitted model tool request and dispatch through this registry.
- General E4 policy, approvals, side effects, MCP adapters, and dynamic extension loading remain
  later milestones.
