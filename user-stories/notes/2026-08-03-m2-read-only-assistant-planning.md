# 2026-08-03 M2 read-only assistant planning

## Purpose

Refine the M2 outcome into 16 dependency-ordered, implementation-ready units without hiding the
agent loop inside a framework or turning one review into a repository-wide rewrite. This note
records the cross-epic split, learning priorities, review-size policy, and decisions that let
CAH-024 through CAH-039 proceed independently in the documented dependency order.

**Delivery update (2026-08-06):** CAH-024 is Done. The remaining 15 M2 stories are planned, with
CAH-026 as the next dependency checkpoint and CAH-025 following it.

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

The individual filesystem handlers and bounded provider-definition bridge are supporting units. The
workspace and instruction boundaries, read policy, context builder, registry, provider-neutral
exchange, atomic response admission, argument trust boundary, one-round and iterative loops, OpenAI
mapping, and end-to-end evaluation are core learning units.

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
| 23 | CAH-031 - Register and dispatch read-only tools | E4 | Core | Typed capability registry and fail-closed dispatch | 500-600 |
| 24 | CAH-038 - Canonicalize provider tool definitions | E2 | Supporting | Closed schemas, bounded construction, and atomic definition publication | 275-425 |
| 25 | CAH-032 - Define the provider-neutral tool contract | E2 | Core | LLM context, calls, results, correlation, and bounded replay | 425-575 |
| 26 | CAH-033 - Stage and validate one tool-aware response | E2 | Core | Atomic response grammar and admission before publication or dispatch | 350-500 |
| 27 | CAH-039 - Admit one provider tool argument object | E4 | Core | Raw JSON trust boundary, failure precedence, and typed preparation | 300-450 |
| 28 | CAH-034 - Run one read-tool round trip | E2 | Core | Prepared-call dispatch, result enrichment, and one follow-up | 420-570 |
| 29 | CAH-035 - Run the bounded agent loop | E2 | Core | Loop state, stopping, cancellation, and cumulative limits | 350-500 |
| 30 | CAH-036 - Map OpenAI Responses tool calls | E2 | Core | Strict SDK-event translation and opaque continuation replay | 450-600 |
| 31 | CAH-037 - Prove the read-only assistant | E8 | Core | Composition, grounded behavior, and deterministic evaluation | 250-400 |

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
- CAH-038 builds tool definitions as immutable provider-neutral values from the CAH-031 registry.
  Only the exact four native Pydantic model identities may generate schemas; expected root/property
  `title` and property `default` annotations are charged and omitted inside the same bounded
  shape-directed pass, never by a recursive cleanup pass.
  CAH-039's sole public catalog factory accepts only that registry and invokes CAH-038 internally;
  no caller supplies definitions independently. The resulting immutable catalog owns the exact
  CAH-031 registry identity, re-exposes its bridge-produced tuple to every request, and binds prepared calls
  to the same executor entry. Independently built catalogs are valid when self-consistent, but
  mixing prepared values across distinct catalogs—even over the same registry—or across same-shaped
  registries fails by object identity before handler I/O, replay, or provider follow-up. Opaque
  continuations, calls, and results are likewise immutable, with explicit ordered position
  and call-ID correlation. A continuation is one non-empty,
  content-suppressed history item capped at 65,536 UTF-8 bytes; it immediately precedes its call or
  assistant item, counts once toward the 16-item/512-KiB request limits, and never uses an adapter side
  channel. Provider adapters translate these values but do not dispatch tools or decide policy.
- CAH-039 requires decoded model arguments to contain exactly its catalog-bound CAH-038 definition's advertised
  keys before native Pydantic validation can apply defaults. Native request models remain unchanged
  so trusted direct Python callers retain their defaults.
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
  `read_tool_output_too_large`; it is never truncated. The fixed small error envelope is a known
  tool result that replays against unchanged context, while the oversized content never enters
  provider history. CAH-031 admits signed-64-bit integers, a complete wrapped success envelope whose
  outer `result` object is depth 1 and whose object/list depth is at most 64, and one 65,536-unit
  visit/name/Unicode-scalar work budget before sorted serialization. Cycles, range/depth/work
  overflow, and defensive serializer `RecursionError`/`ValueError` map to a fixed result failure.
  CAH-032 then quote-aware-preflights the complete provider-result envelope under its byte cap before
  decode and maps defensive decoder `RecursionError`/`ValueError` without exposing interpreter text.
