# Repository Guidelines

## Product and Architecture Boundaries

Code Assist Harness is a learning-first coding agent for Ubuntu under WSL. The target application
has an Ink/TypeScript process that owns the terminal and launches a Python harness child. They
communicate using versioned NDJSON: commands go to Python stdin, validated events come from Python
stdout, and Python stderr is reserved for diagnostics.

The Python harness owns orchestration, session lifecycle, context construction, tool policy,
approvals, and transcripts. The TUI reduces events into visible state; it must not decide whether a
tool is safe or whether an agent turn is complete. The project owns its explicit agent loop. Keep
OpenAI and any future LangChain adapter behind provider boundaries so framework SDK types never
enter core domain APIs.

## Project Structure and Module Organization

Python application code belongs in `src/code_assist_harness/`. Keep modules focused and expose only
intentional package APIs from `__init__.py`. Python tests live in `tests/` and mirror the source area
they cover.

The TypeScript application lives in `tui/`, with source in `tui/src/` and tests in
`tui/test/`. Shared cross-language fixtures belong in `protocol/fixtures/`; do not make either
language's generated output the unreviewed source of truth during the first implementation.
Evaluation scenarios belong in `evals/`. Architecture guidance belongs in `docs/`, accepted
decisions in `docs/adr/`, unit learning companions in `docs/lessons/`, and dependency-ordered
delivery work in `user-stories/`. Retained presentation files are frozen historical artifacts; the
lesson decks through CAH-022 remain under `docs/lessons/assets/`. Starting with CAH-023, Markdown
lessons and their compact text diagrams are the only lesson artifacts. Markdown lessons are
authoritative. Do not add or revise presentation files unless the user explicitly reverses this
freeze.

Do not add empty planned directories. Introduce a path with the story that first uses it. Project
metadata, Python dependencies, and tool settings are defined in `pyproject.toml`; commit `uv.lock`
whenever Python dependency resolution changes. The TUI uses npm and must commit `package-lock.json`
whenever JavaScript dependency resolution changes. Pin the supported Node version in a repository
version file when the TUI is introduced.

## Build, Test, and Development Commands

The current Python scaffold supports:

- `uv sync --dev` to create the Python 3.12 environment and install locked dependencies.
- `uv run pytest` to run the Python test suite.
- `uv run ruff check .` to check lint rules and import ordering.
- `uv run ruff format --check .` to verify formatting; use `uv run ruff format .` to apply it.
- `uv build` to create ignored distributions under `dist/`.

The canonical repository-wide gate is `./scripts/check`. It runs the locked Python and TUI checks,
including both protocol implementations, the real process boundary, documentation policy, top-level
Python/Node process guards, and network-source policy for the sanitized Python child. It uses
installed dependencies without making a live-provider or other network request. Keep the focused
Python commands above and the TUI's independent type-check, lint, and test scripts available for
local iteration; focused checks do not replace `./scripts/check` before a unit is marked complete.

## Python Style and Documentation

Use four-space indentation, type hints for public functions, and a maximum line length of 100
characters. Follow `snake_case` for modules, functions, and variables; `PascalCase` for classes; and
`UPPER_CASE` for constants. Keep imports sorted and prefer small, explicit functions over hidden
global state. Ruff is the style authority.

Production modules and public APIs use Google-style docstrings. Document responsibility, important
inputs and outputs, exceptions, side effects, cancellation, security assumptions, and invariants
when relevant. Add a concise example for a non-obvious abstraction. Tests and trivial private
helpers are exempt from mechanical docstrings, but private code still needs explanation when it
encodes a protocol invariant, security boundary, concurrency rule, context-selection decision, or
deliberate tradeoff. Comments explain why a choice exists rather than restating code.

Ruff `D` rules with the Google convention enforce this policy. Keep test exemptions narrow and do
not silence missing documentation broadly across production code.

## TypeScript and TUI Conventions

Use TypeScript for all TUI production code. Exported protocol types, reducers, hooks, components,
and other meaningful contracts use TSDoc. State whether a type is a wire shape or local UI state,
document legal states and transition invariants for state machines, and state whether reducers must
remain pure, how duplicate or unknown events behave, and what happens after the child process exits
when those concerns apply.

