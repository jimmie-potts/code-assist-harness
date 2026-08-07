from __future__ import annotations

import os
import traceback
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pathspec import GitIgnoreSpec

import code_assist_harness.repository_access as repository_access
from code_assist_harness.repository_access import (
    DEFAULT_LIST_ITEMS,
    DEFAULT_RECURSIVE_DEPTH,
    DEFAULT_SEARCH_MATCHES,
    MAX_CONTEXT_BYTES,
    MAX_CONTEXT_ITEMS,
    MAX_LIST_ITEMS,
    MAX_POLICY_BYTES,
    MAX_POLICY_MATCH_WORK,
    MAX_POLICY_SOURCE_BYTES,
    MAX_POLICY_SOURCES,
    MAX_RECURSIVE_DEPTH,
    MAX_RETURNED_TEXT_BYTES,
    MAX_SEARCH_MATCHES,
    MAX_SOURCE_BYTES,
    RepositoryAccessError,
    RepositoryPathSyntaxError,
    RepositoryReadPolicy,
    is_hard_denied_path,
    is_model_facing_text,
    normalize_repository_path_components,
)
from code_assist_harness.workspace import (
    ResolvedWorkspacePath,
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_workspace_relative_path,
)

ERROR_MESSAGES = {
    "invalid_repository_path": "Repository path must be a valid workspace-relative path.",
    "repository_path_not_found": "Repository path does not exist.",
    "repository_path_unavailable": "Repository path is not available.",
    "repository_path_ignored": "Repository path is ignored.",
    "repository_expected_directory": "Repository path must be a directory.",
    "repository_expected_file": "Repository path must be a regular file.",
    "repository_not_text": "Repository file must be valid UTF-8 text.",
    "repository_source_too_large": "Repository file exceeds the byte limit.",
    "repository_input_limit": "Repository request exceeds the input limit.",
    "repository_result_limit": "Repository result exceeds the item or byte limit.",
    "repository_policy_invalid": "Repository ignore policy could not be loaded safely.",
    "repository_read_failed": "Repository content could not be read.",
}


class _TextSubclass(str):
    pass


def _policy(root: Path) -> RepositoryReadPolicy:
    return RepositoryReadPolicy(WorkspaceBoundary.from_path(root))


def _assert_access_error(error: RepositoryAccessError, code: str) -> None:
    assert error.code == code
    assert str(error) == ERROR_MESSAGES[code]
    assert error.args == (ERROR_MESSAGES[code],)


def _admit_error(policy: RepositoryReadPolicy, path: object, code: str) -> None:
    with pytest.raises(RepositoryAccessError) as caught:
        policy.admit_existing(path)  # type: ignore[arg-type]
    _assert_access_error(caught.value, code)


def _build_policy_chain(workspace: Path, sizes: list[int]) -> str:
    owner = workspace
    parts: list[str] = []
    for index, size in enumerate(sizes):
        content = b"#" + (b"x" * (size - 1)) if size else b""
        (owner / ".gitignore").write_bytes(content)
        component = f"level-{index}"
        parts.append(component)
        owner = owner / component
        owner.mkdir()
    (owner / "target.txt").write_text("target", encoding="utf-8")
    return "/".join([*parts, "target.txt"])


def test_shared_operation_limits_are_the_reviewed_values() -> None:
    assert (MAX_SOURCE_BYTES, MAX_RETURNED_TEXT_BYTES) == (262_144, 65_536)
    assert (DEFAULT_LIST_ITEMS, MAX_LIST_ITEMS) == (200, 500)
    assert (DEFAULT_RECURSIVE_DEPTH, MAX_RECURSIVE_DEPTH) == (4, 8)
    assert (DEFAULT_SEARCH_MATCHES, MAX_SEARCH_MATCHES) == (100, 200)
    assert (MAX_CONTEXT_ITEMS, MAX_CONTEXT_BYTES) == (24, 98_304)
    assert (MAX_POLICY_SOURCE_BYTES, MAX_POLICY_SOURCES, MAX_POLICY_BYTES) == (
        65_536,
        16,
        262_144,
    )
    assert MAX_POLICY_MATCH_WORK == 65_536


@pytest.mark.parametrize(("code", "message"), ERROR_MESSAGES.items())
def test_repository_access_error_surface_is_closed_and_fixed(code: str, message: str) -> None:
    error = RepositoryAccessError(code)  # type: ignore[arg-type]

    assert error.code == code
    assert str(error) == message
    assert error.args == (message,)


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("plain", True),
        ("caf\N{LATIN SMALL LETTER E WITH ACUTE}", True),
        ("cafe\N{COMBINING ACUTE ACCENT}", True),
        ("", True),
        ("nul\x00value", False),
        ("\ud800", False),
        ("\udfff", False),
        (b"bytes", False),
        (_TextSubclass("subclass"), False),
    ],
)
def test_model_facing_text_requires_an_exact_strict_utf8_scalar_string(
    value: object,
    accepted: bool,
) -> None:
    assert is_model_facing_text(value) is accepted


def test_repository_path_adapter_normalizes_only_dots_and_linux_separators() -> None:
    assert normalize_repository_path_components(".") == ()
    assert normalize_repository_path_components("./docs//./guide.md/") == (
        "docs",
        "guide.md",
    )
    assert normalize_repository_path_components(r"docs\guide.md") == (r"docs\guide.md",)


@pytest.mark.parametrize(
    "value",
    [
        "",
        b"bytes",
        Path("path-like"),
        _TextSubclass("subclass"),
        "\ud800",
        "\udfff",
        "contains\x00nul",
        "/absolute",
        "..",
        "docs/../outside",
        "a" * 256,
        "/".join(["a"] * 257),
    ],
)
def test_repository_path_adapter_has_exact_parity_with_workspace_lexical_rejection(
    value: object,
) -> None:
    with pytest.raises(WorkspaceBoundaryError):
        normalize_workspace_relative_path(value)  # type: ignore[arg-type]

    with pytest.raises(RepositoryPathSyntaxError) as caught:
        normalize_repository_path_components(value)  # type: ignore[arg-type]

    assert str(caught.value) == "Repository path syntax is invalid."
    assert caught.value.args == ("Repository path syntax is invalid.",)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert "outside" not in repr(caught.value)


def test_repository_path_adapter_matches_workspace_lexical_budget_endpoints() -> None:
    names_255 = ["a" * 255] * 16
    values = (
        "/".join([*names_255[:-1], "a" * 254]),
        "/".join(names_255),
        "/".join(["a"] * 255),
        "/".join(["a"] * 256),
        "\N{GRINNING FACE}/scalar.txt",
    )

    for value in values:
        assert normalize_repository_path_components(value) == normalize_workspace_relative_path(
            value
        )

    for value in (f"{'/'.join(names_255)}/", "a" * 256, "/".join(["a"] * 257)):
        with pytest.raises(RepositoryPathSyntaxError):
            normalize_repository_path_components(value)


@pytest.mark.parametrize("component", [".git", ".hg", ".svn", ".ssh", ".gnupg", ".aws"])
def test_hard_deny_rejects_exact_sensitive_directory_components(component: str) -> None:
    assert is_hard_denied_path(("safe", component, "child.txt"))
    assert not is_hard_denied_path(("safe", component.upper(), "child.txt"))


