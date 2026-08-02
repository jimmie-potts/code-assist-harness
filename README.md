# Code Assist Harness

Code Assist Harness is a learning-first, local coding agent for Ubuntu under WSL. Its goal is to
inspect and explain a repository, form a plan, propose controlled file changes, run approved
validation commands, show the resulting diff, and summarize the outcome.

The first release is a personal learning project. Its Python core is deliberately separated from
the terminal UI, model provider, and execution environment so it can later become a reusable
harness library.

## Current status

The repository now contains a cancellable M0 mocked-session path. A supervised Ink/TypeScript parent
launches Python through `uv`, completes the validated protocol version 1 readiness handshake, sends
non-empty tasks as correlated `session.start` commands, and renders three deliberately delayed
assistant deltas before completion. While a session is running, Escape sends one correlated
`session.cancel`; Python cooperatively stops the mock and emits the authoritative terminal outcome.
Pydantic and Zod validate strict, hand-maintained wire contracts on both sides; bounded LF readers
contain malformed lines; shared fixtures prove cross-language parity; and real
Node-to-`uv`-to-Python tests prove streaming, cancellation, repeated sessions, and process cleanup.
Pure Python and TypeScript reducers now derive the same eight-state session lifecycle from trusted
domain facts and validated wire events. Fifty shared transition, replay, and failure cases guard
correlation, session identity, contiguous sequence, assistant completion, and absorbing terminals.
The Python mock and TypeScript supervisor route their current event tapes through those cores, while
the Ink conversation projection preserves completed, cancelled, and failed turns.
Each accepted session now attempts an append-only transcript under the WSL XDG state directory and,
after a successfully persisted terminal record, a human-readable summary. The writer emits transcript
version 3; replay accepts internally consistent version-1, version-2, and version-3 tapes. Python
redacts configured sensitive values and recognized credentials, bounds persisted text, writes
owner-only artifacts, flushes every accepted record, and replays lifecycle state through the same
reducer. Provider-backed version-3 tapes may also carry bounded, transcript-only
`model.usage_observed` and `loop.limits_observed` records, restored through a separate evidence
projection. A mock-session version-3 tape may omit loop-limit evidence because the launched mock does
not enter the provider-backed path. A storage failure becomes one recoverable TUI warning without
changing the session outcome. Use `--no-transcript` to disable only these local files.
The default launch still composes `MockSession`, so the protocol-v1 TUI experience remains the
deterministic three-delta mock. Explicitly selecting `--provider openai --model
gpt-5.6-luna` instead composes the first real adapter and runs one harness-owned
`ProviderSession` under the same four immutable hard limits. The adapter owns SDK request/event
translation, fixed safe failure mapping, and one-operation stream/client cleanup; SDK objects and
credentials do not enter provider-neutral, protocol, or transcript types. The request is text-only,
foreground, `background=false`, and `store=false`, with reasoning effort disabled and generated
tokens capped. Luna may contribute one opaque empty reasoning envelope before its message; reasoning
text, summaries, and provider tools still fail closed and never cross the provider port.
Default tests use SDK fakes with network denied, and the credentialed live smoke remains an explicit
non-default check. Each provider session owns a fresh limit tracker, and its deadline excludes local
event and transcript sink latency. Completion, failure, cancellation, deadline expiry, teardown, and
one shared provider-cleanup task remain serialized around one terminal winner; every cleanup await has
a fixed five-second local grace. CAH-009 documents the first end-to-end mocked execution in the
[walking-skeleton guide](docs/walking-skeleton.md). Its normalized success and cancellation examples
are checked against the shared protocol validators and the real process-boundary evidence. CAH-007
adds one offline `./scripts/check` gate and a lockfile-driven Linux workflow for the complete M0
evidence. CAH-010 begins M1 with replayable in-memory lifecycle state, and CAH-011 adds durable local
evidence without moving lifecycle authority into storage. CAH-020 adds the provider port and strict
network-free fake, CAH-021 completes the first injected provider-neutral turn, and
[CAH-022](user-stories/cah-022-enforce-loop-limits.md) completes its hard limits with a
[written lesson](docs/lessons/cah-022-loop-limits.md) and
[visual companion](docs/lessons/assets/cah-022-loop-limits.pptx). CAH-023 adds the strict OpenAI
Responses adapter and explicit launch selection without changing protocol v1. Workspace discovery and
reads, tool execution, policy, and broader multi-turn agent behavior remain unimplemented.

