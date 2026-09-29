"""Cirq runtime: real execution of user circuits via the shared sandbox path."""
from __future__ import annotations

from backend.models import ExecutionResult
from backend.runtimes._exec import execute_in_sandbox
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits


class CirqRuntime(QuantumRuntime):
    name = "cirq"
    probe_imports = ("cirq",)
    version_module = "cirq"

    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        return execute_in_sandbox(code, limits)
