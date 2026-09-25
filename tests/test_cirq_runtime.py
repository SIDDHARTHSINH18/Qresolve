"""Tests for the Cirq runtime: real subprocess execution, error capture,
sandbox isolation, knowledge-base diagnosis, and end-to-end fix/verify.

All tests run offline and deterministically; the AI provider is mocked.
Tests that need Cirq installed are skipped cleanly when it is absent, so the
suite still passes on environments without the optional dependency.
"""
import pytest

from backend.analyzer import detect_framework, error_from_execution
from backend.diagnostics import classify
from backend.models import SolveRequest
from backend.providers.base import AIProvider, ProviderResponse
from backend.reasoning.adaptive import AdaptiveController
from backend.runtimes import CirqRuntime, all_runtimes, get_runtime
from backend.sandbox.limits import SandboxLimits

cirq_available = CirqRuntime().is_available()
requires_cirq = pytest.mark.skipif(not cirq_available, reason="cirq-core not installed")

VALID_CODE = (
    "import cirq\n"
    "q = cirq.LineQubit(0)\n"
    "c = cirq.Circuit(cirq.X(q), cirq.measure(q, key='result'))\n"
    "r = cirq.Simulator().run(c, repetitions=10)\n"
    "print(r)\n"
)

# CNOT applied to the same qubit twice -> ValueError: Duplicate qids (line 3)
BROKEN_CODE = (
    "import cirq\n"
    "q = cirq.LineQubit(0)\n"
    "c = cirq.Circuit(cirq.CNOT(q, q))\n"
    "print(c)\n"
)

FIXED_CODE = (
    "import cirq\n"
    "q0, q1 = cirq.LineQubit.range(2)\n"
    "c = cirq.Circuit(cirq.CNOT(q0, q1))\n"
    "print(c)\n"
)


@pytest.fixture(scope="module")
def runtime():
    rt = CirqRuntime()
    if not rt.is_available():
        pytest.skip("cirq-core must be installed for Cirq runtime tests")
    return rt


# ------------------------------------------------------- registry / detector
def test_cirq_registered_in_runtime_registry():
    assert "cirq" in all_runtimes()
    rt = get_runtime("cirq")
    assert isinstance(rt, CirqRuntime)
    assert get_runtime("CIRQ") is rt  # case-insensitive like the rest


def test_detector_selects_cirq():
    assert detect_framework(VALID_CODE)[0] == "cirq"
    assert detect_framework(BROKEN_CODE)[0] == "cirq"


@requires_cirq
def test_runtime_version(runtime):
    version = runtime.version()
    assert version and version.count(".") >= 1


# ----------------------------------------------------------------- execution
@requires_cirq
def test_valid_circuit_executes(runtime):
    result = runtime.execute(VALID_CODE)
    assert result.success is True
    assert result.exception_type is None
    assert result.traceback_text is None
    assert "result=" in result.stdout           # measurement key captured
    assert result.execution_time_ms is not None and result.execution_time_ms > 0


@requires_cirq
def test_unicode_circuit_output_captured(runtime):
    """Cirq prints box-drawing characters; UTF-8 capture must not crash."""
    result = runtime.execute("import cirq\nprint(cirq.Circuit(cirq.X(cirq.LineQubit(0))))\n")
    assert result.success is True
    assert result.exception_type is None
    assert result.stdout.strip() != ""


@requires_cirq
def test_runtime_error_captured(runtime):
    result = runtime.execute(BROKEN_CODE)
    assert result.success is False
    assert result.exception_type == "ValueError"
    assert "Duplicate qids" in result.exception_message
    assert result.traceback_text and "user_code.py" in result.traceback_text
    # error really originates on line 3 (the CNOT construction)
    assert "line 3" in result.traceback_text
    assert result.execution_time_ms is not None


@requires_cirq
def test_import_failure_is_structured_not_crash(runtime):
    """A missing module is captured as a structured failure, never a crash."""
    result = runtime.execute("import definitely_not_a_real_module\n")
    assert result.success is False
    assert result.exception_type == "ModuleNotFoundError"


@requires_cirq
def test_timeout_enforced(runtime):
    result = runtime.execute("while True:\n    pass\n", limits=SandboxLimits(timeout_s=3.0))
    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()