The TUI must preserve pending user input while background events arrive, expose keyboard
cancellation, and remain understandable in narrow or resized terminals. Keep orchestration and
policy decisions out of React components. Test reducers independently and use
`ink-testing-library` for user-visible screen states.

## Protocol and Runtime Conventions

Treat every process-boundary value as untrusted. Use Pydantic v2 to validate Python commands and
events and Zod at the TypeScript boundary. Validate the common envelope before dispatching by type
so malformed input becomes a structured protocol error and unknown event types cannot crash the
TUI. Every wire message is exactly one JSON object followed by a newline.

Session events carry a session ID and monotonic sequence. Commands carry an ID that resulting
events reference as a correlation ID. Use shared golden JSON fixtures in both languages whenever
the protocol changes. Protocol-message documentation identifies process ownership, correlation,
ordering, sequencing, and expected failure behavior. Never write logs, tracebacks, or diagnostics
to Python protocol stdout.

Use one explicit `asyncio` event loop in the Python runtime. Preserve ordered event writes, model
active work as cancellable tasks, and check cancellation and limits before starting another costly
operation. Move blocking work to a worker thread only when it cannot remain small and bounded. At
M2 synchronous-stage boundaries, use one `cooperate_then_guard` seam: unconditionally
`await asyncio.sleep(0)` outside every lock, run any injected deterministic test observer or gate,
then apply the existing cancellation/deadline guard with its established precedence. Use that seam
before dispatch, after dispatch, after instruction discovery, after context merge, and before the
next provider start. Keep results, context, history, and the bounded request as local candidates
until the final pre-start checkpoint and model admission pass; cancellation must not leave partial
tool-result or context state.
Test the unconditional yield separately from awaited checkpoint gates: with no observer/gate
installed, queue cancellation on the same loop and assert at synchronous guard entry that it already
latched. An awaited `asyncio.Event` hook can pause a stage but is not evidence that the production
yield still exists. Use injected clocks, never elapsed sleeps, for deadline/cancellation ties.
Normal `cooperate_then_guard` return is the sole authorization for the next line; a losing guard raises
the private session stop sentinel, which only the orchestration boundary consumes. Capture each
bounded synchronous stage's value or exception, cross its mandatory following seam, then unwrap or
map it; propagate `CancelledError` as task control only when the task's cancelling count is positive.
Lazy start may await guard-lock acquisition and joined cleanup, but model charge through successful
install is one no-await critical section: start, full operation-port validation, one event-iterator
claim, immutable installed-turn carrier construction, final clock read, then one non-failing pointer
assignment. A deadline after that assignment loses the transition. Join valid uninstalled-operation
cleanup before terminal publication, and explicitly consume the continuation-cleanup result before
argument admission or later work.

Treat a tool-aware provider response as one atomic admission transaction. Buffer and validate its
complete closed grammar before publishing assistant text or dispatching a requested tool; an
invalid, incomplete, mixed, multiple-call, or failed response must cause neither effect. Native M2
read handlers are synchronous and bounded rather than preemptively cancellable: check cancellation
and deadlines before and after execution, discard a late result when cancellation wins, and do not
claim an in-flight synchronous handler was reaped.
Provider text is bounded at its first producer, not only at final admission. Provider models own one
shared 8,192-byte normal-text cap; normal delta/completion carriers require exact built-in strings and
early character/UTF-8 gates. An adapter or fake represents larger text only with the content-free
8,193 overflow observation, and the harness retains ownership of the limit outcome. SDK adapters use
an iterative mapped-empty observation pump and withhold a raw terminal tuple until SDK EOF; an extra
raw event or iterator exception discards that tuple.

Use one CAH-024-owned pure lexical primitive for every model-facing workspace-relative path. Count
the complete raw spelling before legal dot/separator normalization and admit at most 4,095 strict
UTF-8 bytes, 256 normalized non-`.` components, and 255 strict-UTF-8 bytes per component. All three
limits are inclusive; `.` denotes the root, `/` is the Linux separator, backslash is an ordinary
filename character, and Unicode is never normalized or case-folded. Reject an over-bound value
before `Path`, root inspection, policy, or filesystem I/O. CAH-026 may translate the fixed lexical
failure but must delegate the tuple/limit decision; native request, context, and provider-tool paths
must not create another grammar. These are deterministic harness work budgets, not `PATH_MAX`,
`NAME_MAX`, or WSL DrvFS portability guarantees: mount limits vary and the selected absolute root
adds bytes. JSON Schema `maxLength` counts characters rather than UTF-8 bytes, so a schema hint never
claims to enforce this native byte/component/name contract.

