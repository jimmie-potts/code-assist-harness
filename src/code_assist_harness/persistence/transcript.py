"""Append-only, redacted lifecycle transcripts and deterministic replay."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)

from ..protocol import (
    AssistantCompletedEvent,
    AssistantDeltaEvent,
    AssistantTextPayload,
    CommandId,
    SessionEvent,
    SessionFailedEvent,
    SessionFailedPayload,
    SessionId,
    Timestamp,
    utc_timestamp,
)
from ..session_state import (
    INITIAL_SESSION_STATE,
    TERMINAL_SESSION_STATUSES,
    ApprovalRequested,
    ApprovalResolved,
    CancelRequested,
    SessionState,
    SessionUpdate,
    TaskSubmitted,
    reduce_session_state,
)

TRANSCRIPT_VERSION = 1
"""Version of the local transcript envelope, independent of protocol v1."""

MAX_TRANSCRIPT_LINE_BYTES = 128 * 1024
"""Maximum bytes in one encoded transcript object, excluding its newline."""

DEFAULT_TEXT_LIMIT_BYTES = 16 * 1024
"""Default UTF-8 budget for one persisted task, result, or failure text value."""

_TRUNCATION_MARKER = "[TRUNCATED]"
_OMISSION_MARKER = "~"
_REDACTION_MARKER = "[REDACTED]"
_APPLICATION_DIRECTORY = "code-assist-harness"
_TRANSCRIPT_DIRECTORY = "transcripts"
_STREAM_REDACTION_LOOKBEHIND = 1024
_MAX_TRANSCRIPT_BYTES = 16 * 1024 * 1024
_MAX_TRANSCRIPT_RECORDS = 10_000
_MAX_REPLAY_ASSISTANT_BYTES = MAX_TRANSCRIPT_LINE_BYTES + _MAX_TRANSCRIPT_RECORDS
_SECRET_NAME_TOKENS = frozenset(
    {
        "AUTH",
        "AUTHORIZATION",
        "COOKIE",
        "CREDENTIAL",
        "CREDENTIALS",
        "DSN",
        "KEY",
        "PASSWORD",
        "SECRET",
        "TOKEN",
    }
)
_SECRET_WHOLE_NAMES = frozenset(
    {
        "ACCESSKEY",
        "ACCESSTOKEN",
        "APIKEY",
        "APITOKEN",
        "AUTHTOKEN",
        "CLIENTSECRET",
        "DATABASE_URL",
        "DATABASE_PASSWORD",
        "DB_PASSWORD",
        "DB_URL",
        "MONGODB_URI",
        "MONGO_URI",
        "MYSQL_PWD",
        "PGPASSWORD",
        "POSTGRES_PASSWORD",
        "REDIS_URL",
        "PRIVATEKEY",
        "REFRESHTOKEN",
        "SECRETKEY",
    }
)
_CREDENTIAL_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(
        r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]{4,}",
        re.IGNORECASE,
    ),
)
type CredentialContinuationKind = Literal["token", "assignment"]

_CREDENTIAL_PREFIX_PATTERNS: tuple[
    tuple[re.Pattern[str], CredentialContinuationKind],
    ...,
] = (
    (re.compile(r"(?:sk-|gh[pousr]_)[A-Za-z0-9_-]*$"), "token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]*$"), "token"),
    (re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]*$", re.IGNORECASE), "token"),
    (
        re.compile(
            r"(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]*$",
            re.IGNORECASE,
        ),
        "assignment",
    ),
)
_TOKEN_CONTINUATION_PATTERN = re.compile(r"[A-Za-z0-9._~+/=-]*")
_ASSIGNMENT_CONTINUATION_PATTERN = re.compile(r"[^\s,;]*")

type TranscriptPersistenceFailureCode = Literal[
    "transcript_open_failed",
    "transcript_write_failed",
    "transcript_flush_failed",
    "transcript_summary_failed",
]
type TranscriptReplayFailureCode = Literal[
    "transcript_open_failed",
    "invalid_framing",
    "line_too_large",
    "invalid_utf8",
    "invalid_record",
    "record_order_mismatch",
    "workspace_mismatch",
    "session_mismatch",
    "lifecycle_invariant_failed",
    "not_regular_file",
    "transcript_too_large",
]
type OpenFile = Callable[[Path, int, int], int]
type WriteFile = Callable[[int, bytes], int]
type FlushFile = Callable[[int], None]
type TruncateFile = Callable[[int, int], None]
type CloseFile = Callable[[int], None]
type ReplaceFile = Callable[[Path, Path], None]
type UnlinkFile = Callable[[Path], None]


def _validate_persisted_task(value: str) -> str:
    """Reject a task that the live runtime could never accept as a trusted fact."""
    if not value.strip():
        raise ValueError("persisted task must contain non-whitespace text")
    return value


PersistedTask = Annotated[
    str,
    StringConstraints(min_length=1),
    AfterValidator(_validate_persisted_task),
]
"""Safe stored task shape accepted by the same non-whitespace live-input rule."""


class _TranscriptModel(BaseModel):
    """Apply strict immutable validation to every transcript-owned JSON shape."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TaskSubmittedInput(_TranscriptModel):
    """Persisted safe form of a trusted local task submission."""

    type: Literal["task.submitted"]
    command_id: CommandId
    task: PersistedTask


