# CAH-031 lesson: Register read-only tools

- **Unit:** CAH-031
- **Milestone:** M2 - Read-only coding assistant
- **Lesson status:** Planned
- **Implementation status:** Planned; no model-callable read registry exists yet
- **Story:** [CAH-031](../../user-stories/cah-031-register-read-tools.md)
- **Learning emphasis:** Core learning unit
- **Review focus:** Typed capability registration, complete instruction-scope metadata, and dispatch
  as the stable seam for local tools and a future MCP adapter
- **Visual companion:** None; the Markdown diagram is authoritative
- **Related architecture:** [Architecture](../architecture.md), [Tool system](../tool-system.md), and
  [Safety model](../safety-model.md)

> This lesson explains an accepted plan. Code blocks are pseudocode, not shipped evidence.

## Quick summary

CAH-031 puts the four native repository-read operations behind one immutable, typed registry,
extracts the execution-time canonical request scope plus every result-derived instruction scope from
a fully validated success, and projects its result into one bounded canonical JSON envelope. Its
main lesson is that a registry is a harness-owned capability boundary: it controls selection and
typed metadata, while tools retain validation and filesystem policy.

## Learning objectives

After this unit, you should be able to:

- distinguish registration, dispatch, execution, and policy;
- explain why only read capabilities enter the M2 registry;
- derive ordered `instruction_scopes` from exact validated result types without reusing a mutable
  request alias;
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

Another misconception is that every layer should repeat path parsing. CAH-031 receives an exact
native request type whose path already crossed CAH-024/026's 4,095-byte, 256-component, and
255-byte-name gate. The registry checks exact type only; CAH-039 owns provider-originated native
validation before dispatch.

Another common misconception is that a typed native result can be serialized automatically. A
later field might contain diagnostics or host data. Each `ReadTool` therefore has an explicit
allowlist projector, and the registry validates that projection before producing the compact
`{"result":...}` envelope.

A validated request path is also not proof of what access actually succeeded. Each `ReadTool` has a
pure `instruction_scopes` extractor that runs only after exact result validation. It starts with the
canonical request scope captured by the native operation's final access-time admission, then derives
owner directories from only the provider-visible path records in that typed result. Empty listings
and no-match searches still carry that first scope. The extractor never re-resolves the original
alias after dispatch. Known failures carry no tuple, so later instruction discovery cannot mistake a
rejected request or malformed result path for admitted evidence.

“Pure” is a reviewed property of the four closed harness implementations, not a capability Python
can discover after calling arbitrary plugin code. Static/import policy and interaction spies prove
the production extractors consult only their typed results, with no filesystem, network, provider,
environment, clock, or global-state access. Runtime validation can reject a raised,
malformed, duplicate, or over-bound return, but it cannot undo an arbitrary side effect or infer that
a structurally valid tuple is semantically reordered after the call. Closed production snapshots
prove the documented order; dynamic extractors remain out of scope.

The serialized `output_json` is data, not policy. The extractor never parses it. That distinction
matters for broad tools: if search returns an excerpt from `pkg/file.py`, the harness—not the model or
JSON text—adds `pkg` to the local scope tuple so applicable instructions can be loaded before replay.

## Key concepts

- **Descriptor:** bounded metadata about a tool, separate from its callable.
- **Capability:** the effect class the harness permits; M2 admits only `read_workspace`.
- **Typed dispatch:** exact name lookup followed by exact input- and result-type checks.
- **No duplicate path parser:** native request construction owns path admission; the registry does
  not reinterpret a typed request.
- **Instruction scopes:** ordered, content-suppressed local success metadata containing the
  execution-time canonical request scope first and exact-deduplicated result-owner paths; the tuple
  is absent from model-facing JSON and every failure.
- **Allowlisted projector:** tool-specific mapping from reviewed native result fields to a JSON-safe
  tree; no reflection or generic model dump.
- **Canonical success envelope:** compact sorted-key UTF-8 JSON, at most 65,536 bytes including
  escaping and the `{"result":...}` wrapper, with at most 64 object/list levels across that complete
  wrapper and the outer result object at depth 1.
- **Bounded projection walk:** iterative validation that detects cycles and charges every visited
  value/container, object-member name, and Unicode scalar against one 65,536-unit work budget. That
  count is a lower bound on encoded size, is never restarted for a subtree, and remains separate
  from the final 65,536-byte envelope limit.
- **Fail-closed registration:** duplicate names and non-read capability candidates invalidate the
  whole registry.
- **MCP adapter seam:** a possible future source/executor behind reviewed registry policy, not the
  owner of the agent loop.

## Architecture and design