Keep provider tool arguments as bounded raw JSON until the harness-owned dispatch path. After
unknown-tool lookup, preflight the complete 16-KiB argument payload with an iterative,
quote-and-escape-aware brace/bracket scanner before pair-preserving decode. Count the root object as
structural depth 1, admit at most 64 object/array levels, and never reset the payload/work bound for a
subtree. Decode with `parse_constant` rejection and pair-preserving duplicate detection before
constructing a dictionary. Reject `NaN`, `Infinity`, and `-Infinity`; check member-name uniqueness at
every object depth within the admitted bound; and admit numeric tokens only as signed 64-bit JSON
integers (no fraction or exponent). The quote-aware preflight enforces that numeric grammar before
Python integer conversion. Map numeric overflow, rejected constants, defensive decoder
`RecursionError`/`ValueError`, or duplicates to `invalid_read_tool_input` before the exact-key gate,
Pydantic validation, or tool I/O. Compare names by exact code point after JSON escape decoding,
without case folding or Unicode normalization.

Before replaying any successful tool result to a provider, derive ordered local instruction scopes
from the native operation's execution-time canonical request scope and every model-visible returned
path. The canonical request scope must come from the final access-time admission used by the native
operation, survive empty-list and no-match successes, and remain content-suppressed; never
re-resolve or fall back to the original request alias after dispatch. Discover and fold every
applicable instruction bundle through CAH-025/030, crossing the cooperative guard after each
discovery and merge. After each discovery guard and before merge, require the returned bundle's
`canonical_scope` to exactly equal the captured scope; a retargeted canonical label fails without
alias fallback. Keep the result and every intermediate context candidate local until the
complete scope set, context budgets, final checkpoint, and model admission pass. Any failure
discards the transaction; known tool errors carry no instruction scopes and retain the prior
context.

For every CAH-025 instruction candidate, capture the canonical candidate owner but re-admit that
owner label immediately before the non-following leaf probe and again immediately before content
read. Require both resolutions to remain the same canonical directory; a disappearance or
allowed-to-allowed retarget already present at either checked seam fails as an unavailable
instruction source before that seam's later work. Rechecking only the `AGENTS.md` leaf is
insufficient because a replaced owner directory can silently redirect the whole candidate path.
This is pathname snapshot hardening, not a claim that mutation after the final check cannot race.

A CAH-025 instruction bundle is valid only when its unique owners form the strict root-to-nearest
ancestor chain for its canonical file-parent or directory scope. Validate that topology at the
result factory together with owner-depth precedence; downstream context code may trust the frozen
bundle but must still compare its canonical scope with the caller's captured scope before merge.
Canonical scope, source, and owner labels must come through one exact workspace-relative label
validator before construction; reject absolute, escaping, non-canonical, NUL, and lone-surrogate
spellings so host paths or alternate aliases cannot enter downstream context serialization.

## Tool and Safety Conventions

Implement safe repository reads as native Python tools, not subprocess wrappers. Validate tool
input before policy evaluation. Proposed edits are structured exact-replacement, create, or delete
operations; validate them, generate a unified diff, receive one approval for the exact batch,
re-check file hashes, and only then apply them.

Canonical read-tool JSON projections admit integers only in the signed 64-bit range and at most 64
object/list levels across the complete wrapped envelope, with the outer `result` object at depth 1.
Validate range, cycles, and depth during an iterative pre-serialization walk. Bound that walk before
sorting or serialization with a 65,536-unit work budget that charges every visited value/container,
object-member name, and Unicode scalar; a value that exhausts it is already too large to form an
admitted envelope. Map defensive serializer `RecursionError`/`ValueError` to the fixed invalid-result
failure; do not let interpreter limits become an unbounded exception. Provider-result construction
applies the same quote-aware complete-envelope depth preflight before JSON decode; its 65,536-byte
input cap also bounds scanner width.
Provider-tool schema integer values use the same range. Canonicalize schemas with a shape-directed,
incrementally byte-charged copier rather than a generic deep copy or an unbounded serialize-then-
measure pass. Cap each enum at 256 values and apply O(1) container-length checks plus one global
16,384-unit visit/scalar work budget before uniqueness, sorting, or bounded encoding. Map defensive
serializer `RecursionError`/`ValueError` to the bounded construction failure before a provider sees
the definition tuple. Admit only exact built-in schema containers and scalar types; arbitrary mappings,
sequences, iterators, and subclasses can execute caller-defined work even during apparent length or
iteration checks and therefore fail before their hooks are used.

