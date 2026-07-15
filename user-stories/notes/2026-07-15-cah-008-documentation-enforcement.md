# 2026-07-15 CAH-008 documentation enforcement

## Purpose

Complete CAH-008 by turning the accepted documentation standard into an enforced Python lint policy
and by recording the evidence that the policy distinguishes production contracts from test and
trivial private code.

## Decisions

- Enable Ruff's complete `D` family alongside the existing `E`, `F`, `I`, and `UP` selections, then
  use Ruff's `google` pydocstyle convention to choose the compatible docstring rules.
- Exempt only `tests/**/*.py` from `D` rules. The exemption is path- and language-specific rather
  than a package-wide documentation escape hatch.
- Do not add explicit ignores for private helpers, constructors, special methods, or parameters.
  Ruff already excludes underscore-prefixed private definitions from
  missing-public-docstring rules, while the Google convention defines the supported formatting and
  section rules.
- Keep semantic review as part of the standard. Lint cannot determine whether private code encodes
  a security boundary, protocol invariant, concurrency rule, or other decision that deserves
  rationale.
- Add no runtime dependencies or behavior. Ruff already provides the required enforcement.

## Work completed

`pyproject.toml` now enables Google-style public-docstring checks and the narrow test exemption.
`AGENTS.md` now describes that enforcement as active and makes the state-machine,
protocol-documentation, and non-obvious-test expectations explicit. The CAH-008 story, lesson, and
indexes now report the completed state, while dated baseline notes retain their historical wording.

The CAH-008 lesson was updated with the concrete configuration, observed failure boundary, and
exemption trade-off. The complete lesson library was audited so every representative production
tool now states both its capability and its operational burden, and every named tool's official
reference appears in that lesson's further reading. Planned lessons still distinguish accepted
design from future TUI, protocol, tool, and agent behavior.

## Enforcement probes

- A temporary `undocumented_public_api` function in the production package caused Ruff to report
  `D103 Missing docstring in public function`.
- Removing that probe restored a clean lint result.
- The existing undocumented `test_package_imports` function remained allowed because its file is
  covered by the test-only exemption.
- A temporary underscore-prefixed helper in the production package also passed, confirming that
  trivial private helpers do not need a mechanical docstring.
- Both temporary production probes were removed; neither is part of the completed tree.

## Validation evidence

- `uv run ruff check .` passed with the new Google-style `D` rules active.
- `uv run ruff format --check .` reported both Python files already formatted.
- `uv run pytest` used the configured `tests` path and passed the package test: `1 passed`. The Codex
  shell's transient temporary directory disrupted an initial capture teardown, so the passing run
  used a stable `/tmp/cah-pytest` directory. `uv run pytest -s` independently passed the same test
  selection without capture.
- `uv lock --check` resolved the unchanged eight-package graph, confirming no lockfile update is
  required.
- `uv build` produced the source distribution and wheel successfully.
- `git diff --check` passed.
- A repository-local audit validated 14 reciprocal story/lesson pairs, their status mapping, every
  required lesson heading, three to five production references per lesson, complete production-tool
  reference coverage in further reading, and 209 local links.
- Manual review confirmed that every representative production-tool entry describes both its
  capability and its specific operational burden.
- A credential-shape scan found no likely API keys, access keys, private keys, or GitHub tokens.
  `.env.example` continues to contain only a blank `OPENAI_API_KEY` assignment.
- Review of the completed diff found no runtime behavior, dependency, protocol, or secret-bearing
  example changes.

## Next unit

CAH-002 is now dependency-ready. It introduces the static Ink application shell, Node version pin,
npm lockfile, lifecycle cleanup, and first rendering test without yet starting Python.
