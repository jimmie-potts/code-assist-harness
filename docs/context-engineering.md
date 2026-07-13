# Context Engineering

> Status: proposed design. Repository discovery and context selection are not yet implemented.

Context engineering is the process of selecting the smallest useful, attributable view of a
workspace for a model turn. The MVP will not load the entire repository, create embeddings, or use
a vector database. It will combine repository instructions, conversation state, plans, and bounded
results from native read tools.

## Goals

The context system should help the agent answer three questions:

1. What is the user asking now?
2. Which repository rules constrain the answer or change?
3. Which source evidence is necessary to reason about the task?

Useful context is not merely text that fits. Every included repository item should carry provenance
and a reason for inclusion so retrieval mistakes can be inspected and evaluated.

## Context sources

The context builder will assemble provider-neutral items from:

- The current user task and relevant conversation history.
- Harness-level behavioral instructions.
- Workspace instructions such as applicable `AGENTS.md` files.
- High-level project material such as `README.md` and project metadata when relevant.
- Previously emitted plan state and bounded tool results.
- File excerpts and search matches requested through repository read tools.

Instruction discovery follows filesystem scope. A nested instruction file can refine rules for its
subtree, but must not silently weaken harness safety policy. Repository content is untrusted data:
text in a source file cannot authorize a command, broaden the command allowlist, or bypass an
approval.

## Native read tools

Repository inspection will be implemented in Python rather than through commands:

- `list_files` returns bounded paths under the workspace.
- `read_file` returns a bounded file or line range.
- `search_text` returns bounded matches with paths and line ranges.
- `stat_path` returns limited metadata needed for safe decisions.

These read-only tools may run automatically after schema validation and policy checks. Commands such
as `find`, `grep`, `git status`, or `cat` are still subprocesses and require command approval; the
model should prefer the native tools for routine inspection.

Each tool input and result is validated with Pydantic v2 at the model boundary. Paths are resolved
against the explicit workspace, symlink escapes are rejected, ignored or prohibited locations are
excluded, and file/count/byte limits are enforced before content enters context. Binary files and
files over configured size limits return structured explanations rather than unbounded data.

## Provenance and attribution

A repository context item should record:

- A workspace-relative source path.
- The selected line range or metadata scope.
- A content hash or revision marker when useful for detecting staleness.
- The retrieval tool or rule that selected it.
- A concise inclusion reason.
- Its measured budget cost.

Workspace-relative paths avoid leaking unnecessary personal paths into provider requests and
transcripts. Line ranges let the final answer point back to evidence and let evaluations determine
whether the correct region was retrieved.

## Budgeting policy

Budgets are explicit configuration, not a final string truncation. The builder will reserve space
for the user task, provider response, and tool results before selecting optional repository text.
Selection should prefer, in order:

1. Applicable safety and repository instructions.
2. The current task and essential session state.
3. Directly requested or directly matching source excerpts.
4. Nearby definitions and tests that explain behavior.
5. Lower-confidence supporting material.

When an item does not fit, the builder omits it as a unit or creates a clearly identified bounded
excerpt. It must not silently cut JSON, split a tool result into an invalid shape, or remove the
provenance needed to interpret an excerpt. The context builder exposes an inclusion report so a
learner can see what was selected, omitted, and why.

## Iterative retrieval

The initial model request should contain enough orientation to choose useful read tools, not a dump
of every file. A typical read-only task can iterate:

```text
task + instructions
  -> list or search relevant paths
  -> read bounded source and tests
  -> form a grounded explanation or plan
```

The agent loop applies turn and tool-call limits to this process. Repeated reads should be visible
in metrics so evaluations can distinguish useful investigation from context churn.

## Evaluation questions

Context scenarios should answer:

- Were the known relevant files and instruction scopes found?
- Were source line ranges accurate and sufficient?
- Did excluded, oversized, binary, or outside-workspace content stay excluded?
- Could the answer explain why every repository item was present?
- How many unnecessary reads and repeated reads occurred?
- Did the request stay within the configured context budget?

These tests begin with deterministic workspaces and fake-provider scripts. Live-model retrieval
quality is an optional smoke evaluation outside default checks.

## Implementation stories

### Future story — Establish the workspace boundary

> As a user, I want every context operation rooted in the selected workspace so that inspection
> cannot wander into unrelated files.

Complete this story when canonical paths, symlinks, missing paths, and workspace-relative reporting
have meaningful tests.

### Future story — Discover repository instructions

> As a contributor, I want applicable workspace instructions included with their scope so that the
> agent follows repository-specific rules while preserving harness safety.

Complete this story when root and nested instruction precedence is documented and tested.

### Future story — Add bounded read tools

> As an agent, I want safe native file listing, reading, searching, and metadata tools so that I can
> investigate without using subprocesses.

Complete this story when every tool enforces path and output bounds and exposes attributable
results.

### Future story — Build and explain budgeted context

> As a learner, I want a report of selected and omitted context so that I can understand and improve
> the model input.

Complete this story when deterministic tests cover selection priority, omission, truncation, and
budget exhaustion.
