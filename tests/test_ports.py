"""Tests for the QResolve port policy (backend/ports.py)."""
import os
import socket
import subprocess
import time

import pytest

from backend.ports import (
    BACKEND_HOST,
    DEFAULT_BACKEND_PORT,
    ENMA_BACKEND_PORT,
    PortConflictError,
    backend_port_from_env,
    ensure_port_free,
    parse_netstat_listeners,
)


def test_default_ports_are_dedicated_and_disjoint_from_enma():
    assert DEFAULT_BACKEND_PORT != ENMA_BACKEND_PORT
    assert ENMA_BACKEND_PORT == 8000
    assert backend_port_from_env({}) == DEFAULT_BACKEND_PORT


def test_env_override_is_respected():
    assert backend_port_from_env({"QRESOLVE_BACKEND_PORT": "8450"}) == 8450


def test_port_8000_is_refused_with_clear_reason():
    with pytest.raises(PortConflictError) as exc:
        backend_port_from_env({"QRESOLVE_BACKEND_PORT": "8000"})
    assert "ENMA" in str(exc.value)


@pytest.mark.parametrize("value", ["not-a-port", "0", "70000"])
def test_invalid_env_values_fail_clearly(value):
    with pytest.raises(PortConflictError):
        backend_port_from_env({"QRESOLVE_BACKEND_PORT": value})


def test_ensure_port_free_accepts_an_unused_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    ensure_port_free(free_port)  # must not raise


def test_ensure_port_free_detects_a_live_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        with pytest.raises(PortConflictError) as exc:
            ensure_port_free(port)
        assert str(port) in str(exc.value)
        assert "already being used" in str(exc.value)
        assert "Close the application using this port" in str(exc.value)
        assert "never switches ports silently" in str(exc.value)


_NETSTAT_SAMPLE = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    127.0.0.1:135          0.0.0.0:0              LISTENING       1104
  TCP    127.0.0.1:8321         127.0.0.1:62349        TIME_WAIT       0
  TCP    127.0.0.1:62349        127.0.0.1:8321         TIME_WAIT       0
  TCP    127.0.0.1:8321         0.0.0.0:0              LISTENING       4321
  TCP    0.0.0.0:8321           0.0.0.0:0              LISTENING       4321
  TCP    [::]:8321              [::]:0                 LISTENING       4321
  TCP    127.0.0.1:83210        0.0.0.0:0              LISTENING       99
  TCP    127.0.0.1:5321         127.0.0.1:5322         ESTABLISHED     777
  UDP    0.0.0.0:5353           *:*                                    1234
"""


def test_parse_counts_only_real_listening_sockets():
    assert parse_netstat_listeners(_NETSTAT_SAMPLE, 8321, "127.0.0.1") == [4321, 4321, 4321]


def test_parse_time_wait_rows_are_never_a_conflict():
    # same output minus the LISTENING rows -> port must be considered free
    text = "\n".join(ln for ln in _NETSTAT_SAMPLE.splitlines() if "LISTENING" not in ln)
    assert parse_netstat_listeners(text, 8321, "127.0.0.1") == []


def test_parse_matches_exact_port_not_prefix():
    # a listener on 83210 must not look like a listener on 8321
    assert parse_netstat_listeners(_NETSTAT_SAMPLE, 8321, "127.0.0.1") == [4321, 4321, 4321]
    assert parse_netstat_listeners(_NETSTAT_SAMPLE, 83210, "127.0.0.1") == [99]


def test_parse_ignores_foreign_bind_addresses():
    # only our host or a wildcard may conflict with a 127.0.0.1 bind
    text = "  TCP    10.1.2.3:8321          0.0.0.0:0              LISTENING       55"
    assert parse_netstat_listeners(text, 8321, "127.0.0.1") == []


@pytest.mark.skipif(os.name != "nt", reason="Windows path: netstat-based LISTENING check")
def test_time_wait_residue_does_not_block_startup():
    """M6 s4/s16: after a previous instance dies, its leftover TIME_WAIT rows
    (the shape '127.0.0.1:<ephemeral> -> 127.0.0.1:<port> TIME_WAIT') must not
    be reported as a conflict."""
    listener = socket.socket()
    listener.bind((BACKEND_HOST, 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = socket.create_connection((BACKEND_HOST, port), timeout=3)
    server_sock, _ = listener.accept()
    listener.close()
    # close both sides gracefully so TIME_WAIT is left on the port itself
    server_sock.settimeout(3)
    try:
        server_sock.shutdown(socket.SHUT_WR)
        while client.recv(4096):
            pass
    except (OSError, TimeoutError):
        pass
    server_sock.close()
    client.close()
    time.sleep(0.2)

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    out = subprocess.run(
        ["netstat", "-ano"], capture_output=True, text=True, timeout=10, creationflags=flags
    ).stdout
    rows = [
        ln for ln in out.splitlines()
        if ln.strip().upper().startswith("TCP")
        and f":{port}" in ln and "TIME_WAIT" in ln.upper()
    ]
    assert rows, "test setup failed to produce TIME_WAIT residue"
    assert not [ln for ln in out.splitlines() if f":{port}" in ln and "LISTENING" in ln.upper()]
    ensure_port_free(port, BACKEND_HOST)  # must NOT raise despite TIME_WAIT
