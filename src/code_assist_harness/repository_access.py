"""Harness-owned admission policy for bounded repository reads."""

from __future__ import annotations

import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal, TypeGuard

from pathspec import GitIgnoreSpec
from pathspec.patterns.gitignore.spec import GitIgnoreSpecPattern

from code_assist_harness.workspace import (
    ResolvedWorkspacePath,
    WorkspaceBoundary,
    WorkspaceBoundaryError,
    normalize_workspace_relative_path,
)

type RepositoryAccessErrorCode = Literal[
    "invalid_repository_path",
    "repository_path_not_found",
    "repository_path_unavailable",
    "repository_path_ignored",
    "repository_expected_directory",
    "repository_expected_file",
    "repository_not_text",
    "repository_source_too_large",
    "repository_input_limit",
    "repository_result_limit",
    "repository_policy_invalid",
    "repository_read_failed",
]
type RepositoryPathKind = Literal["file", "directory"]
type _PolicyCheckpoint = Literal["before_policy_probe", "before_policy_read"]

MAX_SOURCE_BYTES = 262_144
MAX_RETURNED_TEXT_BYTES = 65_536
DEFAULT_LIST_ITEMS = 200
MAX_LIST_ITEMS = 500
DEFAULT_RECURSIVE_DEPTH = 4
MAX_RECURSIVE_DEPTH = 8
DEFAULT_SEARCH_MATCHES = 100
MAX_SEARCH_MATCHES = 200
MAX_CONTEXT_ITEMS = 24
MAX_CONTEXT_BYTES = 98_304
MAX_POLICY_SOURCE_BYTES = 65_536
MAX_POLICY_SOURCES = 16
MAX_POLICY_BYTES = 262_144
MAX_POLICY_MATCH_WORK = 65_536
_MAX_POLICY_STARS_PER_SEGMENT = 1
_MAX_POLICY_ACTIVE_GLOBSTARS = 1
_SAFE_POLICY_RANGE_LITERALS = frozenset("_*?.")

