"""Tests for the PennyLane runtime: real subprocess execution, error capture,
sandbox isolation, knowledge-base diagnosis, and end-to-end fix/verify.

All errors below are genuine PennyLane failures captured from real runs
(pennylane 0.45.x); no artificial exceptions. Tests skip cleanly when the
optional dependency is absent.
"""
import pytest

from backend.analyzer import detect_framework, error_from_execution
from backend.diagnostics import classify
from backend.models import SolveRequest
from backend.providers.base import AIProvider, ProviderResponse
from backend.reasoning.adaptive import AdaptiveController
from backend.runtimes import PennyLaneRuntime, all_runtimes, get_runtime
from backend.sandbox.limits import SandboxLimits

pennylane_available = PennyLaneRuntime().is_available()
requires_pennylane = pytest.mark.skipif(not pennylane_available, reason="pennylane not installed")

VALID_CODE = (
    "import pennylane as qml\n"
    "dev = qml.device('lightning.qubit', wires=2)\n"
    "@qml.qnode(dev)\n"
    "def circuit():\n"
    "    qml.Hadamard(wires=0)\n"
    "    qml.CNOT(wires=[0, 1])\n"
    "    return qml.probs(wires=[0, 1])\n"
    "print(circuit())\n"
)

# CNOT targets wire 5 on a 2-wire device -> WireError: wires not found on the device
BROKEN_CODE = (
    "import pennylane as qml\n"
    "dev = qml.device('lightning.qubit', wires=2)\n"
    "@qml.qnode(dev)\n"
    "def circuit():\n"
    "    qml.Hadamard(wires=0)\n"
    "    qml.CNOT(wires=[0, 5])\n"
    "    return qml.probs(wires=[0, 1])\n"
    "print(circuit())\n"
)

FIXED_CODE = (
    "import pennylane as qml\n"
    "dev = qml.device('lightning.qubit', wires=6)\n"
    "@qml.qnode(dev)\n"
    "def circuit():\n"
    "    qml.Hadamard(wires=0)\n"
    "    qml.CNOT(wires=[0, 5])\n"
    "    return qml.probs(wires=[0, 1])\n"
    "print(circuit())\n"
)


@pytest.fixture(scope="module")
def runtime():
    rt = PennyLaneRuntime()
    if not rt.is_available():
        pytest.skip("pennylane must be installed for PennyLane runtime tests")
    return rt


# ------------------------------------------------------- registry / detector
def test_pennylane_registered_in_runtime_registry():
    assert "pennylane" in all_runtimes()
    rt = get_runtime("pennylane")
    assert isinstance(rt, PennyLaneRuntime)
    assert get_runtime("PENNYLANE") is rt  # case-insensitive like the rest


def test_detector_selects_pennylane():
    assert detect_framework(VALID_CODE)[0] == "pennylane"
    assert detect_framework(BROKEN_CODE)[0] == "pennylane"


@requires_pennylane
def test_runtime_version(runtime):
    version = runtime.version()
    assert version and version.count(".") >= 1


# ----------------------------------------------------------------- execution
@requires_pennylane
def test_valid_circuit_executes(runtime):
    result = runtime.execute(VALID_CODE)
    assert result.success is True
    assert result.exception_type is None
    assert result.traceback_text is None
    assert "0.5" in result.stdout            # Bell-state probabilities
    assert result.execution_time_ms is not None and result.execution_time_ms > 0


@requires_pennylane
def test_runtime_error_captured(runtime):
    result = runtime.execute(BROKEN_CODE)
    assert result.success is False
    assert result.exception_type == "WireError"
    assert "wires not found on the device" in result.exception_message
    assert result.traceback_text and "user_code.py" in result.traceback_text
    # error originates from the qnode call on line 8 (raised at execution)
    assert "line 8" in result.traceback_text
    assert result.execution_time_ms is not None


@requires_pennylane
def test_import_failure_is_structured_not_crash(runtime):
    result = runtime.execute("import definitely_not_a_real_module\n")
    assert result.success is False
    assert result.exception_type == "ModuleNotFoundError"


@requires_pennylane
def test_timeout_enforced(runtime):
    result = runtime.execute("while True:\n    pass\n", limits=SandboxLimits(timeout_s=3.0))
    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()


# ------------------------------------------------------------ sandbox safety
@requires_pennylane
def test_sandbox_scrubs_environment_secrets(runtime, monkeypatch):
    monkeypatch.setenv("QRESOLVE_AI_API_KEY", "sk-should-not-leak")
    code = "import os\nprint('KEY=' + repr(os.environ.get('QRESOLVE_AI_API_KEY')))\n"
    result = runtime.execute(code)
    assert result.success is True
    assert "KEY=None" in result.stdout
    assert "sk-should-not-leak" not in result.stdout


