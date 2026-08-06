"""Minimal supervised runtime entry point for the Python harness child."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .loop_limits import LoopLimits, LoopLimitsObserved
from .mock_session import MockSession, MockSessionRunner
from .model_evidence import ModelUsageObserved
from .persistence import SessionTranscript, TranscriptPersistenceError, TranscriptSettings
from .protocol import (
    Command,
    CommandLineReader,
    OrderedEventWriter,
    ProtocolParseFailure,
    RuntimeInitializeCommand,
    RuntimeShutdownCommand,
    SessionCancelCommand,
    SessionId,
    SessionStartCommand,
)
from .provider import Provider, RepositoryInstruction
from .provider.openai_config import (
    DEFAULT_PROVIDER,
    OpenAIProviderConfiguration,
    ProviderConfigurationError,
    ProviderName,
    resolve_provider_configuration,
    validate_provider_selection,
)
from .provider_session import (
    MonotonicClock,
    MonotonicWaiter,
    ProviderSession,
    ProviderSessionRunner,
)
from .session_state import SessionState, SessionUpdate
from .workspace import WorkspaceBoundary, WorkspaceBoundaryError

_READ_CHUNK_SIZE = 64 * 1024


class RuntimeConfigurationError(ValueError):
    """Report an invalid runtime configuration without exposing a traceback."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RuntimeConfigurationError(message)


@dataclass(frozen=True, slots=True)
class _RuntimeOptions:
    """Validated process configuration supplied outside protocol stdin.

    The selected boundary is constructed once during argument admission and passed unchanged to
    the runtime so later consumers share its captured root identity.
    """

    workspace: WorkspaceBoundary
    transcript_enabled: bool
    provider: ProviderName
    model: str | None