```text
Ink TUI                     Python harness                         Provider
task/events only       CAH-038 definitions -----------------> advertised tools
    |                  CAH-032 carrier <---------------------- name + raw JSON
    |                  CAH-033 atomic response
    |                  CAH-039 catalog-bound preparation
    |                  CAH-034 guard
    |                           v
    |                  [CAH-031 read registry]
    |          exact bound entry + typed input/result + canonical scope
    |                           |
    |              +------------+-------------+
    |              v            v             v
    |       list/stat tools   read_file   search_text     Tool boundary
    |              +------------+-------------+
    |                           v
    |                  allowlisted projector
    |       local instruction scopes + canonical {"result":...}
    |                    |               |
    |     later CAH-025/030 merge   provider result later
    +---------------- final assistant text later    Evidence: none in CAH-031

Future MCP: catalog snapshot -> schema/name/capability re-admission -> generalized registry port
            -> remote execution mapping (not direct compatibility; never owns loop continuation)
```

The registry preserves deterministic order, rejects duplicate names atomically, and exposes no
mutation after construction. Its immutable `entries: tuple[ReadTool, ...]` is the sole ordered
inventory. Each `ReadToolDescriptor` has exact fields `name`, `description`, `input_model`,
`result_type`, and `capability`; later schema and argument bridges use that named `input_model`
instead of inventing a forwarding property. Exact lookup returns the registry-owned `ReadTool` object.
The descriptor name grammar is exactly `[a-z][a-z0-9_]{0,63}`. Name and description must be exact
built-in strings; O(1) 64/1,024-character gates run before regex, Unicode-scalar inspection, or
strict UTF-8 encoding, and description bytes are capped at 1,024 without normalization.
`dispatch_bound(read_tool, validated_input)` first verifies that exact object belongs to the same
registry; a same-shaped entry from a second registry raises
`ReadToolRegistryError(code="invalid_read_tool_binding", message="Read tool binding is invalid.")`
before either handler. This API accepts
no CAH-039 or provider type, so the dependency remains one-way. Dispatch then executes only an exact
typed input, validates the native result, derives the complete scope tuple from typed fields, calls
its allowlisted projector, and returns local content-suppressed scopes beside canonical JSON. Scopes
are never placed in that JSON.
CAH-038 creates model-facing definitions; CAH-032 reuses the envelope in bounded provider history;
CAH-039 admits the raw call into one prepared request; and CAH-034 later consumes that request plus
the local scope tuple for guarded dispatch, instruction discovery, merge, and result replay.

Runtime obtains this inventory only through
`build_read_tool_registry(metadata_reader, text_reader, searcher)`. The factory requires the
searcher's retained metadata/text readers to be those exact objects and all three services to retain
one policy identity before it binds handlers. A cross-wired or equal-but-distinct graph raises exact
`invalid_read_tool_registration` before descriptor construction, tool execution, or filesystem I/O.
Direct `ReadToolRegistry(entries)` remains useful for generic unit tests; it is not another M2 runtime
composition path.

## Practical walkthrough

1. Define a frozen descriptor and generic read-tool protocol.
2. Call the sole M2 factory with the exact shared metadata/text/search services; it constructs one
   registry from `list_files`, `stat_path`, `read_file`, and `search_text`.
3. Reject duplicates and every non-read capability before publishing the registry.
4. Resolve the exact registry-owned entry, then dispatch it only through that registry's
   `dispatch_bound` path with its exact validated input type.
5. Validate the declared result type before extracting scopes or projecting fields.
6. Start the scope sequence with the validated result's execution-time canonical request scope;
   append reviewed result-owner paths in native order and retain only the first occurrence of each
   exact label. Do not consult the original request alias.
7. Run the explicit projector, wrap it as `{"result":...}`, and iteratively validate the complete
   candidate. Count the outer object as depth 1, reject an object/list level above 64 or a cycle, and
   charge values/containers, member names, and Unicode scalars against one 65,536-unit work budget.
   Stop at the first over-limit contribution instead of visiting later siblings; because this count
   is a lower bound on encoded bytes, exhaustion is `read_tool_output_too_large`.
8. Serialize only an admitted candidate, require the inclusive 65,536-byte UTF-8 bound after
   escaping, and map a defensive serializer `RecursionError` or `ValueError` to the fixed invalid
   result.
9. Prove pre-dispatch rejection executes zero times and every failure exposes neither scopes nor
   invalid or oversized output.

## Implementation code samples

### Planned pseudocode: typed dispatch

```python
registry = build_read_tool_registry(metadata_reader, text_reader, searcher)
request = ReadFileRequest(path="current.py")  # internal alias to src/app.py at execution
read_file_entry = registry.lookup_exact("read_file")
success = registry.dispatch_bound(read_file_entry, request)
assert success.instruction_scopes == (
    "src/app.py",  # execution-time canonical request scope first
    "src",         # canonical result file's owner
)
assert success.output_json == (
    '{"result":{"end_line":1,"path":"src/app.py","returned_bytes":6,'
    '"source_bytes":6,"start_line":1,"text":"hello\\n",'
    '"total_lines":1,"truncated":false}}'
)
```

