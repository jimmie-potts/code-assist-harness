from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path, PurePosixPath

import pytest

import code_assist_harness.workspace as workspace_module
from code_assist_harness.workspace import (
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_workspace_relative_path,
)

ERROR_MESSAGES = {
    "invalid_workspace_root": "Workspace root must be an existing directory.",
    "stale_workspace_root": "The selected workspace is no longer available.",
    "invalid_workspace_path": "Workspace path must be a non-empty relative path.",
    "workspace_path_not_found": "Workspace path does not exist.",
    "workspace_path_outside": "Workspace path is outside the selected workspace.",
}


class _TextSubclass(str):
    pass


class _BytesPathLike:
    def __fspath__(self) -> bytes:
        return b"private-bytes-path"


class _SubclassPathLike:
    def __fspath__(self) -> str:
        return _TextSubclass(".")


class _FailingPathLike:
    def __fspath__(self) -> str:
        raise LookupError("private path-like failure")


def _assert_error(error: WorkspaceBoundaryError, code: str) -> None:
    assert error.code == code
    assert str(error) == ERROR_MESSAGES[code]
    assert error.args == (ERROR_MESSAGES[code],)


@pytest.mark.parametrize(("code", "message"), ERROR_MESSAGES.items())
def test_workspace_error_surface_is_closed_and_fixed(code: str, message: str) -> None:
    error = WorkspaceBoundaryError(code)  # type: ignore[arg-type]

    assert error.code == code
    assert str(error) == message
    assert error.args == (message,)


def test_normalize_workspace_relative_path_normalizes_only_linux_dot_and_separators() -> None:
    assert normalize_workspace_relative_path(".") == ()
    assert normalize_workspace_relative_path("././") == ()
    assert normalize_workspace_relative_path("./docs//./guide.md/") == (
        "docs",
        "guide.md",
    )
    assert normalize_workspace_relative_path(r"docs\guide.md") == (r"docs\guide.md",)


def test_normalize_workspace_relative_path_preserves_case_and_unicode_spelling() -> None:
    composed = "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
    decomposed = "cafe\N{COMBINING ACUTE ACCENT}"

    assert normalize_workspace_relative_path(composed) == (composed,)
    assert normalize_workspace_relative_path(decomposed) == (decomposed,)
    assert normalize_workspace_relative_path("Readme") != normalize_workspace_relative_path(
        "README"
    )


def test_normalize_workspace_relative_path_enforces_complete_raw_byte_endpoints() -> None:
    names_255 = ["a" * 255] * 16
    at_4_095 = "/".join(names_255)
    at_4_094 = "/".join([*names_255[:-1], "a" * 254])
    at_4_096 = f"{at_4_095}/"

    assert len(at_4_094.encode()) == 4_094
    assert len(at_4_095.encode()) == 4_095
    assert len(at_4_096.encode()) == 4_096
    assert normalize_workspace_relative_path(at_4_094)[-1] == "a" * 254
    assert normalize_workspace_relative_path(at_4_095) == tuple(names_255)
    with pytest.raises(WorkspaceBoundaryError) as caught:
        normalize_workspace_relative_path(at_4_096)
    _assert_error(caught.value, "invalid_workspace_path")


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("a" * 254, True),
        ("a" * 255, True),
        ("a" * 256, False),
        ("é" * 127, True),
        ("é" * 127 + "a", True),
        ("é" * 128, False),
    ],
)
def test_normalize_workspace_relative_path_counts_component_utf8_bytes(
    value: str,
    accepted: bool,
) -> None:
    if accepted:
        assert normalize_workspace_relative_path(value) == (value,)
        return

    with pytest.raises(WorkspaceBoundaryError) as caught:
        normalize_workspace_relative_path(value)
    _assert_error(caught.value, "invalid_workspace_path")


@pytest.mark.parametrize(("count", "accepted"), [(255, True), (256, True), (257, False)])
def test_normalize_workspace_relative_path_enforces_component_count_endpoints(
    count: int,
    accepted: bool,
) -> None:
    value = "/".join(["a"] * count)
    if accepted:
        assert len(normalize_workspace_relative_path(value)) == count
        return

    with pytest.raises(WorkspaceBoundaryError) as caught:
        normalize_workspace_relative_path(value)
    _assert_error(caught.value, "invalid_workspace_path")


@pytest.mark.parametrize(
    "value",
    [
        "",
        b"bytes",
        Path("path-object"),
        _TextSubclass("subclass"),
        "\ud800",
        "contains\x00nul",
        "/absolute",
        "..",
        "docs/../outside",
        "a" * 256,
        "/".join(["a"] * 257),
    ],
)
def test_normalize_workspace_relative_path_rejects_invalid_values(value: object) -> None:
    with pytest.raises(WorkspaceBoundaryError) as caught:
        normalize_workspace_relative_path(value)  # type: ignore[arg-type]
    _assert_error(caught.value, "invalid_workspace_path")


