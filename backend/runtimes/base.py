"""Runtime abstraction: execute quantum code for a specific framework."""
from __future__ import annotations

from abc import ABC, abstractmethod

from backend.models import ExecutionResult
from backend.sandbox.limits import SandboxLimits


class QuantumRuntime(ABC):
    """A runtime executes user quantum code in the sandbox and reports
    exactly what happened. Implementations must never fabricate results."""

    name: str = "abstract"

    @abstractmethod
    def is_available(self) -> bool:
        """True if the framework is importable in this environment."""

    @abstractmethod
    def version(self) -> str | None:
        """Installed framework version, if available."""

    @abstractmethod
    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        """Run the code and capture success/stdout/stderr/exception/traceback/time."""
