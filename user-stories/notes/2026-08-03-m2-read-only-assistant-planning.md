# 2026-08-03 M2 read-only assistant planning

## Purpose

Refine the M2 outcome into dependency-ordered, implementation-ready units without hiding the agent
loop inside a framework or turning one review into a repository-wide rewrite. This note records the
cross-epic split, learning priorities, review-size policy, and decisions that let CAH-024 through
CAH-037 proceed independently.

## Milestone outcome

M2 is complete only when the Python harness can use scoped repository instructions and bounded native
read tools to produce a grounded explanation or implementation plan through both the deterministic
fake and the explicitly selected OpenAI adapter.

```text
task + scoped instructions
        |
        v
Python-owned loop -> provider-neutral tool request -> typed read registry -> workspace reads
        ^                                                        |
        +--------------- bounded result + provenance ------------+
        |
        v
final assistant explanation or plan + redacted evidence
```

The existing Ink stream renders the final answer. M2 does not add approval, write, subprocess,
network, remote-MCP, structured-plan, or rich tool-activity UI behavior.

## Human-decision audit

No unresolved product or architecture decision blocks refinement:

- M2 already promises an agent that can inspect, explain, and plan, so filesystem primitives without
  a model-callable loop would not satisfy the milestone.
- ADRs already assign the loop, context selection, tool validation, policy, and terminal outcome to
  Python while the TUI remains a projection.
- Native reads are already automatic only after validation, containment, ignore policy, and hard
  bounds; side-effecting capabilities remain approval-gated later work.
- The provider port already represents a serialized tool request but deliberately rejects it. The
  next units can extend that harness-owned seam without importing OpenAI or MCP types into core APIs.

The generic registry kernel is introduced in M2 because model-callable reads must not bypass typed
validation and dispatch. E4/M3 still owns write and command capabilities, layered policy, approvals,
executors, and side-effect audit behavior. Epics describe ownership; dependency-ordered vertical
slices may cross an epic boundary when the milestone outcome requires the seam.

## Learning priority

Stories are delivered in dependency order, but review emphasis is not uniform:

- **Core learning units** receive the closest review, fuller exercises, and explicit teach-back on
  system ownership, context engineering, provider-response grammar, tool calling, the agent loop,
  safety, or evaluation.
- **Supporting implementation units** remain independently tested and documented, but their lessons
  stay shorter when they primarily implement an already-reviewed contract.

The individual filesystem handlers are supporting units. The workspace and instruction boundaries,
read policy, context builder, registry, provider-neutral exchange, atomic response admission,
one-round and iterative loops, OpenAI mapping, and end-to-end evaluation are core learning units.

## Dependency-ordered story map

| Order | Story | Primary epic | Learning emphasis | Review focus | Estimated production churn |
| ---: | --- | --- | --- | --- | ---: |
| 16 | CAH-024 - Establish the workspace boundary | E3 | Core | Containment ownership and residual check/use risk | 250-400 |
| 17 | CAH-026 - Define repository read contracts and policy | E3 | Core | Capability, ignore, secret-path, and limit policy | 300-450 |
| 18 | CAH-025 - Discover scoped repository instructions | E3 | Core | Instruction scope, provenance, applicability, and untrusted guidance | 350-500 |
| 19 | CAH-027 - List files and inspect path metadata | E3 | Supporting | Deterministic enumeration through the shared policy | 350-500 |
| 20 | CAH-028 - Read one bounded text file | E3 | Supporting | Exact excerpts, encoding, and access-time recheck | 300-450 |
| 21 | CAH-029 - Search repository text literally | E3 | Supporting | Bounded native search and stable result order | 400-550 |
| 22 | CAH-030 - Build budgeted repository context | E3 | Core | Selection priority, provenance, and omission evidence | 475-600 |
| 23 | CAH-031 - Register and dispatch read-only tools | E4 | Core | Typed capability registry and fail-closed dispatch | 450-600 |
| 24 | CAH-032 - Define the provider-neutral tool contract | E2 | Core | LLM context, tool definitions, calls, results, and correlation | 450-600 |
| 25 | CAH-033 - Stage and validate one tool-aware response | E2 | Core | Atomic response grammar and admission before publication or dispatch | 350-500 |
| 26 | CAH-034 - Run one read-tool round trip | E2 | Core | One explicit request-call-execute-result-response cycle | 450-600 |
| 27 | CAH-035 - Run the bounded agent loop | E2 | Core | Loop state, stopping, cancellation, and cumulative limits | 350-500 |
| 28 | CAH-036 - Map OpenAI Responses tool calls | E2 | Core | Strict SDK-event translation and opaque continuation replay | 450-600 |
| 29 | CAH-037 - Prove the read-only assistant | E8 | Core | Composition, grounded behavior, and deterministic evaluation | 250-400 |