_PATH_SYNTAX_MESSAGE = "Repository path syntax is invalid."
_ERROR_MESSAGES: dict[RepositoryAccessErrorCode, str] = {
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

_DENIED_COMPONENTS = frozenset({".git", ".hg", ".svn", ".ssh", ".gnupg", ".aws"})
_DENIED_BASENAMES = frozenset(
    {
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
    }
)
_DOCUMENTATION_ENV_FILES = frozenset({".env.example", ".env.sample", ".env.template"})
_DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


class RepositoryPathSyntaxError(ValueError):
    """Report policy-neutral repository path syntax failure without retaining the input."""

    def __init__(self) -> None:
        """Initialize the one fixed lexical-adapter message."""
        super().__init__(_PATH_SYNTAX_MESSAGE)


class _SemanticPolicyLine(str):
    """Prevent PathSpec from broadly trimming an already Git-normalized line."""

    def rstrip(self, chars: str | None = None) -> str:
        """Preserve semantic trailing characters when PathSpec calls bare ``rstrip``."""
        if chars is None:
            return self
        return super().rstrip(chars)


class RepositoryAccessError(ValueError):
    """Report one fixed repository-access failure without path or policy details.

    Attributes:
        code: Stable machine-readable classification paired with the fixed message.
    """

    __slots__ = ("code",)

    def __init__(self, code: RepositoryAccessErrorCode) -> None:
        """Initialize the fixed message for ``code``.

        Args:
            code: One of the closed repository-access failure codes.
        """
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code


def is_model_facing_text(value: object) -> TypeGuard[str]:
    """Return whether ``value`` is an exact NUL-free strict-UTF-8 round trip.

    This primitive deliberately permits empty text.  Request models own field-specific cardinality
    and error mapping after this shared Unicode-scalar admission.

    Args:
        value: Post-decoding value to inspect without normalization.

    Returns:
        ``True`` only for an exact built-in string that round-trips unchanged.
    """
    if type(value) is not str or "\x00" in value:
        return False
    try:
        encoded = value.encode("utf-8", errors="strict")
        return encoded.decode("utf-8", errors="strict") == value
    except UnicodeError:
        return False


def normalize_repository_path_components(value: str) -> tuple[str, ...]:
    """Delegate repository path syntax and work limits to CAH-024's sole lexical owner.

    Args:
        value: Exact model-facing workspace-relative path string.

    Returns:
        Normalized non-``.`` components; an empty tuple represents the root.

    Raises:
        RepositoryPathSyntaxError: If CAH-024 rejects the path's syntax or work budget.
    """
    try:
        return normalize_workspace_relative_path(value)
    except WorkspaceBoundaryError as error:
        if error.code != "invalid_workspace_path":  # pragma: no cover - lexical API invariant
            raise
    raise RepositoryPathSyntaxError()


def is_hard_denied_path(components: tuple[str, ...]) -> bool:
    """Classify one normalized repository path without resolution, I/O, or rule disclosure.

    Args:
        components: CAH-024-normalized workspace-relative components.

    Returns:
        ``True`` when the reviewed VCS or credential policy denies the path.
    """
    if any(component in _DENIED_COMPONENTS for component in components):
        return True
    if not components:
        return False

    basename = components[-1]
    if basename in _DOCUMENTATION_ENV_FILES:
        return False
    lowered = basename.translate(_ASCII_LOWER)
    return (
        lowered in _DENIED_BASENAMES
        or lowered == ".env"
        or lowered.endswith(".env")
        or lowered.startswith(".env.")
        or lowered.endswith(_DENIED_SUFFIXES)
    )


@dataclass(frozen=True, slots=True)
class AdmittedRepositoryPath:
    """Immutable, model-safe snapshot of one admitted existing repository target.

    Attributes:
        path: Canonical workspace-relative POSIX label, using ``.`` for the root.
        kind: Closed supported target kind; special filesystem objects are never admitted.
        is_symlink: Whether the supplied path's direct leaf was a symlink at final inspection.
    """

    path: str
    kind: RepositoryPathKind
    is_symlink: bool


@dataclass(frozen=True, slots=True)
class _CapturedOwner:
    """Bind one view-relative policy owner to its canonical directory identity."""

    components: tuple[str, ...]
    canonical_path: PurePosixPath
    identity: tuple[int, int] = field(repr=False)


@dataclass(frozen=True, slots=True)
class _PolicySource:
    """Hold one bounded canonical policy-source snapshot without exposing its host path."""

    path: PurePosixPath
    absolute_path: Path = field(repr=False)
    size: int


@dataclass(frozen=True, slots=True)
class _PolicyRules:
    """Keep file-kind and direct-directory views of one parsed policy source."""

    file: GitIgnoreSpec
    directory: GitIgnoreSpec


@dataclass(frozen=True, slots=True)
class _ScopedPolicy:
    """Attach cached rules to the view-relative owner that supplies their match scope."""

    owner: tuple[str, ...]
    rules: _PolicyRules


@dataclass(slots=True)
class _AdmissionState:
    """Own the cache and union budgets for exactly one public admission decision."""

    cache: dict[PurePosixPath, _PolicyRules] = field(default_factory=dict)
    loaded_bytes: int = 0
    match_work: int = 0


@dataclass(slots=True)
class _RepositoryAdmission:
    """Share one policy cache and budget across a direct or traversal decision."""

    policy: RepositoryReadPolicy
    state: _AdmissionState = field(default_factory=_AdmissionState)

    def admit_existing(self, path: str) -> AdmittedRepositoryPath:
        """Admit one path inside this decision's shared policy budget."""
        try:
            return self.policy._admit_existing(path, self.state)
        except RepositoryAccessError as error:
            error.__cause__ = error.__context__ = None
            raise


@dataclass(frozen=True, slots=True)
class RepositoryReadPolicy:
    """Compose lexical denial, nested ignore rules, and canonical workspace containment.

    The supplied boundary identity is retained exactly.  Policy caches are decision-local, so a
    successful call never grants persistent authorization to a later read.

    Attributes:
        boundary: Exact CAH-024 workspace boundary used for every resolution.
    """

    boundary: WorkspaceBoundary = field(repr=False)

    def admit_existing(self, path: str) -> AdmittedRepositoryPath:
        """Admit one existing regular file or directory for a later bounded read.

        Args:
            path: Model-facing workspace-relative path.

        Returns:
            Frozen canonical label, supported kind, and direct-leaf symlink provenance.

        Raises:
            RepositoryAccessError: With one fixed validation, containment, ignore, policy, or
                inspection failure.  No error retains the supplied or host path.
        """
        return self._new_admission().admit_existing(path)

    def _new_admission(self) -> _RepositoryAdmission:
        """Create one internal cache/budget scope for direct or descendant admission."""
        return _RepositoryAdmission(self)

    def _admit_existing(
        self,
        path: str,
        state: _AdmissionState,
    ) -> AdmittedRepositoryPath:
        """Run one path through an existing decision's shared policy state."""
        try:
            lexical_components = normalize_repository_path_components(path)
        except RepositoryPathSyntaxError:
            raise RepositoryAccessError("invalid_repository_path") from None

        if is_hard_denied_path(lexical_components):
            raise RepositoryAccessError("repository_path_unavailable")

        lexical_rules = self._prepare_ignore_view(lexical_components, state)
        ignored_as_file = self._is_ignored(
            lexical_rules,
            lexical_components,
            state,
            is_directory=False,
        )
        ignored_as_directory = self._is_ignored(
            lexical_rules,
            lexical_components,
            state,
            is_directory=True,
        )
        if ignored_as_file and ignored_as_directory:
            raise RepositoryAccessError("repository_path_ignored")

        requested_label = _label(lexical_components)
        resolved = self._resolve_requested(requested_label)
        canonical_components = tuple(resolved.relative_path.parts)
        if is_hard_denied_path(canonical_components):
            raise RepositoryAccessError("repository_path_unavailable")

        canonical_rules = self._prepare_ignore_view(canonical_components, state)
        canonical_ignored_as_file = self._is_ignored(
            canonical_rules,
            canonical_components,
            state,
            is_directory=False,
        )
        canonical_ignored_as_directory = self._is_ignored(
            canonical_rules,
            canonical_components,
            state,
            is_directory=True,
        )
        if canonical_ignored_as_file and canonical_ignored_as_directory:
            raise RepositoryAccessError("repository_path_ignored")

        kind = self._supported_kind(resolved)
        if kind == "directory":
            ignored = ignored_as_directory or canonical_ignored_as_directory
        else:
            ignored = ignored_as_file or canonical_ignored_as_file
        if ignored:
            raise RepositoryAccessError("repository_path_ignored")

        is_symlink = self._finalize_snapshot(
            lexical_components,
            requested_label,
            resolved,
            kind,
        )
        return AdmittedRepositoryPath(
            path=resolved.relative_path.as_posix(),
            kind=kind,
            is_symlink=is_symlink,
        )

    def _prepare_ignore_view(
        self,
        components: tuple[str, ...],
        state: _AdmissionState,
    ) -> list[_ScopedPolicy]:
        """Admit every proper owner ancestor and collect its scoped policy rules."""
        rules: list[_ScopedPolicy] = []
        root_owner = self._capture_owner(())
        root_policy = self._load_policy(root_owner, state)
        if root_policy is not None:
            rules.append(_ScopedPolicy((), root_policy))

        for depth in range(1, len(components)):
            owner_components = components[:depth]
            if self._is_ignored(rules, owner_components, state, is_directory=True):
                raise RepositoryAccessError("repository_path_ignored")
            try:
                owner = self._capture_owner(owner_components)
            except RepositoryAccessError as error:
                if error.code != "repository_path_not_found":
                    raise
                ignored_as_file = self._is_ignored(
                    rules,
                    components,
                    state,
                    is_directory=False,
                )
                ignored_as_directory = self._is_ignored(
                    rules,
                    components,
                    state,
                    is_directory=True,
                )
                if ignored_as_file and ignored_as_directory:
                    raise RepositoryAccessError("repository_path_ignored") from None
                raise
            nested_policy = self._load_policy(owner, state)
            if nested_policy is not None:
                rules.append(_ScopedPolicy(owner_components, nested_policy))
        return rules

    def _capture_owner(self, components: tuple[str, ...]) -> _CapturedOwner:
        """Capture an initially admitted candidate-owner directory for one view."""
        resolved = self._resolve_requested(_label(components))
        if is_hard_denied_path(tuple(resolved.relative_path.parts)):
            raise RepositoryAccessError("repository_path_unavailable")
        try:
            observed = resolved.absolute_path.stat()
        except OSError:
            raise RepositoryAccessError("repository_path_unavailable") from None
        if not stat.S_ISDIR(observed.st_mode):
            raise RepositoryAccessError("repository_path_unavailable")
        return _CapturedOwner(
            components,
            resolved.relative_path,
            (observed.st_dev, observed.st_ino),
        )

    def _load_policy(
        self,
        owner: _CapturedOwner,
        state: _AdmissionState,
    ) -> _PolicyRules | None:
        """Safely load or reattach one owner's exact `.gitignore` policy source."""
        owner_label = _label(owner.components)
        self._policy_checkpoint("before_policy_probe", owner_label)
        self._require_same_owner(owner)
        candidate_path = self._policy_candidate_path(owner.components)
        if not self._policy_leaf_is_present(candidate_path):
            return None

        candidate_label = _child_label(owner.components, ".gitignore")
        first_source = self._resolve_policy_source(candidate_label)
        cached = state.cache.get(first_source.path)
        if cached is not None:
            return cached

        self._require_policy_capacity(state, first_source.size)
        self._policy_checkpoint("before_policy_read", owner_label)
        self._require_same_owner(owner)
        if not self._policy_leaf_is_present(candidate_path):
            raise RepositoryAccessError("repository_policy_invalid")
        current_source = self._resolve_policy_source(candidate_label)
        if current_source.path != first_source.path:
            raise RepositoryAccessError("repository_policy_invalid")
        self._require_policy_capacity(state, current_source.size)

        payload = self._read_policy_bytes(current_source.absolute_path)
        if (
            len(payload) > MAX_POLICY_SOURCE_BYTES
            or state.loaded_bytes + len(payload) > MAX_POLICY_BYTES
        ):
            raise RepositoryAccessError("repository_policy_invalid")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        if "\x00" in text:
            raise RepositoryAccessError("repository_policy_invalid")
        try:
            parsed = _compile_policy_rules(text.split("\n"))
        except Exception:
            raise RepositoryAccessError("repository_policy_invalid") from None

        state.cache[current_source.path] = parsed
        state.loaded_bytes += len(payload)
        return parsed

    def _require_same_owner(self, owner: _CapturedOwner) -> None:
        """Require a captured owner label to retain its canonical directory identity."""
        try:
            current = self.boundary.resolve_existing(_label(owner.components))
        except WorkspaceBoundaryError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        if current.relative_path != owner.canonical_path or is_hard_denied_path(
            tuple(current.relative_path.parts)
        ):
            raise RepositoryAccessError("repository_policy_invalid")
        try:
            current_stat = current.absolute_path.stat()
        except OSError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        if (
            not stat.S_ISDIR(current_stat.st_mode)
            or (
                current_stat.st_dev,
                current_stat.st_ino,
            )
            != owner.identity
        ):
            raise RepositoryAccessError("repository_policy_invalid")

    def _resolve_policy_source(self, candidate_label: str) -> _PolicySource:
        """Resolve and type-check one present policy leaf using canonical source identity."""
        try:
            source = self.boundary.resolve_existing(candidate_label)
        except WorkspaceBoundaryError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        if is_hard_denied_path(tuple(source.relative_path.parts)):
            raise RepositoryAccessError("repository_policy_invalid")
        try:
            source_stat = source.absolute_path.stat()
        except OSError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size > MAX_POLICY_SOURCE_BYTES:
            raise RepositoryAccessError("repository_policy_invalid")
        return _PolicySource(source.relative_path, source.absolute_path, source_stat.st_size)

    def _require_policy_capacity(self, state: _AdmissionState, candidate_bytes: int) -> None:
        """Fail before content I/O when one new canonical policy source cannot fit."""
        if (
            len(state.cache) >= MAX_POLICY_SOURCES
            or candidate_bytes < 0
            or state.loaded_bytes + candidate_bytes > MAX_POLICY_BYTES
        ):
            raise RepositoryAccessError("repository_policy_invalid")

    def _is_ignored(
        self,
        policies: list[_ScopedPolicy],
        target: tuple[str, ...],
        state: _AdmissionState,
        *,
        is_directory: bool,
    ) -> bool:
        """Fold bounded kind-aware Git decisions in root-to-nearest owner order."""
        ignored: bool | None = None
        for policy in policies:
            if target[: len(policy.owner)] != policy.owner:
                continue
            relative = target[len(policy.owner) :]
            if not relative:
                continue
            rules = policy.rules.directory if is_directory else policy.rules.file
            match_cost = len(rules.patterns)
            if match_cost > MAX_POLICY_MATCH_WORK - state.match_work:
                raise RepositoryAccessError("repository_policy_invalid")
            state.match_work += match_cost
            try:
                decision = _check_policy(rules, "/".join(relative))
            except Exception:
                raise RepositoryAccessError("repository_policy_invalid") from None
            if decision is not None:
                ignored = decision
        return ignored is True

    def _resolve_requested(self, label: str) -> ResolvedWorkspacePath:
        """Resolve requested-path work and map only a true missing target distinctly."""
        try:
            return self.boundary.resolve_existing(label)
        except WorkspaceBoundaryError as error:
            code: RepositoryAccessErrorCode = (
                "repository_path_not_found"
                if error.code == "workspace_path_not_found"
                else "repository_path_unavailable"
            )
            raise RepositoryAccessError(code) from None

    @staticmethod
    def _supported_kind(resolved: ResolvedWorkspacePath) -> RepositoryPathKind:
        """Admit only regular files and directories without opening the target."""
        try:
            target_stat = resolved.absolute_path.stat()
        except OSError:
            raise RepositoryAccessError("repository_path_unavailable") from None
        if stat.S_ISREG(target_stat.st_mode):
            return "file"
        if stat.S_ISDIR(target_stat.st_mode):
            return "directory"
        raise RepositoryAccessError("repository_path_unavailable")

    def _finalize_snapshot(
        self,
        components: tuple[str, ...],
        label: str,
        expected: ResolvedWorkspacePath,
        expected_kind: RepositoryPathKind,
    ) -> bool:
        """Recheck target identity and capture direct-leaf symlink provenance at return."""
        is_symlink = False
        if components:
            try:
                parent = self.boundary.resolve_existing(_label(components[:-1]))
                parent_stat = parent.absolute_path.stat()
            except (WorkspaceBoundaryError, OSError):
                raise RepositoryAccessError("repository_path_unavailable") from None
            if is_hard_denied_path(tuple(parent.relative_path.parts)) or not stat.S_ISDIR(
                parent_stat.st_mode
            ):
                raise RepositoryAccessError("repository_path_unavailable")
            try:
                leaf_stat = (parent.absolute_path / components[-1]).stat(follow_symlinks=False)
            except OSError:
                raise RepositoryAccessError("repository_path_unavailable") from None
            is_symlink = stat.S_ISLNK(leaf_stat.st_mode)

        current = self._resolve_requested(label)
        if is_hard_denied_path(tuple(current.relative_path.parts)):
            raise RepositoryAccessError("repository_path_unavailable")
        if (
            current.relative_path != expected.relative_path
            or self._supported_kind(current) != expected_kind
        ):
            raise RepositoryAccessError("repository_path_unavailable")
        return is_symlink

    def _policy_candidate_path(self, owner: tuple[str, ...]) -> Path:
        """Build one admitted owner-relative policy leaf without following that leaf."""
        return self.boundary.root.joinpath(*owner, ".gitignore")

    @staticmethod
    def _policy_leaf_is_present(candidate: Path) -> bool:
        """Probe a policy leaf without following it; only exact absence is normal."""
        try:
            candidate.stat(follow_symlinks=False)
        except FileNotFoundError:
            return False
        except OSError:
            raise RepositoryAccessError("repository_policy_invalid") from None
        return True

    @staticmethod
    def _read_policy_bytes(source: Path) -> bytes:
        """Read at most one byte beyond the per-policy limit for growth detection."""
        try:
            with source.open("rb") as stream:
                return stream.read(MAX_POLICY_SOURCE_BYTES + 1)
        except OSError:
            raise RepositoryAccessError("repository_policy_invalid") from None

    def _policy_checkpoint(self, stage: _PolicyCheckpoint, owner_label: str) -> None:
        """Expose a deterministic no-op mutation seam for owner-stability tests."""
        del stage, owner_label


def _label(components: tuple[str, ...]) -> str:
    """Render normalized components as one model-safe POSIX label."""
    return "." if not components else "/".join(components)


def _child_label(owner: tuple[str, ...], basename: str) -> str:
    """Render one fixed child below an already normalized owner label."""
    return "/".join((*owner, basename))


def _check_policy(rules: GitIgnoreSpec, label: str) -> bool | None:
    """Match one direct entry without letting an ancestor negation impersonate it."""
    decision: bool | None = None
    for pattern in rules.patterns:
        if pattern.include is None:
            continue
        match = pattern.match_file(label)
        if match is None:
            continue
        if match.match.groupdict().get("ps_d"):
            continue
        decision = pattern.include
    return decision


def _normalize_policy_line(line: str) -> str:
    """Apply Git's CR and unescaped trailing-ASCII-space line normalization."""
    if line.endswith("\r"):
        line = line[:-1]

    trailing_space: int | None = None
    index = 0
    while index < len(line):
        character = line[index]
        if character == "\\":
            if index + 1 == len(line):
                return line
            trailing_space = None
            index += 2
            continue
        if character == " ":
            if trailing_space is None:
                trailing_space = index
        else:
            trailing_space = None
        index += 1
    return line if trailing_space is None else line[:trailing_space]


def _ascii_range_group(character: str) -> int | None:
    """Classify one ASCII alphanumeric for a separator-safe range."""
    if "0" <= character <= "9":
        return 0
    if "A" <= character <= "Z":
        return 1
    if "a" <= character <= "z":
        return 2
    return None


def _validate_policy_range(content: str) -> None:
    """Admit only positive ASCII ranges and fixed literals that cannot include ``/``."""
    if not content or content[0] in ("!", "^", "]"):
        raise ValueError("policy pattern uses unsupported bracket syntax")
    index = 0
    while index < len(content):
        character = content[index]
        group = _ascii_range_group(character)
        if index + 1 < len(content) and content[index + 1] == "-":
            if index + 2 == len(content):
                raise ValueError("policy pattern uses unsupported bracket syntax")
            endpoint = content[index + 2]
            if group is None or _ascii_range_group(endpoint) != group or character > endpoint:
                raise ValueError("policy pattern uses unsupported bracket syntax")
            index += 3
            continue
        if group is None and character not in _SAFE_POLICY_RANGE_LITERALS:
            raise ValueError("policy pattern uses unsupported bracket syntax")
        index += 1


def _validate_policy_segment(segment: str) -> None:
    """Reject backend-divergent ranges and ambiguous local wildcard repetition."""
    stars = 0
    in_range = False
    range_has_member = False
    range_start = 0
    index = 0
    while index < len(segment):
        character = segment[index]
        if character == "\\" and not in_range:
            index += 2
            continue
        if not in_range:
            if character == "[":
                in_range = True
                range_has_member = False
                range_start = index + 1
            elif character == "*":
                stars += 1
                if stars > _MAX_POLICY_STARS_PER_SEGMENT:
                    raise ValueError("policy pattern exceeds the bounded wildcard grammar")
            elif character == "?":
                raise ValueError("policy pattern uses an unsupported question-mark wildcard")
            index += 1
            continue
        if character == "]" and range_has_member:
            _validate_policy_range(segment[range_start:index])
            in_range = False
            index += 1
            continue
        range_has_member = True
        index += 1


def _validate_policy_line(line: str) -> None:
    """Admit one semantic line only when every regex repetition remains bounded."""
    if not line or line.startswith("#") or line == "/":
        return
    body = line[1:] if line.startswith("!") else line
    segments = body.split("/")
    last_nonempty = next(
        (index for index in range(len(segments) - 1, -1, -1) if segments[index]),
        -1,
    )
    active_globstars = 0
    trailing_empty_activates_last_globstar = body.endswith("//")
    for index, segment in enumerate(segments):
        if segment == "**":
            if index < last_nonempty or (
                index == last_nonempty and trailing_empty_activates_last_globstar
            ):
                active_globstars += 1
                if active_globstars > _MAX_POLICY_ACTIVE_GLOBSTARS:
                    raise ValueError("policy pattern exceeds the bounded globstar grammar")
            continue
        _validate_policy_segment(segment)


def _compile_policy_pattern(line: str) -> GitIgnoreSpecPattern:
    """Compile one trusted semantic line while retaining exact built-in-string identity."""
    pattern = GitIgnoreSpecPattern(_SemanticPolicyLine(line))
    pattern.pattern = line
    return pattern


def _directory_pattern(line: str) -> str:
    """Convert one semantic directory terminator into a safe bare-label pattern."""
    body = line[1:] if line.startswith("!") else line
    if body == "/" or body.endswith("//") or not body.endswith("/"):
        return line
    return line[:-1]


def _compile_policy_rules(lines: list[str]) -> _PolicyRules:
    """Compile kind-specific views without activating an original no-op pattern."""
    semantic_lines = [_normalize_policy_line(line) for line in lines]
    for line in semantic_lines:
        _validate_policy_line(line)
    file_rules = GitIgnoreSpec.from_lines(
        semantic_lines,
        pattern_factory=_compile_policy_pattern,
        backend="simple",
    )
    retained_lines = [line for line in semantic_lines if line]
    if len(retained_lines) != len(file_rules.patterns):
        raise ValueError("GitIgnoreSpec retained an unexpected pattern count")
    directory_lines: list[str] = []
    for line, pattern in zip(retained_lines, file_rules.patterns, strict=True):
        if type(pattern.pattern) is not str or pattern.pattern != line:
            raise ValueError("GitIgnoreSpec changed a retained policy pattern")
        directory_lines.append(line if pattern.include is None else _directory_pattern(line))
    directory_rules = GitIgnoreSpec.from_lines(
        directory_lines,
        pattern_factory=_compile_policy_pattern,
        backend="simple",
    )
    if len(directory_rules.patterns) != len(file_rules.patterns):
        raise ValueError("directory rules changed the retained pattern count")
    for line, original, derived in zip(
        directory_lines,
        file_rules.patterns,
        directory_rules.patterns,
        strict=True,
    ):
        if derived.pattern != line or derived.include != original.include:
            raise ValueError("directory rules changed a retained pattern identity")
    return _PolicyRules(file=file_rules, directory=directory_rules)
