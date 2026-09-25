"""Tests for the QResolve port policy (backend/ports.py)."""
import socket

import pytest

from backend.ports import (
    DEFAULT_BACKEND_PORT,
    ENMA_BACKEND_PORT,
    PortConflictError,
    backend_port_from_env,
    ensure_port_free,
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
        assert "never switches ports silently" in str(exc.value)