def test_boundary_construction_canonicalizes_alias_and_captures_identity(tmp_path: Path) -> None:
    workspace = tmp_path / "private-workspace-root"
    workspace.mkdir()
    alias = tmp_path / "private-workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)

    boundary = WorkspaceBoundary.from_path(alias)
    direct_boundary = WorkspaceBoundary.from_path(workspace)

    assert boundary.root == workspace.resolve()
    assert boundary == direct_boundary
    assert hash(boundary) == hash(direct_boundary)
    assert str(tmp_path) not in repr(boundary)
    assert "private-workspace" not in repr(boundary)


def test_boundary_construction_expands_leading_user_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_home = tmp_path / "private-home"
    workspace = local_home / "repository"
    workspace.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(local_home))

    assert WorkspaceBoundary.from_path("~/repository").root == workspace.resolve()


@pytest.mark.parametrize("kind", ["missing", "file", "bytes-path-like", "failing-path-like"])
def test_boundary_construction_maps_invalid_roots_without_leaking_paths(
    tmp_path: Path,
    kind: str,
) -> None:
    private_name = "private-invalid-workspace"
    candidate: object = tmp_path / private_name
    if kind == "file":
        assert isinstance(candidate, Path)
        candidate.write_text("not a directory", encoding="utf-8")
    elif kind == "bytes-path-like":
        candidate = _BytesPathLike()
    elif kind == "failing-path-like":
        candidate = _FailingPathLike()

    with pytest.raises(WorkspaceBoundaryError) as caught:
        WorkspaceBoundary.from_path(candidate)  # type: ignore[arg-type]

    _assert_error(caught.value, "invalid_workspace_root")
    assert private_name not in repr(caught.value)
    assert str(tmp_path) not in repr(caught.value)


def test_workspace_boundary_rejects_direct_construction_and_is_frozen(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="from_path"):
        WorkspaceBoundary()

    boundary = WorkspaceBoundary.from_path(tmp_path)
    with pytest.raises(TypeError):
        WorkspaceBoundary(  # type: ignore[call-arg]
            root=tmp_path,
            _root_device=tmp_path.stat().st_dev,
            _root_inode=tmp_path.stat().st_ino,
        )
    with pytest.raises(TypeError):
        replace(boundary)
    with pytest.raises(FrozenInstanceError):
        boundary.root = tmp_path / "replacement"  # type: ignore[misc]


def test_resolve_existing_reports_root_and_normal_descendants(tmp_path: Path) -> None:
    workspace = tmp_path / "private-workspace"
    workspace.mkdir()
    docs = workspace / "docs"
    docs.mkdir()
    guide = docs / "guide-😀.md"
    guide.write_text("guide", encoding="utf-8")
    boundary = WorkspaceBoundary.from_path(workspace)

    root_result = boundary.resolve_existing(Path("."))
    guide_result = boundary.resolve_existing("./docs//guide-😀.md")

    assert root_result.absolute_path == workspace.resolve()
    assert root_result.relative_path == PurePosixPath(".")
    assert guide_result.absolute_path == guide.resolve()
    assert guide_result.relative_path == PurePosixPath("docs/guide-😀.md")
    assert str(tmp_path) not in repr(root_result)
    assert str(tmp_path) not in repr(guide_result)


