# CAH-007 lesson: Repository-wide checks

- **Unit:** CAH-007
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Planned
- **Implementation status:** Planned; no unified cross-language check or Linux CI workflow exists yet
- **Story:** [CAH-007](../../user-stories/cah-007-establish-repository-checks.md)
- **Related architecture:** [Architecture](../architecture.md), [evaluation](../evaluation.md), and
  [ADR 0002](../adr/0002-ink-python-process-boundary.md)

> This lesson defines the planned validation seam. Current Python commands remain useful, but they
> are not evidence that the future TUI, protocol fixtures, or integration path have been checked.

## Quick summary

CAH-007 will make one repository script the executable definition of all non-live checks and make
Linux CI call that same script. Focused Python and TypeScript commands remain available, but the
unified path prevents one ecosystem or the real Node-Python boundary from being forgotten.

## Learning objectives

After completing this unit, you should be able to:

- distinguish a canonical validation entry point from its constituent tools;
- explain why CI should invoke the same script developers run locally;
- combine lockfile, static, unit, contract, render, and integration evidence;
- keep test execution model-free and network-free after dependencies are installed; and
- recognize when a small sequential script should become a larger CI pipeline.

## Why this unit matters

The walking skeleton spans Python, Node, protocol fixtures, terminal projection, and a real child
process. Separate commands can all pass while the boundary between them fails. One explicit check
turns the definition of done into repeatable evidence and keeps CI from becoming a second,
silently divergent implementation of repository policy.

## Key concepts

**Canonical check:** the single command that answers whether the repository's required non-live
quality gates pass for the current change.

**Focused check:** a fast command for one layer, such as pytest, Ruff, TypeScript type checking, or a
TUI test. Focused checks optimize iteration but do not replace the canonical check before completion.

**Contract test:** both languages parse the same golden protocol fixtures and reject agreed invalid
fixtures. It proves cross-language interpretation rather than only one implementation.

**Hermetic test behavior:** after a prepared lockfile-based install, the default suite needs no API
key and makes no live provider or other network request. Dependency installation itself may require
an available package source and is a separate supply-chain step.

**Fail-fast with clear attribution:** the unified script returns nonzero when a constituent fails and
its output identifies Python, TUI, protocol, documentation, or integration as the failing layer.

## Architecture and design

```text
scripts/check
  -> Python lint + format + docstrings + pytest
  -> TUI typecheck + lint + optional format check + tests
  -> shared protocol fixture validation in both languages
  -> real model-free Node-Python integration tests
  -> lightweight documentation checks

Linux CI -> install from locks -> invoke the same scripts/check
```

| Concern | Planned owner | Invariant |
| --- | --- | --- |
| Required check list | Repository script | One reviewed source defines the gate. |
| Python-specific behavior | Python tools/config | Focused commands remain independently runnable. |
| TUI-specific behavior | npm scripts | Type, lint, and test failures retain attribution. |
| Cross-language behavior | Shared fixtures/integration | Both implementations and the real process seam run. |
| CI environment | Linux workflow | Supported pinned runtimes and lockfiles are used. |

Keep orchestration boring: an explicit sequential script is easier to reproduce than an early
monorepo build graph. It must preserve each command's exit status and avoid masking earlier failures.
CI may add setup and caching, but it must not duplicate or replace the actual check list.

Default validation excludes live-provider smoke tests. It should also run without
`OPENAI_API_KEY`. Network prevention belongs in tests or a controlled test environment; merely
unsetting one credential does not prove that arbitrary code cannot open a connection.

## Practical walkthrough

1. Inventory every check required by the definition of done and map it to an owning tool.
2. Add or confirm focused npm scripts for type checking, linting, formatting if selected, and tests.
3. Ensure Python keeps independent pytest, Ruff lint, Ruff format, and docstring enforcement commands.
4. Add both Python and TypeScript protocol fixture suites to the required path.
5. Add the real deterministic Node-parent/Python-child integration scenario.
6. Add a small repository check script that runs the complete list and preserves failures.
7. Document the unified and focused commands, prerequisites, and common failure attribution.
8. Add Linux CI with supported Python and Node versions and lockfile-based installs.
9. Have CI invoke the repository script rather than repeat its internal commands in YAML.
10. Prove propagation by deliberately failing one assertion in each layer, then discard those changes.