@pytest.mark.parametrize(
    "basename",
    [
        ".envrc",
        ".netrc",
        ".npmrc",
        ".pypirc",
        ".git-credentials",
        "credentials",
        "credentials.json",
        "application_default_credentials.json",
        "service-account.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "CREDENTIALS.JSON",
        ".env",
        ".ENV",
        "dev.env",
        ".env.local",
        ".env.Example",
        "certificate.pem",
        "certificate.KEY",
        "certificate.p12",
        "certificate.PFX",
    ],
)
def test_hard_deny_rejects_sensitive_basenames_and_ascii_casefolded_suffixes(
    basename: str,
) -> None:
    assert is_hard_denied_path(("safe", basename))


@pytest.mark.parametrize(
    "components",
    [
        (),
        ("src", "normal.py"),
        ("safe", ".GIT", "config"),
        ("docs", ".env.example"),
        ("docs", ".env.sample"),
        ("docs", ".env.template"),
        ("docs", "normal.env.example"),
        ("docs", "certificate.\N{KELVIN SIGN}EY"),
    ],
)
def test_hard_deny_allows_normal_and_exact_documentation_paths(
    components: tuple[str, ...],
) -> None:
    assert not is_hard_denied_path(components)


def test_policy_retains_boundary_identity_and_returns_frozen_canonical_results(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("target", encoding="utf-8")
    alias = workspace / "alias.txt"
    alias.symlink_to(target)
    boundary = WorkspaceBoundary.from_path(workspace)
    policy = RepositoryReadPolicy(boundary)

    result = policy.admit_existing("alias.txt")

    assert policy.boundary is boundary
    assert result.path == "target.txt"
    assert result.kind == "file"
    assert result.is_symlink is True
    assert str(tmp_path) not in repr(policy)
    assert str(tmp_path) not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.kind = "directory"  # type: ignore[misc]


def test_policy_admits_root_and_directories(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    directory = workspace / "docs"
    directory.mkdir(parents=True)
    policy = _policy(workspace)

    root = policy.admit_existing(".")
    docs = policy.admit_existing("docs")

    assert (root.path, root.kind, root.is_symlink) == (".", "directory", False)
    assert (docs.path, docs.kind, docs.is_symlink) == (
        "docs",
        "directory",
        False,
    )


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("missing.txt", "repository_path_not_found"),
        (".git/config", "repository_path_unavailable"),
        ("../outside", "invalid_repository_path"),
        ("\ud800", "invalid_repository_path"),
        ("contains\x00nul", "invalid_repository_path"),
    ],
)
def test_policy_maps_path_failures_to_exact_safe_errors(
    tmp_path: Path,
    path: str,
    code: str,
) -> None:
    workspace = tmp_path / "private-workspace"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("private", encoding="utf-8")
    policy = _policy(workspace)

    with pytest.raises(RepositoryAccessError) as caught:
        policy.admit_existing(path)

    _assert_access_error(caught.value, code)
    assert path not in repr(caught.value)
    assert str(tmp_path) not in repr(caught.value)


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("invalid-lexical", "invalid_repository_path"),
        ("missing-target", "repository_path_not_found"),
        ("invalid-policy", "repository_policy_invalid"),
    ],
)
def test_safe_error_tracebacks_suppress_inputs_host_paths_and_policy_text(
    tmp_path: Path,
    scenario: str,
    expected_code: str,
) -> None:
    secret = "trace-secret-marker"
    workspace = tmp_path / "private-workspace"
    workspace.mkdir()
    requested = f"../{secret}"
    if scenario == "missing-target":
        requested = f"{secret}-missing"
    elif scenario == "invalid-policy":
        requested = "target.txt"
        (workspace / requested).write_text("target", encoding="utf-8")
        (workspace / ".gitignore").write_text(f"{secret}\\", encoding="utf-8")

    with pytest.raises(RepositoryAccessError) as caught:
        _policy(workspace).admit_existing(requested)

    rendered = "".join(
        traceback.format_exception(
            type(caught.value),
            caught.value,
            caught.value.__traceback__,
        )
    )
    _assert_access_error(caught.value, expected_code)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert secret not in rendered
    assert str(tmp_path) not in rendered


