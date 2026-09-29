"""PennyLane runtime: real execution of user programs via the shared sandbox path."""
from __future__ import annotations

from backend.models import ExecutionResult
from backend.runtimes._exec import execute_in_sandbox
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits


class PennyLaneRuntime(QuantumRuntime):
    name = "pennylane"
    probe_imports = ("pennylane",)
    version_module = "pennylane"

    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        return execute_in_sandbox(code, limits)