Treat every present `.gitignore` as untrusted policy input. Resolve its source through the workspace
boundary, hard-deny-check the canonical source, and re-resolve and recheck immediately before its
bounded read. Missing candidates are normal; escaping, hard-denied, dangling, non-regular, stale, or
unreadable candidates fail with the fixed ignore-policy error without reading or charging content.
An admitted internal symlink keeps the candidate owner as rule scope while its canonical source owns
cache identity and byte accounting.
Capture each lexical/canonical view owner's canonical workspace-relative label and followed
directory device/inode when that directory is admitted. Re-admit the owner immediately before the
non-following `.gitignore` probe and again before a cache-miss read. At both seams require the same
captured label and identity; a persistent retarget or replacement
fails before replacement leaf work. Cache hits still require current owner/leaf/source admission
before attaching cached rules. Device/inode reuse and mutation after the final check remain possible;
these pathname snapshots narrow races rather than eliminating them.
Compile every admitted policy source into two kind-specific `GitIgnoreSpec` views from the same
bounded text. The file view retains the original lines. The direct-directory view safely removes one
semantic trailing slash before compilation while preserving escaped/trailing whitespace and leaving
degenerate slash forms unchanged. Transform only a retained pattern whose original `include` is not
`None`; require retained count plus pattern/include identity after the derived compile so an invalid
range or other original no-op cannot activate. Both views match the bare relative label and discard `ps_d`
ancestor-only matches. This lets `*/`, `**/`, and `a/**/` match the current directory entry instead
of PathSpec's first ancestor slash. `private` then `!private/` admits the parent and descendants;
`private/*` then `!private/` admits the parent but denies an immediate child directly matched by the
wildcard, because `!private/` cannot impersonate that direct child match.
Reserve file/directory two-form matching for the final leaf until its contained type is known. Bound
all ignore matching with one cumulative 65,536 candidate-pattern-slot budget per admission traversal.
For each logical evaluation, charge the selected kind-specific view's complete stored pattern-slot
count, including no-op slots, across ancestors, lexical and canonical views, both final-leaf forms,
shared cached policies, and recursive descendant admissions. Cache hits avoid content I/O, not match
work. Exactly 65,536 is inclusive; fail with the fixed `repository_policy_invalid` result before an
evaluation that would exceed it.

Represent subprocesses as argument arrays and never use `shell=True`. Built-in policy supplies the
initial candidates, user configuration may broaden or narrow them, and workspace configuration may
only narrow them. Every allowed subprocess still requires its own approval. Approval never makes a
denied command safe. Enforce workspace boundaries after resolving symlinks, strip secrets from tool
environments, and apply time and output limits.

Every tool documents its purpose, input and output schemas, capability classification, approval
requirement, filesystem access, subprocess or network behavior, timeout and output limits,
cancellation, expected failures, and security considerations.

## Testing and Definition of Done

Use pytest for Python and the TUI's chosen test runner for TypeScript. Name Python test files
`test_*.py` and test functions `test_*`. Add focused regression coverage for every behavior change,
including at least one meaningful failure path. Unit tests replace model and network interactions
with deterministic fakes. When a test's setup and intent are not self-evident, document the modeled
scenario and why it matters; trivial tests do not need explanatory comments.

Every implementation-ready story, including documentation-only work, must keep its linked lesson
consistent with the story status and delivered evidence. The additional behavioral checks below
apply when the story changes executable behavior.

All retained presentation files under `docs/lessons/assets/` are frozen historical artifacts. They
may diverge from later design corrections and are not authoritative evidence. Starting with CAH-023,
units include only the Markdown lesson and its compact text diagram. Do not add, revise, or retrofit
presentation files unless the user explicitly reverses the presentation freeze.

A behavioral story is complete only when:

