# PR 28 review churn learnings

- **Date:** 2026-08-03
- **Scope:** All inline review findings on
  [PR 28](https://github.com/jimmie-potts/code-assist-harness/pull/28)
- **Purpose:** Preserve the architectural corrections and turn recurring review failures into
  pre-review evidence.
- **Review snapshot:** Remote head `c462581a185d7c7365afa21a21c20f6d73bdd099`, refreshed through
  the sixth review round on 2026-08-03. The counts below describe that fixed snapshot; append a new
  round instead of silently rewriting them if later comments arrive.
- **Production-code and presentation impact:** None. This record and its guardrails change planning,
  documentation, and executable repository-policy tests only; retained presentations remain frozen.

## Review inventory

The thread-aware review snapshot contained no top-level conversation comments and 21 substantive
inline findings: 13 P1 and 8 P2. Six review rounds produced 6, 3, 2, 5, 3, and 2 findings. Nineteen
threads had already been fixed, validated, replied to, and resolved before the last round; the final
two concerned execution-time canonical request scope and CAH-030 lesson ordering.

The PR changed about 9,000 lines across more than 40 files and initially introduced 13 planned
stories with 13 linked lessons. Review-driven single-responsibility splits brought the final M2 plan
to 16 stories and 16 lessons. That surface was too large for one coherent contract audit. The
per-story 600-production-line target did not constrain this planning-only change because
documentation and tests are excluded from that count.

## Root-cause taxonomy

| Primary root cause | Findings | What the review exposed |
| --- | ---: | --- |
| Filesystem identity, indirection, and TOCTOU | 6 | “Path” had been treated as one value instead of separate request alias, execution target, owner, provenance, accounting identity, and visible label. |
| Cross-story carriers and downstream consumers | 6 | A producer was corrected without closing every carrier, consumer, composition root, empty branch, and evaluation path. |
| Provider and serialization boundaries | 5 | Early decoding, implicit SDK/Pydantic behavior, or incomplete replay lost information or admitted unsupported shapes. |
| Producer and scheduler realism | 3 | Proposed tests could not reproduce the real upstream limit or actual event-loop scheduling behavior. |
| Story and lesson pipeline drift | 1 | The lesson reordered filesystem work and contradicted the story's failure precedence. |

The first three categories account for 17 of 21 findings. The churn was systemic rather than a set
of unrelated wording problems.

## Finding and prevention ledger

| # | Review finding and recorded disposition | Pre-review evidence that should catch it |
| ---: | --- | --- |
| 1 | Ignore policy now distinguishes lexical candidate ownership from canonical policy-source identity. | Identity ledger plus alias/symlink matrix. |
| 2 | M2 turn and call limits are composed so every claimed terminal branch is reachable. | Producer-to-consumer trace and below/at/above-limit state table. |
| 3 | Stateless OpenAI replay retains bounded opaque reasoning continuation instead of silently dropping it. | Provider history grammar and lossless carrier audit. |
| 4 | A provider failure after any valid nonterminal prefix discards staged effects without laundering an invalid grammar. | Full prefix/failure matrix and zero-publication/zero-dispatch assertions. |
| 5 | CAH-039's model-facing exact required-key gate uses CAH-038's required names before native Pydantic defaults can fill omissions. | Wire-to-domain transformation order and missing/extra-key mutations. |
| 6 | Search rejects the complete `str.splitlines()` separator repertoire rather than only common newline characters. | Closed input grammar with exhaustive boundary corpus. |
| 7 | Ignored parents cannot be traversed to reach apparently unignored descendants. | Ancestor-walk policy tests, including direct reads and nested candidates. |
| 8 | Opaque provider continuation has one bounded, ordered, provider-neutral carrier. | Producer -> carrier -> replay consumer table with item and byte accounting. |
| 9 | Omitted and null optional reasoning fields normalize compatibly while explicit values remain distinct. | Cartesian compatibility matrix and replay mutations. |
| 10 | Search's 501st-candidate scenario is expressed through CAH-027's observable listing truncation, not an unreachable file-only count. | Reachability proof through the actual upstream producer. |
| 11 | Successful tool results discover and merge every applicable instruction scope before provider replay. | Side-effect gate showing result/context remain local until the full scope union passes. |
| 12 | Canonically hard-denied instruction targets fail even when reached through an admitted alias. | Lexical/canonical denial matrix with zero content read. |
| 13 | Instruction `source` provenance remains distinct from candidate-owner `applies_to`. | Identity ledger and shared-target/different-owner examples. |
| 14 | Explicit focus paths contribute their complete instruction chains before content selection. | Composition-root audit across scope, focus, and search-owner inputs. |
| 15 | CAH-030 constructs the exact CAH-029 search projection and never infers new search roots. | Exact request-spy assertion and no-fanout test. |
| 16 | Cooperative cancellation uses an unconditional event-loop yield independently of optional test gates. | Hook-free scheduler test and deletion mutation. |
| 17 | A symlinked `.gitignore` keeps candidate-owner rule scope while canonical source owns containment, cache, and byte accounting. | Control-plane identity ledger and pre-read/re-read mutation tests. |
| 18 | CAH-039 rejects duplicate decoded tool-argument names at every object depth before key/Pydantic validation or I/O. | Pair-preserving decoder corpus, including escaped and nested duplicates. |
| 19 | Broad list/search results derive instruction owners for every model-visible returned path. | Maximum-fanout carrier/consumer tests and empty-result control. |
| 20 | Native successes carry the final access-time canonical request scope; post-dispatch code never re-resolves or falls back to the mutable alias. | Alias retarget/removal tests for list, stat, read, and search, including empty/no-match successes. |
| 21 | CAH-030 validates projections with zero I/O, discovers/folds root first, finishes focus work before search, and keeps that order in its lesson. | One named stage sequence shared by story, lesson, diagram, pseudocode, spies, and failure-precedence tests. |

## Additional gaps found before handoff

A fresh adversarial pass over the complete contract neighborhood found issues that were not yet
GitHub comments. Their planning contracts and deterministic test requirements were fixed in this
PR rather than left for another review round; executable implementation remains planned. No
production code or presentation artifact changed:

| Missed gap | Correction and reusable check |
| --- | --- |
| A captured canonical label could itself retarget before instruction discovery. | Require every post-native CAH-025 `bundle.canonical_scope` to equal the captured expected scope before merge; test canonical-label replacement, not only request-alias replacement. |
| A captured instruction owner could retarget while only its leaf was rechecked. | Re-admit the exact owner directory before both non-following probe and content read; inject a persistent `owner A -> allowed B` mutation already present at each checked seam and prove it performs no replacement leaf resolution/read or false `applies_to=A` binding. |
| CAH-030 could execute later searches before noticing the first result-scope mismatch. | Compare each result immediately before match inspection or the next search; assert zero later calls. |
| CAH-025 numeric precedence was ambiguous when ancestors were missing or inserted late. | Define rank as canonical owner depth (`.` = 0), then require CAH-030, CAH-032, and later consumers to copy that rank exactly rather than renumbering by list position; gaps are legal and equal-depth siblings gain no precedence. |
| Recursive duplicate detection had no structural recursion ceiling and Python JSON constants were implicit. | Bound structural nesting, reject non-JSON constants, map recursion safely, and test quoted delimiters plus below/at/above nesting. |
| Python's integer conversion and JSON serialization limits could turn an otherwise bounded provider payload, tool schema, or tool result into an unbounded exception. | Before Python conversion, use the same quote-aware 16-KiB preflight to admit only signed 64-bit JSON integer tokens and reject fractions or exponents; keep schema integers and result projections in that signed 64-bit range, and map defensive decoder or serializer `RecursionError`/`ValueError` to the bounded definition, invalid-input, or invalid-result failure. |
| Search limit-reason order and `truncated` consistency were unspecified. | Use one closed canonical tuple order, reject duplicate/unknown values, and require `truncated == bool(limit_reasons)`. |
| A following existence check could treat a dangling `AGENTS.md` symlink as absent. | Probe the exact directory entry without following; only true absence is normal, while dangling/disappeared/unsafe entries fail closed. |
| The registry implied it could detect arbitrary extractor side effects after invocation. | Treat the four extractors as closed trusted harness code; require static/import inspection plus interaction tests proving they receive only the validated result and perform no filesystem, network, provider, environment, clock, or global-state access. Runtime handling is limited to raised or malformed returns. |
| CAH-028 did not explicitly ground `ReadFileResult.path` in final read admission. | Copy final pre-open canonical provenance and test allowed-to-allowed retarget. |
| List/stat/search claimed final native provenance without pre-access replacement evidence. | Re-admit list roots and stat leaves immediately before inspection, reuse CAH-028 for direct search, and test allowed `A -> B` before access plus post-return stability for empty/no-match results. |
| Search's aggregate byte budget did not say whether decoded-invalid or no-match reads were charged, and pre-admission metadata could undercount an allowed small-to-larger replacement. | After final access-time admission, compute the remaining aggregate budget and perform one bounded read of `min(remaining, per-file cap) + 1` bytes. Charge every candidate-content byte up to the active cap, including invalid, NUL-containing, and no-match content; treat the one extra sentinel as separately bounded detection I/O used only to classify aggregate versus per-file overflow, and test an admitted small file replaced by a larger allowed source before open. |
| A bundle could have a matching canonical scope but forged binding topology. | Make CAH-025's sole result factory validate the file-parent/directory ancestor chain, unique owners, strict root-to-nearest order, and depth-derived ranks; mutate unrelated, duplicate, equal-depth, and reversed owners before any downstream consumer can trust the bundle. |
| A native-max result could reach `read_tool_output_too_large`, but the round-trip known-error set omitted it. | Treat the fixed overflow code as a normal bounded tool error with no scopes: cross `after_dispatch`, retain context, replay only the small error envelope, and test exact wrapped boundaries plus the real native producer maximum. |
| Schema candidates could consume unbounded `deepcopy`, validation, enum-dedup, or serialization work before the 16-KiB check. | Use a flat shape-directed copy with O(1) cardinality gates, a 256-value enum cap, one global 16,384-unit work budget, and an incremental byte-bounded encoder; use cyclic/deep/huge-string/million-enum sentinels to prove early rejection. |
| Valid owner topology alone did not prevent a forged absolute or non-canonical `source` label from reaching provider context. | Gate every CAH-025 scope/source/owner through one exact canonical workspace-label validator and mutate absolute, escaping, alternate-spelling, NUL, and surrogate inputs before downstream serialization; retain backslash as a legal Linux filename character. |
| `.gitignore` rechecks stabilized the canonical source but not the candidate-owner directory whose scope receives those rules. | Capture each view owner's canonical directory, re-admit it before leaf probe and cache-miss read, and test persistent lexical/canonical `A -> allowed B` mutations at both seams, including cache-hit current-admission behavior and the residual pathname race. |
| Provider schema construction, provider exchange, raw argument admission, and round-trip orchestration had accumulated in two oversized ownership neighborhoods. | Split CAH-038 as the sole bounded definition bridge and CAH-039 as the sole raw-argument admission path; narrow CAH-032 to exchange/results and CAH-034 to prepared-call dispatch/enrichment, with import guards preventing parser or schema logic from drifting back. |
| The split stories still inherited impossible tests from an earlier ownership boundary. | Treat CAH-032 as the producer gate for malformed tool names, over-16-KiB calls, and over-bound opaque continuations; run CAH-039/033 public tests only with constructible carriers, label any helper-only defense separately, and remove cyclic decoded JSON from CAH-032 because the standard decoder cannot produce it. |
| Schema O(1) cardinality claims implicitly trusted Python container hooks. | Admit only exact built-in schema containers/scalars before length or iteration, reject custom mappings/sequences/subclasses without invoking their hooks, and retain hostile-subclass interaction tests alongside the 32/33 and 256/257 limits. |
| A final request-size cap still allowed UTF-8 or `JSONEncoder` to materialize a huge direct provider string first. | Require exact built-in strings and O(1) character ceilings before scalar walks, UTF-8, escaping, or encoder entry; gate exact input/tools tuple counts before iteration, then apply the complete 512-KiB projection. Keep huge-string, subclass-hook, traversal, and encoder spies in CAH-032 evidence. |
| OpenAI reasoning replay could canonicalize hostile SDK `id` or `encrypted_content` before discovering the six-key envelope was too large. | Pre-bound exact SDK strings by O(1) characters and strict UTF-8 bytes before copying or JSON serialization; retain huge-value, hostile-subclass, canonicalizer, and serializer-spy tests in CAH-036. |
| Ignoring Pydantic `title`/`default` through a generic cleanup walk could consume unmetered work, while arbitrary schema generators were implicitly trusted. | Restrict generation to the exact four native model identities; charge and omit only expected annotation positions inside CAH-038's bounded shape-directed pass, and test huge/misplaced annotations, hook-bearing subclasses, foreign models, and real-schema drift. |
| Definition, validation, and execution could use three same-shaped but different tool catalogs. | Give CAH-039 one registry-only factory that invokes CAH-038 internally, owns the exact CAH-031 registry identity, and re-exposes the bridge-produced definitions advertised in every request. Bind prepared calls to the same entry; cross-catalog mixing—including distinct catalogs over one registry or same-schema registries with different handlers—is a session failure before handler I/O, replay, or follow-up. |
| Model-facing repository paths had strict Unicode and containment rules but no shared work ceiling, so direct, context, and provider carriers could drift or reach filesystem-dependent long-name behavior. | Put one pure lexical owner in CAH-024: 4,095 raw strict-UTF-8 bytes, 256 normalized components, and 255 UTF-8 bytes per name. Delegate through CAH-026; map CAH-025/native/context/provider failures at their existing stages; test 4,094/4,095/4,096, 254/255/256, and 255/256/257 with zero-I/O spies. Record that these are harness budgets, not `PATH_MAX`/`NAME_MAX`/DrvFS guarantees, and that JSON Schema `maxLength` counts characters. |
| CAH-032 remained close to the reviewability ceiling after two ownership splits. | Record a counted-path allocation totaling 425-575 lines and require a pre-implementation diff estimate; split result admission before coding if the estimate exceeds 575 or acquires another runtime responsibility. |
| Late handoff edits left CAH-039 returning direct values while CAH-034/035 pseudocode consumed an invented wrapper, used the wrong call-ID field, omitted follow-up tool definitions, and skipped the explicit provider-failure branch. | Lock the exact `PreparedReadToolCall | ProviderToolResult` return, exact prepared fields, concrete consumer branch, unchanged `catalog.definitions`, and all CAH-033 outcome variants in story/lesson policy assertions. Trace field names and callable signatures after every ownership split. |
| A late CAH-031 lesson edit duplicated a reverse-dependency sentence even though its underlying contract was correct. | Re-read the rendered neighborhood after mechanical reconciliation, search for stale/duplicate handoff prose, and keep the semantic policy check on `dispatch_bound(read_tool, validated_input)` plus the no-CAH-039 import direction. |

## Final-round architectural corrections

Native read provenance now follows one carrier rule:

- CAH-025 returns content-suppressed `canonical_scope`, including an empty instruction bundle.
- CAH-027 list results and CAH-029 search results return content-suppressed
  `canonical_request_scope`, including empty-list and no-match successes.
- CAH-031 derives `instruction_scopes` from the validated result. The execution-time canonical
  request scope is first; model-visible result owners follow in deterministic first-occurrence
  order. The registry does not consult the original alias.
- CAH-034 and CAH-035 keep the result and all context candidates local while CAH-025/030 freshly
  admit and discover every scope, verify `bundle.canonical_scope` against the captured label, then
  merge, budget, and guard. Failure never falls back to the alias.
- CAH-030 uses its root bundle's `canonical_scope` as a transaction snapshot and rejects a search
  result whose canonical request scope differs before inspecting matches.

CAH-030's ordered pipeline is now explicit: validate every focus/search projection with zero I/O;
discover, fold, and budget-check the root as the first filesystem work; complete each focus read,
verify its discovered bundle scope, and fold it; run one search and verify its canonical request
scope before another search; discover and verify every match-owner bundle; then append focus and
optional search content. Root failure produces zero focus/search calls, focus failure produces zero
search calls, and a first-search scope mismatch produces zero later search calls.

This remains pathname-snapshot hardening, not descriptor-relative isolation. Deterministic
replacement tests claim detection only for a persistent mutation already present at the checked
seam. Any mutation after the final check can still race, whether or not it keeps the same canonical
label. That residual risk stays explicit until a future descriptor-relative or sandboxed filesystem
unit owns it.

## Process changes adopted

1. Split future milestone refinement by contract neighborhood. Prefer one core learning story or two
   to three tightly coupled supporting stories per PR. A small skeleton milestone map may land first.
2. Complete the [story template's adversarial audit](../story-template.md#pre-review-adversarial-audit)
   with story-specific evidence or explicit `N/A` before opening a PR.
3. Run three independent lenses:
   - security plus identity and indirection;
   - end-to-end contract handoff plus composition; and
   - provider/protocol limits plus real scheduler behavior.
4. Trace each contract as producer -> carrier -> consumer -> observable side effect. Include
   composition/evaluation roots, empty/no-match/error/cancellation branches, and control-plane files
   such as `.gitignore` and `AGENTS.md`. For a tool, prove that the exact definition tuple advertised
   to the provider, the catalog used for validation, and the executor entry used after the guard all
   share one captured identity.
5. Prove claimed boundary tests are reachable through the actual upstream producer and scheduler.
   Trace concrete callable signatures and return types as well as conceptual nouns: the producing
   factory's allowed inputs, the exact carrier fields, the consuming method's parameters, and the
   layer that constructs the next domain value must all be implementable without a reverse import.
6. Close every grammar and cardinality: exact accepted variants, canonical order, duplicates,
   structural depth/item/byte ceilings, and safe parser/runtime-limit mapping.
   For workspace paths, trace raw UTF-8 bytes, normalized component count, per-name bytes, native
   error mapping, provider-stage precedence, and the distinction between application limits and
   mount portability.
7. Give a shared named stage sequence to the story, lesson, architecture diagram, pseudocode, and
   test spies. Preserve failure precedence rather than reordering work for exposition.
8. After any review fix, repeat the full contract-neighborhood audit. Then validate, push, reply with
   evidence, resolve the inline thread, and refresh thread-aware state before handoff.

## Seventh handoff audit round

This append-only round records proactive findings from the final whole-PR audit after the 21-comment
GitHub snapshot above. They are not additional reviewer comments and do not change that snapshot's
P1/P2 counts. They explain what would otherwise have become another review round:

| Missed contract neighborhood | Fix and future pre-review evidence |
| --- | --- |
| CAH-028 and CAH-029 independently described final admission/open/decode work. | Introduce one exact `RepositoryTextReader.read_text_candidate` producer and a closed three-state `TextSourceCandidate`; make direct read and search consume it once and test identity, byte accounting, overflow, and non-text branches through the real producer. |
| Context search provenance had no stable duplicate-query rank. | Define `query_rank` as strict one-based first-occurrence position after exact deduplication and copy it unchanged through CAH-030/032; test duplicate and gap cases instead of inferring rank from output order. |
| Hand-built schema fixtures missed real Pydantic root descriptions and annotation placement. | Snapshot all four real generated models, including root title/description, required/default shapes, and allowed annotation positions; mutate the real producer output and fail on drift. |
| Provider-request bounds blurred four tuple collections and cumulative versus per-snapshot accounting. | Gate conversation, legacy instructions, repository context, and tools independently before iteration. Label session counters cumulative while reapplying the 512-KiB cap independently to each complete request snapshot. |
| Equal-shaped services, definitions, catalogs, and handlers could be cross-wired, and a tool path could inherit an unusable default limit profile. | Name one boundary-only service factory and frozen nine-identity carrier; require services-present runners to receive explicit limits; prove exact object identity from request advertisement through catalog admission, dispatch, and evaluation. |
| Lazy provider start was treated as one call instead of a transaction. | Separate awaitable lock/cleanup edges from the no-await critical section. Test charge -> synchronous `start` -> one `events()` claim -> immutable installed-state carrier -> final clock read -> one non-failing pointer assignment. Lock pre/post-commit deadline semantics, retain charge on failure, and join uninstalled cleanup before terminal publication. |
| A one-turn cleanup finalizer could be reused between tool turns, stopping the absolute watcher or allowing unreaped work to overlap. | Give every operation one generation and one cleanup-task owner. Separate continuation cleanup from terminal cleanup, preserve the session-wide watcher, force-reap before dispatch/next start, and join an already-owned cleanup task without mode drift. Test force failure and cancellation/deadline races with zero later side effects. |
| CAH-033's returned outcome and CAH-034 accounting had no explicit linearization point. | Use one guard-owned outcome-adoption transaction. Prove terminal-first causes no new call/output/usage charge, while adoption-first charges exactly once and later cancellation cannot roll it back. |
| Final output and usage could partially commit, and incomplete usage subsets could look complete. | Validate all-turn usage as all-or-none, then reserve the whole staged text once before any chunk. Test every missing-usage subset, arithmetic overflow, output overflow, and zero-publication/zero-evidence rollback. |
| Adapter transport validation was incorrectly described as turn atomicity. | Permit validated provider-neutral observations such as text deltas to cross the port as SDK events arrive; make CAH-033 the sole staging/admission owner and assert zero publication/dispatch when a later observation invalidates the turn. |
| OpenAI direct-call grammar omitted SDK `caller`/`namespace`, bounded-work order, and exact replay fields. | Reject `caller`/`namespace` at added/done/completed snapshots; exact-type/character/UTF-8-gate every argument snapshot before comparison or retention; join fragments once; replay a call as exactly `type`, `call_id`, `name`, and `arguments`, and a result as exactly `type`, `call_id`, and `output`, while omitting output-only identity/lifecycle fields. |
| Moving the launched default mock onto the real provider session changes opaque IDs, cancellation atomicity, and evidence. | Enumerate runtime, fixture, transcript, protocol-consumer, cancellation, and documentation surfaces for every default-path migration; lock intentional `ses_provider_*`, zero partial deltas on cancellation, exact loop-limit evidence, absent usage, and zero network. |
| CAH-034 grew materially during review while its old line estimate stayed unchanged. | Allocate production churn by counted path, re-estimate before coding, and split service composition or operation-generation work before implementation when the estimate exceeds 575 lines or gains another responsibility. |
| Async checkpoint and cleanup helpers had prose-only stop semantics, so pseudocode continued after a losing transition. | Give every async transition an exact Boolean, return union, or private stop sentinel and show every caller consuming it. Mutation-test an ignored stop result; stage synchronous values and errors through the same following seam before mapping. |
| The downstream response collector had an 8-KiB cap, but the SDK mapper and neutral constructors could retain, scan, or join unbounded text first. | Trace each bound to the first producer and every carrier. Require exact bounded neutral text, saturating adapter work, a content-free overflow marker, one bounded normal join, zero overflow-tail work, and harness-owned limit selection. |
| SDK-to-neutral review stopped at the neutral grammar and missed transport recursion and hidden post-terminal values. | Pump mapped-empty SDK events iteratively, stage raw terminal tuples until raw EOF, and discard them on an extra event or iterator exception. Test the maximum legal one-byte fragment count at constant stack depth. |

The reusable rule is to audit a planning PR like executable code: use the real producer, name every
identity and accounting scope, close scheduler ownership through cleanup, and prove the final
publication boundary. A document can be internally polished while still being impossible to compose.

The templates and repository policy now require those checks. The executable policy suite checks
balanced Markdown fences and, for the refined M2 inventory, rejects story audit evidence copied
verbatim from the generic template plus an unchanged `Independent lenses` prompt. Those mechanical
gates complement, but cannot replace, the three independent semantic review lenses.

The repository policy gate checks that these durable prompts remain in `AGENTS.md`, the story and
lesson templates, and this review record. Static policy checks cannot prove architectural
correctness, so the independent adversarial passes remain required human/agent review evidence.
