"""Canonical workspace containment for local repository paths.

The values in this module are pathname snapshots.  They deliberately do not authorize later
filesystem access: a caller must resolve a path again immediately before using it.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

type WorkspaceBoundaryErrorCode = Literal[
    "invalid_workspace_root",
    "stale_workspace_root",
    "invalid_workspace_path",
    "workspace_path_not_found",
    "workspace_path_outside",
]

_ERROR_MESSAGES: dict[WorkspaceBoundaryErrorCode, str] = {
    "invalid_workspace_root": "Workspace root must be an existing directory.",
    "stale_workspace_root": "The selected workspace is no longer available.",
    "invalid_workspace_path": "Workspace path must be a non-empty relative path.",
    "workspace_path_not_found": "Workspace path does not exist.",
    "workspace_path_outside": "Workspace path is outside the selected workspace.",
}

_MAX_RAW_PATH_BYTES = 4_095
_MAX_COMPONENTS = 256
_MAX_COMPONENT_BYTES = 255


class WorkspaceBoundaryError(ValueError):
    """Report one bounded workspace failure without exposing path or operating-system details.

    Attributes:
        code: Stable machine-readable classification paired with the exception's fixed message.
    """

    __slots__ = ("code",)

    def __init__(self, code: WorkspaceBoundaryErrorCode) -> None:
        """Initialize the fixed message for ``code``.

        Args:
            code: One of the five closed workspace-boundary failure codes.
        """
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code


def _invalid_workspace_path() -> WorkspaceBoundaryError:
    """Create the shared lexical-admission failure."""
    return WorkspaceBoundaryError("invalid_workspace_path")


def normalize_workspace_relative_path(value: str) -> tuple[str, ...]:
    """Validate and normalize one model-facing workspace-relative Linux path.

    This is the sole pure lexical owner for workspace-relative paths.  It counts the complete raw
    spelling before normalizing repeated separators and ``.`` components.  Backslash is an
    ordinary filename character, and Unicode is neither normalized nor case-folded.

    Args:
        value: An exact built-in string containing a non-empty relative Linux path.

    Returns:
        The normalized non-``.`` components.  An empty tuple represents the canonical root label
        ``.``.

    Raises:
        WorkspaceBoundaryError: If the value is not an exact string, is not strict UTF-8, is
            absolute, contains NUL or ``..``, or exceeds a path work budget.
    """
    if type(value) is not str or not value or len(value) > _MAX_RAW_PATH_BYTES:
        raise _invalid_workspace_path()

    try:
        encoded = value.encode("utf-8", errors="strict")
        round_tripped = encoded.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise _invalid_workspace_path() from error

    if (
        len(encoded) > _MAX_RAW_PATH_BYTES
        or round_tripped != value
        or "\x00" in value
        or value.startswith("/")
    ):
        raise _invalid_workspace_path()

    components: list[str] = []
    encoded_components = encoded.split(b"/")
    for component, component_bytes in zip(value.split("/"), encoded_components, strict=True):
        if not component or component == ".":
            continue
        if component == ".." or len(component_bytes) > _MAX_COMPONENT_BYTES:
            raise _invalid_workspace_path()
        components.append(component)
        if len(components) > _MAX_COMPONENTS:
            raise _invalid_workspace_path()

    return tuple(components)


@dataclass(frozen=True, slots=True)
class ResolvedWorkspacePath:
    """An immutable, best-effort containment snapshot for one existing workspace target.

    ``absolute_path`` is local-only and omitted from the representation.  ``relative_path`` is the
    canonical model-safe POSIX label and uses ``.`` for the workspace root.

    Attributes:
        absolute_path: Canonical absolute target for local filesystem work.
        relative_path: Canonical workspace-relative POSIX target label.
    """

    absolute_path: Path = field(repr=False)
    relative_path: PurePosixPath


@dataclass(frozen=True, slots=True, init=False)
class WorkspaceBoundary:
    """Own one canonical workspace root and resolve contained existing paths.

    Construct instances only with :meth:`from_path`.  The captured device and inode narrow
    ordinary root-replacement races but are not a persistent filesystem capability.  The root is
    rechecked on both sides of target resolution; later callers must still resolve again
    immediately before access.

    Attributes:
        root: Canonical local workspace directory.  It is excluded from the representation.
    """

    root: Path = field(repr=False)
    _root_device: int = field(repr=False)
    _root_inode: int = field(repr=False)

    def __init__(self) -> None:
        """Reject direct construction so filesystem validation cannot be bypassed.

        Raises:
            TypeError: Always; use :meth:`from_path` instead.
        """
        raise TypeError("WorkspaceBoundary must be constructed with from_path().")

    @classmethod
    def from_path(cls, value: str | os.PathLike[str]) -> WorkspaceBoundary:
        """Capture one canonical existing directory as the workspace root.

        A leading user marker in the explicitly supplied local root is expanded before strict
        resolution.  The originally supplied alias is not retained.

        Args:
            value: String or string-valued path-like local workspace root.

        Returns:
            An immutable boundary containing the canonical root and its device/inode identity.

        Raises:
            WorkspaceBoundaryError: With ``invalid_workspace_root`` when the value cannot resolve
                to an accessible directory.
        """
        try:
            canonical_root = Path(value).expanduser().resolve(strict=True)
            root_stat = canonical_root.stat()
        except Exception as error:
            raise WorkspaceBoundaryError("invalid_workspace_root") from error

        if not stat.S_ISDIR(root_stat.st_mode):
            raise WorkspaceBoundaryError("invalid_workspace_root")

        boundary = object.__new__(cls)
        object.__setattr__(boundary, "root", canonical_root)
        object.__setattr__(boundary, "_root_device", root_stat.st_dev)
        object.__setattr__(boundary, "_root_inode", root_stat.st_ino)
        return boundary

    def resolve_existing(
        self,
        value: str | os.PathLike[str],
    ) -> ResolvedWorkspacePath:
        """Resolve one existing relative target and return its contained canonical snapshot.

        Symlinks are followed.  Internal aliases report the canonical target-relative label, while
        any established escape is rejected.  Root identity is checked before and after the target
        attempt, including a failed attempt, so observed root staleness wins over a target error.

        Args:
            value: Exact string or string-valued path-like relative Linux path.

        Returns:
            The canonical absolute target and canonical workspace-relative POSIX label.

        Raises:
            WorkspaceBoundaryError: With one fixed invalid, stale, missing, or outside failure.
        """
        path_value = self._path_like_string(value)
        components = normalize_workspace_relative_path(path_value)

        self._assert_current_root()
        target: Path | None = None
        target_error: WorkspaceBoundaryError | None = None
        try:
            target = self._resolve_target(components)
        except WorkspaceBoundaryError as error:
            target_error = error

        self._assert_current_root()
        if target_error is not None:
            raise target_error
        if target is None:  # pragma: no cover - defensive invariant
            raise WorkspaceBoundaryError("workspace_path_not_found")

        try:
            relative_target = target.relative_to(self.root)
        except ValueError as error:  # pragma: no cover - _resolve_target already checks this
            raise WorkspaceBoundaryError("workspace_path_outside") from error

        label = "." if not relative_target.parts else relative_target.as_posix()
        canonical_components = normalize_workspace_relative_path(label)
        canonical_label = "." if not canonical_components else "/".join(canonical_components)
        if canonical_label != label:
            raise _invalid_workspace_path()

        return ResolvedWorkspacePath(
            absolute_path=target,
            relative_path=PurePosixPath(canonical_label),
        )

    @staticmethod
    def _path_like_string(value: str | os.PathLike[str]) -> str:
        """Obtain an exact string from the local path-like API without filesystem access."""
        try:
            path_value = os.fspath(value)
        except Exception as error:
            raise _invalid_workspace_path() from error
        if type(path_value) is not str:
            raise _invalid_workspace_path()
        return path_value

    def _assert_current_root(self) -> None:
        """Require the captured canonical root path and identity to remain observable."""
        try:
            observed_root = self.root.resolve(strict=True)
            observed_stat = observed_root.stat()
        except (OSError, RuntimeError, ValueError) as error:
            raise WorkspaceBoundaryError("stale_workspace_root") from error

        if (
            observed_root != self.root
            or not stat.S_ISDIR(observed_stat.st_mode)
            or observed_stat.st_dev != self._root_device
            or observed_stat.st_ino != self._root_inode
        ):
            raise WorkspaceBoundaryError("stale_workspace_root")

    def _resolve_target(self, components: tuple[str, ...]) -> Path:
        """Strictly resolve each target prefix and stop at the first established escape.

        Resolving the complete candidate before checking containment would let a path traverse an
        outside directory and follow a later symlink back into the workspace.  Advancing only from
        an already-contained canonical prefix prevents later components from masking that escape.
        """
        target = self.root
        for component in components:
            candidate = target / component
            try:
                resolved_candidate = candidate.resolve(strict=True)
            except (OSError, RuntimeError, ValueError) as error:
                self._raise_resolution_failure(candidate, error)

            if not resolved_candidate.is_relative_to(self.root):
                raise WorkspaceBoundaryError("workspace_path_outside")
            target = resolved_candidate
        return target

    def _raise_resolution_failure(
        self,
        candidate: Path,
        original_error: Exception,
    ) -> None:
        """Classify an established dangling escape before mapping an unresolved target.

        The admitted candidate has at most 256 components and 4,095 raw bytes.  A non-strict
        resolution is therefore a bounded fallback that can expose the direction of a dangling
        symlink without claiming the target exists.  Symlink loops and other unresolved states do
        not establish an escape and retain the fixed not-found result.
        """
        try:
            unresolved_target = candidate.resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            unresolved_target = None
        if unresolved_target is not None and not unresolved_target.is_relative_to(self.root):
            raise WorkspaceBoundaryError("workspace_path_outside") from original_error
        raise WorkspaceBoundaryError("workspace_path_not_found") from original_error


__all__ = [
    "ResolvedWorkspacePath",
    "WorkspaceBoundary",
    "WorkspaceBoundaryError",
    "normalize_workspace_relative_path",
]