The original LangChain-based direction has been superseded. The project will own its agent loop
directly. LangChain may be considered later as an adapter, but it is not the MVP orchestrator and
core domain types must not depend on it.

The superseded LangChain packages have been removed from Python project metadata and `uv.lock`.
Pydantic v2 is the Python runtime's first boundary-validation dependency. The TUI's Ink, React,
Zod, and development dependencies are kept separately in `tui/package.json` and its committed npm
lockfile.

Start with the [architecture overview](docs/architecture.md), the
[walking-skeleton execution guide](docs/walking-skeleton.md), the [decision records](docs/adr/), and
the [dependency-ordered backlog](user-stories/README.md).

## MVP boundary

The MVP will:

- inspect, search, and read workspace files automatically;
- answer repository questions and display an implementation plan;
- stage structured edit proposals and ask before applying a complete edit batch;
- ask before every allowlisted subprocess command;
- display proposed and applied diffs;
- run approved tests and linters;
- support cancellation and clean shutdown; and
- write a human-readable, append-only session record unless disabled.

The MVP will not commit, push, branch, access the network through tools, run multiple agents,
resume sessions, use framework-owned orchestration, use embeddings, or run tools in a container.
Native Windows, macOS, and multiple model providers are also outside the initial scope.

## Architecture at a glance

The application will run entirely inside Ubuntu under WSL:

```text
Ink TUI (TypeScript / Node)
  owns terminal input, rendering, approval presentation, and keyboard cancellation
            |
            | versioned NDJSON: commands on stdin, events on stdout
            v
Python harness runtime
  owns session state, the agent loop, context, policy, approval authority, tools, and transcripts
            |
            +-- provider adapter (OpenAI first)
            +-- workspace reads, staged edits, and approved subprocesses

Python stderr is reserved for human-readable diagnostics.
```

Important boundaries:

- The TUI is a projection of harness events, not the orchestrator or policy authority.
- The TUI presents approval requests; Python binds decisions to actions and authorizes them.
- OpenAI SDK objects stay inside the OpenAI provider adapter.
- Process and model-boundary data is validated with Pydantic v2 in Python and Zod in TypeScript.
- Native reads may run automatically, while edits and every subprocess require informed approval.
- Commands are argument arrays, never shell strings, and approval cannot override the allowlist.
- Transcripts live under the WSL XDG state directory, not in the target workspace.

See [architecture.md](docs/architecture.md) for the complete target structure and ownership model.

## Supported development environment

- Ubuntu under WSL
- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- Node 22.22.1, pinned in `.node-version`; the enforced TUI range is `>=22.13.0 <23`
- npm 9 or newer

An OpenAI API key is not needed for the walking skeleton, default launch, or default tests. The
adapter consumes `OPENAI_API_KEY` only after OpenAI and the exact model are explicitly
selected; Python rejects every other ambient `OPENAI_*` setting and `SSLKEYLOGFILE` before SDK
import. CAH-011 may inspect a recognized credential value solely to seed transcript redaction.
Credentials and `.env` files must never be committed. The optional repository-root `dev.env` is
ignored, stores one local plaintext key, and is read only by the explicit
`scripts/with-openai-dev-key` helper.

## Setup, launch, and checks

Install the Python scaffold and the locked TUI dependencies:

```bash
uv sync --dev
npm --prefix tui ci
```

Run the canonical non-live gate from any directory:

```bash
/path/to/code-assist-harness/scripts/check
```

