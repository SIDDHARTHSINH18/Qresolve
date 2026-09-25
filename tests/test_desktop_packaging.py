"""Tests for the desktop packaging support: port/interpreter policy invariants.

The packaged app pins the sandbox interpreter via QRESOLVE_SANDBOX_PYTHON
(frozen builds) — these tests lock in that the mechanism cannot leak into
executed user code and cannot be hijacked by a nonexistent path.
"""
import sys

from backend.sandbox.executor import _ENV_ALLOWLIST, _interpreter


def test_no_qresolve_variables_reach_the_sandbox_environment():
    assert not [k for k in _ENV_ALLOWLIST if k.startswith("QRESOLVE")]


def test_interpreter_defaults_to_current_python(monkeypatch):
    monkeypatch.delenv("QRESOLVE_SANDBOX_PYTHON", raising=False)
    assert _interpreter() == sys.executable


def test_pinned_interpreter_is_used_only_when_it_exists(monkeypatch, tmp_path):
    real = sys.executable
    monkeypatch.setenv("QRESOLVE_SANDBOX_PYTHON", real)
    assert _interpreter() == real
    monkeypatch.setenv("QRESOLVE_SANDBOX_PYTHON", str(tmp_path / "nope" / "python.exe"))
    assert _interpreter() == sys.executable  # stale pin must not break execution


def test_frontend_is_served_same_origin_by_design():
    """The desktop app mounts the built UI on the API port; the frontend API
    layer uses same-origin relative paths, so no host is hard-wired."""
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "qresolve.js"
    text = src.read_text(encoding="utf-8")
    assert "8000" not in text and "localhost" not in text
