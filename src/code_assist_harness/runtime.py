"""Minimal supervised runtime entry point for the Python harness child."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

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
    except (OSError, RuntimeError) as error:
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


async def _wait_for_stdin_eof() -> None:
    """Drain command-pipe bytes until EOF without retaining unimplemented messages."""
    loop = asyncio.get_running_loop()
    stdin_fd = sys.stdin.fileno()
    eof: asyncio.Future[None] = loop.create_future()

    def discard_available_input() -> None:
        try:
            data = os.read(stdin_fd, _READ_CHUNK_SIZE)
        except BlockingIOError:
            return
        except OSError as error:
            loop.remove_reader(stdin_fd)
            if not eof.done():
                eof.set_exception(error)
            return

        if data:
            return

        loop.remove_reader(stdin_fd)
        if not eof.done():
            eof.set_result(None)

    loop.add_reader(stdin_fd, discard_available_input)
    try:
        await eof
    finally:
        loop.remove_reader(stdin_fd)


async def run_runtime(workspace: Path) -> None:
    """Run one harness child until its supervising command pipe closes.

    The runtime owns exactly one canonical workspace for its lifetime. This initial
    implementation deliberately discards stdin bytes because command parsing arrives in CAH-004,
    and it writes nothing to stdout so that channel remains protocol-only.

    Args:
        workspace: Canonical existing directory owned by this runtime process.

    Raises:
        RuntimeConfigurationError: If ``workspace`` is not canonical or is no longer a directory.
        OSError: If the stdin pipe cannot be monitored or read.

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

    await _wait_for_stdin_eof()


def main(argv: Sequence[str] | None = None) -> int:
    """Validate child configuration and run its single asyncio event loop.

    Args:
        argv: Optional command-line arguments without the executable name.

    Returns:
        A process exit status. Configuration errors return 2, stdin failures return 1,
        and a clean supervising-pipe EOF returns 0.

    Side Effects:
        Writes brief human diagnostics only to stderr. Stdout is reserved for protocol events.
    """
    arguments = sys.argv[1:] if argv is None else argv
    try:
        workspace = _parse_workspace(arguments)
        asyncio.run(run_runtime(workspace))
    except RuntimeConfigurationError as error:
        print(f"runtime configuration error: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"runtime stdin error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
