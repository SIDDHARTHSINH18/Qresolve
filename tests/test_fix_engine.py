"""Tests for the deterministic fix generator.

These rules run with no AI provider: they must either produce a patch that is
provably correct for the failing line, or nothing at all. Everything they emit
still goes through the sandbox re-execution in backend/validation, so a
candidate is a hypothesis to verify, never a claim of success.
"""
import pytest

from backend.fix_engine.generator import propose_fixes
from backend.models import Diagnosis, ErrorInfo


def _diagnosis(category: str, code: str, line_number: int | None) -> Diagnosis:
    return Diagnosis(
        summary=category,
        category=category,
        error=ErrorInfo(
            exception_type="ValueError",
            message="Duplicate qids for <cirq.CNOT>",
            traceback_text=(
                'Traceback (most recent call last):\n'
                f'  File "user_code.py", line {line_number}, in <module>\n'
            ),
            line_number=line_number,
            source_snippet=None,
        ),
    )


def _only_patch(code: str, line_number: int) -> tuple[str, str, str, float]:
    proposals = propose_fixes(code, _diagnosis("cirq_duplicate_qids", code, line_number))
    assert len(proposals) == 1, f"expected exactly one candidate, got {proposals}"
    strategy, description, patched, confidence = proposals[0]
    assert strategy == "cirq_distinct_qubits"
    assert patched != code, "a patch that changes nothing is not a fix"
    compile(patched, "<test-patch>", "exec")
    assert 0.0 < confidence <= 1.0
    assert description
    return proposals[0]


# ------------------------------------------------------- safe, deterministic
def test_builtin_example_gets_a_second_distinct_linequbit():
    """The UI's built-in Cirq example: one qubit passed to both CNOT operands."""
    code = (
        "import cirq\n"
        "q = cirq.LineQubit(0)\n"
        "c = cirq.Circuit(cirq.CNOT(q, q))\n"
        "print(c)\n"
    )
    _, _, patched, _ = _only_patch(code, 3)
    assert patched.splitlines() == [
        "import cirq",
        "q = cirq.LineQubit(0)",
        "q2 = cirq.LineQubit(1)",
        "c = cirq.Circuit(cirq.CNOT(q, q2))",
        "print(c)",
    ]


def test_range_unpacked_qubits_are_counted_before_allocating():
    """range(2) already occupies indices 0 and 1, so the new qubit must be 2."""
    code = (
        "import cirq\n"
        "q0, q1 = cirq.LineQubit.range(2)\n"
        "c = cirq.Circuit(cirq.CNOT(q0, q0))\n"
    )
    _, _, patched, _ = _only_patch(code, 3)
    assert "q2 = cirq.LineQubit(2)" in patched
    assert "cirq.CNOT(q0, q2)" in patched
    assert "cirq.LineQubit.range(2)" in patched      # the original binding is untouched


def test_every_repeated_operand_after_the_first_is_replaced():
    code = (
        "import cirq\n"
        "q = cirq.LineQubit(0)\n"
        "c = cirq.Circuit(cirq.CCX(q, q, q))\n"
    )
    _, _, patched, _ = _only_patch(code, 3)
    assert "q2 = cirq.LineQubit(1)" in patched
    assert "q3 = cirq.LineQubit(2)" in patched
    assert "cirq.CCX(q, q2, q3)" in patched


def test_new_qubit_avoids_names_and_indices_already_in_the_source():
    """q2 is taken by name and index 5 by value; the patch must collide with neither."""
    code = (
        "import cirq\n"
        "q = cirq.LineQubit(0)\n"
        "q2 = cirq.LineQubit(5)\n"
        "c = cirq.Circuit(cirq.CNOT(q, q))\n"
        "print(q2)\n"
    )
    _, _, patched, _ = _only_patch(code, 4)
    assert "q3 = cirq.LineQubit(6)" in patched
    assert "cirq.CNOT(q, q3)" in patched


def test_declaration_keeps_the_failing_line_indentation():
    code = (
        "import cirq\n"
        "def build():\n"
        "    q = cirq.LineQubit(0)\n"
        "    return cirq.Circuit(cirq.CNOT(q, q))\n"
    )
    _, _, patched, _ = _only_patch(code, 4)
    assert "    q2 = cirq.LineQubit(1)" in patched
    assert "    return cirq.Circuit(cirq.CNOT(q, q2))" in patched


# ------------------------------------------- unsafe input must yield nothing
@pytest.mark.parametrize(
    "code, line_number",
    [
        # which indices are occupied is decided at run time
        ("import cirq\nn = 2\nq0, q1 = cirq.LineQubit.range(n)\nc = cirq.Circuit(cirq.CNOT(q0, q0))\n", 4),
        # the repeated name is a parameter: nothing proves it is a LineQubit
        ("import cirq\ndef build(q):\n    return cirq.Circuit(cirq.CNOT(q, q))\n", 3),
        # the operands are subscripts, not plain identifiers
        ("import cirq\nqs = cirq.LineQubit.range(2)\nc = cirq.Circuit(cirq.CNOT(qs[0], qs[0]))\n", 3),
        # the failing line has no repeated operand at all
        ("import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.CNOT(q, q))\n", 2),
        # two different operands repeat: which one is wrong is ambiguous
        ("import cirq\nq = cirq.LineQubit(0)\nr = cirq.LineQubit(1)\nc = cirq.Circuit(cirq.CNOT(q, q), cirq.CNOT(r, r))\n", 4),
    ],
)
def test_no_candidate_when_the_correction_is_not_determinable(code, line_number):
    assert propose_fixes(code, _diagnosis("cirq_duplicate_qids", code, line_number)) == []


def test_no_candidate_without_a_line_number():
    code = "import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.CNOT(q, q))\n"
    assert propose_fixes(code, _diagnosis("cirq_duplicate_qids", code, None)) == []


def test_no_candidate_when_the_line_number_is_outside_the_source():
    code = "import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.CNOT(q, q))\n"
    for line_number in (0, -1, 99):
        diagnosis = _diagnosis("cirq_duplicate_qids", code, line_number)
        assert propose_fixes(code, diagnosis) == []


def test_no_candidate_without_an_error():
    code = "import cirq\nq = cirq.LineQubit(0)\n"
    diagnosis = Diagnosis(summary="cirq_duplicate_qids", category="cirq_duplicate_qids", error=None)
    assert propose_fixes(code, diagnosis) == []


def test_rule_is_scoped_to_its_own_category():
    """A different Cirq failure must not borrow the duplicate-qubit rewrite."""
    code = "import cirq\nq = cirq.LineQubit(0)\nc = cirq.Circuit(cirq.CNOT(q, q))\n"
    diagnosis = _diagnosis("cirq_wrong_qubit_count", code, 3)
    assert propose_fixes(code, diagnosis) == []


# ------------------------------------------- the Qiskit rules must be intact
def test_qiskit_rules_still_propose_both_strategies():
    code = (
        "from qiskit import QuantumCircuit\n"
        "qc = QuantumCircuit(2)\n"
        "qc.cx(0, 2)\n"
    )
    diagnosis = Diagnosis(
        summary="qubit_index_out_of_range",
        category="qubit_index_out_of_range",
        error=ErrorInfo(
            exception_type="CircuitError",
            message="qarg 2 out of range",
            line_number=3,
        ),
    )
    strategies = [p[0] for p in propose_fixes(code, diagnosis)]
    assert strategies == ["qubit_index", "increase_qubits"]