- CAH-030 context projects into provider requests without its inclusion report. CAH-038 admits a
  small portable Draft 2020-12 subset that requires all properties and
  `additionalProperties=false`. It uses O(1) shape cardinality gates, an enum cap of 256 values, one
  non-resetting 16,384-unit visit/scalar work budget, a shape-directed fresh copy, and incremental
  16,384-byte encoding before atomic definition publication. Every direct CAH-032 string and exact
  conversation, legacy-instruction, repository-context, and tool tuples are O(1)
  character/cardinality-gated before UTF-8, iteration, escaping, or serialization; the complete
  canonical provider-neutral request is capped at 512 KiB before every provider start.
- OpenAI continuation uses stateless full replay with `store=false`; it does not depend on
  `previous_response_id`. Every request, starting with turn one, sets exactly
  `include=["reasoning.encrypted_content"]` so an accepted reasoning item contains the opaque replay
  payload. The adapter preserves each complete reasoning item as a bounded canonical opaque replay
  envelope—including its required ID and item fields, not only encrypted content—and reconstructs the
  required input fields on later turns even while reasoning context remains `current_turn`. Completed
  output `content` and `status` may each be omitted or null; either form becomes a canonical null
  marker and then an omitted non-nullable input key. `content=[]` and `status="completed"` remain
  present. Exact SDK reasoning `id` and `encrypted_content` strings are O(1) character- and strict
  UTF-8-byte-bounded before canonicalization. The fixed six-key canonical payload keeps all four
  combinations bounded and exact. Core
  code never interprets that provider continuation state. `parallel_tool_calls=false` keeps the
  adapter aligned with the one-call grammar.

### Repository context and reads

- CAH-024 owns one pure model-facing path grammar before any `Path`, root, policy, or filesystem
  work. The complete raw spelling is at most 4,095 strict-UTF-8 bytes, contains at most 256
  normalized non-dot components, and uses at most 255 UTF-8 bytes per component. CAH-026 delegates
  that exact tuple/failure decision and maps repository vocabulary; CAH-025 and CAH-027 through
  CAH-030 reuse it, CAH-031 receives already-typed requests, and CAH-039 reaches it only at the
  existing strict-Pydantic stage after lookup/raw-JSON/exact-key precedence. These are harness work
  budgets, not Linux `PATH_MAX`, mount `NAME_MAX`, or WSL DrvFS promises. JSON Schema character
  `maxLength` cannot claim exact byte/component parity.
- M2 discovers only exact `AGENTS.md` files. CAH-026 first supplies pure lexical-path and hard-deny
  helpers used by ordinary reads and instruction discovery. Every present `.gitignore` keeps its
  candidate-owner directory for rule scope while its canonical source resolves through
  `WorkspaceBoundary` and passes canonical hard denial. The view captures its admitted owner's
  canonical directory, re-admits that owner immediately before the non-following leaf probe and
  again before a cache-miss read, and then re-resolves and rechecks the source. A persistent
  owner retarget already present at either deterministic seam fails before replacement-leaf work;
  cache hits still require current owner, leaf, and source admission. Pre-read-rejected sources fail as
  `repository_policy_invalid`, cause no requested-content read, and are not opened, cached, or
  charged. Invalid UTF-8 or NUL is read only into a bounded uncommitted candidate and is never
  exposed, cached, or charged; safe internal symlinks remain owner-relative. CAH-025 exempts
  instruction files from `.gitignore`, never from lexical or
  hard-deny admission, and does not inherit ordinary-read limits
  or errors. Each binding preserves the resolved canonical instruction
  source separately from the canonical candidate-owner directory to which it applies. The same
  source reached through two owners therefore remains two separately charged bindings. CAH-025's
  sole result factory requires unique binding owners to form the exact strict root-to-nearest
  ancestor chain for the canonical file-parent or directory scope and validates each precedence
  rank as the canonical owner depth (`.` is 0); missing ancestors leave legal rank gaps. One exact
  workspace-relative label validator gates every scope, source, and owner before construction and
  rejects absolute, escaping, non-canonical, NUL, or lone-surrogate spellings. The validated
  bindings remain untrusted guidance that cannot weaken harness policy.
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
- Every accepted path is re-admitted immediately before its native access. CAH-027 re-admits list
  roots and stat leaves before inspection, CAH-028 captures final pre-open provenance, and CAH-029
  reuses that final read seam for direct search. Results copy those execution-time canonical
  workspace-relative labels and fixed failures rather than host paths or raw OS errors.
