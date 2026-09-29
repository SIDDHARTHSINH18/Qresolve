"""Runtime abstraction shared by every framework adapter.

One contract per framework: say what it actually is (does the framework
import, which version) and execute user code in the sandbox. Verification is
deliberately NOT part of this interface — it lives in backend/validation so no
adapter can certify its own result, and implementations must never fabricate
what they did not run.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module

from backend.models import ExecutionResult
from backend.sandbox.limits import SandboxLimits


class QuantumRuntime(ABC):
    name: str = "abstract"

    #: Modules that must import cleanly for this runtime to be usable.
    probe_imports: tuple[str, ...] = ()

    #: Module whose ``__version__`` identifies the runtime.
    version_module: str | None = None

    @abstractmethod
    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        """Run the code and capture success/stdout/stderr/exception/traceback/time."""

    # ------------------------------------------------------------------
    # Availability, measured rather than assumed.
    # ------------------------------------------------------------------
    def import_probe(self) -> tuple[bool, str | None]:
        """Return ``(available, version)`` for this process.

        Any exception during import counts as unavailable, not only
        ImportError: a native extension blocked by an application-control
        policy leaves a half-initialised package whose next import can raise
        TypeError, and such a framework must never be reported as working.
        """
        for module in self.probe_imports:
            try:
                import_module(module)
            except BaseException:
                return False, None
        return True, self._read_version()

    def _read_version(self) -> str | None:
        if not self.version_module:
            return None
        try:
            version = getattr(import_module(self.version_module), "__version__", None)
        except BaseException:
            return None
        return str(version) if version else None

    def is_available(self) -> bool:
        return self.import_probe()[0]

    def version(self) -> str | None:
        return self.import_probe()[1]

    def sandbox_probe(self, limits: SandboxLimits | None = None) -> dict:
        """Availability inside the interpreter that will actually run code.

        The packaged app executes user code in a bundled interpreter that is
        not the one serving the API, so host-side availability can disagree
        with what the sandbox can really do. Callers that need the executing
        truth (the local CLI) use this; it is cached per interpreter.
        """
        from backend.runtimes._exec import probe_framework

        return probe_framework(self.probe_imports, self.version_module, limits)