1. Its happy path and a meaningful failure path are tested.
2. Public Python APIs are typed and documented, and meaningful exported TypeScript APIs use TSDoc.
3. Protocol changes have documentation and cross-language fixtures.
4. Side effects and user-visible failures are represented in validated events and transcripts.
5. Secrets do not enter events, logs, fixtures, snapshots, examples, or transcripts.
6. Python linting, formatting, docstring checks, and tests pass.
7. TypeScript type checking, linting, and tests pass when the TUI is in scope.
8. Visible TUI changes include a reducer or rendering test.
9. The unit lesson is updated with the implemented path, observed trade-offs, and test evidence.
10. Relevant conceptual documentation and user-story notes are updated.

## Unit Lesson Conventions

Every implementation-ready user story has one learning companion under `docs/lessons/`. The story
defines what must be delivered; the lesson explains what the unit teaches, why its architecture
exists, how to study its failure paths, and how a production organization might expand the design.

Follow `docs/lessons/lesson-template.md`. Each lesson includes status metadata, a quick summary,
learning objectives, why the unit matters, a junior-engineer foundation, key concepts, architecture
and invariants, a practical walkthrough, failure scenarios, a production expansion, a direct
local-versus-production comparison, trade-offs and graduation signals, exercises, key takeaways, a
local glossary, and further reading. Explain prerequisite concepts in plain language before relying
on their abstractions, including small concrete examples and common beginner misconceptions.

After implementation code exists, every completed lesson also includes exact, repository-backed code
samples that trace the important path and at least one failure or test path. Keep samples focused,
link them to their source files, and explain each sample line-by-line or in small logical chunks so a
junior engineer can connect syntax to behavior. Planned lessons may use clearly labeled pseudocode,
but must not present it as shipped code.

Retained PPTX companions through CAH-022 keep their historical validation evidence, but they are
frozen and may differ from later design corrections. CAH-023 and later require only the Markdown
lesson. The written lesson is the authoritative learning artifact.

Starting with CAH-022, keep new lessons concise and centered on system design, agentic-loop design,
and harness ownership. Every new written lesson includes a compact architecture diagram that
locates the unit in the relevant TUI, Python harness, provider, tool, and evidence boundaries. This
requirement is prospective; do not retrofit older completed lessons or presentations.

Every planned story identifies its learning emphasis. Give **core learning units** the strongest
review prompts, exercises, and teach-back questions when they cover the explicit agent loop, context
selection, provider-response handling, tool contracts and dispatch, future MCP extension and trust
boundaries, safety ownership, or evaluation. Keep **supporting implementation units** concise when
they mainly connect or implement an already-taught contract. Dependency order still wins; the label
changes review emphasis, not delivery truth.

Production-tool examples are illustrative rather than approved dependencies. Include three to five
representative tools with official references, describe the capability being compared, and discuss
operational cost as well as benefit. Keep lesson status honest: planned stories use `Planned`, work
in progress uses `Implementation companion`, blocked work states its blocker, and completed stories
use `Verified against implementation`. After a story ships, replace hypothetical paths with
concrete modules, events, tests, and observations.

## User Stories and Planning Notes

Use the story identifiers and dependency order in `user-stories/`. A story states its outcome,
dependencies, scope, acceptance criteria, validation, documentation impact, and exclusions, and
links to its lesson. Keep status accurate: documentation of a future capability is not evidence
that the capability works.

Use `user-stories/story-template.md` for new implementation-ready stories. Target roughly 600 or
fewer changed production lines per story, counted as additions plus deletions under
`src/code_assist_harness/` and `tui/src/`. Tests, documentation, fixtures, lockfiles, and generated
artifacts do not count toward that reviewability target. Record the planned range and delivered
production churn in the story. Split the unit before review when it gains a second responsibility or
is likely to exceed the target; do not pad a smaller coherent unit to reach the number. Every story
maps acceptance criteria to deterministic tests and carries an explicit story-specific definition of
done in addition to the repository-wide checklist.

