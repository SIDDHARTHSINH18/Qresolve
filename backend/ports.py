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
import subprocess

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


_ADDR_WILDCARDS = {"0.0.0.0", "::", "[::]"}


def _endpoint_addr_port(local_addr: str) -> tuple[str, int] | None:
    """Split a netstat local endpoint ('127.0.0.1:8321', '[::]:8321') -> ('127.0.0.1', 8321)."""
    head, sep, tail = local_addr.rpartition(":")
    if not sep or not tail.isdigit():
        return None
    return head, int(tail)


def parse_netstat_listeners(text: str, port: int, host: str) -> list[int]:
    """PIDs of real LISTENING sockets bound where our bind of host:port would fail.

    Only the LISTENING state counts. TIME_WAIT / CLOSE_WAIT / ESTABLISHED rows
    are residue of past or open connections (QResolve's own health checks and
    browser tabs leave 'ephemeral -> 8321 TIME_WAIT' rows for minutes) and must
    never be read as a conflict.
    """
    pids: list[int] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP":
            continue
        if parts[3].upper() != "LISTENING":
            continue
        endpoint = _endpoint_addr_port(parts[1])
        if endpoint is None or endpoint[1] != port:
            continue
        if endpoint[0] not in _ADDR_WILDCARDS and endpoint[0] != host:
            continue
        pids.append(int(parts[-1]) if parts[-1].isdigit() else -1)
    return pids


def _blocking_listener_pids(port: int, host: str) -> list[int]:
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash from a GUI exe
        try:
            proc = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10, creationflags=flags,
            )
        except (OSError, subprocess.TimeoutExpired):
            proc = None  # netstat unavailable -> bind-probe fallback below
        if proc is not None and proc.returncode == 0:
            return parse_netstat_listeners(proc.stdout, port, host)
    # POSIX / netstat-unavailable: a plain bind fails iff a live listener (not
    # TIME_WAIT residue) holds the port; we immediately release it.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
        except OSError:
            return [-1]
    return []


def ensure_port_free(port: int, host: str = BACKEND_HOST) -> None:
    """Fail loudly if another process is LISTENING on port; TIME_WAIT never blocks.

    The M5 implementation probed with connect(), which raced with a listener
    that was shutting down (Windows briefly completes the handshake) and
    reported a false 'already in use' while only TIME_WAIT rows remained.
    """
    pids = _blocking_listener_pids(port, host)
    if not pids:
        return
    owner = next((p for p in pids if p > 0), None)
    by = f" by another application (PID {owner})" if owner else " by another application"
    raise PortConflictError(
        f"Port {port} is already being used{by}.\n"
        "Close the application using this port and try again.\n"
        "QResolve never switches ports silently."
    )
