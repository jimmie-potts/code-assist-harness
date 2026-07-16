"""Minimal supervised runtime entry point for the Python harness child."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

from .protocol import (
    CommandLineReader,
    OrderedEventWriter,
    ProtocolParseFailure,
    RuntimeInitializeCommand,
    RuntimeShutdownCommand,
)

_READ_CHUNK_SIZE = 64 * 1024


class RuntimeConfigurationError(ValueError):
    """Report an invalid runtime configuration without exposing a traceback."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise RuntimeConfigurationError(message)


def resolve_workspace(value: str | Path) -> Path:
    """Resolve and validate the runtime's single workspace directory.

    Args:
        value: Workspace path supplied by the supervising TUI.

    Returns:
        The canonical absolute path to an existing directory.

    Raises:
        RuntimeConfigurationError: If the path cannot be resolved or is not a directory.
    """
    try:
        candidate = Path(value).expanduser()
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise RuntimeConfigurationError(
            f"workspace does not exist or cannot be accessed: {str(value)!r}"
        ) from error

    if not resolved.is_dir():
        raise RuntimeConfigurationError(f"workspace is not a directory: {resolved}")

    return resolved


def _parse_workspace(arguments: Sequence[str]) -> Path:
    parser = _ArgumentParser(
        prog="python -m code_assist_harness.runtime",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument("--workspace", action="append", metavar="PATH")
    parsed = parser.parse_args(arguments)

    workspace_values: list[str] | None = parsed.workspace
    if workspace_values is None:
        raise RuntimeConfigurationError("--workspace PATH is required exactly once")
    if len(workspace_values) != 1:
        raise RuntimeConfigurationError("--workspace PATH must be provided exactly once")

    return resolve_workspace(workspace_values[0])


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


async def run_runtime(workspace: Path) -> None:
    """Validate commands and emit ordered protocol events until shutdown or pipe EOF.

    The runtime owns exactly one canonical workspace for its lifetime. Each physical stdin line is
    contained independently: malformed input becomes a safe ``runtime.error`` and a later valid
    line is still processed. Initialization succeeds only when its payload resolves to the same
    canonical workspace supplied by the supervisor. Session commands validate as protocol v1 but
    report ``command_unavailable`` until CAH-005 and CAH-006 implement their behavior.

    Args:
        workspace: Canonical existing directory owned by this runtime process.

    Raises:
        RuntimeConfigurationError: If ``workspace`` is not canonical or is no longer a directory.
        OSError: If a protocol pipe cannot be monitored, read, written, or flushed.

    Note:
        Cancellation removes the event-loop reader before propagating to the caller.
    """
    try:
        resolved_workspace = workspace.resolve(strict=True)
    except OSError as error:
        raise RuntimeConfigurationError(
            "workspace must remain a canonical existing directory"
        ) from error

    if workspace != resolved_workspace or not resolved_workspace.is_dir():
        raise RuntimeConfigurationError("workspace must be a canonical existing directory")

    reader = CommandLineReader()
    writer = OrderedEventWriter(_write_stdout_line)
    initialized = False

    async for chunk in _read_stdin_chunks():
        for result in reader.feed(chunk):
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
                    requested_workspace = resolve_workspace(result.payload.workspace)
                except RuntimeConfigurationError:
                    requested_workspace = None
                if requested_workspace != workspace:
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
                    {"workspace": str(workspace)},
                    correlation_id=result.command_id,
                )
                continue

            error_code = "command_unavailable" if initialized else "not_initialized"
            error_message = (
                "Session commands are unavailable until the mocked-session unit is implemented."
                if initialized
                else "Runtime initialization must complete before session commands are accepted."
            )
            await writer.emit_runtime(
                "runtime.error",
                {
                    "code": error_code,
                    "message": error_message,
                    "recoverable": True,
                },
                correlation_id=result.command_id,
            )

    for failure in reader.finish():
        await writer.emit_runtime(
            "runtime.error",
            {
                "code": failure.code.value,
                "message": failure.message,
                "recoverable": True,
            },
        )


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
        workspace = _parse_workspace(arguments)
        asyncio.run(run_runtime(workspace))
    except RuntimeConfigurationError as error:
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
