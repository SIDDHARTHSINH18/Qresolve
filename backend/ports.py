"""QResolve network port policy — single source of truth.

Port allocation (documented, never chosen silently at runtime):
- 8000  RESERVED for the foreign ENMA backend. QResolve must never bind it.
- 8321  QResolve FastAPI backend (127.0.0.1 only).
- 5321  QResolve Vite dev frontend (strictPort; never drifts).

If a QResolve port is taken, the launcher fails with an actionable error
naming the port; it does NOT silently pick another one.
"""
from __future__ import annotations

import os
import socket

ENMA_BACKEND_PORT = 8000          # owned by another project — never bind
DEFAULT_BACKEND_PORT = 8321
DEFAULT_FRONTEND_DEV_PORT = 5321
BACKEND_HOST = "127.0.0.1"        # loopback only; never 0.0.0.0

_PORT_ENV = "QRESOLVE_BACKEND_PORT"


class PortConflictError(RuntimeError):
    """Raised when the requested port is in use or reserved for another app."""


def backend_port_from_env(env: dict[str, str] | None = None) -> int:
    """Resolve the backend port from QRESOLVE_BACKEND_PORT (default 8321).

    Port 8000 is refused explicitly: it belongs to ENMA and a mis-set
    environment variable must not cause a silent collision.
    """
    raw = (env if env is not None else os.environ).get(_PORT_ENV, "").strip()
    if not raw:
        return DEFAULT_BACKEND_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise PortConflictError(f"{_PORT_ENV}={raw!r} is not a valid port number") from exc
    if port == ENMA_BACKEND_PORT:
        raise PortConflictError(
            f"Port {ENMA_BACKEND_PORT} is reserved for the ENMA backend. "
            f"QResolve must not use it; pick another {_PORT_ENV} (default {DEFAULT_BACKEND_PORT})."
        )
    if not (1 <= port <= 65535):
        raise PortConflictError(f"{_PORT_ENV}={port} is outside the valid port range")
    return port


def ensure_port_free(port: int, host: str = BACKEND_HOST) -> None:
    """Fail loudly, with the port named, if something already listens on it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        try:
            probe.connect((host, port))
        except OSError:
            return  # connection refused / unreachable -> port is free
    raise PortConflictError(
        f"Port {port} on {host} is already in use by another process. "
        f"QResolve never switches ports silently: stop that process or set "
        f"{_PORT_ENV} to a dedicated free port."
    )
