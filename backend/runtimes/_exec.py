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
from backend.sandbox.executor import run_files, run_python_code, sandbox_interpreter
from backend.sandbox.limits import MAX_TIMEOUT_S, SandboxLimits

_RESULT_FILE = "result.json"
_USER_FILE = "user_code.py"

# Runner executed inside the sandbox. It execs the user's code with a stable
# filename so tracebacks reference "user_code.py" line numbers, captures the
# exception, and writes a structured result file. `compiled` is recorded
# separately from `success` so a syntax error can never be reported as a
# runtime failure and vice versa.
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
    "compiled": False,
    "exception_type": None,
    "exception_message": None,
    "traceback": None,
}}

try:
    with open({_USER_FILE!r}, "r", encoding="utf-8") as _f:
        _src = _f.read()
    _code = compile(_src, {_USER_FILE!r}, "exec")
    result["compiled"] = True
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
        # Nothing was measured, so `compiled` stays unknown rather than False.
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
        compiled=payload.get("compiled"),
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


# --------------------------------------------------------------------- probe
_PROBE_PREFIX = "__QRESOLVE_PROBE__"

_PROBE_SCRIPT = '''
import json, sys

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

report = {{"available": False, "version": None, "error": None}}
try:
    for _module in {imports!r}:
        __import__(_module)
    report["available"] = True
    _versioned = {version_module!r}
    if _versioned:
        report["version"] = str(getattr(__import__(_versioned), "__version__", "") or "") or None
except BaseException as _exc:
    report["error"] = f"{{type(_exc).__name__}}: {{_exc}}"

print({prefix!r} + json.dumps(report, ensure_ascii=False))
'''

_PROBE_CACHE: dict[tuple, dict] = {}


def probe_framework(
    imports: tuple[str, ...],
    version_module: str | None = None,
    limits: SandboxLimits | None = None,
) -> dict:
    """Ask the executing interpreter whether a framework really imports.

    A cold import of a heavy framework can exceed the default user timeout, so
    an unbounded probe uses the maximum budget; the answer is cached per
    interpreter. Failure is reported as unavailable plus the real error text —
    never as available.
    """
    interpreter = sandbox_interpreter()
    key = (interpreter, tuple(imports), version_module)
    cached = _PROBE_CACHE.get(key)
    if cached is not None:
        return dict(cached)

    limits = limits or SandboxLimits(timeout_s=MAX_TIMEOUT_S)
    script = _PROBE_SCRIPT.format(
        imports=list(imports), version_module=version_module, prefix=_PROBE_PREFIX
    )
    result = run_python_code(script, limits=limits)

    report = {"available": False, "version": None, "error": None,
              "interpreter": interpreter, "probe_time_ms": result.execution_time_ms}
    line = next(
        (ln for ln in reversed(result.stdout.splitlines()) if ln.startswith(_PROBE_PREFIX)),
        None,
    )
    if line is None:
        report["error"] = (
            f"probe produced no answer (exit_code={result.exit_code}, "
            f"timed_out={result.timed_out})"
        )
    else:
        try:
            payload = json.loads(line[len(_PROBE_PREFIX):])
        except json.JSONDecodeError as exc:
            payload = {"available": False, "error": f"unparsable probe answer: {exc}"}
        report["available"] = bool(payload.get("available"))
        report["version"] = payload.get("version")
        report["error"] = payload.get("error")

    _PROBE_CACHE[key] = dict(report)
    return report


def clear_probe_cache() -> None:
    """Forget cached framework probes (used when the interpreter changes)."""
    _PROBE_CACHE.clear()