Before opening a planning or implementation PR, close each affected contract neighborhood. Use the
story template's pre-review adversarial audit to trace upstream producers through every carrier and
consumer to the observable side effect, including composition roots, evaluation wiring,
control-plane inputs, empty/error/cancellation paths, and the linked lesson's exact stage order and
failure precedence. Run three independent review lenses: security plus identity/indirection;
end-to-end handoff plus composition; and provider/protocol limits plus real scheduler behavior.
Trace concrete factory inputs, carrier fields, return types, and consumer method parameters so the
planned handoff is implementable without a reverse dependency. When definitions, validation, and
execution share an inventory, prove the advertised tuple, validation catalog, and guarded executor
entry come from one captured identity; never rely on independently supplied same-shaped copies.
Exercise the real upstream producer, including framework- or SDK-generated snapshots, rather than
only hand-built values; mutate defaults, required markers, annotations, optional execution-context
fields, and every downstream snapshot that repeats a value. Trace every byte/item bound back to the
first producer: a downstream cap is not evidence when an upstream adapter, constructor, or fake can
already retain, scan, join, recurse over, or serialize an unbounded value. For SDK-to-neutral streams,
prove mapped-empty observations use an iterative pump and raw terminals drain to EOF before neutral
release. Give every failure an exact owner, type,
code/message, replay-versus-terminal disposition, and precedence. State whether each counter or byte
cap is per value, per request snapshot, per session, or cumulative, and linearize accounting against
cancellation/deadline under the real guard. Give every async checkpoint/transition an exact
continue/stop return or private sentinel and show each caller consuming it; stage synchronous values
and exceptions through the same following seam. For every lazy async producer, distinguish awaitable
lock/cleanup edges from the no-await critical section and trace charge, synchronous start, one-time
iterator claim, immutable installed-state carrier construction, final clock read, one non-failing
pointer commit, terminal-to-EOF consumption, uninstalled/intermediate/terminal cleanup, one
cleanup-task owner, and watcher lifetime. Lock which side wins immediately before and after the
pointer commit.
Name the sole composition factory and prove exact service/catalog/handler identities and explicit
runtime profiles. When a default runtime path or opaque identifier changes, enumerate every external
consumer, fixture, transcript, cancellation semantic, and documentation surface that must migrate.
Finally, render the changed Markdown neighborhood: check diagrams mechanically for every success and
failure branch, balance code fences, and compare pseudocode fields/signatures with their producers.
After fixing a review finding, repeat the neighborhood audit instead of checking only the cited
line. The production-line budget does not constrain documentation-only planning changes, so split a
large milestone refinement by contract neighborhood—normally one core learning story or two to
three tightly coupled supporting stories—and land a skeleton milestone map separately when useful.

Record durable implementation discoveries under `user-stories/notes/`. Capture decisions,
unexpected constraints, failure causes, validation evidence, and follow-up work without turning the
notes into a second backlog. Update an ADR when a new decision supersedes an accepted architectural
choice.

## Commit and Pull Request Guidelines

Use short, imperative commit subjects consistent with history, such as `Document harness
architecture`. Keep each commit to one logical change and, where practical, one user story. Branch
names should be descriptive, such as `agent/add-tool-registry`. Pull requests explain what changed,
why it changed, and developer impact; list validation commands and link relevant stories or issues.
Include screenshots only for visible UI changes.

Whenever a review comment is addressed, mark its inline review thread as resolved. Reply with the
fix or decision evidence when that context will help the reviewer, and resolve the thread only after
the change or documented disposition has been validated. Leave a thread open while work, a blocker,
or an unresolved design conflict remains. Before review handoff, fetch thread-aware state and verify
that no unresolved actionable review thread remains.

When a unit reaches **Done** and its required validation passes, complete the publish workflow in the
same unit: create or switch to a descriptive branch, commit only the intended changes, push the
branch, open a pull request, and mark it ready for review. Use a draft pull request while work is
incomplete, but do not leave a completed unit only in the local worktree or in draft state unless the
user explicitly requests that outcome.

## Security and Configuration

Never commit API keys or `.env`. Copy `.env.example` locally and provide `OPENAI_API_KEY` through
the environment only when an explicitly live-provider workflow requires it. Keep sample values
blank or unmistakably fake. Do not log credentials, environment values, raw provider responses, or
unbounded tool output.

Explicit OpenAI-provider selection authorizes bounded, policy-admitted repository context and tool
results to leave the local machine for that session. Warn users that path deny and ignore rules are
not content-level secret scanning: an otherwise allowed source file may contain sensitive text. The
mock path remains local and network-free.

Store validated, redacted transcripts under the WSL XDG state directory with restrictive local
permissions. Do not add harness state to target repositories. Support `--no-transcript` before the
first real-provider release.
