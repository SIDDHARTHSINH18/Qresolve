"""Tests for error parsing (raw tracebacks + runtime results)."""
import pytest

from backend.analyzer import error_from_execution, parse_error
from backend.runtimes import QiskitRuntime

BROKEN_CODE = """
from qiskit import QuantumCircuit

qc = QuantumCircuit(2)
qc.cx(0, 2)
"""


@pytest.fixture(scope="module")
def runtime_result():
    rt = QiskitRuntime()
    return rt.execute(BROKEN_CODE)


def test_parse_raw_traceback():
    tb = '''Traceback (most recent call last):
  File "user_code.py", line 4, in <module>
    qc.cx(0, 2)
IndexError: Index for qubit out of range for 2-qubit circuit.
'''
    info = parse_error(traceback_text=tb, source_code=BROKEN_CODE)
    assert info.exception_type == "IndexError"
    assert "out of range" in info.message
    assert info.line_number == 4
    assert "qc.cx(0, 2)" in info.source_snippet


def test_parse_runtime_error(runtime_result):
    assert runtime_result.success is False
    info = error_from_execution(runtime_result, BROKEN_CODE)
    assert info is not None
    assert info.exception_type  # whatever the installed qiskit actually raises
    assert info.message
    assert info.line_number == 5  # leading newline in the literal puts cx on line 5
    assert info.source_snippet and "cx" in info.source_snippet


def test_parse_success_returns_none():
    from backend.models import ExecutionResult

    ok = ExecutionResult(success=True)
    assert error_from_execution(ok, "print('hi')") is None


def test_no_line_number_for_foreign_tracebacks():
    tb = 'Traceback (most recent call last):\n  File "server.py", line 10, in handler\nValueError: bad input\n'
    info = parse_error(traceback_text=tb, source_code="")
    assert info.exception_type == "ValueError"
    assert info.line_number is None