From the repository root, the usual form is `./scripts/check`. Setup and validation are deliberately
separate: the gate does not install or update dependencies. It checks the Python lock and prepared
environment, runs Python lint/docstring rules and formatting, then labels Python unit tests, Python
protocol fixtures, and Node compatibility separately. The Node stage runs before repository policy,
whose complete-lock-graph check invokes npm, and before every TUI npm stage. The gate then labels
repository policy, TUI type checking, lint, unit tests, TypeScript protocol fixtures, and the real
Node-to-`uv`-to-Python integration as distinct stages. Repository policy uses Git's tracked and
nonignored untracked files to check local documentation links and anchors, the complete TUI lock
graph, and the production-source network boundary.

The script verifies the Python environment with `uv sync --check --locked --offline`, runs Python
tools with `uv run --offline --frozen --no-sync`, and uses npm offline mode. It sets `TMPDIR=/tmp`,
suppresses Python bytecode writes, and removes common OpenAI, Azure OpenAI, Anthropic, and Google
provider credentials from its child environment. It also clears ambient uv project, environment,
interpreter, working-directory, and no-project selectors so local Python checks cannot be redirected
away from the repository's prepared environment, and clears isolated-run mode so `uv run` cannot
substitute an ephemeral environment. The top-level Python and Node checks preload guards that reject
common socket/network client entry points. The runtime supervisor deliberately strips ambient Python
selectors, including `PYTHONPATH`, and `SSLKEYLOGFILE` before its real Python child, then starts Python
with `-E` so remaining `PYTHON*` variables are ignored. Source policy permits the approved SDK and
network surface only inside the concrete OpenAI adapter; provider-neutral code remains isolated. The
canonical gate deselects the live-provider marker and removes OpenAI credentials and routing
configuration. These are defense-in-depth controls, not a general-purpose network sandbox for
arbitrary native executables.

`uv sync --dev` is required before launch. The runtime supervisor verifies that `.venv/pyvenv.cfg`
and an executable `.venv/bin/python` already exist before it invokes `uv`; an unprepared checkout
therefore fails without spawning a child or creating `.venv`. The launch then selects that exact
interpreter and starts it without resolving, downloading, or synchronizing dependencies. Launch the
supervised shell from the repository root inside Ubuntu WSL:

```bash
./scripts/run-tui
```

That command selects the deterministic mock. To keep a local development key outside shell history,
create the ignored repository-root `dev.env` from an interactive prompt:

```bash
./scripts/with-openai-dev-key --init
```

The initializer refuses to replace an existing file or symlink, creates the path exclusively at mode
`0600` before prompting, never places the key on the command line, and removes the file if entry,
validation, or persistence fails. The file may contain blank lines and comments, but exactly one
non-empty `OPENAI_API_KEY=...` assignment and no other setting. It remains plaintext; mode `0600`
limits access to its owner but is not encryption. Keep provider/model selection out of the file. Then
opt into the real bounded turn through the explicit reader and the reviewed Luna model:

```bash
./scripts/with-openai-dev-key \
  ./scripts/run-tui --provider openai --model gpt-5.6-luna --no-transcript
```

Provider and model are child-process configuration, not NDJSON fields. TypeScript validates the pair
for early feedback and Python validates it again before importing or constructing the SDK adapter.
The helper never sources or evaluates `dev.env`; it rejects symlinks, permissions other than `0600`,
every already exported `OPENAI_*` variable, `SSLKEYLOGFILE`, malformed assignments, and unsafe
whitespace/control characters in the key before preserving the command arguments with `exec`. It
runs through Ubuntu's absolute system Python in isolated mode so ambient Python import settings
cannot alter credential admission. Direct `run-tui`, `uv`, and `./scripts/check` commands never read
`dev.env` automatically, and the canonical gate removes provider credentials from its children.

The directory from which the launcher is invoked is the default workspace. Select a different
single workspace with an absolute path, or with a path relative to that launch directory:

