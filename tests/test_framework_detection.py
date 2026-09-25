"""Tests for framework detection."""
from backend.analyzer import detect_framework

QISKIT_CODE = """
from qiskit import QuantumCircuit
qc = QuantumCircuit(2)
qc.h(0)
qc.measure_all()
"""

PLAIN_CODE = """
def add(a, b):
    return a + b
"""

CIRQ_CODE = """
import cirq
q = cirq.LineQubit(0)
circuit = cirq.Circuit(cirq.H(q))
"""


def test_detects_qiskit():
    framework, confidence, matched = detect_framework(QISKIT_CODE)
    assert framework == "qiskit"
    assert confidence == 1.0
    assert matched  # at least the import pattern matched


def test_detects_nothing_for_plain_code():
    framework, confidence, matched = detect_framework(PLAIN_CODE)
    assert framework is None
    assert confidence == 0.0
    assert matched == []


def test_detects_cirq_by_import():
    framework, _, _ = detect_framework(CIRQ_CODE)
    assert framework == "cirq"
