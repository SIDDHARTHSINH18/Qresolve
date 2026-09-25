"""Validation: a proposed fix is verified only if the runtime actually
executes the patched code successfully. No shortcuts, no faked results."""
from __future__ import annotations

from backend.models import ExecutionResult, Verification
from backend.runtimes.base import QuantumRuntime


def verify_fix(runtime: QuantumRuntime, patched_code: str) -> Verification:
    """Re-run patched code in the sandbox; verified == actual success."""
    execution = runtime.execute(patched_code)
    return Verification(
        verified=execution.success,
        execution=execution,
        notes=(
            "Patched code executed successfully in the sandbox."
            if execution.success
            else "Patched code still fails at runtime; fix not verified."
        ),
    )


def verify_original(runtime: QuantumRuntime, code: str) -> ExecutionResult:
    """Execute the original code (used to reproduce the reported error)."""
    return runtime.execute(code)