def test_resolve_existing_preserves_distinct_unicode_spellings(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    composed = "caf\N{LATIN SMALL LETTER E WITH ACUTE}.md"
    decomposed = "cafe\N{COMBINING ACUTE ACCENT}.md"
    (workspace / composed).write_text("composed", encoding="utf-8")
    (workspace / decomposed).write_text("decomposed", encoding="utf-8")
    boundary = WorkspaceBoundary.from_path(workspace)

    assert boundary.resolve_existing(composed).relative_path == PurePosixPath(composed)
    assert boundary.resolve_existing(decomposed).relative_path == PurePosixPath(decomposed)


def test_resolve_existing_reports_internal_symlink_targets_not_aliases(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    canonical = workspace / "canonical"
    canonical.mkdir()
    target_file = canonical / "guide.md"
    target_file.write_text("guide", encoding="utf-8")
    (workspace / "file-alias").symlink_to(target_file)
    (workspace / "dir-alias").symlink_to(canonical, target_is_directory=True)
    boundary = WorkspaceBoundary.from_path(workspace)

    file_result = boundary.resolve_existing("file-alias")
    directory_result = boundary.resolve_existing("dir-alias/guide.md")

    assert file_result.absolute_path == target_file.resolve()
    assert file_result.relative_path == PurePosixPath("canonical/guide.md")
    assert directory_result == file_result


@pytest.mark.parametrize(
    "requested",
    ["file-escape", "dir-escape", "dir-escape/missing", "dangling-outside"],
)
def test_resolve_existing_rejects_established_symlink_escapes(
    tmp_path: Path,
    requested: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "workspace-copy-private"
    outside.mkdir()
    outside_file = outside / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    (workspace / "file-escape").symlink_to(outside_file)
    (workspace / "dir-escape").symlink_to(outside, target_is_directory=True)
    (workspace / "dangling-outside").symlink_to(outside / "missing")
    boundary = WorkspaceBoundary.from_path(workspace)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing(requested)

    _assert_error(caught.value, "workspace_path_outside")
    assert str(tmp_path) not in repr(caught.value)
    assert "workspace-copy-private" not in repr(caught.value)


def test_resolve_existing_rejects_escape_even_when_a_later_symlink_reenters(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    internal_target = workspace / "internal-target"
    internal_target.mkdir()
    (internal_target / "guide.md").write_text("guide", encoding="utf-8")
    outside = tmp_path / "outside-private"
    outside.mkdir()
    (outside / "back-inside").symlink_to(internal_target, target_is_directory=True)
    (workspace / "outside-alias").symlink_to(outside, target_is_directory=True)
    boundary = WorkspaceBoundary.from_path(workspace)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing("outside-alias/back-inside/guide.md")

    _assert_error(caught.value, "workspace_path_outside")
    assert str(tmp_path) not in repr(caught.value)
    assert "outside-private" not in repr(caught.value)


@pytest.mark.parametrize("requested", ["missing", "dangling", "loop-a"])
def test_resolve_existing_maps_unresolved_in_workspace_targets_to_not_found(
    tmp_path: Path,
    requested: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "dangling").symlink_to(workspace / "missing-target")
    (workspace / "loop-a").symlink_to(workspace / "loop-b")
    (workspace / "loop-b").symlink_to(workspace / "loop-a")
    boundary = WorkspaceBoundary.from_path(workspace)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing(requested)

    _assert_error(caught.value, "workspace_path_not_found")
    assert str(tmp_path) not in repr(caught.value)


@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        b"bytes",
        _BytesPathLike(),
        _TextSubclass("."),
        _SubclassPathLike(),
        _FailingPathLike(),
        "\ud800",
        "contains\x00nul",
        "/absolute",
        "docs/../secret",
        "a" * 256,
        "/".join(["a"] * 257),
    ],
)
def test_resolve_existing_rejects_invalid_values_before_path_or_filesystem_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_value: object,
) -> None:
    boundary = WorkspaceBoundary.from_path(tmp_path)

    def unexpected_work(*_args: object, **_kwargs: object) -> None:
        pytest.fail("invalid path reached Path construction or root inspection")

    monkeypatch.setattr(workspace_module, "Path", unexpected_work)
    monkeypatch.setattr(WorkspaceBoundary, "_assert_current_root", unexpected_work)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing(invalid_value)  # type: ignore[arg-type]

    _assert_error(caught.value, "invalid_workspace_path")
    assert "private" not in repr(caught.value)


@pytest.mark.parametrize("mutation", ["remove", "rename", "replace", "redirect", "type-change"])
def test_resolve_existing_rejects_observably_stale_roots(
    tmp_path: Path,
    mutation: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    boundary = WorkspaceBoundary.from_path(workspace)
    retained = tmp_path / "retained-original"

    if mutation == "remove":
        workspace.rmdir()
    elif mutation == "rename":
        workspace.rename(retained)
    elif mutation == "replace":
        original_identity = (workspace.stat().st_dev, workspace.stat().st_ino)
        workspace.rename(retained)
        workspace.mkdir()
        replacement_identity = (workspace.stat().st_dev, workspace.stat().st_ino)
        assert replacement_identity != original_identity
    elif mutation == "redirect":
        workspace.rename(retained)
        workspace.symlink_to(retained, target_is_directory=True)
    else:
        workspace.rmdir()
        workspace.write_text("now a file", encoding="utf-8")

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing(".")

    _assert_error(caught.value, "stale_workspace_root")
    assert str(tmp_path) not in repr(caught.value)


def test_post_resolution_root_snapshot_runs_after_target_failure_and_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    boundary = WorkspaceBoundary.from_path(workspace)
    retained = tmp_path / "retained-original"
    original_check = WorkspaceBoundary._assert_current_root
    check_count = 0

    def replace_before_second_check(current: WorkspaceBoundary) -> None:
        nonlocal check_count
        check_count += 1
        if check_count == 2:
            workspace.rename(retained)
            workspace.mkdir()
        original_check(current)

    monkeypatch.setattr(WorkspaceBoundary, "_assert_current_root", replace_before_second_check)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing("missing")

    assert check_count == 2
    _assert_error(caught.value, "stale_workspace_root")


def test_resolve_existing_revalidates_canonical_label_limits(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    boundary = WorkspaceBoundary.from_path(workspace)
    deep_target = workspace
    for _index in range(257):
        deep_target /= "d"
        deep_target.mkdir()
    (workspace / "short-alias").symlink_to(deep_target, target_is_directory=True)

    with pytest.raises(WorkspaceBoundaryError) as caught:
        boundary.resolve_existing("short-alias")

    _assert_error(caught.value, "invalid_workspace_path")
    assert str(tmp_path) not in repr(caught.value)