# ------------------------------------------------------------ sandbox safety
@requires_cirq
def test_sandbox_scrubs_environment_secrets(runtime, monkeypatch):
    """Secrets held by the API process must never reach executed quantum code."""
    monkeypatch.setenv("QRESOLVE_AI_API_KEY", "sk-should-not-leak")
    code = "import os\nprint('KEY=' + repr(os.environ.get('QRESOLVE_AI_API_KEY')))\n"
    result = runtime.execute(code)
    assert result.success is True
    assert "KEY=None" in result.stdout
    assert "sk-should-not-leak" not in result.stdout


@requires_cirq
def test_sandbox_runs_in_isolated_temp_dir(runtime):
    import os
    code = "import os\nprint('CWD=' + os.getcwd())\n"
    result = runtime.execute(code)
    assert result.success is True
    cwd = result.stdout.split("CWD=", 1)[1].strip()
    assert "qresolve-sandbox" in cwd
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assert not cwd.lower().startswith(project_root.lower())  # not the project tree


# ------------------------------------------------- knowledge-base diagnosis
@requires_cirq
@pytest.mark.parametrize(
    "code, expected_category",
    [
        (BROKEN_CODE, "cirq_duplicate_qids"),
        ("import cirq\na, b = cirq.LineQubit.range(2)\nc = cirq.Circuit(cirq.CX(a))\n", "cirq_wrong_qubit_count"),
        ("import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.X(q))\nr = cirq.Simulator().run(c, repetitions=5)\nprint(r)\n", "cirq_no_measurements"),
        ("import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.Moment(cirq.X(q), cirq.Z(q)))\n", "cirq_overlapping_operations"),
        ("import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.XYZ(q))\n", "cirq_unknown_attribute"),
    ],
)
def test_cirq_error_patterns_diagnosed(runtime, code, expected_category):
    result = runtime.execute(code)
    assert result.success is False, f"expected real failure for {expected_category}"
    error = error_from_execution(result, code)
    diagnosis = classify(error)
    assert diagnosis.category == expected_category
    assert diagnosis.hypotheses, "each pattern must yield at least one hypothesis"


# --------------------------------------------- end-to-end fix/verify (mocked AI)
class _ScriptedProvider(AIProvider):
    name = "scripted-cirq"

    def __init__(self, patched_code: str):
        self._patched = patched_code

    @property
    def model_id(self) -> str:
        return "scripted-cirq"

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        return ProviderResponse(
            model=self.model_id,
            content={
                "hypothesis": "CNOT was given the same qubit twice.",
                "diagnosis": "Duplicate qids in a two-qubit gate.",
                "proposed_fix": "Apply CNOT to two distinct qubits.",
                "patched_code": self._patched,
                "reasoning_summary": "Distinct LineQubits satisfy the gate's unique-qid contract.",
                "evidence": ["ValueError: Duplicate qids for <cirq.CNOT>."],
                "confidence": 0.9,
                "next_action": "apply_fix",
            },
            raw_text="",
        )


@requires_cirq
def test_end_to_end_solve_verifies_ai_fix(runtime):
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(FIXED_CODE))
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.framework.framework == "cirq"
    assert response.execution.success is False          # original really failed
    assert response.diagnosis.category == "cirq_duplicate_qids"
    assert response.status == "solved"
    assert response.attempts[0].source == "ai"
    assert response.verification.verified is True       # verified by real re-execution
    assert response.verification.execution.success is True
    assert response.fix.patched_code == FIXED_CODE


@requires_cirq
def test_validator_rejects_bad_ai_fix(runtime):
    """If the AI proposes code that still fails, the validator must reject it."""
    still_broken = "import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.CNOT(q, q))\n"
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(still_broken))
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert all(a.verified is False for a in response.attempts)
    assert response.fix is None


@requires_cirq
def test_no_provider_degrades_without_crash(runtime):
    """Cirq has no heuristic auto-fixer; with no provider the controller must
    stop cleanly with a structured 'unsolved' rather than crashing."""
    controller = AdaptiveController(runtime=runtime, provider=None)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert response.diagnosis.category == "cirq_duplicate_qids"
    assert response.fix is None