Construction establishes the closed capability set. Dispatch validates the typed result, derives the
ordered local tuple, and explicitly projects every shown JSON field. Sorted keys and compact
separators make output stable; content suppression keeps both scopes and JSON out of ordinary
representations. Search projection preserves CAH-029's fixed
`matches`, `candidate_bytes`, `listing` reason tuple and consistent `truncated` flag rather than
sorting or repairing native output. Integer projection is similarly closed: only signed 64-bit
values are admitted. The complete wrapped candidate may contain at most 64 object/list levels, with
the outer `result` object at depth 1. Its iterative walk charges each value/container, member name,
and Unicode scalar against the one 65,536-unit work budget, so an extremely wide value known to
exceed the later byte cap fails before the remaining siblings or serializer are reached.
Only an admitted candidate reaches `json.dumps`; a defensive serializer `RecursionError` or
`ValueError` becomes the fixed invalid-result failure instead of exposing interpreter behavior.

The other tools use the same rule with tool-specific typed paths:

```text
candidate 1: list/search result.canonical_request_scope or stat/read result.path
list_files: append directory entry itself or file entry parent, in result order
stat_path:  append result directory itself or result file parent
read_file:  append result file parent
search_text: append every match file parent, in match order
then keep the first occurrence of each exact label
```

The parent of a root-level file is `.`. Native result ceilings bound extraction before deduplication:
501 candidates for listing, 201 for search, and two for stat/read. CAH-025 later performs canonical
admission, so this pure registry step neither resolves aliases nor touches the filesystem. A later
retarget of `current.py` cannot change the captured first candidate. CAH-030 requires the discovered
bundle's `canonical_scope` to equal that candidate before merge; if the canonical label itself is
stale or retargeted at discovery, the transaction fails rather than falling back to the alias.

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
| foreign same-shaped entry | registry identity gate | fixed `invalid_read_tool_binding`; neither handler runs | two-registry identity test |
| unknown name | dispatcher | fixed failure, zero tool calls | spy-tool test |
| wrong input type | dispatcher | fixed failure before execution | parameterized type test |
| raising or malformed scope extractor | registry runtime invariant | no success and no scopes | extractor spy test |
| empty list/no-match search alias retarget | post-dispatch mutation | keep the execution-time canonical scope only | `alias -> A`, retarget to `B`, assert tuple `(A,)` and no alias lookup |
| 501st list entry or 201st search match | native/result bound | `invalid_read_tool_result`; no partial tuple | exact boundary tests |
| serialized JSON is mutated | scope ownership | typed scope tuple is unchanged | no-JSON-parsing spy test |
| wrong result type | dispatcher | fixed invariant failure after one call; no value escapes | bad-spy test |
| float/cycle/lone surrogate or complete-envelope depth 65 from projector | iterative projection validator | `invalid_read_tool_result`; no value escapes | table-driven values plus depth 63/64/65 |
| extremely wide projection exceeds the shared envelope/work budget | iterative projection validator | `read_tool_output_too_large`; stop before the sentinel sibling or serializer | visited-node and serializer-spy test |
| signed-64-bit overflow or serializer `RecursionError`/`ValueError` | projection validator/serializer guard | `invalid_read_tool_result`; no interpreter text | endpoint, 5,000-digit, and injected-failure tests |
| wrapped output above 65,536 bytes | output boundary | `read_tool_output_too_large`; no truncation | exact byte and native-max tests |
| write/network candidate | capability admission | structurally rejected | import/capability policy test |
| native read failure | native tool | preserve its bounded domain result | integration test |

The closed production extractor implementations also have static/import and interaction tests that
prove exact candidate order and no filesystem, policy, provider, alias-resolution, instruction, or
JSON calls. That evidence does not claim the registry can detect or roll back arbitrary effects, or
recognize a semantically reordered but structurally valid tuple, from injected Python code.

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
3. Derive the exact tuples for list directory/file entries, stat directory/file results, one read,
   and repeated search matches; include a root-level file and exact duplicates.
4. Retarget an empty-list or no-match alias after dispatch and explain why only the native result's
   canonical scope may lead instruction discovery.
5. Teach back the difference between a registry, an executor, and the agent loop.
6. Explain why a 65,536-byte native text result can exceed the 65,536-byte envelope limit.
7. Construct depth-64 and very wide result candidates. Explain why the first can be admitted while
   the second must stop before visiting every sibling even if Python could hold both values.
8. Sketch the re-admission steps an MCP-capable generalized registry port needs without letting it
   choose the next model turn.

## Key takeaways

- The Python harness owns the admitted tool catalog and dispatch decision.
- Exact names/types, success-only ordered instruction scopes, explicit projectors, canonical bytes,
  and read-only capability admission are the core invariants.
- MCP needs a future generalized and re-admitting registry port; it is neither direct compatibility
  nor a replacement for harness policy or orchestration.

## Glossary

- **Registry:** immutable mapping from reviewed tool names to implementations.
- **Dispatcher:** component that selects one registered implementation.
- **Capability:** classified effect a tool may perform.
- **Instruction scopes:** execution-time canonical request scope and typed result-owner paths retained
  in exact first-occurrence order only as local metadata on a successful read.
- **MCP:** protocol for connecting model applications to external context and tools.

## Further reading

- [CAH-031 delivery contract](../../user-stories/cah-031-register-read-tools.md)
- [Python protocols](https://docs.python.org/3/library/typing.html#typing.Protocol)
- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
