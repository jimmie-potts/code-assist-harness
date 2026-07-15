# CAH-003 lesson: Python runtime supervision

- **Unit:** CAH-003
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; neither a Python runtime entry point nor child supervisor exists
- **Story:** [CAH-003](../../user-stories/cah-003-supervise-python-runtime.md)
- **Related architecture:** [ADR 0002](../adr/0002-ink-python-process-boundary.md) and
  [protocol design](../protocol.md#process-responsibilities)

> This lesson describes planned CAH-003 behavior. It establishes process lifetime and stream
> ownership but deliberately stops before CAH-004's versioned message parsing.

## Quick summary

This unit makes the Ink parent and Python child behave as one local application. It teaches safe
argument-array spawning, explicit workspace selection, pipe ownership, failure classification,
bounded diagnostics, and cleanup without involving a model or mutating a workspace.

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

TUI exit -> terminate -> await/reap child -> restore terminal
```

The planned invariants are:

- the TUI starts Python through `uv` with an argument array and no shell interpolation;
- one runtime process serves exactly one explicit workspace;
- stdin and stdout remain protocol-only pipes, while diagnostics use stderr;
- startup and unexpected-exit errors are actionable, bounded, and secret-safe;
- cleanup is idempotent and leaves no child behind; and
- tests use controlled children and never invoke a model, network, or workspace mutation.

## Practical walkthrough

1. **Add the minimal Python entry point.** Accept the explicit workspace argument, validate basic
   startup configuration, and write human diagnostics only to stderr. Do not add an agent loop.
2. **Resolve workspace in the CLI.** Default to the launch directory; resolve `--workspace` before
   spawn and reject an unusable path with an actionable error.
3. **Build the launch request.** Express `uv` and every runtime option as separate arguments. Set
   stdin, stdout, and stderr handling explicitly rather than relying on defaults.
4. **Model supervisor states.** At minimum distinguish starting, running, failed-to-start,
   unexpectedly-exited, and stopping. These are child states, not yet full session states.
5. **Bound diagnostics.** Retain enough stderr context to help with a missing `uv`, bad workspace,
   or Python import failure without copying an unlimited stream or environment values.
6. **Implement one cleanup path.** On normal TUI exit, request or force child termination as the
   current contract allows, await process completion, detach listeners, and unmount Ink.
7. **Use controlled fixtures.** Test a child that stays alive, cannot start, exits unexpectedly,
   writes to each stream, and records termination. Avoid timing-sensitive sleeps where events or
   controllable barriers can prove ordering.
8. **Run one real boundary check.** Start the minimal Python entry point through the actual TUI
   supervisor and verify clean exit, stream separation, and no model/network behavior.

## Failure scenarios to study

### `uv` cannot be started

**Symptom:** the spawn operation emits an error and no child PID becomes usable. **Boundary:** TUI
supervisor. **Safe outcome:** show the missing executable and setup action, remain out of running
state, and restore the terminal. **Evidence:** a fake nonexistent executable test.

### Python exits after starting

**Symptom:** pipes close with a nonzero exit and bounded stderr. **Boundary:** supervisor lifecycle.
**Safe outcome:** move the UI to visible failure and never treat EOF as successful completion.
**Evidence:** a fixture child exits with a known code and diagnostic.

### The TUI exits but Python remains

**Symptom:** an orphan child retains pipes or workspace resources. **Boundary:** parent cleanup.
**Safe outcome:** terminate, wait for exit, and reap exactly once. **Evidence:** the fixture records a
termination signal and the test observes its final status.

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
| Lifetime | Bound to one terminal process | Durable jobs independent of client connection |
| Recovery | Show failure; user restarts | Retry policy, rescheduling, and persisted state |
| Cost | Direct, inspectable process API | Control plane, capacity, security, and on-call ownership |

### Trade-offs and graduation signals

A scheduler can improve recovery and utilization but adds distributed state, queues, identity,
network failure, and operational ownership. Graduate when concurrent demand, remote execution,
client-disconnect survival, or measured orphan/recovery incidents require those capabilities.

## Practical exercises

1. Draw the lifecycle for spawn error, successful spawn, unexpected exit, and parent-requested exit.
2. Design a fake child that proves stdin, stdout, and stderr are wired separately.
3. Compare `spawn(program, args)` with a shell string containing a path with spaces; explain which
   interpretation risks disappear with the argument array.

## Key takeaways

- The TUI owns child supervision; Python owns harness behavior after startup.
- Pipes and workspace identity are explicit contracts, not ambient implementation details.
- Every exit path must terminate or observe and reap the child predictably.

## Glossary

- **Child process:** The Python runtime started and owned by the Ink parent.
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