def _parse_runtime_options(arguments: Sequence[str]) -> _RuntimeOptions:
    parser = _ArgumentParser(
        prog="python -m code_assist_harness.runtime",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--workspace", action="append", metavar="PATH")
    parser.add_argument("--no-transcript", action="store_true")
    parser.add_argument("--provider", action="append", metavar="NAME")
    parser.add_argument("--model", action="append", metavar="MODEL")
    parsed = parser.parse_args(arguments)

    workspace_values: list[str] | None = parsed.workspace
    if workspace_values is None:
        raise RuntimeConfigurationError("--workspace PATH is required exactly once")
    if len(workspace_values) != 1:
        raise RuntimeConfigurationError("--workspace PATH must be provided exactly once")

    provider_values: list[str] | None = parsed.provider
    if provider_values is not None and len(provider_values) != 1:
        raise RuntimeConfigurationError("--provider NAME may be provided at most once")
    model_values: list[str] | None = parsed.model
    if model_values is not None and len(model_values) != 1:
        raise RuntimeConfigurationError("--model MODEL may be provided at most once")

    provider_candidate = DEFAULT_PROVIDER if provider_values is None else provider_values[0]
    model_candidate = None if model_values is None else model_values[0]
    try:
        provider, model = validate_provider_selection(provider_candidate, model_candidate)
    except ProviderConfigurationError as error:
        raise RuntimeConfigurationError(str(error)) from None

    try:
        workspace = WorkspaceBoundary.from_path(workspace_values[0])
    except WorkspaceBoundaryError as error:
        raise RuntimeConfigurationError(str(error)) from error

    return _RuntimeOptions(
        workspace=workspace,
        transcript_enabled=not parsed.no_transcript,
        provider=provider,
        model=model,
    )


def _create_openai_provider(configuration: OpenAIProviderConfiguration) -> Provider:
    """Import and construct the concrete adapter only after SDK-free validation.

    Args:
        configuration: Validated model and credential retained inside the provider boundary.

    Returns:
        One reusable provider whose operations own their SDK resources lazily.
    """
    from .provider.openai_responses import OpenAIResponsesProvider

    return OpenAIResponsesProvider(configuration)


def _compose_provider(
    options: _RuntimeOptions,
    environment: Mapping[str, str],
) -> Provider | None:
    """Select the mock path or construct OpenAI after complete local validation.

    Args:
        options: Provider/model pair already validated by the Python argument boundary.
        environment: Process environment inspected only when OpenAI was selected.

    Returns:
        ``None`` for ``MockSessionRunner`` or the concrete OpenAI adapter.

    Raises:
        ProviderConfigurationError: If OpenAI environment or credential validation fails.
    """
    configuration = resolve_provider_configuration(
        options.provider,
        options.model,
        environment,
    )
    if configuration is None:
        return None
    return _create_openai_provider(configuration)


async def _read_stdin_chunks() -> AsyncIterator[bytes]:
    """Yield bounded stdin chunks without blocking the runtime event loop.

    The file-descriptor reader is armed for one read at a time. It is re-armed only after the
    consumer requests another chunk, which bounds queued input while protocol errors are written.

    Yields:
        Raw bytes in process-pipe arrival order until EOF.

    Raises:
        OSError: If the stdin pipe cannot be read.
    """
    loop = asyncio.get_running_loop()
    stdin_fd = sys.stdin.fileno()
    pending: asyncio.Queue[bytes | OSError | None] = asyncio.Queue(maxsize=1)
    reader_registered = False

    def read_available_input() -> None:
        nonlocal reader_registered
        loop.remove_reader(stdin_fd)
        reader_registered = False
        try:
            data = os.read(stdin_fd, _READ_CHUNK_SIZE)
        except OSError as error:
            pending.put_nowait(error)
            return

        pending.put_nowait(data if data else None)

    try:
        while True:
            loop.add_reader(stdin_fd, read_available_input)
            reader_registered = True
            item = await pending.get()
            if item is None:
                return
            if isinstance(item, OSError):
                raise item
            yield item
    finally:
        if reader_registered:
            loop.remove_reader(stdin_fd)


async def _write_stdout_line(line: bytes) -> None:
    """Write one already validated bounded event line to protocol stdout."""
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()


async def _read_commands() -> AsyncIterator[Command | ProtocolParseFailure]:
    """Incrementally parse stdin and yield each command or contained line failure.

    Yields:
        Validated commands and safe parse failures in physical input order.

    Raises:
        OSError: If the stdin pipe cannot be monitored or read.
    """
    reader = CommandLineReader()
    async for chunk in _read_stdin_chunks():
        for result in reader.feed(chunk):
            yield result
    for failure in reader.finish():
        yield failure


async def run_runtime(
    workspace: WorkspaceBoundary | str | Path,
    *,
    transcript_enabled: bool = True,
    transcript_settings: TranscriptSettings | None = None,
    provider: Provider | None = None,
    repository_instructions: tuple[RepositoryInstruction, ...] = (),
    loop_limits: LoopLimits | None = None,
    monotonic_now: MonotonicClock | None = None,
    monotonic_waiter: MonotonicWaiter | None = None,
) -> None:
    """Validate commands and emit ordered protocol events until shutdown or pipe EOF.

    The runtime owns exactly one canonical workspace for its lifetime. Each physical stdin line is
    contained independently: malformed input becomes a safe ``runtime.error`` and a later valid
    line is still processed. Initialization succeeds only when its payload resolves to the same
    canonical workspace supplied by the supervisor. After readiness, one ``session.start`` runs the
    deterministic CAH-005 stream in a child task so the command reader can reject overlapping work
    and honor orderly shutdown. Tests may inject a provider to run one CAH-022 provider-neutral
    turn. The launched ``main()`` path supplies none for the default mock or the explicitly selected
    OpenAI adapter. Python remains authoritative for every terminal event.

    Args:
        workspace: Validated boundary owned by this runtime process. A string or path is accepted
            as a direct-call compatibility seam and delegates immediately to the sole boundary
            constructor.
        transcript_enabled: Whether accepted session inputs should create local evidence files.
        transcript_settings: Optional explicit storage and redaction settings. When omitted and
            persistence is enabled, settings are derived from XDG and recognized sensitive
            environment values. Disabled mode never inspects those locations or values.
        provider: Optional provider implementation selected by the composition root or a test seam.
        repository_instructions: Ordered, already-resolved instructions supplied only to an injected
            provider session. Discovery and precedence remain later work.
        loop_limits: Optional immutable hard budgets for injected provider-backed sessions.
        monotonic_now: Optional provider-deadline clock, supplied with ``monotonic_waiter``.
        monotonic_waiter: Optional absolute-deadline waiter paired with ``monotonic_now``.

    Raises:
        RuntimeConfigurationError: If ``workspace`` cannot establish a current boundary.
        OSError: If a protocol pipe cannot be monitored, read, written, or flushed.

    Note:
        Cancellation removes the event-loop reader before propagating to the caller.
    """
    if isinstance(workspace, WorkspaceBoundary):
        workspace_boundary = workspace
    else:
        try:
            workspace_boundary = WorkspaceBoundary.from_path(workspace)
        except WorkspaceBoundaryError as error:
            raise RuntimeConfigurationError(str(error)) from error
    try:
        workspace_boundary.resolve_existing(".")
    except WorkspaceBoundaryError as error:
        raise RuntimeConfigurationError(str(error)) from error
    workspace_root = workspace_boundary.root
    if (monotonic_now is None) != (monotonic_waiter is None):
        raise RuntimeConfigurationError(
            "provider monotonic clock and waiter must be supplied together"
        )

    settings = transcript_settings
    if transcript_enabled and settings is None:
        settings = TranscriptSettings.from_environment()

    writer = OrderedEventWriter(_write_stdout_line)
    session_runner: MockSessionRunner | ProviderSessionRunner
    if provider is None:
        session_runner = MockSessionRunner(writer)
    elif monotonic_now is None or monotonic_waiter is None:
        session_runner = ProviderSessionRunner(
            writer,
            provider,
            repository_instructions,
            limits=loop_limits,
        )
    else:
        session_runner = ProviderSessionRunner(
            writer,
            provider,
            repository_instructions,
            limits=loop_limits,
            monotonic_now=monotonic_now,
            monotonic_waiter=monotonic_waiter,
        )
    transcript_available = transcript_enabled
    initialized = False
    active_session: MockSession | ProviderSession | None = None
    active_session_task: asyncio.Task[SessionId] | None = None
    active_transcript: SessionTranscript | None = None
    latest_terminal_session_id: SessionId | None = None
    commands = _read_commands()
    next_command = asyncio.create_task(anext(commands))

    try:
        while True:
            waiters: set[asyncio.Task[object]] = {next_command}
            if active_session_task is not None:
                waiters.add(active_session_task)
            completed, _pending = await asyncio.wait(
                waiters,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if active_session_task is not None and active_session_task in completed:
                await active_session_task
                if active_session is None:
                    raise RuntimeError("active session task is missing its lifecycle owner")
                latest_terminal_session_id = active_session.session_id
                if active_transcript is not None:
                    await active_transcript.close()
                active_session = None
                active_session_task = None
                active_transcript = None

            if next_command not in completed:
                continue

            try:
                result = next_command.result()
            except StopAsyncIteration:
                if active_session_task is not None:
                    if isinstance(active_session, ProviderSession):
                        await active_session.request_teardown()
                    await active_session_task
                return
            next_command = asyncio.create_task(anext(commands))

            if isinstance(result, ProtocolParseFailure):
                await writer.emit_runtime(
                    "runtime.error",
                    {
                        "code": result.code.value,
                        "message": result.message,
                        "recoverable": True,
                    },
                )
                continue

            if isinstance(result, RuntimeShutdownCommand):
                if active_session_task is not None:
                    if isinstance(active_session, ProviderSession):
                        await active_session.request_teardown()
                    await active_session_task
                return

            if isinstance(result, RuntimeInitializeCommand):
                if initialized:
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "already_initialized",
                            "message": "Runtime initialization has already completed.",
                            "recoverable": True,
                        },
                        correlation_id=result.command_id,
                    )
                    continue

                try:
                    requested_workspace = WorkspaceBoundary.from_path(result.payload.workspace)
                    workspace_boundary.resolve_existing(".")
                except WorkspaceBoundaryError:
                    requested_workspace = None
                if requested_workspace != workspace_boundary:
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "workspace_mismatch",
                            "message": (
                                "Initialization workspace does not match the supervised workspace."
                            ),
                            "recoverable": False,
                        },
                        correlation_id=result.command_id,
                    )
                    return

                initialized = True
                await writer.emit_runtime(
                    "runtime.ready",
                    {"workspace": str(workspace_root)},
                    correlation_id=result.command_id,
                )
                continue

            if not initialized:
                await writer.emit_runtime(
                    "runtime.error",
                    {
                        "code": "not_initialized",
                        "message": (
                            "Runtime initialization must complete before session commands are "
                            "accepted."
                        ),
                        "recoverable": True,
                    },
                    correlation_id=result.command_id,
                )
                continue

            if isinstance(result, SessionStartCommand):
                if not result.payload.task.strip():
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "invalid_task",
                            "message": "A session task must contain non-whitespace text.",
                            "recoverable": True,
                        },
                        correlation_id=result.command_id,
                    )
                    continue
                if active_session is not None:
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "session_active",
                            "message": "A session is already active.",
                            "recoverable": True,
                        },
                        correlation_id=result.command_id,
                    )
                    continue
                active_session = session_runner.create(result)
                if transcript_available:
                    if settings is None:
                        raise RuntimeError("enabled transcripts are missing their settings")
                    try:
                        active_transcript = await SessionTranscript.create(
                            settings,
                            workspace_root,
                            active_session.session_id,
                        )
                    except TranscriptPersistenceError:
                        transcript_available = False
                        await writer.emit_runtime(
                            "runtime.error",
                            {
                                "code": "transcript_persistence_failed",
                                "message": (
                                    "Session recording is unavailable; session work will continue."
                                ),
                                "recoverable": True,
                            },
                            correlation_id=result.command_id,
                        )
                    else:
                        transcript = active_transcript
                        start_command_id = result.command_id

                        async def _record_lifecycle(
                            update: SessionUpdate,
                            accepted_state: SessionState,
                        ) -> None:
                            """Persist one accepted input or emit the one safe warning."""
                            nonlocal transcript_available
                            failure = await transcript.record(update, accepted_state)
                            if failure is None:
                                return
                            transcript_available = False
                            await writer.emit_runtime(
                                "runtime.error",
                                {
                                    "code": "transcript_persistence_failed",
                                    "message": failure.message,
                                    "recoverable": True,
                                },
                                correlation_id=start_command_id,
                            )

                        await active_session.attach_lifecycle_observer(_record_lifecycle)
                        if isinstance(active_session, ProviderSession):

                            async def _record_model_usage(
                                observation: ModelUsageObserved,
                            ) -> None:
                                """Persist admitted usage or emit the one safe warning."""
                                nonlocal transcript_available
                                failure = await transcript.record_model_usage(observation)
                                if failure is None:
                                    return
                                transcript_available = False
                                await writer.emit_runtime(
                                    "runtime.error",
                                    {
                                        "code": "transcript_persistence_failed",
                                        "message": failure.message,
                                        "recoverable": True,
                                    },
                                    correlation_id=start_command_id,
                                )

                            await active_session.attach_model_usage_observer(_record_model_usage)

                            async def _record_loop_limits(
                                observation: LoopLimitsObserved,
                            ) -> None:
                                """Persist loop-budget evidence or emit the one safe warning."""
                                nonlocal transcript_available
                                failure = await transcript.record_loop_limits(observation)
                                if failure is None:
                                    return
                                transcript_available = False
                                await writer.emit_runtime(
                                    "runtime.error",
                                    {
                                        "code": "transcript_persistence_failed",
                                        "message": failure.message,
                                        "recoverable": True,
                                    },
                                    correlation_id=start_command_id,
                                )

                            await active_session.attach_loop_limits_observer(_record_loop_limits)
                active_session_task = asyncio.create_task(active_session.run())
                continue

            if isinstance(result, SessionCancelCommand):
                target_session_id = result.payload.session_id
                if active_session is None:
                    if target_session_id == latest_terminal_session_id:
                        continue
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "session_not_active",
                            "message": "No matching active or recently completed session exists.",
                            "recoverable": True,
                        },
                        correlation_id=result.command_id,
                    )
                    continue

                if target_session_id != active_session.session_id:
                    await writer.emit_runtime(
                        "runtime.error",
                        {
                            "code": "session_mismatch",
                            "message": "Cancellation target does not match the active session.",
                            "recoverable": True,
                        },
                        correlation_id=result.command_id,
                    )
                    continue

                await active_session.request_cancellation(result.command_id)
                if active_session_task is None:
                    raise RuntimeError("active session is missing its task")
                # Reap the bounded cooperative task before accepting another command. Its sole
                # terminal event is written before this await returns, so a task submitted after
                # the TUI observes cancellation cannot race a stale active-session reference.
                await active_session_task
                latest_terminal_session_id = active_session.session_id
                if active_transcript is not None:
                    await active_transcript.close()
                active_session = None
                active_session_task = None
                active_transcript = None
                continue

            raise RuntimeError(f"unhandled validated command type: {type(result).__name__}")
    finally:
        if not next_command.done():
            next_command.cancel()
        try:
            await asyncio.gather(next_command, return_exceptions=True)
            await commands.aclose()
        finally:
            try:
                if active_session_task is not None:
                    if isinstance(active_session, ProviderSession):
                        await active_session.request_teardown()
                    elif not active_session_task.done():
                        active_session_task.cancel()
            finally:
                try:
                    if active_session_task is not None:
                        try:
                            await active_session_task
                        except asyncio.CancelledError:
                            pass
                finally:
                    if active_transcript is not None:
                        await active_transcript.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Validate child configuration and run its single asyncio event loop.

    Args:
        argv: Optional command-line arguments without the executable name.

    Returns:
        A process exit status. Configuration errors return 2, stdin failures return 1,
        and a clean supervising-pipe EOF returns 0.

    Side Effects:
        Writes validated protocol events to stdout and brief human diagnostics only to stderr.
    """
    arguments = sys.argv[1:] if argv is None else argv
    try:
        options = _parse_runtime_options(arguments)
        provider = _compose_provider(options, os.environ)
        asyncio.run(
            run_runtime(
                options.workspace,
                transcript_enabled=options.transcript_enabled,
                provider=provider,
                loop_limits=LoopLimits() if provider is not None else None,
            )
        )
    except (ProviderConfigurationError, RuntimeConfigurationError) as error:
        print(f"runtime configuration error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"runtime pipe error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
