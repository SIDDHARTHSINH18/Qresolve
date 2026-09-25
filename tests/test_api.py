"""End-to-end API tests, including the broken-demo solve pipeline."""
from fastapi.testclient import TestClient

import pytest

from backend.main import app
from backend.providers.base import AIProvider, ProviderResponse
from backend.runtimes import CirqRuntime, OpenQasmRuntime, PennyLaneRuntime

client = TestClient(app)

BROKEN_CODE = """
from qiskit import QuantumCircuit

qc = QuantumCircuit(2)
qc.cx(0, 2)
"""

GOOD_CODE = """
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
Statevector.from_instruction(qc)
"""


def test_analyze_endpoint():
    res = client.post("/api/analyze", json={"code": BROKEN_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["framework"]["framework"] == "qiskit"


def test_analyze_with_error_input():
    res = client.post(
        "/api/analyze",
        json={
            "code": BROKEN_CODE,
            "error": {
                "traceback_text": (
                    'Traceback (most recent call last):\n  File "user_code.py", line 4, in <module>\n'
                    "    qc.cx(0, 2)\nIndexError: qubit index out of range\n"
                )
            },
        },
    )
    assert res.status_code == 200
    error = res.json()["error"]
    assert error["exception_type"] == "IndexError"
    assert error["line_number"] == 4


def test_diagnose_endpoint_runs_code():
    res = client.post("/api/diagnose", json={"code": BROKEN_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["error"] is not None
    assert body["category"] == "qubit_index_out_of_range"
    assert body["hypotheses"]


def test_run_endpoint_success():
    res = client.post("/api/run", json={"code": GOOD_CODE})
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_run_endpoint_failure():
    res = client.post("/api/run", json={"code": BROKEN_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is False
    assert body["exception_type"]
    assert body["traceback_text"]


def test_fix_endpoint():
    res = client.post("/api/fix", json={"code": BROKEN_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "proposed"
    assert body["fix"]["strategy"] in ("qubit_index", "increase_qubits")
    assert "patched_code" in body["fix"]


def test_validate_endpoint():
    res = client.post("/api/validate", json={"code": GOOD_CODE})
    assert res.status_code == 200
    assert res.json()["verified"] is True


@pytest.mark.parametrize("path", ["/api/nope"])
def test_unknown_route_404(path):
    assert client.get(path).status_code == 404


def test_solve_pipeline_on_broken_demo():
    """Full pipeline: run -> parse -> diagnose -> fix -> verify by real re-run."""
    res = client.post("/api/solve", json={"code": BROKEN_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "solved", f"expected solved, got: {body}"
    assert body["execution"]["success"] is False  # original really failed
    assert body["error"]["exception_type"]
    assert body["diagnosis"]["category"] == "qubit_index_out_of_range"
    assert body["fix"] is not None
    assert body["verification"]["verified"] is True  # verified by real execution
    assert body["verification"]["execution"]["success"] is True


def test_solve_pipeline_on_good_code():
    res = client.post("/api/solve", json={"code": GOOD_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_error"
    assert body["execution"]["success"] is True


def test_solve_unknown_framework_rejected():
    res = client.post("/api/solve", json={"code": "print(1)", "framework": "madeup"})
    assert res.status_code == 422


PENNYLANE_CODE = """
import pennylane as qml

dev = qml.device('default.qubit', wires=2)
"""


def test_frameworks_endpoint_reports_runtime_availability():
    """All four frameworks are fully executable runtimes registered in the
    registry, so /api/frameworks must report them available with versions."""
    res = client.get("/api/frameworks")
    assert res.status_code == 200
    frameworks = {f["name"]: f for f in res.json()["frameworks"]}
    for name in ("qiskit", "cirq", "pennylane", "openqasm"):
        assert frameworks[name]["runtime_available"] is True
        assert frameworks[name]["version"]


def test_frameworks_reports_cirq_unavailable_when_missing(monkeypatch):
    """Graceful degradation: if Cirq cannot be imported, /api/frameworks must
    report it unavailable without crashing the endpoint."""
    monkeypatch.setattr(CirqRuntime, "is_available", lambda self: False)
    res = client.get("/api/frameworks")
    assert res.status_code == 200
    frameworks = {f["name"]: f for f in res.json()["frameworks"]}
    assert frameworks["cirq"]["runtime_available"] is False


def test_solve_without_runtime_degrades_to_analysis_only(monkeypatch):
    """A framework whose runtime is unavailable must not crash the pipeline:
    with a supplied error they get analysis + diagnosis, no verification
    claims. The runtime lookup is forced to None to exercise that branch."""
    import backend.runtimes

    monkeypatch.setattr(backend.runtimes, "get_runtime", lambda name: None)
    res = client.post(
        "/api/solve",
        json={
            "code": PENNYLANE_CODE,
            "error": {
                "traceback_text": (
                    'Traceback (most recent call last):\n  File "user_code.py", line 3, in <module>\n'
                    "    dev = qml.device('default.qubit', wires=2)\n"
                    "ModuleNotFoundError: No module named 'pennylane'\n"
                )
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["framework"]["framework"] == "pennylane"
    assert body["status"] == "unsolved"
    assert body["fix"] is None
    assert body["verification"] is None
    assert "No runtime available" in body["detail"]
    assert body["error"] is not None


def test_solve_without_runtime_or_error_reports_no_error_path():
    res = client.post("/api/solve", json={"code": PENNYLANE_CODE})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "no_error"
    assert body["framework"]["framework"] == "pennylane"


@pytest.mark.skipif(not CirqRuntime().is_available(), reason="cirq-core not installed")
def test_api_solve_cirq_end_to_end(monkeypatch):
    """/api/solve with a broken Cirq program must use the real CirqRuntime to
    reproduce, then verify the AI-proposed patch by re-execution (mocked AI)."""
    fixed = (
        "import cirq\n"
        "q0, q1 = cirq.LineQubit.range(2)\n"
        "circuit = cirq.Circuit(cirq.CNOT(q0, q1))\n"
        "print(circuit)\n"
    )
    broken = (
        "import cirq\n"
        "q0 = cirq.LineQubit(0)\n"
        "circuit = cirq.Circuit(cirq.CNOT(q0, q0))\n"
        "print(circuit)\n"
    )

    class _ScriptedProvider(AIProvider):
        name = "scripted"
        @property
        def model_id(self): return "scripted"
        def generate(self, prompt, *, timeout_s=30.0):
            return ProviderResponse(model="scripted", content={
                "hypothesis": "CNOT applied to the same qubit twice.",
                "diagnosis": "Duplicate qids.",
                "proposed_fix": "Use two distinct qubits.",
                "patched_code": fixed,
                "reasoning_summary": "Distinct qubits satisfy CNOT's contract.",
                "evidence": ["Duplicate qids"],
                "confidence": 0.9,
                "next_action": "apply_fix",
            }, raw_text="")

    monkeypatch.setattr("backend.api.solve.get_provider_or_none", lambda: _ScriptedProvider())

    res = client.post("/api/solve", json={"code": broken})
    assert res.status_code == 200
    body = res.json()
    assert body["framework"]["framework"] == "cirq"
    assert body["execution"]["success"] is False          # original really failed
    assert body["diagnosis"]["category"] == "cirq_duplicate_qids"
    assert body["status"] == "solved"
    assert body["attempts"][0]["source"] == "ai"
    assert body["verification"]["verified"] is True       # real re-execution
    assert body["fix"]["patched_code"] == fixed


@pytest.mark.skipif(
    not PennyLaneRuntime().is_available(),
    reason="pennylane not installed",
)
def test_api_solve_pennylane_end_to_end(monkeypatch):
    """/api/solve must reproduce a real PennyLane WireError and verify the
    AI-proposed patch by re-execution (mocked AI)."""
    fixed = (
        "import pennylane as qml\n"
        "dev = qml.device('lightning.qubit', wires=6)\n"
        "@qml.qnode(dev)\n"
        "def circuit():\n"
        "    qml.CNOT(wires=[0, 5])\n"
        "    return qml.probs(wires=[0, 1])\n"
        "print(circuit())\n"
    )
    broken = (
        "import pennylane as qml\n"
        "dev = qml.device('lightning.qubit', wires=2)\n"
        "@qml.qnode(dev)\n"
        "def circuit():\n"
        "    qml.CNOT(wires=[0, 5])\n"
        "    return qml.probs(wires=[0, 1])\n"
        "print(circuit())\n"
    )

    class _ScriptedProvider(AIProvider):
        name = "scripted"
        @property
        def model_id(self): return "scripted"
        def generate(self, prompt, *, timeout_s=30.0):
            return ProviderResponse(model="scripted", content={
                "hypothesis": "Wire 5 does not exist on a 2-wire device.",
                "diagnosis": "Device has too few wires.",
                "proposed_fix": "Allocate a device with enough wires.",
                "patched_code": fixed,
                "reasoning_summary": "A 6-wire device makes wires=[0, 5] valid.",
                "evidence": ["WireError: wires not found on the device"],
                "confidence": 0.9,
                "next_action": "apply_fix",
            }, raw_text="")

    monkeypatch.setattr("backend.api.solve.get_provider_or_none", lambda: _ScriptedProvider())

    res = client.post("/api/solve", json={"code": broken})
    assert res.status_code == 200
    body = res.json()
    assert body["framework"]["framework"] == "pennylane"
    assert body["execution"]["success"] is False
    assert body["diagnosis"]["category"] == "pl_wire_not_on_device"
    assert body["status"] == "solved"
    assert body["verification"]["verified"] is True
    assert body["fix"]["patched_code"] == fixed


@pytest.mark.skipif(
    not OpenQasmRuntime().is_available(),
    reason="qiskit qasm2 stack unavailable",
)
def test_api_solve_openqasm_end_to_end(monkeypatch):
    """/api/solve must reproduce a real QASM2 parse error at the user line and
    verify the AI-patched QASM by re-execution (mocked AI)."""
    broken = 'OPENQASM 2.0;\ninclude "qelib1.inc";\nqreg q[2];\nh q[5];\n'
    fixed = broken.replace("h q[5];", "h q[1];")

    class _ScriptedProvider(AIProvider):
        name = "scripted"
        @property
        def model_id(self): return "scripted"
        def generate(self, prompt, *, timeout_s=30.0):
            return ProviderResponse(model="scripted", content={
                "hypothesis": "q[5] is out of range for qreg q[2].",
                "diagnosis": "Index outside the declared register.",
                "proposed_fix": "Use an index within the declared register.",
                "patched_code": fixed,
                "reasoning_summary": "h q[1] stays inside the declared register.",
                "evidence": ["line 4: index 5 is out-of-range"],
                "confidence": 0.9,
                "next_action": "apply_fix",
            }, raw_text="")

    monkeypatch.setattr("backend.api.solve.get_provider_or_none", lambda: _ScriptedProvider())

    res = client.post("/api/solve", json={"code": broken})
    assert res.status_code == 200
    body = res.json()
    assert body["framework"]["framework"] == "openqasm"
    assert body["execution"]["success"] is False
    assert body["diagnosis"]["category"] == "qasm2_parse_error"
    assert body["error"]["line_number"] == 4
    assert body["status"] == "solved"
    assert body["verification"]["verified"] is True
    assert body["fix"]["patched_code"] == fixed