- Context items are atomic. Selection either includes a complete bounded item or records why it was
  omitted; it never silently cuts invalid JSON or removes provenance. An instruction item copies
  CAH-025's canonical candidate-owner `applies_to`; it never derives scope from a symlink target
  `source`. Sibling directories do not invent a precedence relationship.
- Plain runtime tasks use **initial** context scope `.` with empty `focus_paths` and `search_queries`.
  Evaluation may inject those fields explicitly through a test-only composition seam; the model does
  not choose initial context-selection inputs. Every focus/search projection validates before I/O. A
  non-empty request discovers, folds, and budget-checks the instruction bundle for `scope` as the
  first I/O, then completes every validated, canonical-distinct explicit focus read/discovery/fold in
  input order before search. Each search query projects exactly to
  `SearchTextRequest(query=query, path=request.scope, max_depth=4, max_matches=100)`; a focus or result
  path never becomes a search root. Each result's execution-time canonical request scope must match
  the root-discovery snapshot before matches are inspected; mismatch fails with no package. Every
  first-occurrence search-match owner does trigger instruction discovery and joins the required union
  before its excerpt can enter context.
- Successful native result carriers retain the execution-time canonical request scope, including
  empty-list and no-match successes. CAH-031's closed result-only extractors derive ordered,
  content-suppressed `instruction_scopes`: that request scope first, then the exact-deduplicated owner
  of every model-visible result path. They never receive or re-resolve the original request alias.
  Before replay or another provider start, CAH-034/035 use CAH-025 and CAH-030 to discover every
  scope and require each returned bundle's `canonical_scope` to exactly equal the captured scope
  after the discovery guard and before merge. They then add all previously unseen applicable
  instructions atomically without evicting prior items. A newly appearing ancestor enters
  before existing descendants while every prior pair retains its relative order. A repeat for the
  same `applies_to` owner is idempotent only when source, content, and original bytes agree; the same
  source under a different owner is a distinct binding. Changed duplicates, discovery failures, and
  item/byte overflow stop before replay. A broad list or search result is all-or-nothing: one denied,
  invalid, changed, or over-budget owner discards the complete result/context transaction. Known tool
  failures carry no scopes and keep context unchanged. These checked pathname snapshots narrow but
  do not eliminate any mutation race after the final check; descriptor-relative isolation remains
  later work.
- CAH-032, CAH-033, and CAH-036 preserve the provider's bounded raw argument string without parsing.
  After CAH-033 admits the complete call response, CAH-039 owns the sole structural/decode admission
  path and hands CAH-034 one prepared invocation or fixed error. Exact unknown-tool lookup runs first.
  CAH-039 then preflights the complete 16,384-byte argument value with
  an iterative quote-and-escape-aware brace/bracket stack, counts the root object as structural depth
  1, and rejects mismatched containers or depth above 64 before pair-preserving decode. The byte cap
  is one aggregate payload/work bound and does not reset per subtree. That scan admits only the JSON
  integer grammar in the signed-64-bit range before Python conversion; fractions, exponents, and
  overflow fail. Decode rejects `NaN`, `Infinity`, and `-Infinity` through `parse_constant`, maps
  defensive decoder/conversion `RecursionError` or `ValueError` to
  `invalid_read_tool_input`, and uses an iterative tree walk to reject repeated decoded member names
  at every admitted object depth before dictionary construction, CAH-039's exact-key gate against
  CAH-038 required names, strict Pydantic validation, or dispatch. Equality is exact after escape
  decoding with no normalization or case folding. Tests cover depth 63/64/65, quoted delimiters and
  escapes, mixed arrays/objects, deepest
  admitted duplicates, signed-64 endpoints and overflow, fractions/exponents, non-finite constants,
  and injected decoder `RecursionError`/`ValueError`. CAH-035 reuses that exact CAH-039 path on every
  iteration, and CAH-037 proves it at the composition boundary.

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
are not M2 scope. Lessons for CAH-031 through CAH-039 in dependency order compare the local seam with
MCP and OpenAI tool calling without treating either vendor or transport as the owner of harness
policy.

## Definition-of-done policy

Each story uses the repository story template, maps every acceptance criterion to deterministic test
evidence, exercises exact limits below/at/above their boundary, updates its concise Markdown lesson,
records actual production churn, and passes `./scripts/check`. Protocol, transcript, provider, or TUI
parity evidence is required only when that boundary changes; an unchanged boundary is stated and
tested at the nearest integration seam.

No presentation is planned or accepted as evidence for any M2 unit.
