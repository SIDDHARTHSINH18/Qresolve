"""Tests for the OpenQASM runtime: real parsing/simulation of OpenQASM 2.0
via the installed Qiskit stack, user-line error mapping, knowledge-base
diagnosis, and end-to-end fix/verify.

All failures below are genuine parser/simulator errors captured from real
runs; OpenQASM 3 handling is asserted to be an honest 'unsupported'
structured failure, not a partial execution.
"""
import pytest

from backend.analyzer import detect_framework, error_from_execution
from backend.diagnostics import classify
from backend.models import SolveRequest
from backend.providers.base import AIProvider, ProviderResponse
from backend.reasoning.adaptive import AdaptiveController
from backend.runtimes import OpenQasmRuntime, all_runtimes, get_runtime

openqasm_available = OpenQasmRuntime().is_available()
requires_openqasm = pytest.mark.skipif(
    not openqasm_available, reason="qiskit qasm2/BasicSimulator must be importable"
)

VALID_QASM = (
    'OPENQASM 2.0;\n'
    'include "qelib1.inc";\n'
    'qreg q[2];\n'
    'creg c[2];\n'
    'h q[0];\n'
    'cx q[0],q[1];\n'
    'measure q->c;\n'
)

# h applied to q[5] on a 2-qubit register -> parse error at line 4
BROKEN_QASM = (
    'OPENQASM 2.0;\n'
    'include "qelib1.inc";\n'
    'qreg q[2];\n'
    'h q[5];\n'
)

FIXED_QASM = BROKEN_QASM.replace("h q[5];", "h q[1];")

# Undeclared gate -> parser error
BAD_GATE_QASM = (
    'OPENQASM 2.0;\n'
    'include "qelib1.inc";\n'
    'qreg q[2];\n'
    'hadd q[0];\n'
)

QASM3_PROGRAM = (
    'OPENQASM 3.0;\n'
    'include "stdgates.inc";\n'
    'qubit[2] q;\n'
    'h q[0];\n'
)


@pytest.fixture(scope="module")
def runtime():
    rt = OpenQasmRuntime()
    if not rt.is_available():
        pytest.skip("the OpenQASM stack (qiskit qasm2 + BasicSimulator) must be importable")
    return rt


# ------------------------------------------------------- registry / detector
def test_openqasm_registered_in_runtime_registry():
    assert "openqasm" in all_runtimes()
    rt = get_runtime("openqasm")
    assert isinstance(rt, OpenQasmRuntime)
    assert get_runtime("OpenQASM") is rt


def test_detector_selects_openqasm():
    assert detect_framework(VALID_QASM)[0] == "openqasm"
    assert detect_framework(BROKEN_QASM)[0] == "openqasm"


@requires_openqasm
def test_supported_version_is_documented(runtime):
    version = runtime.version()
    assert version and version.startswith("OpenQASM 2.0")


# ----------------------------------------------------------------- execution
@requires_openqasm
def test_valid_bell_program_executes(runtime):
    result = runtime.execute(VALID_QASM)
    assert result.success is True
    assert result.exception_type is None
    # Bell state: only correlated outcomes appear
    counts_line = [ln for ln in result.stdout.splitlines() if ln.startswith("counts:")]
    assert counts_line, result.stdout
    keys = {"'00'", "'11'", "00", "11"}
    assert any(k.strip("'") in counts_line[0] for k in keys)


@requires_openqasm
def test_parse_error_maps_to_user_line(runtime):
    result = runtime.execute(BROKEN_QASM)
    assert result.success is False
    assert result.exception_type == "QASM2ParseError"
    # message is normalized to the position inside the user's QASM source
    assert result.exception_message.startswith("line 4")
    assert "out-of-range" in result.exception_message
    # traceback frames reference user_code.py at the *QASM* line, not the harness
    assert 'File "user_code.py", line 4' in result.traceback_text
    error = error_from_execution(result, BROKEN_QASM)
    assert error.line_number == 4
    assert "h q[5]" in error.source_snippet


@requires_openqasm
def test_openqasm3_is_honestly_unsupported(runtime):
    result = runtime.execute(QASM3_PROGRAM)
    assert result.success is False
    assert result.exception_type == "NotImplementedError"
    assert "OpenQASM 3 is not supported" in result.exception_message
    assert 'File "user_code.py", line 1' in result.traceback_text


