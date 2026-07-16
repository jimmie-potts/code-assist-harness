# CAH-003 lesson: Python runtime supervision

- **Unit:** CAH-003
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; the physical Node-to-uv-to-Python boundary and cleanup path are tested
- **Story:** [CAH-003](../../user-stories/cah-003-supervise-python-runtime.md)
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md) and
  [protocol design](../protocol.md#process-responsibilities)
- **Visual companion:** [CAH-003 lesson deck](assets/cah-003-python-runtime-supervision.pptx)

> This lesson follows the implemented CAH-003 path. It establishes process lifetime and stream
> ownership but deliberately stops before CAH-004's versioned readiness and message parsing.

![Concept illustration of one parent process supervising one child through three distinct
channels](assets/cah-003-process-supervision-concept.png)

*Concept illustration—not an implementation screenshot. The paired process modules and three
channels represent the planned parent-child lifetime and stdin, stdout, and stderr ownership.*

## Quick summary

This unit makes the Ink parent and Python child behave as one local application. The implementation
uses a shell-free argument array with a prevalidated Linux `uv` and prepared interpreter, canonical
single-workspace selection, typed supervisor states, bounded redacted diagnostics, and detached
process-group cleanup. Eight Python tests and 53 TUI tests verify the boundary without involving a
model, network request, or workspace mutation.

## Learning objectives

After completing this unit, you should be able to:

- explain which process owns startup, runtime work, rendering, and shutdown;
- preflight a Linux `uv` and prepared project environment before spawning without a shell;
- pass one canonical workspace and one prepared Python interpreter explicitly;
- keep machine protocol streams separate from human diagnostics;
- prove child termination and reaping with controlled process fixtures.

## Why this unit matters

If process ownership is vague, later protocol and cancellation bugs become indistinguishable from
orphaned processes, bad working directories, and mixed stdout logs. CAH-003 proves the physical
boundary before messages acquire domain meaning.

One parent and one child also create the replaceable seam needed for a future CLI or library caller:
the TUI supervises a runtime; it does not absorb runtime responsibilities.

## Key concepts

### Supervision owns the whole child lifetime

Starting a process is only the first transition. The parent must observe spawn errors, normal and
abnormal exit, close pipes, terminate on UI shutdown, and reap the child exactly once.

### Argument arrays avoid shell interpretation

The parent invokes `uv` with a program and argument list. It must not concatenate a workspace or
runtime option into a shell string. This is both safer and easier to test exactly.

### Preflight keeps setup failure non-mutating

`--no-sync` tells `uv` not to synchronize an existing environment; it does not prevent `uv` from
creating a missing project environment. The supervisor must therefore validate the resolved `uv`
path and prepared `.venv` before spawn. This check establishes presence and executable structure,
not freshness against `uv.lock`; `uv sync --dev` remains an explicit developer action.

### Workspace is configuration, not ambient state

The CLI resolves the launch directory or `--workspace PATH`, then passes the canonical choice to
Python. The child must not silently choose a different root from its incidental current directory.

### Standard streams are typed channels by convention

stdin and stdout are reserved pipes for the forthcoming protocol. stderr carries bounded human
diagnostics. A debug `print()` on stdout is therefore a contract violation even before CAH-004
defines JSON schemas.

## Architecture and design

```text
Ink CLI
  | resolve one workspace
  | preflight: Linux uv + prepared .venv
  | spawn: validated uv [runtime arguments], shell disabled
  v
Python runtime
  stdin  <- reserved protocol pipe
  stdout -> reserved protocol pipe
  stderr -> bounded diagnostics -> visible TUI failure/help

Ink exit and terminal restore -> finally close stdin -> signal if needed -> await/reap child
```

The implemented invariants are:

- the TUI resolves and realpaths `uv`, rejects `/mnt` and `.exe` paths, and does not spawn when the
  supported Linux executable cannot be established;
- `.venv/pyvenv.cfg` and executable `.venv/bin/python` must exist before spawn, so an unprepared
  checkout cannot be mutated by `uv` during failed startup;
- the TUI starts the prepared Python interpreter through `uv` with an argument array and no shell
  interpolation;
- one runtime process serves exactly one explicit workspace;
- the child environment inherits parent settings except `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`,
  and all `UV_*` variables;
- stdin and stdout remain protocol-only pipes, while diagnostics use stderr;
- startup and unexpected-exit errors are actionable, bounded, and secret-safe;
- cleanup is idempotent, waits for `close`, and leaves neither the `uv` wrapper nor Python child
  behind; and
- tests use controlled children and never invoke a model, network, or workspace mutation.

`tui/src/runtime-supervisor.ts` builds this exact logical request:

```text
PREVALIDATED_LINUX_UV run --project REPOSITORY_ROOT --frozen
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  --python VENV_PYTHON
  -- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE
```

Node passes each token separately with `shell: false`, uses the harness repository as `uv`'s project
and working directory, configures all three streams as pipes, and starts a detached process group.
The separately resolved workspace may contain spaces because it is one argument rather than shell
text. Before spawning this request, the supervisor resolves `uv` from filtered `PATH`, realpaths it,
rejects a resolved path under `/mnt` or ending in `.exe`, and requires `.venv/pyvenv.cfg` plus an
executable `.venv/bin/python`. The explicit `--python` fixes that prepared interpreter. `--frozen`
prevents lockfile updates, `--no-sync` avoids synchronizing the existing environment, and the
offline and download flags prevent network-backed preparation. The child environment omits
`PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, and every `UV_*` variable so inherited project,
environment, and interpreter selectors cannot bypass the preflight. The developer must run
`uv sync --dev` before starting the TUI.

The supervisor's local UI state machine is
`starting -> running -> stopping -> stopped` for requested cleanup. A spawn error instead reaches
`failed-to-start`; any close before `stop()` reaches `unexpectedly-exited`, even when the exit code
is zero. The operating-system `spawn` event is only CAH-003's temporary running boundary. It does
not assert that Python is ready for commands; CAH-004 owns that proof.

## Practical walkthrough

1. **Preserve the caller's workspace context.** `scripts/run-tui` captures `pwd -P` before npm's
   `--prefix` can change process context, exports it as `CODE_ASSIST_LAUNCH_DIRECTORY`, and forwards
   `--workspace` plus its value as distinct arguments. `tui/src/workspace.ts` accepts either no
   arguments or exactly `--workspace PATH`, resolves relative values from that captured directory,
   removes symlinks, and rejects missing paths or files before spawn.
2. **Create one fixed supervisor.** `tui/src/cli.ts` resolves the harness repository independently
   from the target workspace and constructs one `PythonRuntimeSupervisor`. The supervisor stores one
   workspace for its lifetime, so a later request cannot switch roots accidentally.
3. **Preflight, then launch through a typed argument array.** The supervisor resolves `uv` from the
   filtered child `PATH`, realpaths and validates that Linux path, and checks the prepared venv
   metadata and interpreter before calling the injected spawn seam. `buildRuntimeLaunchRequest`
   fixes the explicit `--python` interpreter, every supported `uv` option, repository working
   directory, three pipes, `shell: false`, and `detached: true`; `prepareRuntimeLaunch` replaces the
   logical command with the validated absolute executable. The request also snapshots the parent
   environment without Python or `uv` environment-selection overrides. Tests prove invalid paths
   and unprepared environments never reach spawn or create `.venv`.
4. **Keep transport bytes opaque.** `src/code_assist_harness/runtime.py` revalidates the canonical
   workspace, creates one `asyncio` loop, and uses an event-loop reader to discard stdin bytes until
   EOF. It writes no stdout. Node calls `resume()` on child stdout so the pipe cannot stall, but does
   not parse or render it before CAH-004.
5. **Project lifecycle without owning policy.** `tui/src/run-application.tsx` subscribes to
   supervisor transitions and rerenders `tui/src/app.tsx`. The component displays starting,
   running, startup-failure, unexpected-exit, stopping, and stopped projections; it never decides a
   transition.
6. **Sanitize diagnostics before UI state.** `tui/src/runtime-diagnostics.ts` retains only the last
   4,096 stderr bytes and tracks whether that tail begins at a physical-line boundary. When it begins
   mid-line, the collector discards the leading fragment before redaction; if no complete line
   remains, the safe result is only the omission marker. It redacts sufficiently distinctive
   inherited environment values plus recognized separator-delimited and common camel-case or
   concatenated credential names through the end of their physical line, including multi-part
   authorization, cookie, API-key, and auth-token values. Known-secret fragments cut at either tail
   boundary are also removed. It strips terminal controls, normalizes whitespace, and limits the
   displayed summary to 1,200 characters. Stdout is never an input to that summary.
7. **Clean up from one `finally` path.** After Ink exits and restores the terminal, or if rendering
   fails before spawn, `runApplication` calls `stop()`. The supervisor closes stdin first, waits for
   normal EOF exit, then sends `SIGTERM` and `SIGKILL` to the detached process group only after
   successive grace periods. Parent `SIGHUP` and `SIGTERM` request an Ink unmount and enter the same
   path. Those signal handlers stay installed until child shutdown settles, while a first-signal
   guard absorbs repeats. Repeated stops share one promise, and completion waits for `close`.
8. **Verify both seams.** Controlled tests force preflight rejection, spawn error, unexpected exit,
   secret output, and signal escalation deterministically. `tui/test/runtime-boundary.test.ts`
   performs the real Node-to-uv-to-Python launch, walks every uv task's descendants under `/proc`,
   and verifies the match is a Python executable running the genuine runtime rather than the uv
   command line echoing its child arguments. The exact prepared-interpreter argument is proven
   separately by the request unit test. The boundary test then stops the supervisor, proves both
   observed PIDs are gone, and confirms the temporary workspace stayed empty.

The completed validation evidence is eight Python tests, including seven runtime tests, and 53 TUI
tests across ten files. `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and
the TUI type-check, lint, and test scripts pass without a model or live network access.

## Failure scenarios to study

### `uv` is missing or resolves outside Linux

**Symptom:** `uv` is absent from the filtered `PATH`, cannot be resolved, or realpaths under `/mnt`
or to a name ending in `.exe`. **Boundary:** supervisor preflight before spawn. **Safe outcome:** show
the failed executable requirement, remain out of running state, and never hand Linux repository or
workspace paths to a Windows process. **Evidence:** supervisor tests cover missing, direct-Windows,
and symlink-hidden Windows paths and prove the spawn seam is not called.

### The prepared project environment is missing

**Symptom:** `.venv/pyvenv.cfg` or executable `.venv/bin/python` is absent. **Boundary:** supervisor
preflight before `uv`. **Safe outcome:** direct the developer to `uv sync --dev`, remain out of
running state, and do not create or update `.venv`. **Evidence:** supervisor tests use an unprepared
repository fixture and prove the spawn seam is not called and the environment remains absent.

### Workspace selection is invalid

**Symptom:** the default or `--workspace` value is missing, inaccessible, a file, duplicated, or
combined with an unknown option. **Boundary:** CLI configuration before spawn, with defense in depth
at the Python entry point. **Safe outcome:** reject the configuration with an actionable error and
never infer a fallback root. **Evidence:** `tui/test/workspace.test.ts` covers canonical defaults,
relative paths with spaces, invalid arguments, files, and missing paths;
`tests/test_runtime.py` independently covers the Python validation and stderr-only failure.

### Python exits after starting

**Symptom:** pipes close with a nonzero exit and bounded stderr. **Boundary:** supervisor lifecycle.
**Safe outcome:** move the UI to visible failure and never treat EOF, or even an unrequested exit
code zero, as successful completion. **Evidence:** `tui/test/runtime-supervisor.test.ts` injects
stdout that resembles a future protocol line plus stderr containing configured and named secrets.
The failure includes safe stderr context, excludes stdout, redacts full known-secret fragments and
complete multi-part credential lines, recognizes common forms such as `apiKey`, `authToken`, and
`accesskey`, and drops a credential remainder when the byte tail begins mid-line while retaining
later complete diagnostics. `tui/test/app.test.tsx` verifies both startup and runtime failures are
visible.

### Ambient runtime configuration redirects startup

**Symptom:** inherited `PYTHONPATH`, `PYTHONHOME`, `VIRTUAL_ENV`, or `UV_*` configuration selects an
external module, environment, project, or interpreter instead of the prepared harness environment.
**Boundary:** preflight and parent-to-child environment construction. **Safe outcome:** preserve
required parent settings but omit every redirecting selector without mutating the source
environment, and supply the supported choices explicitly in argv. **Evidence:** request tests prove
the filter, and the real boundary test supplies poisoned values yet still observes the genuine
runtime.

### The TUI exits but Python remains

**Symptom:** an orphan child retains pipes or workspace resources. **Boundary:** parent cleanup.
**Safe outcome:** close stdin, signal the detached process group if needed, wait for `close`, and
make repeated cleanup harmless. **Evidence:** the controlled test records `SIGTERM` then `SIGKILL`
and proves repeated `stop()` calls share a promise. A regression also sets the uv leader's exit code
before inherited descendant pipes close and proves the process group still receives `SIGTERM`; the
`close` event, not the leader's exit-code field, is the cleanup guard. The real boundary test
observes that `uv` may be a wrapper with a separate Python descendant, then proves neither PID
remains under `/proc` after cleanup. A lifecycle regression sends a second termination request
while `stop()` is pending and proves the persistent handler absorbs it until cleanup completes.

## Production expansion

### Example enterprise scenario

Imagine remote execution workers processing thousands of concurrent sessions. Workers may run on
different hosts, need health checks and durable job state, and must survive client disconnects.
Local parent-child supervision is no longer enough to provide scheduling, recovery, or fleet-wide
diagnostics.

### Typical production capabilities and tools

- [Node child processes](https://nodejs.org/api/child_process.html) represent local spawn, pipes,
  signals, and exit observation used by this story, but application code must own signal races,
  pipe backpressure, and platform edge cases.
- [Python asyncio subprocesses](https://docs.python.org/3/library/asyncio-subprocess.html) represent
  asynchronous process and stream supervision within Python services, while cancellation, stream
  draining, and event-loop shutdown require specialized tests.
- [systemd](https://systemd.io/) represents host-level service lifecycle, process tracking, and
  restart policy, at the cost of unit-file rollout, host operations, log retention, and on-call
  response.
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) represent
  scheduled, retried, and observable finite workloads across a cluster, while capacity, manifests,
  telemetry, and cluster upgrades require platform ownership.

These references describe capabilities, not required deployment choices for the local MVP.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Topology | One Node parent and one Python child | Client, scheduler, and worker fleet |
| Identity | One canonical workspace fixed before spawn | Authenticated tenant, job, and storage identities |
| Lifetime | Bound to one terminal process | Durable jobs independent of client connection |
| Readiness | OS spawn only until CAH-004 | Health and readiness contracts routed through a control plane |
| Shutdown | stdin EOF, then bounded process-group signals | Lease expiry, drain policy, retries, and worker replacement |
| Recovery | Show failure; user restarts | Retry policy, rescheduling, and persisted state |
| Diagnostics | Bounded redacted stderr tail | Central telemetry with retention, access, and incident controls |
| Cost | Direct, inspectable process API | Control plane, capacity, security, and on-call ownership |

### Trade-offs and graduation signals

A scheduler can improve recovery and utilization but adds distributed state, queues, identity,
network failure, and operational ownership. CAH-003 also exposed several local trade-offs: `uv` can
remain a wrapper around a separate Python process, so signaling only its PID is insufficient;
`--no-sync` does not prevent creation of a missing project environment, so an explicit preflight is
required; path validation rejects known WSL-to-Windows crossings without attempting binary-format
inspection; ambient Python, virtual-environment, and `uv` selectors are intentionally ignored to
preserve the prepared interpreter; dropping a leading partial diagnostic line may sacrifice useful
text to avoid exposing an unlabelled credential remainder; and the spawn event is useful for
lifecycle state but too weak for protocol readiness. A detached process group, documented
`uv sync --dev` prerequisite, supervisor preflight, narrow environment filter, conservative
diagnostic truncation, and deferred CAH-004 handshake address those constraints without introducing
a daemon or scheduler. Graduate when concurrent demand, remote execution, client-disconnect
survival, or measured orphan/recovery incidents require those capabilities.

## Practical exercises

1. Trace `PythonRuntimeSupervisor.start()` for spawn error, spawn followed by close, and requested
   stop. Identify why exit code zero has different meaning before and after `stop()`.
2. Run the focused Python runtime test and identify the assertions proving that stdin may contain
   unimplemented bytes while stdout and stderr remain empty on clean EOF.
3. Compare the exact launch request with a shell string containing a workspace path with spaces;
   explain which interpretation risks disappear with the argument array.
4. Read the real boundary test's `/proc` observations. Explain why closing or signaling only the
   observed `uv` PID would be weaker than owning the detached process group.
5. Remove a prepared `.venv` in a disposable checkout and compare invoking `uv run --no-sync`
   directly with the supervisor preflight. Identify which layer prevents repository mutation.
6. Compare `apiKey`, `accesskey`, and `monkey` diagnostics. Explain why recognizing common
   concatenated credential forms requires a bounded allowlist rather than an arbitrary `key`
   substring match.

## Key takeaways

- The TUI owns child supervision; Python owns harness behavior after startup.
- Preflight establishes the supported executable and prepared environment before any child can
  mutate the harness repository.
- Pipes and workspace identity are explicit contracts, not ambient implementation details.
- OS spawn proves a process exists, not that a protocol runtime is ready.
- Every exit path must terminate or observe and reap the complete child process group predictably.

## Glossary

- **Child process:** The Python runtime started and owned by the Ink parent.
- **Process group:** The detached uv/Python process set that receives shutdown escalation together.
- **Reap:** Observe process termination and release its operating-system bookkeeping resources.
- **Supervisor:** Code that starts, observes, stops, and reports the child lifecycle.
- **Workspace identity:** The single resolved root passed explicitly to the runtime.

See the shared [project glossary](../glossary.md) for runtime, workspace, command, and event terms.

## Further reading

- [CAH-003 delivery contract](../../user-stories/cah-003-supervise-python-runtime.md)
- [ADR 0002: Ink and Python process boundary](../adr/0002-ink-python-process-boundary.md)
- [Process protocol responsibilities](../protocol.md#process-responsibilities)
- [Node child-process documentation](https://nodejs.org/api/child_process.html)
- [Python asyncio subprocesses](https://docs.python.org/3/library/asyncio-subprocess.html)
- [systemd documentation](https://systemd.io/)
- [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