Production churn counts additions plus deletions under `src/code_assist_harness/` and `tui/src/`.
Tests, documentation, fixtures, lockfiles, and generated files do not count. Roughly 600 lines is a
review ceiling, not a quota. A story is split before review when it gains another responsibility or
is likely to cross the ceiling.

## Locked cross-story defaults

### Agent loop and tool exchange

- One provider turn may produce ordinary final text or exactly one tool call. Tool calls are handled
  sequentially; mixed text/tool terminal grammars and multiple or parallel calls fail closed.
- A tool-aware turn is an atomic transaction. The harness buffers its complete provider-neutral
  response, validates the closed grammar and terminal observation, and only then admits final text
  for publication or a tool call for dispatch. A normalized provider failure may terminate any
  otherwise valid nonterminal prefix: its entire stage is discarded, only its bounded classification
  survives, and publication and dispatch remain zero. Premature EOF, mixed output, and a second call
  also produce zero published text and zero dispatches.
- The initial M2 profile admits at most four model turns and three within-budget tool calls. A fourth
  call is retained only as the single rejecting maximum-plus-one observation required by CAH-022.
  This supports orientation, search/list, read, and a final answer while keeping the loop easy to
  inspect. CAH-037's composition root supplies all four values explicitly—four turns, 120
  provider-work seconds, 4,096 assistant-output bytes, and three observed calls—rather than inheriting
  `LoopLimits()` defaults.
- Provider work deadline and assistant-output accounting remain cumulative across the session. Context
  admission uses deterministic UTF-8 bytes and item counts; provider token usage remains evidence.
- Optional provider usage is session-aggregate evidence. It is retained only when the session admits
  final assistant text; tool-only turns do not publish per-turn usage records.
- Tool definitions, opaque continuations, calls, and results are immutable provider-neutral values
  with explicit ordered position and call-ID correlation. A continuation is one non-empty,
  content-suppressed history item capped at 65,536 UTF-8 bytes; it immediately precedes its call or
  assistant item, counts once toward the 16-item/512-KiB request limits, and never uses an adapter side
  channel. Provider adapters translate these values but do not dispatch tools or decide policy.
- Decoded model arguments must contain exactly the advertised required keys before native Pydantic
  validation can apply defaults. Native request models remain unchanged so trusted direct Python
  callers retain their defaults.
- Registry handlers remain synchronous and bounded. Before dispatch, after each synchronous
  dispatch/discovery/merge stage, and before provider start, the loop unconditionally yields once to
  the shared event loop outside locks and then applies the existing cancellation/deadline guard. An
  in-flight handler is non-preemptive, but the yield lets an already-readable cancel command latch
  before the next guard; later work must add a cooperative handler interface before claiming
  mid-call reap.
- Dispatch results, discovered instructions, merged context, history, and the next bounded request
  remain local candidates until the final post-yield pre-provider guard passes. Cancellation at any
  named seam commits none of them. Deterministic tests pause at injected named `asyncio.Event` gates
  and use injected clocks rather than elapsed-time sleeps.
- Every provider-facing tool outcome uses compact, sorted-key UTF-8 JSON capped at 65,536 bytes
  inclusive: exactly `{"result":<projected>}` for success or
  `{"error":{"code":"<code>","message":"<fixed message>"}}` for failure. Oversize output fails with
  `read_tool_output_too_large`; it is never truncated before entering provider history.
- CAH-030 context projects into provider requests without its inclusion report. Strict tool schemas
  use a small portable Draft 2020-12 subset that requires all properties and
  `additionalProperties=false`; the complete canonical provider-neutral request is capped at 512
  KiB before every provider start.
- OpenAI continuation uses stateless full replay with `store=false`; it does not depend on
  `previous_response_id`. Every request, starting with turn one, sets exactly
  `include=["reasoning.encrypted_content"]` so an accepted reasoning item contains the opaque replay
  payload. The adapter preserves each complete reasoning item as a bounded canonical opaque replay
  envelope—including its required ID and item fields, not only encrypted content—and reconstructs the
  required input fields on later turns even while reasoning context remains `current_turn`. Completed
  output `content` and `status` may each be omitted or null; either form becomes a canonical null
  marker and then an omitted non-nullable input key. `content=[]` and `status="completed"` remain
  present. The fixed six-key canonical payload keeps all four combinations bounded and exact. Core
  code never interprets that provider continuation state. `parallel_tool_calls=false` keeps the
  adapter aligned with the one-call grammar.

### Repository context and reads

- M2 discovers only exact `AGENTS.md` files. CAH-026 first supplies pure lexical-path and hard-deny
  helpers used by ordinary reads and instruction discovery; CAH-025 exempts instruction files from
  `.gitignore`, never from lexical or hard-deny admission, and does not inherit ordinary-read limits
  or errors. Each binding preserves the resolved canonical instruction
  source separately from the canonical candidate-owner directory to which it applies. The same
  source reached through two owners therefore remains two separately charged bindings. Applicable
  bindings are ordered from workspace root to the deepest target scope and remain untrusted guidance
  that cannot weaken harness policy.
