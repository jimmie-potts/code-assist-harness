# PR 30 ignore-matcher review learnings

## Purpose

Capture the reusable checks exposed while reviewing CAH-026's untrusted `.gitignore` boundary. These
are implementation lessons, not new backlog items.

## Findings and prevention

| Review finding | Durable pre-review check |
| --- | --- |
| PathSpec's bare `rstrip()` removes tabs and Unicode whitespace that Git treats as literal. | For every compatibility adapter, compare the dependency's lexical preprocessing with the claimed source grammar. Lock CR, escaped/unescaped ASCII space, tab, and representative Unicode-whitespace boundaries before relying on downstream matching tests. |
| A candidate-pattern counter did not bound catastrophic backtracking inside one Python regex match. | Trace each work budget through the smallest operation it claims to bound. Add one adversarial value that consumes a single outer unit but maximizes work inside that unit; reject it before the expensive dependency call without timing-based tests. |
| PathSpec's Unicode `?` and Python bracket ranges differ from Git's bytewise, separator-safe semantics, allowing false denial or re-inclusion. | Inventory unsupported dependency grammar explicitly. Test Unicode names, slash-spanning ranges, POSIX/negated/escaped forms, malformed syntax, and comment controls; admit only a proved safe subset before compilation when faithful translation is not owned by the unit. |

CAH-026 now normalizes each line once, applies one linear bounded-grammar scan—including
compiler-effective globstar topology after trailing separators—before either kind compile, and
commits no cache, bytes, match work, or matcher effect on rejection. Future matcher
changes should rerun this producer-to-side-effect audit rather than checking only the cited pattern.
