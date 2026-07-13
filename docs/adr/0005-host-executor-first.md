# ADR 0005: Use a restricted host executor before container isolation

- **Status:** Accepted
- **Date:** 2026-07-13
- **Decision scope:** Subprocess execution and future isolation

## Context

Approved tests and linters must run against the active WSL workspace. A container would provide a
stronger isolation boundary, but introducing image management, mounts, user mapping, cache
behavior, and container lifecycle before the core loop and approval flow are understood would
expand the first implementation substantially.

Running arbitrary host shell text is not acceptable. The first executor still needs enforceable
policy, bounded resources, cancellation, environment filtering, and a replaceable boundary so the
learning-focused implementation does not permanently couple the loop to host process APIs.

## Decision

The MVP will implement a restricted host subprocess executor behind a harness-defined executor
interface. A future container-backed executor must be able to implement the same domain contract
without changing the agent loop, tool registry, approval model, or event model.

The host executor accepts a normalized executable-and-argument array only after tool validation,
policy approval, and individual user approval. It never accepts a shell command string and never
uses shell interpolation or `shell=True`.

Every invocation defines and records:

- the exact executable and argument array;
- a resolved working directory within the workspace;
- a minimal, filtered environment that excludes credentials and unrelated secrets;
- a timeout and bounded stdout and stderr capture;
- cancellation behavior;
- a capability and risk classification; and
- a structured success, failure, timeout, output-limit, or cancellation result.

The executor must terminate the launched process tree when the session is cancelled or its timeout
is reached. Captured output is bounded before it enters session events, provider context, or
transcripts. Truncation is explicit rather than silent.

Only commands allowed by the effective command policy may reach the executor. Every allowed
command still requires its own approval. Git-state-changing commands, network behavior,
privileged execution, and commands outside the configured policy are unavailable in the MVP.

Subprocess supervision participates in the runtime's single `asyncio` event loop. Blocking file
or process support work moves to a bounded worker thread only when the asynchronous subprocess APIs
cannot provide the needed behavior.

## Executor contract

The provider and model do not interact with the executor directly. A subprocess tool validates its
input, the policy engine classifies the action, the approval service binds a decision to that exact
action, and only then does the executor receive an execution request. The result is converted to a
provider-neutral tool result and complete audit events.

The interface must avoid host-specific return types. It should describe commands, exit status,
bounded stream output, elapsed time, termination reason, and cancellation using harness domain
types. Container-specific concerns remain inside a future adapter.

## Consequences

### Benefits

- The MVP can run the repository's normal WSL validation tools without container setup.
- Argument arrays, an allowlist, per-command approval, environment filtering, and resource bounds
  provide layered controls.
- The executor seam makes stronger isolation an implementation replacement rather than an agent
  loop redesign.
- Host behavior is observable and testable with short-lived fixture commands before model tools
  are introduced.

### Costs and risks

- A host process does not provide the isolation of a well-configured container or virtual machine.
- Process-tree termination and platform-specific executable resolution require careful WSL tests.
- An incomplete environment filter or command policy could expose secrets or capabilities.
- Very noisy or adversarial processes require robust timeout and output-bound enforcement.

These risks constrain the initial allowlist to documented development checks, require explicit
approval for every invocation, and make adversarial executor tests part of the reliability work.
The host executor must not be presented as a security sandbox.

## Alternatives considered

### Start with a container-backed executor

Deferred because container lifecycle and filesystem mapping would distract from the first
agent-loop, protocol, and approval lessons. The interface is intentionally designed to admit this
implementation later.

### Execute arbitrary shell strings on the host

Rejected because interpolation, quoting, redirection, pipelines, and shell startup behavior make
validation and action identity substantially less reliable.

### Do not support subprocesses in the MVP

Rejected because running approved tests and linters is part of the confirmed coding workflow and
is necessary to report grounded validation results.

### Treat containers as proof that commands are safe

Rejected as a future design principle. Container execution would strengthen isolation but would
not replace schema validation, policy, approval, limits, auditing, or secret handling.

## Implementation status

This is an accepted target decision. At acceptance time, the repository had no executor or
subprocess tool. The restricted host implementation arrives with controlled command execution;
container execution remains a post-MVP story behind the same interface.
