# CAH-003 lesson: Python runtime supervision

- **Unit:** CAH-003
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; the physical Node-to-uv-to-Python boundary and cleanup path are tested
- **Story:** [CAH-003](../../user-stories/cah-003-supervise-python-runtime.md)
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md) and
  [protocol design](../protocol.md#process-responsibilities)

> This lesson follows the implemented CAH-003 path. It establishes process lifetime and stream
> ownership but deliberately stops before CAH-004's versioned readiness and message parsing.

## Quick summary

This unit makes the Ink parent and Python child behave as one local application. The implementation
uses a shell-free `uv` argument array, canonical single-workspace selection, typed supervisor
states, bounded redacted diagnostics, and detached process-group cleanup. Eight Python tests and 41
TUI tests verify the boundary without involving a model, network request, or workspace mutation.

## Learning objectives

After completing this unit, you should be able to:

- explain which process owns startup, runtime work, rendering, and shutdown;
- spawn Python through `uv` without a shell and pass a canonical workspace explicitly;
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
  | spawn: uv [runtime arguments], shell disabled
  v
Python runtime
  stdin  <- reserved protocol pipe
  stdout -> reserved protocol pipe
  stderr -> bounded diagnostics -> visible TUI failure/help

Ink exit and terminal restore -> finally close stdin -> signal if needed -> await/reap child
```

The implemented invariants are:

- the TUI starts Python through `uv` with an argument array and no shell interpolation;
- one runtime process serves exactly one explicit workspace;
- stdin and stdout remain protocol-only pipes, while diagnostics use stderr;
- startup and unexpected-exit errors are actionable, bounded, and secret-safe;
- cleanup is idempotent, waits for `close`, and leaves neither the `uv` wrapper nor Python child
  behind; and
- tests use controlled children and never invoke a model, network, or workspace mutation.

`tui/src/runtime-supervisor.ts` builds this exact logical request:

```text
uv run --project REPOSITORY_ROOT
  --no-cache --no-sync --offline --no-env-file --no-progress --no-python-downloads
  -- python -m code_assist_harness.runtime --workspace CANONICAL_WORKSPACE
```

Node passes each token separately with `shell: false`, uses the harness repository as `uv`'s
project and working directory, configures all three streams as pipes, and starts a detached process
group. The separately resolved workspace may contain spaces because it is one argument rather than
shell text. The no-sync and offline flags keep launch non-mutating and network-free, which means the
developer must run `uv sync --dev` before starting the TUI.

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
3. **Launch through a typed argument array.** `buildRuntimeLaunchRequest` fixes the program, every
   `uv` option, repository working directory, three pipes, `shell: false`, and `detached: true` in a
   value asserted exactly by `tui/test/runtime-supervisor.test.ts`.
4. **Keep transport bytes opaque.** `src/code_assist_harness/runtime.py` revalidates the canonical
   workspace, creates one `asyncio` loop, and uses an event-loop reader to discard stdin bytes until
   EOF. It writes no stdout. Node calls `resume()` on child stdout so the pipe cannot stall, but does
   not parse or render it before CAH-004.
5. **Project lifecycle without owning policy.** `tui/src/run-application.tsx` subscribes to
   supervisor transitions and rerenders `tui/src/app.tsx`. The component displays starting,
   running, startup-failure, unexpected-exit, stopping, and stopped projections; it never decides a
   transition.
6. **Sanitize diagnostics before UI state.** `tui/src/runtime-diagnostics.ts` retains only the last
   4,096 stderr bytes, redacts all sufficiently distinctive inherited environment values plus
   common and quoted credential assignments, strips terminal controls, normalizes whitespace, and
   limits the displayed summary to 1,200 characters. Stdout is never an input to that summary.
7. **Clean up from one `finally` path.** After Ink exits and restores the terminal, or if rendering
   fails before spawn, `runApplication` calls `stop()`. The supervisor closes stdin first, waits for
   normal EOF exit, then sends `SIGTERM` and `SIGKILL` to the detached process group only after
   successive grace periods. Parent `SIGHUP` and `SIGTERM` request an Ink unmount and enter the same
   path. Repeated stops share one promise, and completion waits for the child `close` event.
8. **Verify both seams.** Controlled `FakeChild` tests force spawn error, unexpected exit, secret
   output, and signal escalation deterministically. `tui/test/runtime-boundary.test.ts` performs the
   real Node-to-uv-to-Python launch, finds the Python runtime under `/proc`, stops the supervisor,
   proves both observed PIDs are gone, and confirms the temporary workspace stayed empty.

The completed validation evidence is eight Python tests, including seven runtime tests, and 41 TUI
tests across ten files. `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and
the TUI type-check, lint, and test scripts pass without a model or live network access.

## Failure scenarios to study

### `uv` cannot be started

**Symptom:** the spawn operation emits an error and no child PID becomes usable. **Boundary:** TUI
supervisor. **Safe outcome:** show the missing executable and setup action, remain out of running
state, and preserve cleanup idempotence. **Evidence:** `tui/test/runtime-supervisor.test.ts` emits an
`ENOENT` error and asserts the visible guidance names `uv` and `uv sync --dev`; a synchronous spawn
failure also proves `shell` remained disabled.

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
stdout that resembles a future protocol line plus stderr containing a configured secret. The
failure includes safe stderr context, redacts the secret, excludes stdout, and classifies exit zero
as unexpected. `tui/test/app.test.tsx` verifies both startup and runtime failures are visible.

### The TUI exits but Python remains

**Symptom:** an orphan child retains pipes or workspace resources. **Boundary:** parent cleanup.
**Safe outcome:** close stdin, signal the detached process group if needed, wait for `close`, and
make repeated cleanup harmless. **Evidence:** the controlled test records `SIGTERM` then `SIGKILL`
and proves repeated `stop()` calls share a promise. A regression also sets the uv leader's exit code
before inherited descendant pipes close and proves the process group still receives `SIGTERM`; the
`close` event, not the leader's exit-code field, is the cleanup guard. The real boundary test
observes that `uv` may be a wrapper with a separate Python descendant, then proves neither PID
remains under `/proc` after cleanup.

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
network failure, and operational ownership. CAH-003 also exposed three local trade-offs: `uv` can
remain a wrapper around a separate Python process, so signaling only its PID is insufficient;
`--no-sync` makes launch deterministic but requires explicit setup; and the spawn event is useful
for lifecycle state but too weak for protocol readiness. A detached process group, documented
`uv sync --dev` prerequisite, and deferred CAH-004 handshake address those constraints without
introducing a daemon or scheduler. Graduate when concurrent demand, remote execution,
client-disconnect survival, or measured orphan/recovery incidents require those capabilities.

## Practical exercises

1. Trace `PythonRuntimeSupervisor.start()` for spawn error, spawn followed by close, and requested
   stop. Identify why exit code zero has different meaning before and after `stop()`.
2. Run the focused Python runtime test and identify the assertions proving that stdin may contain
   unimplemented bytes while stdout and stderr remain empty on clean EOF.
3. Compare the exact launch request with a shell string containing a workspace path with spaces;
   explain which interpretation risks disappear with the argument array.
4. Read the real boundary test's `/proc` observations. Explain why closing or signaling only the
   observed `uv` PID would be weaker than owning the detached process group.

## Key takeaways

- The TUI owns child supervision; Python owns harness behavior after startup.
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
