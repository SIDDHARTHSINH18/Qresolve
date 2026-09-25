"""PennyLane runtime: real execution of user programs via the shared sandbox path."""
from __future__ import annotations

from backend.models import ExecutionResult
from backend.runtimes._exec import execute_in_sandbox
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits


class PennyLaneRuntime(QuantumRuntime):
    name = "pennylane"

    def is_available(self) -> bool:
        try:
            import pennylane  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str | None:
        try:
            import pennylane
            return pennylane.__version__
        except ImportError:
            return None

    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        return execute_in_sandbox(code, limits)
