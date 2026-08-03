"""Async provider port owned by the harness agent-loop domain."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Literal, Protocol, runtime_checkable

from .models import ProviderRequest, ProviderStreamEvent

type ProviderCancellationResult = Literal["cancelled", "already_closed"]
"""Result of awaiting one provider operation's idempotent cancellation."""


@runtime_checkable
class ProviderOperation(Protocol):
    """One single-consumer provider response stream and its cleanup boundary.

    Calling :meth:`events` claims the stream exactly once. A normal stream ends with
    ``ProviderCompleted`` or ``ProviderFailed``. Cancellation is different from provider failure:
    it ends iteration without fabricating a failure event because the session layer already owns
    the user's cancellation intent.
    """

    def events(self) -> AsyncIterator[ProviderStreamEvent]:
        """Claim and return this operation's single-consumer event stream.

        Returns:
            An asynchronous iterator of harness-owned provider events.

        Raises:
            RuntimeError: If the stream was already claimed.
        """
        ...

    async def cancel(self) -> ProviderCancellationResult:
        """Request cancellation and wait until provider cleanup finishes.

        Returns:
            ``cancelled`` when this call stopped active work, or ``already_closed`` when normal
            completion, failure, or an earlier cancellation had already closed the operation.

        Note:
            Once this awaitable returns, the iterator is closed and cannot yield another event.
            Implementations must release provider-specific stream resources before returning.
        """
        ...

    async def wait_closed(self) -> None:
        """Wait for natural completion, failure, or cancellation cleanup.

        After this method returns, no later provider event may be yielded. Waiting does not request
        cancellation and is safe to repeat.
        """
        ...

    async def force_cancel_cleanup(self) -> None:
        """Authoritatively stop and reap operation-owned work after cleanup grace expires.

        This session-only escape hatch is distinct from ordinary cancellation. Implementations
        must cancel and await every operation-owned cleanup or SDK task without shielding, close
        the event stream logically, and prevent later events. Returning confirms only that no
        local provider-owned task can continue; it does not claim that remote resources closed.

        The method is idempotent and safe before, during, or after :meth:`cancel` and
        :meth:`wait_closed`. Caller cancellation must propagate.
        """
        ...


@runtime_checkable
class Provider(Protocol):
    """Start provider operations without exposing SDK-specific values."""

    def start(self, request: ProviderRequest) -> ProviderOperation:
        """Create one lazy provider operation for a harness-owned request.

        Concrete adapters perform network work only while the returned event stream is consumed;
        constructing the operation itself must not leak provider objects into the caller.

        Args:
            request: Immutable provider-neutral input for one model turn.

        Returns:
            A single-use operation whose stream and cleanup the caller owns.
        """
        ...


__all__ = [
    "Provider",
    "ProviderCancellationResult",
    "ProviderOperation",
]
