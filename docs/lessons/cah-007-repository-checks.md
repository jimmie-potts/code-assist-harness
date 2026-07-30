# CAH-007 lesson: Repository-wide checks

- **Unit:** CAH-007
- **Milestone:** M0 - Walking skeleton
- **Lesson status:** Verified against implementation
- **Implementation status:** Done; verified through the offline repository script, policy tests, and
  lockfile-driven Linux CI workflow
- **Story:** [CAH-007](../../user-stories/cah-007-establish-repository-checks.md)
- **Visual companion:** [Repository-wide checks](assets/cah-007-repository-checks.pptx)
- **Related architecture:** [Architecture](../architecture.md), [evaluation](../evaluation.md), and
  [ADR 0002](../adr/0002-ink-python-process-boundary.md)

> This lesson describes the implemented CAH-007 validation seam. `./scripts/check` is the canonical
> non-live gate, and the `Repository checks` Linux workflow installs from both lockfiles before
> invoking that same script.

## Quick summary

CAH-007 makes one POSIX shell script the executable definition of all required M0 non-live checks.
Focused Python and TypeScript commands remain available, but the unified path prevents one ecosystem,
the teaching fixtures, documentation policy, or the real Node-Python boundary from being forgotten.

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
  -> resolve repository root; unset provider credentials and uv selectors; force offline modes
  -> preload guards into top-level Python and Node checks
  -> uv sync --check --locked --offline
  -> uv run --offline --frozen --no-sync ruff check .
  -> uv run --offline --frozen --no-sync ruff format --check .
  -> Python tests
  -> Protocol fixtures: Python
  -> Repository policy: check script, Markdown links/anchors, TUI lock, and network
  -> Node runtime compatibility: reuse the TUI's supported-range assertion
  -> npm --offline --prefix tui run typecheck
  -> npm --offline --prefix tui run lint
  -> TUI tests
  -> Protocol fixtures: TypeScript
  -> Node-Python integration