@requires_pennylane
def test_sandbox_runs_in_isolated_temp_dir(runtime):
    import os
    code = "import os\nprint('CWD=' + os.getcwd())\n"
    result = runtime.execute(code)
    assert result.success is True
    cwd = result.stdout.split("CWD=", 1)[1].strip()
    assert "qresolve-sandbox" in cwd
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    assert not cwd.lower().startswith(project_root.lower())


# ------------------------------------------------- knowledge-base diagnosis
@requires_pennylane
@pytest.mark.parametrize(
    "code, expected_category",
    [
        (BROKEN_CODE, "pl_wire_not_on_device"),
        (
            "import pennylane as qml\n"
            "dev = qml.device('lightning.qubit', wires=2)\n"
            "@qml.qnode(dev)\n"
            "def c():\n"
            "    qml.CNOT(wires=[0, 0])\n"
            "    return qml.expval(qml.PauliZ(0))\n"
            "print(c())\n",
            "pl_duplicate_wires",
        ),
        (
            "import pennylane as qml\n"
            "dev = qml.device('lightning.qubit', wires=2)\n"
            "@qml.qnode(dev)\n"
            "def c():\n"
            "    qml.CNOT(wires=[0])\n"
            "    return qml.expval(qml.PauliZ(0))\n"
            "print(c())\n",
            "pl_wrong_number_of_wires",
        ),
        (
            "import pennylane as qml\n"
            "dev = qml.device('definitely.not.a.device', wires=2)\n"
            "print(dev)\n",
            "pl_device_not_found",
        ),
        (
            "import pennylane as qml\n"
            "dev = qml.device('default.qubit', wires=1)\n"
            "@qml.qnode(dev)\n"
            "def c():\n"
            "    qml.Hadamard(wires=0)\n"
            "    qml.expval(qml.PauliZ(0))\n"
            "    return 42\n"
            "print(c())\n",
            "pl_qnode_bad_return",
        ),
    ],
)
def test_pennylane_error_patterns_diagnosed(runtime, code, expected_category):
    result = runtime.execute(code)
    assert result.success is False, f"expected real failure for {expected_category}"
    error = error_from_execution(result, code)
    diagnosis = classify(error)
    assert diagnosis.category == expected_category
    assert diagnosis.hypotheses, "each pattern must yield at least one hypothesis"


# --------------------------------------------- end-to-end fix/verify (mocked AI)
class _ScriptedProvider(AIProvider):
    name = "scripted-pennylane"

    def __init__(self, patched_code: str):
        self._patched = patched_code

    @property
    def model_id(self) -> str:
        return "scripted-pennylane"

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        return ProviderResponse(
            model=self.model_id,
            content={
                "hypothesis": "The device had fewer wires than the CNOT target index.",
                "diagnosis": "Wire 5 does not exist on a 2-wire device.",
                "proposed_fix": "Allocate a device with enough wires.",
                "patched_code": self._patched,
                "reasoning_summary": "A 6-wire device makes wires=[0, 5] valid.",
                "evidence": ["WireError: wires not found on the device: {5}."],
                "confidence": 0.9,
                "next_action": "apply_fix",
            },
            raw_text="",
        )


@requires_pennylane
def test_end_to_end_solve_verifies_ai_fix(runtime):
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(FIXED_CODE))
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.framework.framework == "pennylane"
    assert response.execution.success is False          # original really failed
    assert response.diagnosis.category == "pl_wire_not_on_device"
    assert response.status == "solved"
    assert response.attempts[0].source == "ai"
    assert response.verification.verified is True       # verified by real re-execution
    assert response.verification.execution.success is True
    assert response.fix.patched_code == FIXED_CODE


@requires_pennylane
def test_validator_rejects_bad_ai_fix(runtime):
    """If the AI proposes code that still fails, the validator must reject it."""
    controller = AdaptiveController(runtime=runtime, provider=_ScriptedProvider(BROKEN_CODE))
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert all(a.verified is False for a in response.attempts)
    assert response.fix is None


@requires_pennylane
def test_no_provider_degrades_without_crash(runtime):
    """PennyLane has no heuristic auto-fixer; with no provider the controller must
    stop cleanly with a structured 'unsolved' rather than crashing."""
    controller = AdaptiveController(runtime=runtime, provider=None)
    response = controller.solve(SolveRequest(code=BROKEN_CODE))
    assert response.status == "unsolved"
    assert response.diagnosis.category == "pl_wire_not_on_device"
    assert response.fix is None