- Repository enumeration honors nested `.gitignore` semantics through the small `pathspec`
  `GitIgnoreSpec` dependency plus a non-overridable harness denylist for VCS internals and local
  credential-bearing files. Ignore rules are evaluated independently against the normalized supplied
  path and its resolved canonical target. Each view walks directory prefixes root-to-leaf, loads a
  nested policy only after its directory admits, and denies when any ancestor or the target remains
  ignored; a leaf negation cannot cross an ignored parent, and a negation in one view cannot re-include
  a path ignored in the other. The bounded union of reachable policy files charges a canonically
  identical policy input once, while both views still attach and evaluate its cached rules at their
  own owner-relative scopes. M2 has no ignored-path override.
- `search_text` is literal, case-sensitive UTF-8 search with deterministic path and line order. Its
  one-line query grammar rejects every separator recognized by Python `str.splitlines()`, including
  VT, FF, FS/GS/RS, NEL, and Unicode line/paragraph separators in addition to CR/LF. Regex, ranking,
  embeddings, and subprocess search are deferred.
- Every accepted path is resolved again immediately before access. Results use canonical
  workspace-relative labels and fixed failures rather than host paths or raw OS errors.
- Context items are atomic. Selection either includes a complete bounded item or records why it was
  omitted; it never silently cuts invalid JSON or removes provenance. An instruction item copies
  CAH-025's canonical candidate-owner `applies_to`; it never derives scope from a symlink target
  `source`. Sibling directories do not invent a precedence relationship.
- Plain runtime tasks use **initial** context scope `.` with empty `focus_paths` and `search_queries`.
  Evaluation may inject those fields explicitly through a test-only composition seam; the model does
  not choose initial context-selection inputs. A non-empty request discovers the instruction bundle
  for `scope` first and for every validated, canonical-distinct explicit focus path in input order,
  completing that required union before focus content. Each search query projects exactly to
  `SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)`; focus paths,
  search results, and matched files never become inferred search or instruction roots.
- Each successful native read returns the validated requested `path` as harness-only target-scope
  metadata. Before another provider start, CAH-034/035 use CAH-025 and CAH-030 to add previously unseen
  applicable instructions atomically without evicting prior items. A newly appearing ancestor enters
  before existing descendants while every prior pair retains its relative order. A repeat for the
  same `applies_to` owner is idempotent only when source, content, and original bytes agree; the same
  source under a different owner is a distinct binding. Changed duplicates, discovery failures, and
  item/byte overflow stop before replay.
  Known tool failures keep context unchanged. M2 does not fan out instructions for paths merely
  returned by a broad listing or search, so its grounded evaluation performs a specific
  path-targeting read before final text.

### Evidence and interface boundaries

- Tool-call, result, and context-selection evidence is bounded, typed, redacted, and content-aware
  only where the story explicitly permits it. Host paths, credentials, raw provider objects, and
  unbounded repository text never become diagnostics or transcripts.
- M2 keeps protocol version 1 and the current final-answer TUI projection. Rich tool-call rendering
  and structured plan state remain E7/E6 work in M3.
- Default tests use temporary fixture workspaces, deterministic fake-provider scripts, and no model,
  network, or subprocess. CAH-037 introduces `evals/` only when executable scenarios exist.
- Selecting the OpenAI provider explicitly authorizes the harness to send the bounded,
  policy-admitted repository context and read-tool results needed for that session. Path deny and
  ignore rules are not content-level secret scanning: ordinary allowed source files may still
  contain sensitive text, and the CLI/docs must warn about that egress boundary. Mock execution
  remains local and network-free.

## Function calling versus MCP

Function calling is the model-facing conversation: advertise tools, receive a typed call, execute
application code, return a correlated result, and continue the loop. MCP is a transport and discovery
standard that can supply tool definitions and invocations from another process or service. M2 builds
and teaches a deliberately narrow local read registry and loop first. It does not claim that this
registry is directly MCP-compatible. A later generalized registry port must snapshot and re-admit a
remote catalog, classify network capability, filter or translate broader schemas and result shapes,
and apply the harness's trust, policy, cancellation, and evidence rules.

Remote MCP, server trust, authentication, network policy, approval UX, and dynamic tool-list changes
are not M2 scope. Lessons for CAH-031 through CAH-036 compare the local seam with MCP and OpenAI tool
calling without treating either vendor or transport as the owner of harness policy.

## Definition-of-done policy

Each story uses the repository story template, maps every acceptance criterion to deterministic test
evidence, exercises exact limits below/at/above their boundary, updates its concise Markdown lesson,
records actual production churn, and passes `./scripts/check`. Protocol, transcript, provider, or TUI
parity evidence is required only when that boundary changes; an unchanged boundary is stated and
tested at the nearest integration seam.

No presentation is planned or accepted as evidence for any M2 unit.
