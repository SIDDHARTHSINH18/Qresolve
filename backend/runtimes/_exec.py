"""Framework-agnostic sandbox execution shared by quantum runtimes.

Runs user code in the sandboxed subprocess via an exec-runner that captures
success/exception/traceback into a structured result file, then normalizes
it into an ExecutionResult. No framework-specific logic lives here — every
runtime delegates to this single sandbox path, so there is exactly one
security boundary.
"""
from __future__ import annotations

import json

from backend.models import ExecutionResult
from backend.sandbox.executor import run_files
from backend.sandbox.limits import SandboxLimits

_RESULT_FILE = "result.json"
_USER_FILE = "user_code.py"

# Runner executed inside the sandbox. It execs the user's code with a stable
# filename so tracebacks reference "user_code.py" line numbers, captures the
# exception, and writes a structured result file.
_RUNNER = f'''
import json
import sys
import traceback

# Isolated mode (-I) implies -E, which discards PYTHONIOENCODING, so the
# child's std streams would default to the locale codec (cp1252 on Windows)
# and raise UnicodeEncodeError on framework output such as Cirq's circuit
# diagrams. Reconfigure to UTF-8 so output capture is faithful for any
# framework. This changes only text encoding, not sandbox isolation.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

result = {{
    "success": False,
    "exception_type": None,
    "exception_message": None,
    "traceback": None,
}}

try:
    with open({_USER_FILE!r}, "r", encoding="utf-8") as _f:
        _src = _f.read()
    _code = compile(_src, {_USER_FILE!r}, "exec")
    exec(_code, {{"__name__": "__main__"}})
    result["success"] = True
except BaseException as exc:
    result["exception_type"] = type(exc).__name__
    result["exception_message"] = str(exc)
    result["traceback"] = traceback.format_exc()
finally:
    with open({_RESULT_FILE!r}, "w", encoding="utf-8") as _f:
        json.dump(result, _f)
'''


def execute_in_sandbox(code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
    """Execute user code in the sandbox and normalize the structured result."""
    limits = limits or SandboxLimits()
    sandbox = run_files(
        files={_USER_FILE: code, "runner.py": _RUNNER},
        entry="runner.py",
        limits=limits,
        collect_files=[_RESULT_FILE],
    )

    raw = sandbox.files.get(_RESULT_FILE)
    if raw is None:
        # Sandbox died before writing a result (crash, timeout, hard kill).
        return ExecutionResult(
            success=False,
            exit_code=sandbox.exit_code,
            stdout=sandbox.stdout,
            stderr=sandbox.stderr,
            execution_time_ms=sandbox.execution_time_ms,
            timed_out=sandbox.timed_out,
            output_truncated=sandbox.output_truncated,
            exception_type="SandboxError",
            exception_message=(
                "Execution produced no result "
                f"(exit_code={sandbox.exit_code}, timed_out={sandbox.timed_out})"
            ),
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ExecutionResult(
            success=False,
            stdout=sandbox.stdout,
            stderr=sandbox.stderr,
            execution_time_ms=sandbox.execution_time_ms,
            exception_type="SandboxError",
            exception_message="Could not decode runner result file",
        )

    return ExecutionResult(
        success=bool(payload.get("success")),
        exit_code=sandbox.exit_code,
        stdout=sandbox.stdout,
        stderr=sandbox.stderr,
        exception_type=payload.get("exception_type"),
        exception_message=payload.get("exception_message"),
        traceback_text=payload.get("traceback"),
        execution_time_ms=sandbox.execution_time_ms,
        timed_out=sandbox.timed_out,
        output_truncated=sandbox.output_truncated,
    )
