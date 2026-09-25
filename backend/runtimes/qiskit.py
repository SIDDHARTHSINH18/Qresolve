"""Qiskit runtime: real execution of user circuits via the sandbox.

The execution mechanics are framework-agnostic and live in
backend/runtimes/_exec.py, shared with the other runtimes.
"""
from __future__ import annotations

from backend.models import ExecutionResult
from backend.runtimes._exec import execute_in_sandbox
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits


class QiskitRuntime(QuantumRuntime):
    name = "qiskit"

    def is_available(self) -> bool:
        try:
            import qiskit  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str | None:
        try:
            import qiskit
            return qiskit.__version__
        except ImportError:
            return None

    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        return execute_in_sandbox(code, limits)
