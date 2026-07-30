"""Disable Python socket clients during the repository validation gate."""

from __future__ import annotations

import socket
from typing import NoReturn

MESSAGE = "Network access is disabled by ./scripts/check"


def _deny_network(*args: object, **kwargs: object) -> NoReturn:
    """Reject a Python networking operation before it reaches the operating system."""
    del args, kwargs
    raise RuntimeError(MESSAGE)


socket.create_connection = _deny_network
socket.getaddrinfo = _deny_network
socket.getfqdn = _deny_network
socket.gethostbyaddr = _deny_network
socket.gethostbyname = _deny_network
socket.gethostbyname_ex = _deny_network
socket.getnameinfo = _deny_network
socket.socket.connect = _deny_network
socket.socket.connect_ex = _deny_network
socket.socket.sendto = _deny_network
if hasattr(socket.socket, "sendmsg"):
    socket.socket.sendmsg = _deny_network
