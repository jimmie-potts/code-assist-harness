# CAH-031 lesson: Register read-only tools

- **Unit:** CAH-031
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; no model-callable read registry exists yet
- **Story:** [CAH-031](../../user-stories/cah-031-register-read-tools.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Typed capability registration, target-scope metadata, and dispatch as the stable
  seam for local tools and a future MCP adapter
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Architecture](../architecture.md), [Tool system](../tool-system.md), and
  [Safety model](../safety-model.md)

> This lesson explains an accepted plan. Code blocks are pseudocode, not shipped evidence.

## Quick summary

CAH-031 puts the four native repository-read operations behind one immutable, typed registry,
extracts each successful request's local target scope, and projects its result into one bounded
canonical JSON envelope. Its main lesson is that a registry is a harness-owned capability boundary:
it controls selection and typed metadata, while tools retain validation and filesystem policy.

## Learning objectives

After this unit, you should be able to:

- distinguish registration, dispatch, execution, and policy;
- explain why only read capabilities enter the M2 registry;
- trace pure `target_scope` extraction from validated input to local success metadata;
- trace exact-name typed dispatch without provider SDK types; and
- explain why explicit result projectors are safer than reflection; and
- contrast this local registry with a future generalized MCP-capable registry port.

## Why this unit matters

Without one registry, every agent-loop branch could invent its own name lookup or bypass tool
policy. CAH-031 creates one narrow seam before provider arguments and iterative orchestration are
introduced.

## Junior engineer foundation

A registry is a map from a stable name to a known implementation. It is not permission to run
arbitrary code. A typed dispatcher receives an already-validated request of the tool's exact input
type:

```text
"read_file" + ReadFileRequest  -> accepted
"read_file" + SearchTextRequest -> rejected before execution
```

A common misconception is that a model-provided tool name is equivalent to a function pointer. It
is untrusted text until the harness finds an exact registered name and validates the input.

Another common misconception is that a typed native result can be serialized automatically. A
later field might contain diagnostics or host data. Each `ReadTool` therefore has an explicit
allowlist projector, and the registry validates that projection before producing the compact
`{"result":...}` envelope.

A validated path is also not yet proof that access succeeded. Each `ReadTool` has a pure
`target_scope` extractor that returns its validated `request.path`, but the registry attaches that
local metadata only to a fully successful result. Known failures carry no scope, so later instruction
discovery cannot mistake a rejected target for an admitted one.

## Key concepts

- **Descriptor:** bounded metadata about a tool, separate from its callable.
- **Capability:** the effect class the harness permits; M2 admits only `read_workspace`.
- **Typed dispatch:** exact name lookup followed by exact input- and result-type checks.
- **Target scope:** content-suppressed local success metadata copied exactly from validated
  `request.path`; it is absent from model-facing JSON and every failure.
- **Allowlisted projector:** tool-specific mapping from reviewed native result fields to a JSON-safe
  tree; no reflection or generic model dump.
- **Canonical success envelope:** compact sorted-key UTF-8 JSON, at most 65,536 bytes including
  escaping and `{"result":...}` wrapper.
- **Fail-closed registration:** duplicates and side-effect candidates invalidate the whole registry.
- **MCP adapter seam:** a possible future source/executor behind reviewed registry policy, not the
  owner of the agent loop.

## Architecture and design

```text
Ink TUI                     Python harness                         Provider
task/events only       round trip / loop (CAH-034/035)      tool name + JSON
    |                           |                                    |
    |                           v                                    |
    |                  [CAH-031 read registry] <---------------------+
    |          exact name + typed input/result + pure target_scope
    |                           |
    |              +------------+-------------+
    |              v            v             v
    |       list/stat tools   read_file   search_text     Tool boundary
    |              +------------+-------------+
    |                           v
    |                  allowlisted projector
    |          local target scope + canonical {"result":...}
    |                    |               |
    |     later CAH-025/030 merge   provider result later
    +---------------- final assistant text later    Evidence: none in CAH-031

Future MCP: catalog snapshot -> schema/name/capability re-admission -> generalized registry port
            -> remote execution mapping (not direct compatibility; never owns loop continuation)
```

The registry preserves deterministic order, rejects duplicate names atomically, and exposes no
mutation after construction. Dispatch extracts the exact typed path without effects, validates the
native result, calls its allowlisted projector, and returns both local content-suppressed scope and
canonical JSON. Scope is never placed in that JSON. CAH-032 creates model-facing definitions and
reuses only the envelope; CAH-034 later consumes local scope for instruction discovery and merge.

## Practical walkthrough

1. Define a frozen descriptor and generic read-tool protocol.
2. Construct one registry from `list_files`, `stat_path`, `read_file`, and `search_text`.
3. Reject duplicates and every non-read capability before publishing the registry.
4. Dispatch only an exact registered name with its exact validated input type.
5. Extract exact `request.path` without resolution or effects; attach it only if execution succeeds.
6. Validate the declared result type, run its explicit projector, and validate the projected JSON
   tree.