```bash
./scripts/run-tui --workspace /path/to/repository
```

Transcripts are enabled by default and live under
`$XDG_STATE_HOME/code-assist-harness/transcripts/`, falling back to
`~/.local/state/code-assist-harness/transcripts/`. Disable transcript and summary creation for a
run with either of these equivalent forms:

```bash
./scripts/run-tui --no-transcript
./scripts/run-tui --workspace /path/to/repository --no-transcript
```

The flag controls local harness artifacts only; it does not cancel an OpenAI request or supersede
provider-account retention controls. Transcript filenames contain a pseudonymous workspace
hash, session ID, and random transcript ID, not the workspace path or repository name. The hash is
not anonymous, file mode `0600` is not encryption, and retention remains the local user's
responsibility.

The launcher reports actionable setup guidance when Node or npm is missing, rejects Windows Node or
npm executables reached directly or through a symlink, and checks the supported Node range before
npm or the TypeScript loader runs. The runtime supervisor separately resolves `uv` from its filtered
`PATH`, follows symlinks, rejects paths under `/mnt` and names ending in `.exe`, and validates the
prepared project environment before spawn. The TUI then sends a validated `runtime.initialize`
command, waits for the correctly correlated `runtime.ready` event, and displays the canonical
workspace and runtime state. With the default provider, type a non-empty task and press Enter to start
the deterministic mock. The conversation renders these three fragments as they arrive:

```text
Mock response:
the task crossed the process boundary
and streamed back successfully.
```

Together they form `Mock response: the task crossed the process boundary and streamed back
successfully.` The session status moves from idle through starting and running to completed; after
completion, another task can run without restarting the application. Entering only whitespace
shows local feedback and sends no command. Input submitted during an active session is preserved
with feedback rather than sent.

The mock pauses for 500 ms before each delta so its lifecycle is visible during manual use. After
`session.started` makes the Python-owned session ID addressable, the running status shows
`Esc to cancel`. Press Escape once to enter `cancelling`; the TUI waits for Python rather than
optimistically declaring success. If cancellation wins, Python emits `session.cancelled`, the TUI
shows `cancelled · ready for another task`, and no later assistant or terminal event is accepted.
If normal completion wins first, `completed` remains authoritative. Repeated or late Escape presses
are harmless local no-ops.

Ctrl+C still exits the whole application rather than cancelling only the session. The lifecycle
sends `runtime.shutdown`; Python drains an accepted bounded mock before exiting, and Node then
closes stdin, terminates the detached process group if it does not exit within bounded grace
periods, and awaits the child close event. `SIGHUP` and `SIGTERM` also request an Ink unmount and
enter this same cleanup path.

Startup troubleshooting:

- If startup says `uv` was not found or resolves to a Windows path, install and select Linux `uv`
  inside Ubuntu WSL, then retry.
- If startup reports that the project environment is unprepared, run `uv sync --dev` in this
  repository and retry. The supervisor checks for `.venv/pyvenv.cfg` and executable
  `.venv/bin/python` before `uv` starts, so this failure does not create or update `.venv`.
