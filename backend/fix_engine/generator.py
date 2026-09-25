"""Deterministic fix strategies for known error patterns.

These are heuristic, rule-based fixes (a seed for the AI reasoning engine,
which will replace/extend them). A fix is only ever *proposed* here — it
becomes "verified" only if the quantum runtime actually re-runs it
successfully (see backend/validation/validator.py).
"""
from __future__ import annotations

import re

from backend.models import Diagnosis, ErrorInfo

_QUBIT_GATE_CALL_RE = re.compile(
    r"^\s*qc\.(?P<gate>[a-z_]\w*)\s*\((?P<args>[^)]*)\)\s*(#.*)?$"
)
_CIRCUIT_SIZE_RE = re.compile(r"QuantumCircuit\s*\(\s*(\d+)\s*[,)]")


def _patched_code_for_qubit_index(code: str, error: ErrorInfo) -> str | None:
    """Clamp invalid qubit indices on the failing line down to n_qubits-1."""
    line_number = error.line_number
    if line_number is None:
        return None
    lines = code.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return None

    m = _CIRCUIT_SIZE_RE.search(code)
    if not m:
        return None
    n_qubits = int(m.group(1))

    line = lines[idx]
    gm = _QUBIT_GATE_CALL_RE.match(line)
    if not gm:
        return None

    args = [a.strip() for a in gm.group("args").split(",")]
    if not args:
        return None

    changed = False
    new_args: list[str] = []
    for a in args:
        if re.fullmatch(r"\d+", a) and int(a) >= n_qubits:
            new_args.append(str(n_qubits - 1))
            changed = True
        else:
            new_args.append(a)
    if not changed:
        return None

    patched_line = line.replace("(" + ", ".join(args) + ")", "(" + ", ".join(new_args) + ")")
    if patched_line == line:
        return None

    out = list(lines)
    out[idx] = patched_line
    return "\n".join(out)


def _patched_code_increase_qubits(code: str, error: ErrorInfo) -> str | None:
    """Alternative strategy: enlarge the circuit to fit the highest index used."""
    line_number = error.line_number
    m = _CIRCUIT_SIZE_RE.search(code)
    if m is None or line_number is None:
        return None
    lines = code.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return None
    gm = _QUBIT_GATE_CALL_RE.match(lines[idx])
    if not gm:
        return None
    indices = [int(a) for a in gm.group("args").split(",") if re.fullmatch(r"\d+", a.strip())]
    if not indices:
        return None
    needed = max(indices) + 1
    n_qubits = int(m.group(1))
    if needed <= n_qubits:
        return None
    old = m.group(0)
    new = old.replace(str(n_qubits), str(needed), 1)
    return code.replace(old, new, 1)


def propose_fixes(code: str, diagnosis: Diagnosis) -> list[tuple[str, str, str, float]]:
    """Return candidate fixes as (strategy, description, patched_code, confidence)."""
    error = diagnosis.error
    if error is None:
        return []

    proposals: list[tuple[str, str, str, float]] = []
    if diagnosis.category == "qubit_index_out_of_range":
        patched = _patched_code_for_qubit_index(code, error)
        if patched is not None:
            proposals.append((
                "qubit_index",
                f"Clamp the invalid qubit index on line {error.line_number} to the last valid "
                "index of the circuit.",
                patched,
                0.7,
            ))
        patched2 = _patched_code_increase_qubits(code, error)
        if patched2 is not None:
            proposals.append((
                "increase_qubits",
                "Alternatively, allocate more qubits so every referenced index is valid.",
                patched2,
                0.6,
            ))
    return proposals
