"""Validation: a fix is judged only by executions that actually happened.

The validator sits outside the runtime adapters on purpose, so no adapter can
certify its own result. Its verdict is derived from evidence, and a run that
could not happen is reported as UNVERIFIED — never upgraded into a success and
never downgraded into "the fix is wrong".
"""
from __future__ import annotations

from backend.models import ExecutionResult, Verification, VerificationState
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits

#: Raised by the harness itself: the correction was not judged by the runtime.
_SANDBOX_FAILURE = "SandboxError"


def assess(
    patched: ExecutionResult | None,
    original: ExecutionResult | None = None,
) -> tuple[VerificationState, str]:
    """Classify a correction from the executions that were actually observed."""
    if patched is None:
        return "UNVERIFIED", "The correction was never executed, so nothing about it is verified."

    if patched.timed_out:
        return "UNVERIFIED", (
            "The sandbox stopped the correction at the execution limit; the run produced no verdict."
        )
    if patched.exception_type == _SANDBOX_FAILURE:
        return "UNVERIFIED", (
            "The sandbox could not run the correction to completion "
            f"({patched.exception_message or 'no detail'}); the result is not evidence either way."
        )
    if patched.compiled is False:
        return "FAILED_VERIFICATION", (
            f"The corrected code does not compile: {patched.exception_type}"
            f": {patched.exception_message}"
        )
    if not patched.success:
        return "FAILED_VERIFICATION", (
            f"The corrected code still fails at runtime: {patched.exception_type}"
            f": {patched.exception_message}"
        )
    if original is not None and not original.success:
        return "VERIFIED", (
            "The original failure was reproduced, then the corrected code compiled and "
            "executed with no error."
        )
    return "PARTIALLY_VERIFIED", (
        "The corrected code compiled and executed cleanly, but the reported failure was "
        "never reproduced by this runtime, so only 'it runs' is evidenced."
    )


def verify_execution(
    execution: ExecutionResult, original: ExecutionResult | None = None
) -> Verification:
    """Wrap an execution that already happened into a verdict."""
    state, reason = assess(execution, original)
    if execution.success:
        notes = "Patched code executed successfully in the sandbox."
    elif state == "UNVERIFIED":
        notes = reason
    else:
        notes = "Patched code still fails at runtime; fix not verified."
    return Verification(
        verified=execution.success,
        execution=execution,
        state=state,
        reason=reason,
        notes=notes,
    )


def verify_fix(
    runtime: QuantumRuntime,
    patched_code: str,
    *,
    original: ExecutionResult | None = None,
    limits: SandboxLimits | None = None,
) -> Verification:
    """Re-run patched code in the sandbox and classify what the run showed."""
    return verify_execution(runtime.execute(patched_code, limits=limits), original)


def verify_original(runtime: QuantumRuntime, code: str) -> ExecutionResult:
    """Execute the original code (used to reproduce the reported error)."""
    return runtime.execute(code)