class CancelRequestedInput(_TranscriptModel):
    """Persisted safe form of a trusted local cancellation request."""

    type: Literal["cancel.requested"]
    command_id: CommandId
    session_id: SessionId


class ApprovalRequestedInput(_TranscriptModel):
    """Persisted minimal approval-wait fact defined by CAH-010."""

    type: Literal["approval.requested"]
    session_id: SessionId


class ApprovalResolvedInput(_TranscriptModel):
    """Persisted minimal approval-resolution fact defined by CAH-010."""

    type: Literal["approval.resolved"]
    session_id: SessionId


type DomainFactInput = Annotated[
    TaskSubmittedInput | CancelRequestedInput | ApprovalRequestedInput | ApprovalResolvedInput,
    Field(discriminator="type"),
]
type TranscriptSessionEvent = Annotated[SessionEvent, Field(discriminator="type")]

WorkspaceId = Annotated[
    str,
    StringConstraints(pattern=r"^ws1_[a-f0-9]{24}$"),
]
"""Pseudonymous identifier derived from one canonical workspace path."""


class _TranscriptRecordBase(_TranscriptModel):
    """Fields common to every ordered transcript record."""

    transcript_version: Literal[1]
    record_order: Annotated[int, Field(gt=0)]
    recorded_at: Timestamp
    workspace_id: WorkspaceId
    session_id: SessionId
    kind: str


class DomainFactRecord(_TranscriptRecordBase):
    """One application-owned fact accepted by the lifecycle reducer."""

    kind: Literal["domain_fact"]
    input: DomainFactInput


class SessionEventRecord(_TranscriptRecordBase):
    """One validated protocol event accepted by the lifecycle reducer."""

    kind: Literal["session_event"]
    input: TranscriptSessionEvent


type TranscriptRecord = Annotated[
    DomainFactRecord | SessionEventRecord,
    Field(discriminator="kind"),
]

_TRANSCRIPT_RECORD_ADAPTER = TypeAdapter(TranscriptRecord)
_SESSION_ID_ADAPTER = TypeAdapter(SessionId)


@dataclass(frozen=True, slots=True)
class TranscriptSettings:
    """Configuration for local transcript privacy, location, and content bounds.

    ``state_directory`` is the application-owned directory, not the target repository. Call
    :meth:`from_environment` only when persistence is enabled so ``--no-transcript`` never needs to
    inspect XDG or home configuration.
    """

    state_directory: Path
    sensitive_values: tuple[str, ...] = field(default=(), repr=False)
    text_limit_bytes: int = DEFAULT_TEXT_LIMIT_BYTES

    def __post_init__(self) -> None:
        """Reject unusable content limits even for directly constructed test settings."""
        if self.text_limit_bytes <= len(_TRUNCATION_MARKER.encode("utf-8")):
            raise ValueError("transcript text limit must leave room for its truncation marker")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        home: Path | None = None,
        text_limit_bytes: int = DEFAULT_TEXT_LIMIT_BYTES,
    ) -> TranscriptSettings:
        """Resolve XDG state storage and recognized configured sensitive values.

        Args:
            environment: Environment snapshot to inspect. Only recognized sensitive variable
                values are retained for redaction; the mapping itself is never persisted.
            home: Optional home override used by deterministic tests when ``XDG_STATE_HOME`` is
                absent.
            text_limit_bytes: Positive UTF-8 byte budget for persisted text fields.

        Returns:
            Settings rooted at ``$XDG_STATE_HOME/code-assist-harness`` or, when the variable is
            absent or relative, ``~/.local/state/code-assist-harness``.

        Raises:
            ValueError: If ``text_limit_bytes`` is not positive.
        """
        if text_limit_bytes <= len(_TRUNCATION_MARKER.encode("utf-8")):
            raise ValueError("transcript text limit must leave room for its truncation marker")
        values = os.environ if environment is None else environment
        configured_root = values.get("XDG_STATE_HOME")
        if configured_root and Path(configured_root).is_absolute():
            state_root = Path(configured_root)
        else:
            resolved_home = Path.home() if home is None else home
            state_root = resolved_home / ".local" / "state"
        return cls(
            state_directory=state_root / _APPLICATION_DIRECTORY,
            sensitive_values=configured_sensitive_values(values),
            text_limit_bytes=text_limit_bytes,
        )