7. Wrap it as `{"result":...}` and enforce the inclusive 65,536-byte UTF-8 bound after escaping.
8. Prove pre-dispatch rejection executes zero times and every failure exposes neither scope nor
   invalid/oversized output.

## Implementation code samples

### Planned pseudocode: typed dispatch

```python
registry = ReadToolRegistry((list_files, stat_path, read_file, search_text))
request = ReadFileRequest(path="src/app.py")
success = registry.dispatch("read_file", request)
assert success.target_scope == "src/app.py"  # local and suppressed from repr/JSON
assert success.output_json == (
    '{"result":{"end_line":1,"path":"src/app.py","returned_bytes":6,'
    '"source_bytes":6,"start_line":1,"text":"hello\\n",'
    '"total_lines":1,"truncated":false}}'
)
```

Construction establishes the closed capability set. Dispatch copies the exact validated path,
validates the typed result, and explicitly projects every shown JSON field. Sorted keys and compact
separators make output stable; content suppression keeps both scope and JSON out of ordinary
representations.

### Planned pseudocode: side-effect rejection

```python
with raises(ReadToolRegistryError):
    ReadToolRegistry((read_file, write_file_candidate))
assert write_file_candidate.calls == 0
```

The important assertion is not only the error: no candidate runs while registry construction is
being decided.

## Failure scenarios to study

| Scenario | Owner | Safe result | Planned evidence |
| --- | --- | --- | --- |
| duplicate name | registry construction | reject the complete registry | duplicate-name unit test |
| unknown name | dispatcher | fixed failure, zero tool calls | spy-tool test |
| wrong input type | dispatcher | fixed failure before execution | parameterized type test |
| invalid/effectful scope extractor | registry invariant | no success and no scope | extractor spy test |
| wrong result type | dispatcher | fixed invariant failure after one call; no value escapes | bad-spy test |
| float/cycle/lone surrogate from projector | projection validator | `invalid_read_tool_result`; no value escapes | table-driven projector tests |
| wrapped output above 65,536 bytes | output boundary | `read_tool_output_too_large`; no truncation | exact byte and native-max tests |
| write/network candidate | capability admission | structurally rejected | import/capability policy test |
| native read failure | native tool | preserve its bounded domain result | integration test |

## Production expansion

### Example enterprise scenario

A production platform may combine built-in tools, organization plugins, and remote MCP servers.
MCP is not directly plug-compatible with this local registry. A generalized port would snapshot and
re-admit the catalog, filter names and schemas, classify remote/network capability, map
`structuredContent`, `outputSchema`, and `isError`, and own authentication, timeouts, cancellation,
health, and revocation.

### Typical production capabilities and tools

- [Python protocols](https://docs.python.org/3/library/typing.html#typing.Protocol) model structural
  tool interfaces cheaply, but runtime validation still belongs to the harness.
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/) provide strict input
  validation at the cost of schema/version maintenance.
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture) standardizes remote
  capability discovery and invocation, adding transport, authentication, and trust operations.
- [pluggy](https://pluggy.readthedocs.io/en/stable/) supports plugin registration and hooks, adding
  extension lifecycle and compatibility governance.

These are comparisons, not approved dependencies.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Catalog | four static native operations | versioned local and remote catalogs |
| Capability | read-only, fixed | policy-composed capability classes |
| Dispatch | in-process exact lookup | isolation, health, auth, and routing |
| Operations | deterministic tests | catalog telemetry and revocation |
| Cost | low cognitive load | platform and governance ownership |

### Trade-offs and graduation signals

The static registry is easy to audit but cannot discover remote tools. Graduate when users need a
reviewed external capability, and only after trust, credentials, cancellation, timeouts, and evidence
are designed.

## Practical exercises

1. Explain why duplicate-name rejection is safer than last-registration-wins.
2. Write tests proving a wrong input executes zero tool code and a wrong result never escapes.
3. Prove one successful path is local metadata but absent from JSON/repr, while a known failure has
   no scope.
4. Teach back the difference between a registry, an executor, and the agent loop.
5. Explain why a 65,536-byte native text result can exceed the 65,536-byte envelope limit.
6. Sketch the re-admission steps an MCP-capable generalized registry port needs without letting it
   choose the next model turn.

## Key takeaways

- The Python harness owns the admitted tool catalog and dispatch decision.
- Exact names/types, success-only target scope, explicit projectors, canonical bytes, and read-only
  capability admission are the core invariants.
- MCP needs a future generalized and re-admitting registry port; it is neither direct compatibility
  nor a replacement for harness policy or orchestration.

## Glossary

- **Registry:** immutable mapping from reviewed tool names to implementations.
- **Dispatcher:** component that selects one registered implementation.
- **Capability:** classified effect a tool may perform.
- **Target scope:** validated request path retained only as local metadata on a successful read.
- **MCP:** protocol for connecting model applications to external context and tools.

## Further reading

- [CAH-031 delivery contract](../../user-stories/cah-031-register-read-tools.md)
- [Python protocols](https://docs.python.org/3/library/typing.html#typing.Protocol)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