- If Python exits with an environment or import diagnostic, rerun `uv sync --dev`; launch never
  updates the lockfile or prepared environment for you. The supervised child intentionally removes
  inherited `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, `SSLKEYLOGFILE`, and every `UV_*` variable;
  Python also starts with `-E`, while supported project, environment, and interpreter choices are
  supplied explicitly in the argument array instead.
- If workspace selection fails before Ink renders, check that the `--workspace` value exists, is a
  directory, and is accessible from Ubuntu WSL.
- If Python exits after spawning, the TUI shows a bounded, sanitized stderr summary and remains in
  a failed state until Ctrl+C. The supervisor does not restart it automatically.
- If startup reports a protocol failure, inspect the safe failure code. Unsupported, unknown,
  malformed, mismatched, and timed-out readiness messages never enter trusted TUI state; the
  supervisor closes command input and reaps the child during normal cleanup.

Run focused Python checks while iterating:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Run the TUI checks individually or together:

```bash
npm --prefix tui run typecheck
npm --prefix tui run lint
npm --prefix tui test
npm --prefix tui run check
```

`npm --prefix tui test` includes `tui/test/runtime-boundary.test.ts`, which launches the genuine
offline `uv`/Python child, exercises streamed completion and cancellation, compares the normalized
walking-skeleton message tapes with the teaching fixtures, starts another session, and verifies
cleanup. Python and TypeScript protocol tests also parse every NDJSON line reproduced by the guide.
The `npm --prefix tui run check` command adds TypeScript type checking and linting around that suite.

The TUI start and test scripts set `TMPDIR=/tmp`. This avoids a WSL environment failure observed
when inherited `TEMP` and `TMP` values named a missing Windows directory. The checks use installed
local packages and do not require a model, credentials, or network access.

`uv build` remains available as a focused packaging check, but the M0 gate does not build or publish
an artifact. If `./scripts/check` fails, its `==>` heading identifies the first failing layer. A
Python lock/environment failure means setup is missing or drifted; documentation, TUI lock-graph, or
network-policy failures belong to the repository-policy stage; and the final `Node-Python
integration` stage owns the real process boundary.

The `Repository checks` GitHub Actions workflow runs on pull requests and pushes to `main` using
Ubuntu 24.04, Python from `.python-version`, Node from `.node-version`, and uv 0.11.28. It installs
with `uv sync --locked` and `npm ci`, then invokes the same `./scripts/check` command rather than
duplicating its check list in workflow YAML.

## Current and planned project layout

```text
src/code_assist_harness/  Runtime, reducers, protocol, persistence, and provider implementations
tests/                    Current Python tests mirroring source modules
tui/                      Current supervised Ink app, Zod protocol boundary, metadata, and tests
scripts/run-tui           Current WSL-aware launcher and argument-forwarding boundary
scripts/check             Canonical offline repository validation gate
protocol/                 Reviewed cross-language protocol, lifecycle, and launch-config fixtures
evals/                    Planned deterministic scenario fixtures
docs/                     Architecture and learning documentation
docs/lessons/             Unit-by-unit learning companions
user-stories/             Roadmap, implementation stories, and planning notes
```

The Python runtime, supervised TUI, protocol messages and fixtures, deterministic mocked streaming,
cooperative session cancellation, conversation projection, transcript-v3 persistence with v1/v2/v3
replay, provider-neutral request and stream contracts, strict programmable fake, one hard-bounded
provider session turn, and the explicitly selected OpenAI Responses adapter exist today. The launched
TUI defaults to the mock. Broader evaluation, workspace discovery and reads, tools, policy, and
transcript browsing/export/retention remain planned and are introduced only by the story that needs
them.

## Documentation map

- [Architecture](docs/architecture.md)
- [Walking-skeleton execution guide](docs/walking-skeleton.md)
- [Glossary](docs/glossary.md)
- [Protocol](docs/protocol.md)
- [Agent loop](docs/agent-loop.md)
- [Context engineering](docs/context-engineering.md)
- [Tool system](docs/tool-system.md)
- [Safety model](docs/safety-model.md)
- [Evaluation](docs/evaluation.md)
- [Unit lessons](docs/lessons/README.md)
- [CAH-007 repository-check lesson](docs/lessons/cah-007-repository-checks.md)
- [CAH-007 visual lesson](docs/lessons/assets/cah-007-repository-checks.pptx)
- [CAH-022 loop-limit lesson](docs/lessons/cah-022-loop-limits.md)
- [CAH-022 visual lesson](docs/lessons/assets/cah-022-loop-limits.pptx)
- [User-story backlog](user-stories/README.md)

Documentation is part of the product. Public Python APIs use Google-style docstrings, meaningful
exported TypeScript contracts use TSDoc, and behavioral work updates the relevant conceptual
document alongside code and tests.