@dataclass(frozen=True, slots=True)
class TranscriptFileOperations:
    """Injectable filesystem primitives used for deterministic persistence-failure tests."""

    open_file: OpenFile = os.open
    write: WriteFile = os.write
    flush: FlushFile = os.fsync
    truncate: TruncateFile = os.ftruncate
    close: CloseFile = os.close
    replace: ReplaceFile = os.replace
    unlink: UnlinkFile = os.unlink


@dataclass(frozen=True, slots=True)
class TranscriptPersistenceFailure:
    """Payload-free storage failure safe to convert into one visible runtime warning."""

    code: TranscriptPersistenceFailureCode
    message: str = "Session recording is unavailable; session work will continue."


class TranscriptPersistenceError(RuntimeError):
    """Carry a bounded storage classification without copying paths or exception details."""

    def __init__(self, code: TranscriptPersistenceFailureCode) -> None:
        """Create an internal error from one safe failure classification."""
        super().__init__(code)
        self.code = code


class TranscriptReplayError(ValueError):
    """Report the first unsafe transcript line without reflecting its content."""

    def __init__(self, code: TranscriptReplayFailureCode, line_number: int | None = None) -> None:
        """Create a safe replay error with an optional one-based line number."""
        location = "" if line_number is None else f" at line {line_number}"
        super().__init__(f"transcript replay failed ({code}){location}")
        self.code = code
        self.line_number = line_number


@dataclass(frozen=True, slots=True)
class TranscriptReplay:
    """Validated replay result for a complete terminal tape or a safe incomplete prefix."""

    records: tuple[TranscriptRecord, ...]
    state: SessionState
    complete: bool


