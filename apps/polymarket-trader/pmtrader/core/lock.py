"""Single-instance lock via an exclusively-bound localhost socket.

A held TCP bind dies with its process, so there is no stale-lockfile problem:
if the process is gone, the port is free. Two trader processes sharing one
SQLite DB / heartbeat / dashboard port silently corrupt the burn-in, so the
second instance must refuse to start.
"""
from __future__ import annotations

import socket
from typing import Optional

TRADER_LOCK_PORT = 8763   # held by `python -m pmtrader`
WATCHDOG_LOCK_PORT = 8764  # held by watchdog.py


def acquire_single_instance_lock(port: int) -> Optional[socket.socket]:
    """Bind 127.0.0.1:<port> exclusively. Returns the held socket (keep a
    reference for the process lifetime) or None if another instance holds it."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        return None
    return sock
