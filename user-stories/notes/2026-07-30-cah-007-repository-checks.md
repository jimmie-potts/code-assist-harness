# CAH-007 repository checks implementation note

- **Date:** 2026-07-30
- **Story:** [CAH-007](../cah-007-establish-repository-checks.md)
- **Lesson:** [Repository-wide checks](../../docs/lessons/cah-007-repository-checks.md)
- **Visual companion:** [Repository-wide checks](../../docs/lessons/assets/cah-007-repository-checks.pptx)

## Delivered gate

`scripts/check` is now the canonical developer and CI entry point for every required M0 non-live
check. It is an executable POSIX shell script with `set -eu`, resolves its own repository root, and
therefore behaves the same when invoked from the repository or through an absolute path from another
working directory.

The script labels and runs these 12 stages in order:

1. Python lockfile and environment.
2. Python lint and docstrings.
3. Python format.
4. Python tests.
5. Protocol fixtures: Python.
6. Node runtime compatibility.
7. Repository policy: check script, documentation links, locks, and network.
8. TUI typecheck.
9. TUI lint.
10. TUI tests.
11. Protocol fixtures: TypeScript.
12. Node-Python integration.

Splitting fixtures, policy, and the real process boundary into their own stages keeps a failure
attributable without creating separate sources of truth. The focused pytest, Ruff, and npm commands
remain available for iteration; a completed unit returns to `./scripts/check`.

## Offline and credential boundary

Dependency preparation remains separate: developers use `uv sync --dev` and `npm --prefix tui ci`,
while CI uses `uv sync --locked` and `npm ci`. The gate consumes those installed environments. It
sets uv and npm offline modes, verifies the prepared environment with
`uv sync --check --locked --offline`, and uses `uv run --offline --frozen --no-sync`. It also sets
`TMPDIR=/tmp`, suppresses Python bytecode writes, and removes common OpenAI, Azure OpenAI, Anthropic,
and Google provider credentials before any constituent command. It removes `UV_PROJECT`,
`UV_PROJECT_ENVIRONMENT`, `UV_PYTHON`, `UV_WORKING_DIR`, `UV_NO_PROJECT`, and `UV_ISOLATED` so
ambient project, environment, interpreter, discovery, or ephemeral-environment selectors cannot
redirect local validation.
It also points `PYTHONPATH` at a `sitecustomize.py` socket guard and preloads the Node network guard
through `NODE_OPTIONS`, so the top-level check processes reject common network client attempts. The
runtime supervisor intentionally removes `PYTHONPATH` from its real Python child to preserve the
prepared-interpreter contract; the current child is instead covered by the production-source policy.

`tests/test_repository_policy.py` adds defense in depth:

- Git-tracked and new nonignored Markdown file targets and heading anchors must resolve, while local
  environments, caches, and other ignored artifacts remain outside the scan;
- the package-lock v3 root package must match `tui/package.json` name, version, direct dependency,
  development dependency, and engine metadata;
- `npm ls --package-lock-only --all` must accept the complete graph from temporary manifest copies,
  while a synthetic missing transitive entry must be rejected without creating `node_modules`; and
- current M0 production files under `src/code_assist_harness` and `tui/src` may not import or call a
  reviewed denylist of Python and TypeScript network capabilities, including bare and static
  `globalThis`/`window` fetch forms; and
- focused subprocess probes prove the Python and Node guards reject TCP, UDP, fetch, and
  external-DNS attempts with the expected diagnostic; Node returns a deterministic loopback result
  for local/IP-literal lookups required by Vite without calling the system resolver.

Synthetic missing-link, ignored-directory, Python-network, and TypeScript-network cases prove the
detectors' positive and negative boundaries. External URL availability is intentionally not checked.
The process guards and source denylist do not constrain separately launched native clients and are
not described as an operating-system sandbox.

An attempted repository-local `npm ci --ignore-scripts --dry-run --offline` lock stage was discarded.
npm removed the prepared `node_modules` tree before simulating installation, so it violated the
non-mutating gate contract. The temporary-copy `npm ls` graph check provides the local proof without
that side effect, and CI's actual `npm ci` remains the clean lockfile-install proof.

## Script and failure evidence

`tests/test_check_script.py` uses temporary `uv`, `node`, and `npm` stubs to verify exact command
order, the non-mutating uv environment/no-sync flags, removal of six inherited uv selectors,
offline settings, process-guard preloads, removal of an inherited `OPENAI_API_KEY`, layer labels, the
success footer, and fail-fast propagation. Eight tests cover the script contract, including exit-code
23 injections for Python, Python fixtures, Node compatibility, repository policy, TUI tests, and
Node-Python integration.

The Node stage runs before every npm-backed check from the `tui/` directory and reuses
`assertSupportedNodeVersion(process.versions.node)`. That includes repository policy's complete
lock-graph validation as well as the labeled TUI stages. This keeps the canonical local gate on the same
`>=22.13.0 <23` contract as the interactive bootstrap without duplicating semver logic or requiring
the exact pinned patch release.

The story's separate transient probes also ran through the genuine gate and were restored after each
result:

| Probe | Observed stopping layer | Evidence before the intentional failure |
| --- | --- | --- |
| Inverted Python package assertion | `Python tests` | 104 passed, 1 intentionally failed; no later label ran. |
| Mismatched fixture manifest type | `Protocol fixtures: Python` | 105 core tests passed, then 29 fixture tests passed and 1 intentionally failed. |
| Temporary TUI assertion | `TUI tests` | 126 passed, 1 intentionally failed; fixture and integration labels did not run. |
| Inverted real-boundary assertion | `Node-Python integration` | Earlier stages passed; 3 boundary tests passed and 1 intentionally failed. |

All temporary changes were removed, and each probe target was restored to its pre-probe contents
before the final clean gate.

## Linux CI

`.github/workflows/check.yml` runs for pull requests and pushes to `main` with read-only repository
contents permission and a 15-minute job timeout. It pins Ubuntu 24.04, reads Python 3.12 and Node
22.22.1 from their repository version files, pins uv 0.11.28, and pins every action to a full commit
SHA. After locked installs and npm caching, its only validation step is `./scripts/check`.

This records the workflow contract present in the branch. Remote success remains evidence from the
pull-request run and is not inferred from local execution.

## Final validation

The final clean `./scripts/check` completed all 12 stages and printed
`All repository checks passed.` Evidence was:

- Python lockfile/environment check, Ruff lint/docstrings, and Ruff formatting passed.
- Python core tests: 105 passed.
- Python protocol fixtures: 30 passed.
- Check-script and repository-policy tests: 24 passed.
- Python and Node TCP, UDP, fetch, and external-DNS probes were rejected by the preloaded guards.
- TUI type checking and ESLint passed.
- TUI core tests: 126 passed.
- TypeScript protocol fixtures: 29 passed.
- Real Node-Python boundary tests: 4 passed.
- Total Python evidence: 159 tests; total TUI evidence: 159 tests.
- `git diff --check` passed.

The 10-slide visual companion uses a playful quality-machine/conductor motif, a rail-line stage map,
and a compact failure lab to explain the canonical gate, offline boundary, process seam, defense in
depth, and local/CI parity. Every exported slide was inspected full-size, and `slides_test.py`
reported no overflow.

## Next unit

CAH-010 is now dependency-ready. It will replace the current M0-specific projection boundary with a
documented, shared lifecycle transition model and equivalent pure Python and TypeScript reducers.