@dataclass(slots=True, repr=False)
class _TranscriptSanitizer:
    """Transform typed lifecycle values once before they approach persistence bytes."""

    sensitive_values: tuple[str, ...]
    text_limit_bytes: int
    raw_assistant_tail: str = ""
    safe_assistant_text: str = ""
    assistant_content_bytes: int = 0
    assistant_content_exhausted: bool = False
    credential_continuation: CredentialContinuationKind | None = None

    def sanitize_update(self, update: SessionUpdate) -> SessionUpdate:
        """Return a replay-valid safe copy of one trusted reducer input."""
        if isinstance(update, TaskSubmitted):
            return TaskSubmitted(
                command_id=update.command_id,
                task=self._bounded(self._redact(update.task)),
            )
        if isinstance(update, CancelRequested | ApprovalRequested | ApprovalResolved):
            return update
        if isinstance(update, AssistantDeltaEvent):
            safe_delta = self._redact_stream_fragment(update.payload.text)
            safe_delta = self._bounded_assistant_fragment(safe_delta)
            self.safe_assistant_text += safe_delta
            return update.model_copy(update={"payload": AssistantTextPayload(text=safe_delta)})
        if isinstance(update, AssistantCompletedEvent):
            completed = self.safe_assistant_text or _OMISSION_MARKER
            return update.model_copy(update={"payload": AssistantTextPayload(text=completed)})
        if isinstance(update, SessionFailedEvent):
            return update.model_copy(
                update={
                    "payload": SessionFailedPayload(
                        code=update.payload.code,
                        message=self._bounded(self._redact(update.payload.message)),
                    )
                }
            )
        return update

    def _redact_stream_fragment(self, value: str) -> str:
        """Redact exact secrets even when their match begins in a previous streamed delta."""
        maximum_secret_length = max(map(len, self.sensitive_values), default=1)
        combined = self.raw_assistant_tail + value
        boundary = len(self.raw_assistant_tail)
        ranges: list[tuple[int, int]] = []
        if self.credential_continuation is not None:
            continuation_pattern = (
                _TOKEN_CONTINUATION_PATTERN
                if self.credential_continuation == "token"
                else _ASSIGNMENT_CONTINUATION_PATTERN
            )
            continuation = continuation_pattern.match(value)
            continuation_end = 0 if continuation is None else continuation.end()
            if continuation_end:
                ranges.append((0, continuation_end))
            if continuation_end < len(value):
                self.credential_continuation = None
        for secret in self.sensitive_values:
            start = combined.find(secret)
            while start >= 0:
                end = start + len(secret)
                if end > boundary and start < len(combined):
                    local_start = max(start, boundary) - boundary
                    local_end = min(end, len(combined)) - boundary
                    if local_start < local_end:
                        ranges.append((local_start, local_end))
                start = combined.find(secret, start + 1)
            for prefix_length in range(len(secret) - 1, 0, -1):
                prefix = secret[:prefix_length]
                if not combined.endswith(prefix):
                    continue
                start = len(combined) - prefix_length
                local_start = max(start, boundary) - boundary
                local_end = len(value)
                if local_start < local_end:
                    ranges.append((local_start, local_end))
                break
        for pattern in _CREDENTIAL_PATTERNS:
            for match in pattern.finditer(combined):
                if match.end() > boundary:
                    local_start = max(match.start(), boundary) - boundary
                    local_end = match.end() - boundary
                    if local_start < local_end:
                        ranges.append((local_start, local_end))
        for pattern, continuation_kind in _CREDENTIAL_PREFIX_PATTERNS:
            match = pattern.search(combined)
            if match is None:
                continue
            local_start = max(match.start(), boundary) - boundary
            if local_start < len(value):
                ranges.append((local_start, len(value)))
                self.credential_continuation = continuation_kind
        tail_length = max(maximum_secret_length - 1, _STREAM_REDACTION_LOOKBEHIND)
        self.raw_assistant_tail = combined[-tail_length:] if tail_length else ""
        partially_redacted = _replace_ranges(value, ranges)
        return self._redact(partially_redacted)

    def _redact(self, value: str) -> str:
        redacted = value
        for secret in sorted(self.sensitive_values, key=len, reverse=True):
            redacted = redacted.replace(secret, _REDACTION_MARKER)
        for pattern in _CREDENTIAL_PATTERNS:
            redacted = pattern.sub(_REDACTION_MARKER, redacted)
        return redacted

    def _bounded(self, value: str) -> str:
        return _bound_utf8(value, self.text_limit_bytes)

    def _bounded_assistant_fragment(self, value: str) -> str:
        """Bound user content while retaining later delta cardinality with one-byte sentinels."""
        if self.assistant_content_exhausted:
            return _OMISSION_MARKER
        remaining = self.text_limit_bytes - self.assistant_content_bytes
        encoded = value.encode("utf-8")
        if len(encoded) <= remaining:
            self.assistant_content_bytes += len(encoded)
            return value or _OMISSION_MARKER
        if remaining > len(_TRUNCATION_MARKER.encode("utf-8")):
            safe_value = _bound_utf8(value, remaining)
            self.assistant_content_bytes += len(safe_value.encode("utf-8"))
        else:
            safe_value = _TRUNCATION_MARKER
        self.assistant_content_exhausted = True
        return safe_value