# ------------------------------------------------- knowledge-base diagnosis
@requires_openqasm
@pytest.mark.parametrize(
    "code, expected_category",
    [
        (BROKEN_QASM, "qasm2_parse_error"),
        (BAD_GATE_QASM, "qasm2_parse_error"),
        (QASM3_PROGRAM, "qasm_version_unsupported"),
    ],
)
def test_openqasm_error_patterns_diagnosed(runtime, code, expected_category):
    result = runtime.execute(code)
    assert result.success is False, f"expected real failure for {expected_category}"
    error = error_from_execution(result, code)
    diagnosis = classify(error)
    assert diagnosis.category == expected_category
    assert diagnosis.hypotheses, "each pattern must yield at least one hypothesis"


# ------------------------------------------------------------ sandbox safety
def test_openqasm_shares_the_single_sandbox_path(monkeypatch):
    """The QASM runtime must not build its own execution path: user QASM is
    embedded into a harness and delegated to the one shared sandbox."""
    import backend.runtimes.openqasm as oq

    captured = {}

    def fake_execute_in_sandbox(code, limits=None):
        captured["code"] = code
        from backend.models import ExecutionResult
        return ExecutionResult(success=True, stdout="counts: {}")

    monkeypatch.setattr(oq, "execute_in_sandbox", fake_execute_in_sandbox)
    qasm = 'OPENQASM 2.0;\nqreg q[1];\nh q[0];\n'
    result = OpenQasmRuntime().execute(qasm)
    harness = captured["code"]
    assert "qasm2.loads(QASM_PROGRAM)" in harness     # parsed for real execution
    assert repr(qasm) in harness                      # user program embedded verbatim
    assert "subprocess" not in harness and "os.system" not in harness
    assert result.success is True


# --------------------------------------------- end-to-end fix/verify (mocked AI)
class _ScriptedProvider(AIProvider):
    name = "scripted-openqasm"

    def __init__(self, patched_code: str):
        self._patched = patched_code

    @property
    def model_id(self) -> str:
        return "scripted-openqasm"

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        return ProviderResponse(
            model=self.model_id,
            content={
                "hypothesis": "The gate index 5 exceeds the declared 2-qubit register.",
                "diagnosis": "q[5] is out of range for qreg q[2].",
                "proposed_fix": "Use an index within the declared register.",
                "patched_code": self._patched,
                "reasoning_summary": "h q[1] stays inside the declared register.",
                "evidence": ["line 4: index 5 is out-of-range for register 'q' of size 2"],
                "confidence": 0.9,
                "next_action": "apply_fix",
            },
            raw_text="",
        )


@requires_openqasm
def test_end_to_end_solve_verifies_ai_fix(runtime):
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(FIXED_QASM))
    response = controller.solve(SolveRequest(code=BROKEN_QASM))
    assert response.framework.framework == "openqasm"
    assert response.execution.success is False          # original really failed
    assert response.diagnosis.category == "qasm2_parse_error"
    assert response.status == "solved"
    assert response.attempts[0].source == "ai"
    assert response.verification.verified is True       # verified by real re-execution
    assert response.verification.execution.success is True
    assert response.fix.patched_code == FIXED_QASM


@requires_openqasm
def test_validator_rejects_bad_ai_fix(runtime):
    """A patch that keeps the invalid index must be rejected by real execution."""
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(BROKEN_QASM))
    response = controller.solve(SolveRequest(code=BROKEN_QASM))
    assert response.status == "unsolved"
    assert all(a.verified is False for a in response.attempts)
    assert response.fix is None


@requires_openqasm
def test_no_provider_degrades_without_crash(runtime):
    """OpenQASM has no heuristic auto-fixer; with no provider the controller must
    stop cleanly with a structured 'unsolved' rather than crashing."""
    controller = AdaptiveController(runtime=runtime, provider=None)
    response = controller.solve(SolveRequest(code=BROKEN_QASM))
    assert response.status == "unsolved"
    assert response.diagnosis.category == "qasm2_parse_error"
    assert response.fix is None