@pytest.mark.parametrize(
    "path",
    [".ssh/config", "credentials.json", "dev.env", "certificate.pem"],
)
def test_policy_hard_deny_matches_pure_classifier_and_ignore_negation_cannot_override(
    tmp_path: Path,
    path: str,
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace.joinpath(*path.split("/"))
    target.parent.mkdir(parents=True)
    target.write_text("private", encoding="utf-8")
    (workspace / ".gitignore").write_text(f"!{path}\n", encoding="utf-8")

    assert is_hard_denied_path(normalize_repository_path_components(path))
    _admit_error(_policy(workspace), path, "repository_path_unavailable")


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("requested-alias", "repository_path_unavailable"),
        ("policy-source", "repository_policy_invalid"),
    ],
)
def test_canonical_hard_deny_precedes_explicit_target_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_code: str,
) -> None:
    workspace = tmp_path / "workspace"
    denied = workspace / ".git" / "config"
    denied.parent.mkdir(parents=True)
    denied.write_text("private", encoding="utf-8")
    safe_target = workspace / "target.txt"
    safe_target.write_text("target", encoding="utf-8")
    if scenario == "requested-alias":
        alias = workspace / "safe-alias"
        alias.symlink_to(denied)
        requested = "safe-alias"
    else:
        (workspace / ".gitignore").symlink_to(denied)
        requested = "target.txt"

    policy = _policy(workspace)
    original_stat = Path.stat
    denied_stat_calls = 0

    def track_stat(path: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        nonlocal denied_stat_calls
        if path == denied:
            denied_stat_calls += 1
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", track_stat)

    _admit_error(policy, requested, expected_code)
    assert denied_stat_calls == 0


def test_root_ignore_cannot_downgrade_a_canonical_hard_denied_alias(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    denied = workspace / ".git" / "config"
    denied.parent.mkdir(parents=True)
    denied.write_text("private", encoding="utf-8")
    alias = workspace / "safe-alias"
    alias.symlink_to(denied.parent, target_is_directory=True)
    (workspace / ".gitignore").write_text("safe-alias/config\n", encoding="utf-8")

    _admit_error(_policy(workspace), "safe-alias/config", "repository_path_unavailable")


def test_root_and_nested_gitignore_rules_use_git_precedence_and_owner_scope(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "nested"
    other = workspace / "other"
    nested.mkdir(parents=True)
    other.mkdir()
    (workspace / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (nested / ".gitignore").write_text("!keep.log\nlocal.tmp\n", encoding="utf-8")
    for path in (
        workspace / "root.log",
        nested / "keep.log",
        nested / "local.tmp",
        other / "local.tmp",
    ):
        path.write_text("text", encoding="utf-8")
    policy = _policy(workspace)

    _admit_error(policy, "root.log", "repository_path_ignored")
    assert policy.admit_existing("nested/keep.log").path == "nested/keep.log"
    _admit_error(policy, "nested/local.tmp", "repository_path_ignored")
    assert policy.admit_existing("other/local.tmp").path == "other/local.tmp"


def test_lexically_ignored_missing_target_is_not_an_existence_oracle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("private-missing.txt\n", encoding="utf-8")
    boundary = WorkspaceBoundary.from_path(workspace)
    policy = RepositoryReadPolicy(boundary)
    original_resolve = WorkspaceBoundary.resolve_existing
    requested_resolutions = 0

    def track_resolution(self: WorkspaceBoundary, value: str) -> ResolvedWorkspacePath:
        nonlocal requested_resolutions
        if value == "private-missing.txt":
            requested_resolutions += 1
        return original_resolve(self, value)

    monkeypatch.setattr(WorkspaceBoundary, "resolve_existing", track_resolution)

    _admit_error(
        policy,
        "private-missing.txt",
        "repository_path_ignored",
    )
    assert requested_resolutions == 0


def test_ignored_leaf_below_a_missing_owner_keeps_the_ignore_result(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("missing/deep.txt\n", encoding="utf-8")

    _admit_error(
        _policy(workspace),
        "missing/deep.txt",
        "repository_path_ignored",
    )


def test_directory_only_rule_distinguishes_a_direct_directory_from_a_regular_file(
    tmp_path: Path,
) -> None:
    directory_workspace = tmp_path / "directory-workspace"
    (directory_workspace / "cache").mkdir(parents=True)
    (directory_workspace / ".gitignore").write_text("cache/\n", encoding="utf-8")
    _admit_error(
        _policy(directory_workspace),
        "cache",
        "repository_path_ignored",
    )

    file_workspace = tmp_path / "file-workspace"
    file_workspace.mkdir()
    (file_workspace / ".gitignore").write_text("cache/\n", encoding="utf-8")
    (file_workspace / "cache").write_text("not a directory", encoding="utf-8")

    assert _policy(file_workspace).admit_existing("cache").kind == "file"


@pytest.mark.parametrize(
    ("raw", "semantic"),
    [
        ("foo   ", "foo"),
        ("foo\\ ", "foo\\ "),
        ("foo\\  ", "foo\\ "),
        ("foo\\\\ ", "foo\\\\"),
        ("foo\\\\\\ ", "foo\\\\\\ "),
        ("foo\t", "foo\t"),
        ("foo\N{NO-BREAK SPACE}", "foo\N{NO-BREAK SPACE}"),
        ("foo\N{EM SPACE}", "foo\N{EM SPACE}"),
        ("foo/\t", "foo/\t"),
        ("foo/   ", "foo/"),
        ("foo  \\", "foo  \\"),
        ("foo\r", "foo"),
        ("foo\r\r", "foo\r"),
        ("\t ", "\t"),
        (" \t", " \t"),
    ],
)
def test_policy_line_normalization_matches_git_trailing_whitespace(
    raw: str,
    semantic: str,
) -> None:
    assert repository_access._normalize_policy_line(raw) == semantic


def test_non_space_trailing_whitespace_cannot_reinclude_an_ignored_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    ignored = workspace / "foo"
    ignored.mkdir(parents=True)
    (ignored / "secret.txt").write_text("secret", encoding="utf-8")
    (ignored / ".gitignore").write_bytes(b"\xff")
    (workspace / ".gitignore").write_text("foo\n!foo/\t\n", encoding="utf-8")

    policy = _policy(workspace)
    _admit_error(policy, "foo", "repository_path_ignored")
    _admit_error(policy, "foo/secret.txt", "repository_path_ignored")


@pytest.mark.parametrize("trailing", ["\t", "\N{NO-BREAK SPACE}", "\N{EM SPACE}"])
def test_file_patterns_preserve_non_space_trailing_whitespace(
    tmp_path: Path,
    trailing: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    exact = f"note{trailing}"
    (workspace / exact).write_text("ignored", encoding="utf-8")
    (workspace / "note").write_text("admitted", encoding="utf-8")
    (workspace / ".gitignore").write_text(exact, encoding="utf-8")
    policy = _policy(workspace)

    _admit_error(policy, exact, "repository_path_ignored")
    assert policy.admit_existing("note").kind == "file"


def test_tab_after_a_slash_is_a_literal_child_not_a_directory_terminator(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    parent = workspace / "foo"
    parent.mkdir(parents=True)
    (parent / "\t").write_text("ignored", encoding="utf-8")
    (workspace / ".gitignore").write_text("foo/\t\n", encoding="utf-8")
    policy = _policy(workspace)

    assert policy.admit_existing("foo").kind == "directory"
    _admit_error(policy, "foo/\t", "repository_path_ignored")


@pytest.mark.parametrize(
    "pattern",
    [
        "[[:digit:]].txt",
        "[![:digit:]].txt",
        "![[:digit:]].txt",
        "[a[:digit:]_].txt",
        "[[:bogus:]].txt",
        "[[:DIGIT:]].txt",
        "[[:digit]].txt",
        "[[:digit:].txt",
        "[[:]].txt",
        "*\n![[:digit:]]",
        "*\n![[:bogus:]]",
        "*\n![[:digit]]",
        "*\n![:digit:]",
        "*\n![!a]",
        "*\n![a:]",
        "*\n![\\a]",
        "*\n!?",
        "??",
        "*\n![a\\]*",
        r"[a\][:digit:]]",
        "a/*\n!a[.-0]b",
    ],
)
def test_unsupported_bracket_syntax_fails_before_pathspec_or_state_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pattern: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "target.txt").write_text("target", encoding="utf-8")
    (workspace / ".gitignore").write_text(pattern, encoding="utf-8")
    traversal = _policy(workspace)._new_admission()
    original_compile = repository_access._compile_policy_pattern
    compile_calls = 0

    def track_compile(line: str) -> object:
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(line)

    monkeypatch.setattr(repository_access, "_compile_policy_pattern", track_compile)

    _admit_error(traversal, "target.txt", "repository_policy_invalid")  # type: ignore[arg-type]
    assert compile_calls == 0
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize(
    ("rules", "target"),
    [
        ("*\n!?\n", "\N{LATIN SMALL LETTER E WITH ACUTE}"),
        ("??\n", "\N{LATIN SMALL LETTER E WITH ACUTE}"),
        ("*\n![!a]\n", ":"),
        ("*\n![a:]\n", ":"),
        ("*\n![\\a]\n", "\\"),
        ("a/*\n!a[.-0]b\n", "a/b"),
    ],
)
def test_backend_divergent_patterns_fail_closed_for_their_bypass_targets(
    tmp_path: Path,
    rules: str,
    target: str,
) -> None:
    workspace = tmp_path / "workspace"
    target_path = workspace.joinpath(*target.split("/"))
    target_path.parent.mkdir(parents=True)
    target_path.write_text("target", encoding="utf-8")
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")

    _admit_error(_policy(workspace), target, "repository_policy_invalid")


def test_safe_positive_ascii_range_can_reinclude_a_root_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "b").write_text("target", encoding="utf-8")
    (workspace / ".gitignore").write_text("*\n![a-z]\n", encoding="utf-8")

    assert _policy(workspace).admit_existing("b").kind == "file"


@pytest.mark.parametrize(
    "pattern",
    [
        "#[[:digit:]]",
        "[a-z]",
        "[0-9]*.log",
        "*.py[cod]",
        "[*].txt",
        r"literal\?name",
    ],
)
def test_comments_and_safe_positive_ranges_remain_supported(pattern: str) -> None:
    repository_access._compile_policy_rules([pattern])


@pytest.mark.parametrize(
    "class_name",
    [
        "alnum",
        "alpha",
        "blank",
        "cntrl",
        "digit",
        "graph",
        "lower",
        "print",
        "punct",
        "space",
        "upper",
        "xdigit",
    ],
)
def test_every_git_posix_class_is_inside_the_fail_closed_subset(class_name: str) -> None:
    with pytest.raises(ValueError, match="unsupported bracket syntax"):
        repository_access._compile_policy_rules([f"[[:{class_name}:]]"])


def test_posix_class_at_the_exact_policy_byte_limit_fails_before_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "target.txt").write_text("target", encoding="utf-8")
    suffix = "\n[[:digit:]]"
    content = "#" + ("x" * (MAX_POLICY_SOURCE_BYTES - len(suffix) - 1)) + suffix
    payload = content.encode("utf-8")
    assert len(payload) == MAX_POLICY_SOURCE_BYTES
    (workspace / ".gitignore").write_bytes(payload)
    traversal = _policy(workspace)._new_admission()
    original_compile = repository_access._compile_policy_pattern
    compile_calls = 0

    def track_compile(line: str) -> object:
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(line)

    monkeypatch.setattr(repository_access, "_compile_policy_pattern", track_compile)

    _admit_error(traversal, "target.txt", "repository_policy_invalid")  # type: ignore[arg-type]
    assert compile_calls == 0
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize(
    "pattern",
    [
        "*.log",
        "src/*/generated/*.ts",
        "**/*.py",
        "src/**/generated/*.ts",
        "packages/*/dist/**/*.map",
        "**/node_modules/**",
        r"literal\*name",
        "[*].txt",
        "# *a*a*a*a*ab",
    ],
)
def test_common_linear_ignore_patterns_remain_supported(pattern: str) -> None:
    repository_access._compile_policy_rules([pattern])


@pytest.mark.parametrize(
    "pattern",
    [
        "*a*a*a*a*ab",
        "*generated*",
        "**/foo/**/bar",
        "a/**//**//",
        "/**//**//",
        "*a*b/",
        r"[a\]*a*a*a*a*ab",
    ],
)
def test_ambiguous_ignore_repetition_fails_before_matcher_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pattern: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = "a" * 255
    (workspace / target).write_text("target", encoding="utf-8")
    (workspace / ".gitignore").write_text(pattern, encoding="utf-8")
    traversal = _policy(workspace)._new_admission()
    original_compile = repository_access._compile_policy_pattern
    compile_calls = 0

    def fail_check(*args: object, **kwargs: object) -> bool | None:
        del args, kwargs
        raise AssertionError("an unbounded pattern must not reach the matcher")

    def track_compile(line: str) -> object:
        nonlocal compile_calls
        compile_calls += 1
        return original_compile(line)

    monkeypatch.setattr(repository_access, "_check_policy", fail_check)
    monkeypatch.setattr(repository_access, "_compile_policy_pattern", track_compile)

    _admit_error(traversal, target, "repository_policy_invalid")  # type: ignore[arg-type]
    assert compile_calls == 0
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize(
    ("rule", "directory_name"),
    [
        ("space-name /\n", "space-name "),
        ("tab-name\t/\n", "tab-name\t"),
        ("escaped\\ /\n", "escaped "),
        ("foo\\  /\n", "foo  "),
        ("foo\\ \t/\n", "foo \t"),
    ],
)
def test_directory_terminator_preserves_significant_whitespace_in_the_name(
    tmp_path: Path,
    rule: str,
    directory_name: str,
) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / directory_name
    target.mkdir(parents=True)
    (workspace / ".gitignore").write_text(rule, encoding="utf-8")

    _admit_error(_policy(workspace), directory_name, "repository_path_ignored")


def test_invalid_positive_directory_range_remains_a_no_op_in_derived_rules(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    directory_name = "foo[ "
    target = workspace / directory_name
    target.mkdir(parents=True)
    (target / "file.txt").write_text("text", encoding="utf-8")
    (workspace / ".gitignore").write_text("foo[ /\n", encoding="utf-8")
    policy = _policy(workspace)

    assert policy.admit_existing(directory_name).kind == "directory"
    assert policy.admit_existing(f"{directory_name}/file.txt").kind == "file"


def test_invalid_negated_directory_range_cannot_reinclude_an_ignored_target(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    directory_name = "foo[ "
    target = workspace / directory_name
    target.mkdir(parents=True)
    (target / "file.txt").write_text("text", encoding="utf-8")
    (workspace / ".gitignore").write_text("*/\n!foo[ /\n", encoding="utf-8")
    policy = _policy(workspace)

    _admit_error(policy, directory_name, "repository_path_ignored")
    _admit_error(policy, f"{directory_name}/file.txt", "repository_path_ignored")


@pytest.mark.parametrize(
    ("rules", "kind", "admitted"),
    [
        ("cache\n!cache/\n", "file", False),
        ("cache\n!cache/\n", "directory", True),
        ("cache/\n!cache\ncache/\n", "file", True),
        ("cache/\n!cache\ncache/\n", "directory", False),
    ],
)
def test_opposing_leaf_forms_apply_last_match_precedence_per_exact_kind(
    tmp_path: Path,
    rules: str,
    kind: str,
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    target = workspace / "cache"
    if kind == "directory":
        target.mkdir()
    else:
        target.write_text("regular file", encoding="utf-8")

    policy = _policy(workspace)
    if admitted:
        assert policy.admit_existing("cache").kind == kind
    else:
        _admit_error(policy, "cache", "repository_path_ignored")


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is not available")
def test_special_target_maps_to_generic_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    os.mkfifo(workspace / "private-pipe")

    _admit_error(_policy(workspace), "private-pipe", "repository_path_unavailable")


@pytest.mark.parametrize(
    ("rules", "admitted"),
    [
        ("private/\n!private/keep.py\n", False),
        ("private/*\n!private/keep.py\n", True),
    ],
)
def test_ignored_ancestor_cannot_be_rescued_but_traversable_parent_can(
    tmp_path: Path,
    rules: str,
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    private = workspace / "private"
    private.mkdir(parents=True)
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    (private / "keep.py").write_text("keep", encoding="utf-8")
    if not admitted:
        # This invalid policy must never be loaded below an already ignored directory.
        (private / ".gitignore").write_bytes(b"\xff")
    policy = _policy(workspace)

    if admitted:
        assert policy.admit_existing("private/keep.py").path == "private/keep.py"
    else:
        _admit_error(policy, "private/keep.py", "repository_path_ignored")


@pytest.mark.parametrize(
    ("rules", "parent_name"),
    [
        ("private/*\n!private/\n", "private"),
        ("foo/**\n", "foo"),
    ],
)
def test_git_descendant_patterns_keep_parent_traversable_and_skip_nested_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rules: str,
    parent_name: str,
) -> None:
    workspace = tmp_path / "workspace"
    blocked_directory = workspace / parent_name / "dir"
    blocked_directory.mkdir(parents=True)
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    nested_policy = blocked_directory / ".gitignore"
    nested_policy.write_bytes(b"\xff")
    (blocked_directory / "secret.txt").write_text("secret", encoding="utf-8")
    original_read = RepositoryReadPolicy._read_policy_bytes
    nested_reads = 0

    def track_read(source: Path) -> bytes:
        nonlocal nested_reads
        if source == nested_policy:
            nested_reads += 1
        return original_read(source)

    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )
    policy = _policy(workspace)

    assert policy.admit_existing(parent_name).kind == "directory"
    _admit_error(policy, f"{parent_name}/dir", "repository_path_ignored")
    _admit_error(policy, f"{parent_name}/dir/secret.txt", "repository_path_ignored")
    assert nested_reads == 0


@pytest.mark.parametrize("rules", ["!/\n", "foo//\n", "foo/**//\n"])
def test_degenerate_git_directory_lines_remain_no_ops_in_paired_views(
    tmp_path: Path,
    rules: str,
) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "foo" / "dir"
    nested.mkdir(parents=True)
    (nested / "file.txt").write_text("text", encoding="utf-8")
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    policy = _policy(workspace)

    assert policy.admit_existing("foo").kind == "directory"
    assert policy.admit_existing("foo/dir").kind == "directory"
    assert policy.admit_existing("foo/dir/file.txt").kind == "file"


@pytest.mark.parametrize(
    ("rules", "directory_path"),
    [
        ("cache\n!cache/\n", "cache"),
        ("private/*\n!private/dir/\n", "private/dir"),
    ],
)
def test_direct_parent_reinclusion_applies_to_its_descendants(
    tmp_path: Path,
    rules: str,
    directory_path: str,
) -> None:
    workspace = tmp_path / "workspace"
    directory = workspace.joinpath(*directory_path.split("/"))
    directory.mkdir(parents=True)
    (directory / "key").write_text("value", encoding="utf-8")
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    policy = _policy(workspace)

    assert policy.admit_existing(directory_path).kind == "directory"
    assert policy.admit_existing(f"{directory_path}/key").kind == "file"


@pytest.mark.parametrize(
    ("rules", "parent_path", "blocked_path"),
    [
        ("*/\n!foo/\n", "foo", "foo/bar"),
        ("**/\n!foo/\n", "foo", "foo/bar"),
        ("a/**/\n", "a", "a/foo"),
    ],
)
def test_positive_directory_wildcards_still_ignore_reincluded_parent_descendants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rules: str,
    parent_path: str,
    blocked_path: str,
) -> None:
    workspace = tmp_path / "workspace"
    blocked_directory = workspace.joinpath(*blocked_path.split("/"))
    blocked_directory.mkdir(parents=True)
    nested_policy = blocked_directory / ".gitignore"
    nested_policy.write_bytes(b"\xff")
    (blocked_directory / "file.txt").write_text("secret", encoding="utf-8")
    (workspace / ".gitignore").write_text(rules, encoding="utf-8")
    original_read = RepositoryReadPolicy._read_policy_bytes
    nested_reads = 0

    def track_read(source: Path) -> bytes:
        nonlocal nested_reads
        if source == nested_policy:
            nested_reads += 1
        return original_read(source)

    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )
    policy = _policy(workspace)

    assert policy.admit_existing(parent_path).kind == "directory"
    _admit_error(policy, blocked_path, "repository_path_ignored")
    _admit_error(policy, f"{blocked_path}/file.txt", "repository_path_ignored")
    assert nested_reads == 0


@pytest.mark.parametrize("ignored_view", ["alias", "canonical"])
def test_lexical_or_canonical_alias_ignore_independently_denies(
    tmp_path: Path,
    ignored_view: str,
) -> None:
    workspace = tmp_path / "workspace"
    canonical = workspace / "canonical"
    canonical.mkdir(parents=True)
    (canonical / "file.txt").write_text("text", encoding="utf-8")
    (workspace / "alias").symlink_to(canonical, target_is_directory=True)
    (workspace / ".gitignore").write_text(
        f"{ignored_view}/\n!{'canonical' if ignored_view == 'alias' else 'alias'}/file.txt\n",
        encoding="utf-8",
    )
    policy = _policy(workspace)

    _admit_error(policy, "alias/file.txt", "repository_path_ignored")


def test_dual_view_alias_success_returns_only_the_canonical_label(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    canonical = workspace / "canonical"
    canonical.mkdir(parents=True)
    (canonical / "file.txt").write_text("text", encoding="utf-8")
    (workspace / "alias").symlink_to(canonical, target_is_directory=True)

    result = _policy(workspace).admit_existing("alias/file.txt")

    assert result.path == "canonical/file.txt"
    assert result.is_symlink is False


@pytest.mark.parametrize("mutation", ["retarget", "type-change"])
def test_final_target_snapshot_rejects_retarget_and_type_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if mutation == "retarget":
        original_target = workspace / "original.txt"
        replacement_target = workspace / "replacement.txt"
        original_target.write_text("original", encoding="utf-8")
        replacement_target.write_text("replacement", encoding="utf-8")
        requested_leaf = workspace / "alias.txt"
        requested_leaf.symlink_to(original_target)
    else:
        requested_leaf = workspace / "target.txt"
        requested_leaf.write_text("target", encoding="utf-8")
        replacement_target = requested_leaf
    requested = requested_leaf.name
    boundary = WorkspaceBoundary.from_path(workspace)
    policy = RepositoryReadPolicy(boundary)
    original_resolve = WorkspaceBoundary.resolve_existing
    target_resolutions = 0
    mutated = False

    def mutate_before_final_resolution(
        self: WorkspaceBoundary,
        value: str,
    ) -> ResolvedWorkspacePath:
        nonlocal mutated, target_resolutions
        if self is boundary and value == requested:
            target_resolutions += 1
            if target_resolutions == 2:
                requested_leaf.unlink()
                if mutation == "retarget":
                    requested_leaf.symlink_to(replacement_target)
                else:
                    requested_leaf.mkdir()
                mutated = True
        return original_resolve(self, value)

    monkeypatch.setattr(
        WorkspaceBoundary,
        "resolve_existing",
        mutate_before_final_resolution,
    )

    with pytest.raises(RepositoryAccessError) as caught:
        policy.admit_existing(requested)

    _assert_access_error(caught.value, "repository_path_unavailable")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert target_resolutions == 2
    assert mutated


def test_policy_maps_replaced_workspace_root_to_safe_unavailable(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "target.txt").write_text("target", encoding="utf-8")
    policy = _policy(workspace)
    retained = tmp_path / "retained-workspace"
    workspace.rename(retained)
    workspace.mkdir()

    with pytest.raises(RepositoryAccessError) as caught:
        policy.admit_existing("target.txt")

    _assert_access_error(caught.value, "repository_path_unavailable")
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "source_kind",
    ["dangling", "outside", "hard-denied", "directory", "oversized", "invalid-utf8", "nul"],
)
def test_present_unsafe_gitignore_sources_fail_closed(
    tmp_path: Path,
    source_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "target.txt"
    target.write_text("target", encoding="utf-8")
    candidate = workspace / ".gitignore"

    if source_kind == "dangling":
        candidate.symlink_to(workspace / "missing-policy")
    elif source_kind == "outside":
        outside = tmp_path / "outside-policy"
        outside.write_text("target.txt\n", encoding="utf-8")
        candidate.symlink_to(outside)
    elif source_kind == "hard-denied":
        denied = workspace / ".git" / "config"
        denied.parent.mkdir()
        denied.write_text("target.txt\n", encoding="utf-8")
        candidate.symlink_to(denied)
    elif source_kind == "directory":
        candidate.mkdir()
    elif source_kind == "oversized":
        candidate.write_bytes(b" " * (MAX_POLICY_SOURCE_BYTES + 1))
    elif source_kind == "invalid-utf8":
        candidate.write_bytes(b"\xff")
    else:
        candidate.write_bytes(b"target.txt\x00\n")

    _admit_error(_policy(workspace), "target.txt", "repository_policy_invalid")


@pytest.mark.parametrize(
    ("size", "admitted"),
    [
        (MAX_POLICY_SOURCE_BYTES - 1, True),
        (MAX_POLICY_SOURCE_BYTES, True),
        (MAX_POLICY_SOURCE_BYTES + 1, False),
    ],
)
def test_one_policy_source_enforces_inclusive_byte_limit(
    tmp_path: Path,
    size: int,
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = _build_policy_chain(workspace, [size])
    policy = _policy(workspace)

    if admitted:
        assert policy.admit_existing(target).kind == "file"
    else:
        _admit_error(policy, target, "repository_policy_invalid")


@pytest.mark.parametrize(
    ("count", "admitted"),
    [(MAX_POLICY_SOURCES, True), (MAX_POLICY_SOURCES + 1, False)],
)
def test_distinct_policy_source_count_enforces_inclusive_limit(
    tmp_path: Path,
    count: int,
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = _build_policy_chain(workspace, [1] * count)
    policy = _policy(workspace)

    if admitted:
        assert policy.admit_existing(target).kind == "file"
    else:
        _admit_error(policy, target, "repository_policy_invalid")


@pytest.mark.parametrize(
    ("sizes", "admitted"),
    [
        ([MAX_POLICY_SOURCE_BYTES] * 4, True),
        ([MAX_POLICY_SOURCE_BYTES] * 4 + [1], False),
    ],
)
def test_aggregate_policy_bytes_enforce_inclusive_limit(
    tmp_path: Path,
    sizes: list[int],
    admitted: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = _build_policy_chain(workspace, sizes)
    policy = _policy(workspace)

    if admitted:
        assert policy.admit_existing(target).kind == "file"
    else:
        _admit_error(policy, target, "repository_policy_invalid")


def test_absent_gitignore_is_normal_and_safe_internal_symlink_rules_apply(
    tmp_path: Path,
) -> None:
    absent_workspace = tmp_path / "absent"
    absent_workspace.mkdir()
    (absent_workspace / "target.txt").write_text("target", encoding="utf-8")
    assert _policy(absent_workspace).admit_existing("target.txt").kind == "file"

    linked_workspace = tmp_path / "linked"
    linked_workspace.mkdir()
    source = linked_workspace / "safe-policy"
    source.write_text("target.txt\n", encoding="utf-8")
    (linked_workspace / ".gitignore").symlink_to(source)
    (linked_workspace / "target.txt").write_text("target", encoding="utf-8")
    _admit_error(_policy(linked_workspace), "target.txt", "repository_path_ignored")


def test_policy_source_retarget_before_read_fails_without_accepting_replacement_rules(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_a = workspace / "policy-a"
    source_b = workspace / "policy-b"
    source_a.write_text("unrelated\n", encoding="utf-8")
    source_b.write_text("target.txt\n", encoding="utf-8")
    candidate = workspace / ".gitignore"
    candidate.symlink_to(source_a)
    (workspace / "target.txt").write_text("target", encoding="utf-8")
    traversal = _policy(workspace)._new_admission()
    mutated = False
    read_calls = 0

    def retarget_source(
        self: RepositoryReadPolicy,
        stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated
        if not mutated and stage == "before_policy_read" and owner_label == ".":
            candidate.unlink()
            candidate.symlink_to(source_b)
            mutated = True

    def track_policy_read(source: Path) -> bytes:
        nonlocal read_calls
        del source
        read_calls += 1
        return b""

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", retarget_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_policy_read),
    )

    _admit_error(traversal, "target.txt", "repository_policy_invalid")  # type: ignore[arg-type]
    assert mutated
    assert read_calls == 0
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0


@pytest.mark.parametrize("replacement", ["missing", "directory", "oversized"])
def test_pre_read_policy_rejection_does_not_read_cache_or_charge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    candidate = workspace / ".gitignore"
    candidate.write_text("unrelated\n", encoding="utf-8")
    (workspace / "target.txt").write_text("target", encoding="utf-8")
    policy = _policy(workspace)
    traversal = policy._new_admission()
    read_calls = 0
    mutated = False

    def replace_policy(
        self: RepositoryReadPolicy,
        stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated
        if mutated or stage != "before_policy_read" or owner_label != ".":
            return
        if replacement == "missing":
            candidate.unlink()
        elif replacement == "directory":
            candidate.unlink()
            candidate.mkdir()
        else:
            candidate.write_bytes(b"x" * (MAX_POLICY_SOURCE_BYTES + 1))
        mutated = True

    def track_policy_read(source: Path) -> bytes:
        nonlocal read_calls
        del source
        read_calls += 1
        return b""

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", replace_policy)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_policy_read),
    )

    _admit_error(traversal, "target.txt", "repository_policy_invalid")  # type: ignore[arg-type]
    assert mutated
    assert read_calls == 0
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0


def test_stable_policy_cache_hit_rechecks_owner_and_source_without_recharge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("unrelated\n", encoding="utf-8")
    (workspace / "first.txt").write_text("first", encoding="utf-8")
    (workspace / "second.txt").write_text("second", encoding="utf-8")
    policy = _policy(workspace)
    traversal = policy._new_admission()
    original_require_owner = RepositoryReadPolicy._require_same_owner
    original_resolve_source = RepositoryReadPolicy._resolve_policy_source
    original_read = RepositoryReadPolicy._read_policy_bytes
    owner_checks = 0
    source_resolutions = 0
    content_reads = 0

    def track_owner(self: RepositoryReadPolicy, owner: object) -> None:
        nonlocal owner_checks
        owner_checks += 1
        original_require_owner(self, owner)  # type: ignore[arg-type]

    def track_source(self: RepositoryReadPolicy, label: str) -> object:
        nonlocal source_resolutions
        source_resolutions += 1
        return original_resolve_source(self, label)

    def track_read(source: Path) -> bytes:
        nonlocal content_reads
        content_reads += 1
        return original_read(source)

    monkeypatch.setattr(RepositoryReadPolicy, "_require_same_owner", track_owner)
    monkeypatch.setattr(RepositoryReadPolicy, "_resolve_policy_source", track_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )

    assert traversal.admit_existing("first.txt").kind == "file"
    cached_rules = dict(traversal.state.cache)
    loaded_bytes = traversal.state.loaded_bytes
    owner_checks = source_resolutions = content_reads = 0

    assert traversal.admit_existing("second.txt").kind == "file"
    assert owner_checks == 2
    assert source_resolutions == 2
    assert content_reads == 0
    assert traversal.state.cache == cached_rules
    assert traversal.state.loaded_bytes == loaded_bytes


def test_policy_source_cache_reuses_one_canonical_source_across_many_owner_scopes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "shared-policy"
    source.write_text("unrelated-name\n", encoding="utf-8")
    owner = workspace
    parts: list[str] = []
    for index in range(MAX_POLICY_SOURCES + 1):
        (owner / ".gitignore").symlink_to(source)
        name = f"level-{index}"
        parts.append(name)
        owner = owner / name
        owner.mkdir()
    (owner / "target.txt").write_text("target", encoding="utf-8")

    result = _policy(workspace).admit_existing("/".join([*parts, "target.txt"]))

    assert result.kind == "file"


def test_internal_traversal_decision_shares_policy_source_union_budget(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text("# root\n", encoding="utf-8")

    targets: list[str] = []
    for branch in ("left", "right"):
        owner = workspace
        parts: list[str] = []
        for depth in range(8):
            component = f"{branch}-{depth}"
            parts.append(component)
            owner = owner / component
            owner.mkdir()
            (owner / ".gitignore").write_text("# branch\n", encoding="utf-8")
        (owner / "target.txt").write_text("target", encoding="utf-8")
        targets.append("/".join([*parts, "target.txt"]))

    policy = _policy(workspace)
    assert policy.admit_existing(targets[0]).kind == "file"
    assert policy.admit_existing(targets[1]).kind == "file"

    traversal = policy._new_admission()
    assert traversal.admit_existing(targets[0]).kind == "file"
    _admit_error(traversal, targets[1], "repository_policy_invalid")  # type: ignore[arg-type]


def test_match_work_cap_is_cumulative_across_scopes_views_and_cache_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    nested = workspace / "nested"
    nested.mkdir(parents=True)
    root_pattern_slots = 8_192
    nested_pattern_slots = 4_096
    (workspace / ".gitignore").write_text(
        "z\n#\n" * (root_pattern_slots // 2),
        encoding="utf-8",
    )
    (nested / ".gitignore").write_text(
        "y\n#\n" * (nested_pattern_slots // 2),
        encoding="utf-8",
    )
    (nested / "target.txt").write_text("target", encoding="utf-8")
    traversal = _policy(workspace)._new_admission()
    original_read = RepositoryReadPolicy._read_policy_bytes
    original_check = repository_access._check_policy
    content_reads = 0
    matcher_entries: list[int] = []

    def track_read(source: Path) -> bytes:
        nonlocal content_reads
        content_reads += 1
        return original_read(source)

    def track_check(rules: GitIgnoreSpec, label: str) -> bool | None:
        matcher_entries.append(traversal.state.match_work)
        return original_check(rules, label)

    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )
    monkeypatch.setattr(repository_access, "_check_policy", track_check)

    assert traversal.admit_existing("nested/target.txt").kind == "file"
    assert traversal.state.match_work == MAX_POLICY_MATCH_WORK
    assert len(matcher_entries) == 10
    assert matcher_entries[-1] == MAX_POLICY_MATCH_WORK
    assert content_reads == 2
    cached_rules = dict(traversal.state.cache)
    loaded_bytes = traversal.state.loaded_bytes
    matcher_calls = len(matcher_entries)

    _admit_error(
        traversal,
        "nested/target.txt",
        "repository_policy_invalid",
    )  # type: ignore[arg-type]
    assert traversal.state.match_work == MAX_POLICY_MATCH_WORK
    assert traversal.state.cache == cached_rules
    assert traversal.state.loaded_bytes == loaded_bytes
    assert content_reads == 2
    assert len(matcher_entries) == matcher_calls


@pytest.mark.parametrize("stage", ["before_policy_probe", "before_policy_read"])
def test_lexical_policy_owner_retarget_fails_at_each_stability_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    workspace = tmp_path / "workspace"
    owner_a = workspace / "owner-a"
    owner_b = workspace / "owner-b"
    owner_a.mkdir(parents=True)
    owner_b.mkdir()
    (owner_a / ".gitignore").write_text("unrelated\n", encoding="utf-8")
    (owner_b / ".gitignore").write_text("file.txt\n", encoding="utf-8")
    (owner_a / "file.txt").write_text("a", encoding="utf-8")
    (owner_b / "file.txt").write_text("b", encoding="utf-8")
    alias = workspace / "owner-link"
    alias.symlink_to(owner_a, target_is_directory=True)
    traversal = _policy(workspace)._new_admission()
    original_candidate = RepositoryReadPolicy._policy_candidate_path
    original_probe = RepositoryReadPolicy._policy_leaf_is_present
    original_resolve_source = RepositoryReadPolicy._resolve_policy_source
    original_read = RepositoryReadPolicy._read_policy_bytes
    mutated = False
    replacement_work = {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}

    def retarget_owner(
        self: RepositoryReadPolicy,
        observed_stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated
        if not mutated and observed_stage == stage and owner_label == "owner-link":
            alias.unlink()
            alias.symlink_to(owner_b, target_is_directory=True)
            mutated = True

    def track_candidate(self: RepositoryReadPolicy, owner: tuple[str, ...]) -> Path:
        if mutated:
            replacement_work["candidate"] += 1
        return original_candidate(self, owner)

    def track_probe(candidate: Path) -> bool:
        if mutated:
            replacement_work["probe"] += 1
        return original_probe(candidate)

    def track_source(self: RepositoryReadPolicy, label: str) -> object:
        if mutated:
            replacement_work["resolve"] += 1
        return original_resolve_source(self, label)

    def track_read(source: Path) -> bytes:
        if mutated:
            replacement_work["read"] += 1
        return original_read(source)

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", retarget_owner)
    monkeypatch.setattr(RepositoryReadPolicy, "_policy_candidate_path", track_candidate)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_policy_leaf_is_present",
        staticmethod(track_probe),
    )
    monkeypatch.setattr(RepositoryReadPolicy, "_resolve_policy_source", track_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )

    _admit_error(
        traversal,
        "owner-link/file.txt",
        "repository_policy_invalid",
    )  # type: ignore[arg-type]
    assert mutated
    assert replacement_work == {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize("stage", ["before_policy_probe", "before_policy_read"])
def test_canonical_policy_owner_retarget_fails_at_each_stability_seam(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    workspace = tmp_path / "workspace"
    canonical = workspace / "canonical"
    replacement = workspace / "replacement"
    canonical.mkdir(parents=True)
    replacement.mkdir()
    (canonical / ".gitignore").write_text("unrelated\n", encoding="utf-8")
    (replacement / ".gitignore").write_text("file.txt\n", encoding="utf-8")
    (canonical / "file.txt").write_text("a", encoding="utf-8")
    (replacement / "file.txt").write_text("b", encoding="utf-8")
    alias = workspace / "file-alias"
    alias.symlink_to(canonical / "file.txt")
    preserved = workspace / "preserved-canonical"
    traversal = _policy(workspace)._new_admission()
    original_candidate = RepositoryReadPolicy._policy_candidate_path
    original_probe = RepositoryReadPolicy._policy_leaf_is_present
    original_resolve_source = RepositoryReadPolicy._resolve_policy_source
    original_read = RepositoryReadPolicy._read_policy_bytes
    mutated = False
    replacement_work = {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}

    def retarget_owner(
        self: RepositoryReadPolicy,
        observed_stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated
        if not mutated and observed_stage == stage and owner_label == "canonical":
            canonical.rename(preserved)
            canonical.symlink_to(replacement, target_is_directory=True)
            mutated = True

    def track_candidate(self: RepositoryReadPolicy, owner: tuple[str, ...]) -> Path:
        if mutated:
            replacement_work["candidate"] += 1
        return original_candidate(self, owner)

    def track_probe(candidate: Path) -> bool:
        if mutated:
            replacement_work["probe"] += 1
        return original_probe(candidate)

    def track_source(self: RepositoryReadPolicy, label: str) -> object:
        if mutated:
            replacement_work["resolve"] += 1
        return original_resolve_source(self, label)

    def track_read(source: Path) -> bytes:
        if mutated:
            replacement_work["read"] += 1
        return original_read(source)

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", retarget_owner)
    monkeypatch.setattr(RepositoryReadPolicy, "_policy_candidate_path", track_candidate)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_policy_leaf_is_present",
        staticmethod(track_probe),
    )
    monkeypatch.setattr(RepositoryReadPolicy, "_resolve_policy_source", track_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )

    _admit_error(traversal, "file-alias", "repository_policy_invalid")  # type: ignore[arg-type]
    assert mutated
    assert replacement_work == {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize("stage", ["before_policy_probe", "before_policy_read"])
def test_same_label_policy_owner_replacement_fails_by_directory_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    workspace = tmp_path / "workspace"
    owner = workspace / "owner"
    owner.mkdir(parents=True)
    (owner / ".gitignore").write_text("file.txt\n", encoding="utf-8")
    (owner / "file.txt").write_text("original", encoding="utf-8")
    retained = workspace / "retained-owner"
    traversal = _policy(workspace)._new_admission()
    original_candidate = RepositoryReadPolicy._policy_candidate_path
    original_probe = RepositoryReadPolicy._policy_leaf_is_present
    original_resolve_source = RepositoryReadPolicy._resolve_policy_source
    original_read = RepositoryReadPolicy._read_policy_bytes
    mutated = False
    replacement_work = {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}

    def replace_owner(
        self: RepositoryReadPolicy,
        observed_stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated
        if not mutated and observed_stage == stage and owner_label == "owner":
            owner.rename(retained)
            owner.mkdir()
            (owner / ".gitignore").write_text("unrelated\n", encoding="utf-8")
            (owner / "file.txt").write_text("replacement", encoding="utf-8")
            mutated = True

    def track_candidate(self: RepositoryReadPolicy, components: tuple[str, ...]) -> Path:
        if mutated:
            replacement_work["candidate"] += 1
        return original_candidate(self, components)

    def track_probe(candidate: Path) -> bool:
        if mutated:
            replacement_work["probe"] += 1
        return original_probe(candidate)

    def track_source(self: RepositoryReadPolicy, label: str) -> object:
        if mutated:
            replacement_work["resolve"] += 1
        return original_resolve_source(self, label)

    def track_read(source: Path) -> bytes:
        if mutated:
            replacement_work["read"] += 1
        return original_read(source)

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", replace_owner)
    monkeypatch.setattr(RepositoryReadPolicy, "_policy_candidate_path", track_candidate)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_policy_leaf_is_present",
        staticmethod(track_probe),
    )
    monkeypatch.setattr(RepositoryReadPolicy, "_resolve_policy_source", track_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )

    _admit_error(traversal, "owner/file.txt", "repository_policy_invalid")  # type: ignore[arg-type]
    assert mutated
    assert replacement_work == {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0


@pytest.mark.parametrize("stage", ["before_policy_probe", "before_policy_read"])
def test_canonical_same_label_owner_replacement_fails_by_directory_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    workspace = tmp_path / "workspace"
    canonical = workspace / "canonical"
    canonical.mkdir(parents=True)
    (canonical / ".gitignore").write_text("file.txt\n", encoding="utf-8")
    (canonical / "file.txt").write_text("original", encoding="utf-8")
    alias = workspace / "file-alias"
    alias.symlink_to(canonical / "file.txt")
    retained = workspace / "retained-canonical"
    original_stat = canonical.stat()
    original_identity = (original_stat.st_dev, original_stat.st_ino)
    replacement_identity: tuple[int, int] | None = None
    traversal = _policy(workspace)._new_admission()
    original_candidate = RepositoryReadPolicy._policy_candidate_path
    original_probe = RepositoryReadPolicy._policy_leaf_is_present
    original_resolve_source = RepositoryReadPolicy._resolve_policy_source
    original_read = RepositoryReadPolicy._read_policy_bytes
    mutated = False
    replacement_work = {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}

    def replace_owner(
        self: RepositoryReadPolicy,
        observed_stage: str,
        owner_label: str,
    ) -> None:
        nonlocal mutated, replacement_identity
        if not mutated and observed_stage == stage and owner_label == "canonical":
            canonical.rename(retained)
            canonical.mkdir()
            (canonical / ".gitignore").write_text("unrelated\n", encoding="utf-8")
            (canonical / "file.txt").write_text("replacement", encoding="utf-8")
            replacement_stat = canonical.stat()
            replacement_identity = (replacement_stat.st_dev, replacement_stat.st_ino)
            mutated = True

    def track_candidate(self: RepositoryReadPolicy, components: tuple[str, ...]) -> Path:
        if mutated:
            replacement_work["candidate"] += 1
        return original_candidate(self, components)

    def track_probe(candidate: Path) -> bool:
        if mutated:
            replacement_work["probe"] += 1
        return original_probe(candidate)

    def track_source(self: RepositoryReadPolicy, label: str) -> object:
        if mutated:
            replacement_work["resolve"] += 1
        return original_resolve_source(self, label)

    def track_read(source: Path) -> bytes:
        if mutated:
            replacement_work["read"] += 1
        return original_read(source)

    monkeypatch.setattr(RepositoryReadPolicy, "_policy_checkpoint", replace_owner)
    monkeypatch.setattr(RepositoryReadPolicy, "_policy_candidate_path", track_candidate)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_policy_leaf_is_present",
        staticmethod(track_probe),
    )
    monkeypatch.setattr(RepositoryReadPolicy, "_resolve_policy_source", track_source)
    monkeypatch.setattr(
        RepositoryReadPolicy,
        "_read_policy_bytes",
        staticmethod(track_read),
    )

    _admit_error(traversal, "file-alias", "repository_policy_invalid")  # type: ignore[arg-type]
    assert mutated
    assert replacement_identity is not None
    assert replacement_identity != original_identity
    assert replacement_work == {"candidate": 0, "probe": 0, "resolve": 0, "read": 0}
    assert traversal.state.cache == {}
    assert traversal.state.loaded_bytes == 0
    assert traversal.state.match_work == 0