Linux CI -> locked installs -> invoke the same ./scripts/check
```

| Concern | Implemented owner | Invariant |
| --- | --- | --- |
| Required check list | [`scripts/check`](../../scripts/check) | One reviewed, fail-fast source defines the gate from any working directory. |
| Python-specific behavior | Python tools/config | Focused commands remain independently runnable. |
| TUI-specific behavior | Shared Node-range assertion and npm scripts | Unsupported runtimes fail before TUI npm checks; type, lint, and test failures retain attribution. |
| Cross-language behavior | Shared fixtures and integration tests | Both implementations and the real process seam run. |
| Documentation and offline policy | [`test_repository_policy.py`](../../tests/test_repository_policy.py) | Local links/anchors resolve, the complete TUI lock graph is valid, top-level process guards reject common network APIs, and current production source contains no denylisted network capability. |
| Script contract | [`test_check_script.py`](../../tests/test_check_script.py) | Exact order, environment-check and no-sync flags, uv-selector and credential removal, Node compatibility, network-guard preloads, labels, and fail-fast propagation remain tested. |
| CI environment | [Linux workflow](../../.github/workflows/check.yml) | Pinned Ubuntu, Python, Node, uv, action SHAs, and lockfile installs precede the canonical gate. |

The script uses `set -eu`, changes to its own repository root, suppresses Python bytecode writes,
labels each layer, and executes checks sequentially. `uv sync --check --locked --offline` rejects a
missing or drifted prepared environment without changing it, and every later `uv run` adds
`--no-sync`. Before those commands, the script clears `UV_PROJECT`, `UV_PROJECT_ENVIRONMENT`,
`UV_PYTHON`, `UV_WORKING_DIR`, `UV_NO_PROJECT`, and `UV_ISOLATED`; otherwise an inherited setting
could redirect or disable project-based validation or replace `.venv` with an ephemeral environment.
Before the first labeled TUI npm stage, a tiny TypeScript entry point reuses
`assertSupportedNodeVersion` so the local gate enforces the same `>=22.13.0 <23` contract as the TUI.
The first nonzero command stops the run and remains the process exit status. CI adds checkout, pinned
runtime setup, npm caching, `uv sync --locked`, and `npm ci`, but it does not copy the gate's command
list into YAML. The TUI currently configures independent type-check, lint, and test scripts; it has no
separate formatter or format-check stage.

Default validation excludes live-provider smoke tests. The script removes common OpenAI, Azure
OpenAI, Anthropic, and Google credentials, sets uv and npm offline modes, and uses the prepared local
environments. Top-level Python checks load `tests/network_guard/sitecustomize.py`; Node checks preload
`scripts/deny-network.mjs`. Focused probes prove that both reject TCP, UDP, fetch, and external DNS
attempts through the guarded APIs before they reach the operating system. The Node guard returns a
deterministic loopback result for `localhost` and IP-literal lookups because Vite requires that local
configuration query; it does not call the system resolver for that exception. The real integration
supervisor intentionally strips ambient Python selectors, including `PYTHONPATH`, to preserve its exact
prepared-interpreter invariant. Its current Python source is therefore covered by the static policy
that rejects known Python/TypeScript network imports and calls in M0 production paths. These controls
are deliberately narrow: they are useful defense in depth, not an operating-system sandbox for
separately launched native executables.

The Python lock and prepared environment are checked directly by uv. Repository policy compares the
TUI's root package metadata and runs `npm ls --package-lock-only --all` against temporary manifest
copies, proving that the complete dependency graph is internally valid without consulting or
changing `node_modules`. A synthetic missing transitive entry proves the check can fail. CI still
performs the authoritative clean `npm ci` install. An attempted repository-local `npm ci --dry-run`
check was rejected because it removed the prepared `node_modules` tree even in dry-run mode; a
validation command must not mutate the environment it is about to test.

## Practical walkthrough

1. Prepare dependencies once with `uv sync --dev` and `npm --prefix tui ci`.
2. Run `./scripts/check` from the repository root or invoke its absolute path from another directory.
3. Observe the Python lock/environment, lint/docstring, format, and test headings in order.
4. Observe the separate Python unit, Python protocol-fixture, and repository-policy headings. The
   policy stage owns script behavior, Markdown links/anchors, the complete package-lock graph, and
   current production-source network checks.
5. Observe Node runtime compatibility before the TUI type-check, lint, unit-test,
   TypeScript-fixture, and Node-Python-integration headings. The final stage launches the genuine
   `uv`/Python child.
6. Run focused pytest, Ruff, or npm scripts while iterating, then return to the canonical gate before
   declaring the unit complete.
7. Inspect `.github/workflows/check.yml`: installation belongs in CI setup, and the final step calls
   `./scripts/check` without restating its internal checks.
8. Study `test_check_script.py`, which substitutes bounded `uv`, `node`, and `npm` stubs to prove
   exact order, offline settings, uv-selector and credential removal, runtime compatibility,
   network-guard preloads, labels, success, and first-failure propagation.
9. Study the synthetic missing-transitive, broken-link, and Python/TypeScript network-policy cases.
   Each proves its detector can fail, rather than merely observing that today's source happens to
   pass.
10. Render and inspect the linked visual lesson and run its overflow test before accepting it as unit
    evidence.

## Failure scenarios to study

| Scenario | Observable symptom | Responsible boundary | Safe evidence |
| --- | --- | --- | --- |
| TUI tests are omitted | Python is green while UI regresses | Script contract | Stub test compares the exact command sequence, including `npm test`. |
| CI duplicates commands | Local passes, CI uses stale flags | Workflow design | Workflow's final step calls `./scripts/check`. |
| Pipeline masks an exit code | A later command makes the run green | `set -eu` and script contract | Injected stub failure returns its nonzero status and later commands never run. |
| Ambient uv selectors redirect the gate | Python checks inspect another project, environment, or interpreter | Script environment boundary | Poisoned selectors are absent from every stubbed stage. |
| Lockfile or prepared Python environment drifts | Local and CI checks could exercise different dependencies | Install and policy layers | uv performs a non-mutating environment check; npm validates the complete lock graph; CI uses `npm ci`. |
| Unsupported Node runs local TUI checks | Local green uses a runtime that CI and users reject | Node compatibility stage | The shared range assertion runs before npm; its injected failure prevents TUI type checking. |
| Network capability enters M0 source or top-level tests | Default checks could reach an external service | Process guards and repository policy | Python/Node TCP, UDP, fetch, and external-DNS probes fail; synthetic sources prove denylisted APIs are rejected. |
| A local Markdown link or anchor breaks | Learning material becomes unnavigable | Repository policy | Synthetic missing target/heading test proves link checking fails. |
| Integration is mocked in one language | Contract seam is untested | TUI test tier | Final stage launches the genuine uv/Python child. |
| Visual deck clips or misstates evidence | The learning companion becomes misleading | Presentation QA | Every slide is rendered, inspected, and overflow-tested. |

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
  matrices, protected check results, logs, and reusable workflows, while requiring runner security,
  workflow maintenance, cache management, and control of usage and retention costs.
- [pre-commit](https://pre-commit.com/) illustrates fast developer-side hooks that run selected
  checks before a commit, complementing rather than replacing CI; teams must maintain hook versions,
  local environments, installation guidance, and a policy for bypasses.
- [Renovate](https://docs.renovatebot.com/) illustrates automated dependency and lockfile update
  proposals with configurable policy, at the cost of bot credentials, policy tuning, pull-request
  noise, and sustained review capacity.
- [CodeQL](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)
  illustrates semantic security analysis and pull-request findings while adding database builds,
  analysis time, query maintenance, and specialist triage for findings and false positives.
- [OpenSSF Scorecard](https://github.com/ossf/scorecard) illustrates automated assessment of
  repository supply-chain practices, but its checks require permissions, finding review, exception
  handling, and policy ownership as repository practices evolve.

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
2. Change the script-test stub failure from the Python format command to a TUI command and predict
   the captured command list.
3. Add a synthetic denylisted import in each language and inspect the path/line diagnostic.
4. Compare “CI lists commands” with “CI calls the repository script” and identify the drift path.
5. Design a test fixture that fails immediately on an unexpected outbound network attempt.

## Key takeaways

- One repository command is the authoritative non-live gate; focused commands serve iteration.
- CI must reuse, not reimplement, the local validation contract.
- Cross-language fixtures and a real process test are first-class checks.
- Offline flags, removed credentials, process guards, and a source denylist are complementary
  controls, not an operating-system sandbox.
- A useful check does not mutate the prepared environment or leave bytecode sidecars in source paths.
- More CI infrastructure is warranted by measured scale, governance, or duration—not by default.

## Glossary

- **Canonical check:** the complete repository validation entry point.
- **Constituent check:** one tool invocation within the complete gate.
- **Contract test:** a test proving two boundaries interpret the same external shape.
- **Hermetic behavior:** execution isolated from undeclared credentials, network, and mutable services.
- **Reproducible install:** dependency installation derived from committed lockfiles.
- **Required check:** a gate that must pass before a protected integration action.
- **Source network policy:** a static denylist that rejects known network capabilities in selected
  production paths without claiming runtime isolation.

See the shared [project glossary](../glossary.md) for validation command, provider, protocol, and TUI.

## Further reading

- [CAH-007 user story](../../user-stories/cah-007-establish-repository-checks.md)
- [Evaluation tiers](../evaluation.md)
- [Architecture testing guidance](../architecture.md)
- [Repository guidelines](../../AGENTS.md)
- [Canonical check script](../../scripts/check)
- [Linux check workflow](../../.github/workflows/check.yml)
- [CAH-007 visual lesson](assets/cah-007-repository-checks.pptx)
- [GitHub Actions](https://docs.github.com/en/actions)
- [pre-commit](https://pre-commit.com/)
- [Renovate](https://docs.renovatebot.com/)
- [CodeQL](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning)
- [OpenSSF Scorecard](https://github.com/ossf/scorecard)
