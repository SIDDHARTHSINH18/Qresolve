"""OpenQASM runtime: real parsing + simulation of OpenQASM 2.0 programs.

Supported version (documented on purpose): OpenQASM 2.0, with ``qelib1.inc``.
Programs are parsed with the already-installed Qiskit stack
(``qiskit.qasm2``) and executed on ``BasicSimulator`` — no extra dependency
stack. OpenQASM 3 is detected and reported as unsupported rather than being
partially executed; this build claims no compatibility it has not verified.

The user's QASM text is embedded into a fixed Python harness and run through
the same sandbox path as every other runtime, so there is exactly one
security boundary. Parse errors from the QASM parser report positions inside
the embedded program; ``execute`` maps those back onto the user's original
line numbers so error locations still refer to the user's QASM source.
"""
from __future__ import annotations

import re

from backend.models import ExecutionResult
from backend.runtimes._exec import execute_in_sandbox
from backend.runtimes.base import QuantumRuntime
from backend.sandbox.limits import SandboxLimits

_LOAD_MARKER = "# qresolve:qasm-load"
_VERSION_RAISE_MARKER = "# qresolve:qasm-version-raise"

_QASM3_MESSAGE = (
    "OpenQASM 3 is not supported by this QResolve build; only OpenQASM 2.0 "
    "(qelib1.inc) programs are parsed and simulated."
)

# Matches the Qiskit parser location prefix for in-memory programs,
# e.g. '"<input>":4,4: index 5 is out-of-range ...'
_PARSE_LOC_RE = re.compile(r'"?<input>"?:(\d+),(\d+):\s*(.*)', re.DOTALL)


def _build_harness(qasm: str) -> tuple[str, int, int]:
    """Return (harness source, line of the qasm2.loads call, line of the
    OpenQASM-3 raise) so parser positions can be mapped back afterwards."""
    lines = [
        '"""Generated OpenQASM 2.0 harness (QResolve). User program embedded below."""',
        "from qiskit import qasm2",
        "from qiskit.providers.basic_provider import BasicSimulator",
        "",
        f"QASM_PROGRAM = {qasm!r}",
        "",
        'if QASM_PROGRAM.lstrip().upper().startswith("OPENQASM 3"):',
        f'    raise NotImplementedError({_QASM3_MESSAGE!r})  {_VERSION_RAISE_MARKER}',
        "",
        f"_circuit = qasm2.loads(QASM_PROGRAM)  {_LOAD_MARKER}",
        '_result = BasicSimulator().run(_circuit, shots=1024).result()',
        "print(_circuit.draw(output=\"text\"))",
        "print(\"counts:\", _result.get_counts())",
    ]
    return "\n".join(lines) + "\n", 10, 8


def _map_error_positions(
    result: ExecutionResult, qasm: str, load_line: int, version_raise_line: int
) -> ExecutionResult:
    """Translate harness traceback positions back to lines of the user's QASM."""
    if result.success:
        return result
    updates: dict = {}
    tb = result.traceback_text
    if result.exception_type == "QASM2ParseError" and result.exception_message:
        m = _PARSE_LOC_RE.search(result.exception_message)
        if m:
            line, col = int(m.group(1)), int(m.group(2))
            detail = " ".join(m.group(3).split())
            updates["exception_message"] = f"line {line}, column {col}: {detail}"
            if tb:
                tb = tb.replace(
                    f'File "user_code.py", line {load_line}',
                    f'File "user_code.py", line {line}',
                )
    elif result.exception_type == "NotImplementedError" and tb:
        decl_line = next(
            (i + 1 for i, ln in enumerate(qasm.splitlines())
             if ln.strip().upper().startswith("OPENQASM 3")),
            None,
        )
        if decl_line:
            tb = tb.replace(
                f'File "user_code.py", line {version_raise_line}',
                f'File "user_code.py", line {decl_line}',
            )
    if tb is not None:
        updates["traceback_text"] = tb
    return result.model_copy(update=updates) if updates else result


class OpenQasmRuntime(QuantumRuntime):
    name = "openqasm"

    def is_available(self) -> bool:
        try:
            from qiskit import qasm2  # noqa: F401
            from qiskit.providers.basic_provider import BasicSimulator  # noqa: F401
        except ImportError:
            return False
        return True

    def version(self) -> str | None:
        try:
            import qiskit
        except ImportError:
            return None
        return f"OpenQASM 2.0 via qiskit {qiskit.__version__}"

    def execute(self, code: str, limits: SandboxLimits | None = None) -> ExecutionResult:
        harness, load_line, version_raise_line = _build_harness(code)
        result = execute_in_sandbox(harness, limits)
        return _map_error_positions(result, code, load_line, version_raise_line)