Run the script from a clean prepared environment, without an API key. Inspect logs for the first
failing layer and verify CI and local execution use equivalent commands. If documentation checking is
deferred, record exactly which check and why rather than implying links are already automated.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe evidence |
| --- | --- | --- | --- |
| TUI tests omitted | Python is green while UI regresses | Check manifest | Intentional UI failure breaks unified check. |
| CI duplicates commands | Local passes, CI uses stale flags | Workflow design | CI calls one repository script. |
| Pipeline masks an exit code | Later command makes build green | Shell/script control flow | Each injected failure returns nonzero. |
| Lockfile ignored | CI resolves different dependencies | Install phase | `uv.lock` and package lock drive installs. |
| Test contacts network | Offline/default run hangs or leaks | Test isolation | Network is denied or unexpected calls fail. |
| Integration is mocked in one language | Contract seam is untested | Integration tier | Real Node and Python processes are launched. |

## Production expansion

### Example enterprise scenario

A company maintains hundreds of repositories, protected branches, multiple runtime versions, and
regulated release evidence. It needs centrally governed required checks, dependency updates,
security analysis, artifact attestations, flaky-test ownership, runner isolation, and dashboards for
lead time and failure rate. A single local script remains useful but becomes one component of a
managed software-delivery platform.

### Typical production capabilities and tools

The following illustrate capabilities rather than mandatory choices or endorsements:

- [GitHub Actions](https://docs.github.com/en/actions) illustrates hosted workflow execution,
  matrices, protected check results, logs, and reusable workflows.
- [pre-commit](https://pre-commit.com/) illustrates fast developer-side hooks that run selected
  checks before a commit, complementing rather than replacing CI.
- [Renovate](https://docs.renovatebot.com/) illustrates automated dependency and lockfile update
  proposals with configurable policy.
- [CodeQL](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)
  illustrates semantic security analysis and pull-request findings.
- [OpenSSF Scorecard](https://github.com/ossf/scorecard) illustrates automated assessment of
  repository supply-chain practices.

### Local design versus production design

| Dimension | This repository | Production expansion |
| --- | --- | --- |
| Scope | Python, TUI, protocol, one integration | Many repositories, languages, platforms, artifacts |
| Orchestration | Sequential repository script | Managed DAGs, matrices, reusable organization workflows |
| Runtime | Supported Linux versions | Isolated autoscaled runners and compatibility matrices |
| Security | No-live tests, locks, focused linting | SAST, attestations, policy, secret and dependency scanning |
| Evidence | Console result and CI check | Retained audit records, dashboards, release provenance |
| Ownership | Repository contributors | Platform team plus service and control owners |

### Trade-offs and graduation signals

A small script has low cognitive cost and excellent local reproducibility. Larger CI systems add
parallelism, policy, retention, and centralized visibility, but also runner security, queueing,
caching, governance, and platform ownership. Graduate when check duration blocks iteration,
compatibility matrices grow, regulatory evidence is required, or repeated repository drift justifies
central management.

## Practical exercises

1. List every required M0 check and label its ecosystem and failure owner.
2. Make a temporary failing Python assertion and verify the unified script returns nonzero.
3. Repeat with a TypeScript, protocol fixture, and process-integration failure.
4. Compare “CI lists commands” with “CI calls the repository script” and identify the drift path.
5. Design a test fixture that fails immediately on an unexpected outbound network attempt.

## Key takeaways

- One repository command is the authoritative non-live gate; focused commands serve iteration.
- CI must reuse, not reimplement, the local validation contract.
- Cross-language fixtures and a real process test are first-class checks.
- More CI infrastructure is warranted by measured scale, governance, or duration—not by default.

## Glossary

- **Canonical check:** the complete repository validation entry point.
- **Constituent check:** one tool invocation within the complete gate.
- **Contract test:** a test proving two boundaries interpret the same external shape.
- **Hermetic behavior:** execution isolated from undeclared credentials, network, and mutable services.
- **Reproducible install:** dependency installation derived from committed lockfiles.
- **Required check:** a gate that must pass before a protected integration action.

See the shared [project glossary](../glossary.md) for validation command, provider, protocol, and TUI.

## Further reading

- [CAH-007 user story](../../user-stories/cah-007-establish-repository-checks.md)
- [Evaluation tiers](../evaluation.md)
- [Architecture testing guidance](../architecture.md)
- [Repository guidelines](../../AGENTS.md)