class SessionTranscript:
    """Own one session's append-only JSONL file, safe projection, and final summary.

    Records are serialized under one asyncio lock. Each append is flushed and fsynced before its
    order is committed in memory. The first failure latches the writer unavailable, closes the file,
    and is returned exactly once so the runtime can report it without recursively recording its own
    warning. Persistence never changes the authoritative live reducer state.
    """

    def __init__(
        self,
        *,
        descriptor: int,
        transcript_path: Path,
        summary_path: Path,
        workspace_id: str,
        session_id: str,
        settings: TranscriptSettings,
        operations: TranscriptFileOperations,
        clock: Callable[[], str],
    ) -> None:
        """Keep one already-open session artifact and its safe replay projection."""
        self._descriptor = descriptor
        self._transcript_path = transcript_path
        self._summary_path = summary_path
        self._workspace_id = workspace_id
        self._session_id = session_id
        self._operations = operations
        self._clock = clock
        self._sanitizer = _TranscriptSanitizer(
            sensitive_values=settings.sensitive_values,
            text_limit_bytes=settings.text_limit_bytes,
        )
        self._state = INITIAL_SESSION_STATE
        self._next_record_order = 1
        self._committed_bytes = 0
        self._lock = asyncio.Lock()
        self._failure: TranscriptPersistenceFailure | None = None
        self._failure_reported = False
        self._closed = False

    @classmethod
    async def create(
        cls,
        settings: TranscriptSettings,
        workspace: Path,
        session_id: str,
        *,
        operations: TranscriptFileOperations | None = None,
        clock: Callable[[], str] = utc_timestamp,
        create_transcript_id: Callable[[], str] | None = None,
    ) -> SessionTranscript:
        """Create one unique restrictive transcript outside the target workspace.

        Args:
            settings: Explicit state location, redaction values, and content bounds.
            workspace: Canonical target workspace used only to derive a pseudonymous identifier and
                enforce that harness state is not placed in the repository.
            session_id: Valid Python-owned session identity included in the artifact basename.
            operations: Optional low-level filesystem seams for failure injection.
            clock: Timestamp source for transcript records.
            create_transcript_id: Optional unique suffix source for deterministic tests.

        Returns:
            An open single-session writer before its first lifecycle input is accepted.

        Raises:
            TranscriptPersistenceError: If the location is unsafe or the file cannot be created.
        """
        file_operations = operations or TranscriptFileOperations()
        transcript_id_factory = create_transcript_id or (lambda: uuid4().hex)
        try:
            resolved_workspace = workspace.resolve(strict=True)
            configured_state_directory = settings.state_directory.expanduser()
            resolved_state_directory = configured_state_directory.resolve(strict=False)
            if resolved_state_directory.is_relative_to(resolved_workspace):
                raise OSError("state directory must remain outside the target workspace")
            workspace_id = stable_workspace_id(resolved_workspace)
            validated_session_id = _SESSION_ID_ADAPTER.validate_python(session_id, strict=True)
            transcript_id = _validated_transcript_id(transcript_id_factory())
            transcript_directory = configured_state_directory / _TRANSCRIPT_DIRECTORY
            basename = f"{workspace_id}--{validated_session_id}--tr_{transcript_id}"
            transcript_path = transcript_directory / f"{basename}.jsonl"
            summary_path = transcript_directory / f"{basename}.summary.txt"
            descriptor = _create_transcript_file(
                configured_state_directory,
                transcript_directory,
                transcript_path,
                file_operations,
            )
        except (OSError, RuntimeError, ValueError):
            raise TranscriptPersistenceError("transcript_open_failed") from None
        return cls(
            descriptor=descriptor,
            transcript_path=transcript_path,
            summary_path=summary_path,
            workspace_id=workspace_id,
            session_id=validated_session_id,
            settings=settings,
            operations=file_operations,
            clock=clock,
        )

    @property
    def transcript_path(self) -> Path:
        """Return the unique JSONL path without exposing it through protocol messages."""
        return self._transcript_path

    @property
    def summary_path(self) -> Path:
        """Return the human-readable summary path paired with the JSONL transcript."""
        return self._summary_path

    @property
    def safe_state(self) -> SessionState:
        """Return the reducer projection formed exclusively from persisted safe inputs."""
        return self._state

    async def record(
        self,
        update: SessionUpdate,
        accepted_state: SessionState,
    ) -> TranscriptPersistenceFailure | None:
        """Append one reducer-accepted input and derive a summary after a terminal record.

        Args:
            update: Trusted fact or validated event already accepted by the live reducer.
            accepted_state: Authoritative live state after accepting ``update``. Only its lifecycle
                status is compared; unsanitized text is never serialized.

        Returns:
            The first payload-free persistence failure, or ``None`` after success and after any
            already-reported failure.
        """
        async with self._lock:
            if self._failure is not None:
                return self._take_failure()
            if self._closed:
                return None
            try:
                safe_update = self._sanitizer.sanitize_update(update)
                reduction = reduce_session_state(self._state, safe_update)
                if not reduction.ok or not _same_lifecycle_invariants(
                    reduction.state,
                    accepted_state,
                ):
                    raise TranscriptPersistenceError("transcript_write_failed")
                if (
                    len(reduction.state.assistant_text.encode("utf-8"))
                    > _MAX_REPLAY_ASSISTANT_BYTES
                ):
                    raise TranscriptPersistenceError("transcript_write_failed")
                record = _build_record(
                    safe_update,
                    record_order=self._next_record_order,
                    recorded_at=self._clock(),
                    workspace_id=self._workspace_id,
                    session_id=self._session_id,
                )
                line = _encode_record(record)
                if (
                    self._next_record_order > _MAX_TRANSCRIPT_RECORDS
                    or self._committed_bytes + len(line) > _MAX_TRANSCRIPT_BYTES
                ):
                    raise TranscriptPersistenceError("transcript_write_failed")
                self._append_and_flush(line)
                self._state = reduction.state
                self._next_record_order += 1
                self._committed_bytes += len(line)
                if self._state.status in TERMINAL_SESSION_STATUSES:
                    summary = _build_summary(self._state, self._transcript_path.name)
                    try:
                        self._write_summary(summary)
                    except TranscriptPersistenceError:
                        raise
                    finally:
                        self._close()
            except TranscriptPersistenceError as error:
                self._latch_failure(error.code)
            except (OSError, RuntimeError, ValueError, ValidationError):
                self._latch_failure("transcript_write_failed")
            return self._take_failure()

    async def close(self) -> None:
        """Close the transcript without fabricating a terminal record or summary."""
        async with self._lock:
            self._close()

    def _append_and_flush(self, line: bytes) -> None:
        start_offset = os.lseek(self._descriptor, 0, os.SEEK_END)
        try:
            _write_all(self._descriptor, line, self._operations)
        except OSError as error:
            _rollback_partial_append(self._descriptor, start_offset, self._operations)
            raise TranscriptPersistenceError("transcript_write_failed") from error
        try:
            self._operations.flush(self._descriptor)
        except OSError as error:
            _rollback_partial_append(self._descriptor, start_offset, self._operations)
            raise TranscriptPersistenceError("transcript_flush_failed") from error

    def _write_summary(self, contents: bytes) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        temporary_path = self._summary_path.with_suffix(self._summary_path.suffix + ".tmp")
        descriptor: int | None = None
        try:
            descriptor = self._operations.open_file(temporary_path, flags, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
                _write_all(descriptor, contents, self._operations)
                self._operations.flush(descriptor)
            finally:
                self._operations.close(descriptor)
                descriptor = None
            self._operations.replace(temporary_path, self._summary_path)
        except (OSError, RuntimeError) as error:
            if descriptor is not None:
                try:
                    self._operations.close(descriptor)
                except OSError:
                    pass
            try:
                self._operations.unlink(temporary_path)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            raise TranscriptPersistenceError("transcript_summary_failed") from error

    def _latch_failure(self, code: TranscriptPersistenceFailureCode) -> None:
        if self._failure is None:
            self._failure = TranscriptPersistenceFailure(code=code)
        self._close()

    def _take_failure(self) -> TranscriptPersistenceFailure | None:
        if self._failure is None or self._failure_reported:
            return None
        self._failure_reported = True
        return self._failure

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._operations.close(self._descriptor)
        except OSError:
            pass


def configured_sensitive_values(environment: Mapping[str, str]) -> tuple[str, ...]:
    """Return unique non-empty values from recognized sensitive configuration names.

    The environment mapping itself is never returned or serialized. Even short configured values
    are retained: aggressive masking is preferable to persisting a known credential.
    """
    values = {value for name, value in environment.items() if _is_sensitive_name(name) and value}
    return tuple(sorted(values, key=lambda value: (-len(value), value)))


def _same_lifecycle_invariants(safe: SessionState, authoritative: SessionState) -> bool:
    """Compare replay-critical metadata while allowing deliberately sanitized content to differ."""
    safe_failure_code = None if safe.session_failure is None else safe.session_failure.code
    authoritative_failure_code = (
        None if authoritative.session_failure is None else authoritative.session_failure.code
    )
    return (
        safe.status == authoritative.status
        and safe.start_command_id == authoritative.start_command_id
        and safe.session_id == authoritative.session_id
        and safe.cancel_command_id == authoritative.cancel_command_id
        and safe.last_sequence == authoritative.last_sequence
        and safe.assistant_completed == authoritative.assistant_completed
        and safe_failure_code == authoritative_failure_code
    )


def _is_sensitive_name(name: str) -> bool:
    normalized_name = name.upper()
    with_camel_boundaries = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    tokens = re.split(r"[_-]", with_camel_boundaries.upper())
    return normalized_name in _SECRET_WHOLE_NAMES or any(
        token in _SECRET_NAME_TOKENS for token in tokens
    )


def stable_workspace_id(workspace: Path) -> str:
    """Derive a stable pseudonymous ID from one canonical workspace path.

    The hash prevents personal paths and repository basenames from appearing in filenames. It is
    pseudonymous rather than anonymous because a known candidate path can be hashed for comparison.
    """
    canonical = workspace.resolve(strict=True)
    digest = hashlib.sha256(os.fsencode(canonical)).hexdigest()[:24]
    return f"ws1_{digest}"


def replay_transcript(
    path: Path,
    *,
    expected_workspace: Path | None = None,
) -> TranscriptReplay:
    """Validate and replay a complete transcript or safely terminated JSONL prefix.

    Args:
        path: Existing transcript JSONL file. Symlinks are rejected where the host supports
            ``O_NOFOLLOW``.
        expected_workspace: Optional canonical scope whose derived ID must match every record.

    Returns:
        Validated records, their reducer state, and whether that state is terminal. An incomplete
        prefix is inspectable but is never treated as resumable work.

    Raises:
        TranscriptReplayError: At the first unsafe framing, schema, identity, order, or lifecycle
            invariant. No record content is copied into the exception.
    """
    records: list[TranscriptRecord] = []
    state = INITIAL_SESSION_STATE
    expected_workspace_id: str | None = None
    expected_session_id: str | None = None
    scoped_workspace_id: str | None = None
    assistant_content_bytes = 0
    if expected_workspace is not None:
        try:
            scoped_workspace_id = stable_workspace_id(expected_workspace)
        except (OSError, RuntimeError, ValueError):
            raise TranscriptReplayError("workspace_mismatch") from None
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise TranscriptReplayError("transcript_open_failed") from None
    try:
        file_status = os.fstat(descriptor)
        if not stat.S_ISREG(file_status.st_mode):
            raise TranscriptReplayError("not_regular_file")
        if file_status.st_size > _MAX_TRANSCRIPT_BYTES:
            raise TranscriptReplayError("transcript_too_large")
        with os.fdopen(descriptor, "rb", closefd=True) as transcript:
            descriptor = -1
            line_number = 0
            total_bytes = 0
            while True:
                line = transcript.readline(MAX_TRANSCRIPT_LINE_BYTES + 2)
                if not line:
                    break
                line_number += 1
                total_bytes += len(line)
                if total_bytes > _MAX_TRANSCRIPT_BYTES:
                    raise TranscriptReplayError("transcript_too_large", line_number)
                if line_number > _MAX_TRANSCRIPT_RECORDS:
                    raise TranscriptReplayError("transcript_too_large", line_number)
                if len(line) > MAX_TRANSCRIPT_LINE_BYTES + 1:
                    raise TranscriptReplayError("line_too_large", line_number)
                if not line.endswith(b"\n") or line.endswith(b"\r\n"):
                    raise TranscriptReplayError("invalid_framing", line_number)
                encoded_record = line[:-1]
                try:
                    encoded_record.decode("utf-8", errors="strict")
                except UnicodeDecodeError:
                    raise TranscriptReplayError("invalid_utf8", line_number) from None
                try:
                    record = _TRANSCRIPT_RECORD_ADAPTER.validate_json(encoded_record, strict=True)
                except ValidationError:
                    raise TranscriptReplayError("invalid_record", line_number) from None
                if record.record_order != line_number:
                    raise TranscriptReplayError("record_order_mismatch", line_number)
                if expected_workspace_id is None:
                    expected_workspace_id = record.workspace_id
                    expected_session_id = record.session_id
                    if (
                        scoped_workspace_id is not None
                        and record.workspace_id != scoped_workspace_id
                    ):
                        raise TranscriptReplayError("workspace_mismatch", line_number)
                elif record.workspace_id != expected_workspace_id:
                    raise TranscriptReplayError("workspace_mismatch", line_number)
                elif record.session_id != expected_session_id:
                    raise TranscriptReplayError("session_mismatch", line_number)
                if not _record_matches_session(record):
                    raise TranscriptReplayError("session_mismatch", line_number)
                update = _record_update(record)
                if isinstance(update, AssistantDeltaEvent):
                    assistant_content_bytes += len(update.payload.text.encode("utf-8"))
                    if assistant_content_bytes > _MAX_REPLAY_ASSISTANT_BYTES:
                        raise TranscriptReplayError("transcript_too_large", line_number)
                reduction = reduce_session_state(state, update)
                if not reduction.ok:
                    raise TranscriptReplayError("lifecycle_invariant_failed", line_number)
                state = reduction.state
                records.append(record)
    except OSError:
        raise TranscriptReplayError("transcript_open_failed") from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    return TranscriptReplay(
        records=tuple(records),
        state=state,
        complete=state.status in TERMINAL_SESSION_STATUSES,
    )


def _create_transcript_file(
    state_directory: Path,
    transcript_directory: Path,
    transcript_path: Path,
    operations: TranscriptFileOperations,
) -> int:
    _ensure_private_directory(state_directory)
    _ensure_private_directory(transcript_directory)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = operations.open_file(transcript_path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
    except OSError:
        operations.close(descriptor)
        raise
    return descriptor


def _ensure_private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise OSError("transcript directory is not a regular directory")
    os.chmod(path, 0o700)


def _build_record(
    update: SessionUpdate,
    *,
    record_order: int,
    recorded_at: str,
    workspace_id: str,
    session_id: str,
) -> TranscriptRecord:
    common = {
        "transcript_version": TRANSCRIPT_VERSION,
        "record_order": record_order,
        "recorded_at": recorded_at,
        "workspace_id": workspace_id,
        "session_id": session_id,
    }
    if isinstance(update, TaskSubmitted):
        fact: DomainFactInput = TaskSubmittedInput(
            type="task.submitted",
            command_id=update.command_id,
            task=update.task,
        )
    elif isinstance(update, CancelRequested):
        fact = CancelRequestedInput(
            type="cancel.requested",
            command_id=update.command_id,
            session_id=update.session_id,
        )
    elif isinstance(update, ApprovalRequested):
        fact = ApprovalRequestedInput(
            type="approval.requested",
            session_id=update.session_id,
        )
    elif isinstance(update, ApprovalResolved):
        fact = ApprovalResolvedInput(
            type="approval.resolved",
            session_id=update.session_id,
        )
    else:
        return SessionEventRecord(kind="session_event", input=update, **common)
    return DomainFactRecord(kind="domain_fact", input=fact, **common)


def _record_update(record: TranscriptRecord) -> SessionUpdate:
    if isinstance(record, SessionEventRecord):
        return record.input
    value = record.input
    if isinstance(value, TaskSubmittedInput):
        return TaskSubmitted(command_id=value.command_id, task=value.task)
    if isinstance(value, CancelRequestedInput):
        return CancelRequested(command_id=value.command_id, session_id=value.session_id)
    if isinstance(value, ApprovalRequestedInput):
        return ApprovalRequested(session_id=value.session_id)
    if isinstance(value, ApprovalResolvedInput):
        return ApprovalResolved(session_id=value.session_id)
    raise AssertionError(f"unhandled transcript fact: {type(value).__name__}")


def _record_matches_session(record: TranscriptRecord) -> bool:
    if isinstance(record, SessionEventRecord):
        return record.input.session_id == record.session_id
    if isinstance(record.input, TaskSubmittedInput):
        return True
    return record.input.session_id == record.session_id


def _encode_record(record: TranscriptRecord) -> bytes:
    line = record.model_dump_json(exclude_none=True).encode("utf-8")
    if len(line) > MAX_TRANSCRIPT_LINE_BYTES:
        raise TranscriptPersistenceError("transcript_write_failed")
    return line + b"\n"


def _build_summary(state: SessionState, transcript_name: str) -> bytes:
    task = _single_line(state.task or "unavailable")
    lines = [
        "Code Assist Harness session summary",
        "",
        f"Transcript: {transcript_name}",
        f"Session: {state.session_id or 'unavailable'}",
        f"Task: {task}",
        f"Outcome: {state.status}",
        "Changed files: unavailable - file-edit tools are not implemented in CAH-011.",
        "Check results: unavailable - validation tools are not implemented in CAH-011.",
    ]
    if state.session_failure is not None:
        lines.extend(
            [
                f"Failure code: {_single_line(state.session_failure.code)}",
                f"Failure message: {_single_line(state.session_failure.message)}",
            ]
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _single_line(value: str) -> str:
    return "".join(
        (
            " "
            if character in "\r\n\t" or ord(character) < 32 or 127 <= ord(character) <= 159
            else character
        )
        for character in value
    )


def _bound_utf8(value: str, limit: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value
    marker = _TRUNCATION_MARKER.encode("utf-8")
    prefix = encoded[: limit - len(marker)].decode("utf-8", errors="ignore")
    return prefix + _TRUNCATION_MARKER


def _replace_ranges(value: str, ranges: Sequence[tuple[int, int]]) -> str:
    if not ranges:
        return value
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            prior_start, prior_end = merged[-1]
            merged[-1] = (prior_start, max(prior_end, end))
        else:
            merged.append((start, end))
    pieces: list[str] = []
    cursor = 0
    for start, end in merged:
        pieces.extend((value[cursor:start], _REDACTION_MARKER))
        cursor = end
    pieces.append(value[cursor:])
    return "".join(pieces)


def _write_all(
    descriptor: int,
    contents: bytes,
    operations: TranscriptFileOperations,
) -> None:
    remaining = memoryview(contents)
    while remaining:
        written = operations.write(descriptor, remaining.tobytes())
        if written <= 0:
            raise OSError("transcript write made no progress")
        remaining = remaining[written:]


def _rollback_partial_append(
    descriptor: int,
    start_offset: int,
    operations: TranscriptFileOperations,
) -> None:
    try:
        operations.truncate(descriptor, start_offset)
        operations.flush(descriptor)
    except OSError:
        pass


def _validated_transcript_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", value):
        raise ValueError("transcript ID is invalid")
    return value
