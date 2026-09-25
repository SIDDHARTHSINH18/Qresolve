"""Tests for the Qiskit runtime: real subprocess execution, success and failure."""
import pytest

from backend.runtimes import QiskitRuntime, get_runtime
from backend.sandbox.limits import SandboxLimits

GOOD_CODE = """
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Statevector

qc = QuantumCircuit(2)
qc.h(0)
qc.cx(0, 1)
sv = Statevector.from_instruction(qc)
print("n_qubits:", qc.num_qubits)
print("probabilities:", [round(p, 4) for p in sv.probabilities()])
"""

BROKEN_CODE = """
from qiskit import QuantumCircuit

qc = QuantumCircuit(2)
qc.cx(0, 2)
"""


@pytest.fixture(scope="module")
def runtime():
    rt = QiskitRuntime()
    assert rt.is_available(), "qiskit must be installed for runtime tests"
    return rt


def test_runtime_registry():
    assert get_runtime("qiskit") is not None
    assert get_runtime("nonexistent") is None


def test_runtime_version(runtime):
    version = runtime.version()
    assert version and version.count(".") >= 1


def test_successful_execution(runtime):
    result = runtime.execute(GOOD_CODE)
    assert result.success is True
    assert result.exception_type is None
    assert result.traceback_text is None
    assert "n_qubits: 2" in result.stdout
    assert "probabilities:" in result.stdout
    assert result.execution_time_ms is not None and result.execution_time_ms > 0


def test_failing_execution(runtime):
    result = runtime.execute(BROKEN_CODE)
    assert result.success is False
    assert result.exception_type, "failing run must capture the exception type"
    assert result.exception_message, "failing run must capture the exception message"
    assert result.traceback_text and "user_code.py" in result.traceback_text
    # The error must come from the actual runtime, not a hardcoded guess:
    # leading newline in the literal puts qc.cx(0, 2) on line 5
    assert "line 5" in result.traceback_text
    assert result.execution_time_ms is not None


def test_timeout(runtime):
    slow = "while True:\n    pass\n"
    result = runtime.execute(slow, limits=SandboxLimits(timeout_s=3.0))
    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in result.stderr.lower()
