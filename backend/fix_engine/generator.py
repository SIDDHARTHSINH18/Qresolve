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
_LINEQUBIT_RE = re.compile(r"\bcirq\.LineQubit\s*\(\s*(?P<index>\d+)\s*\)")
_LINEQUBIT_RANGE_RE = re.compile(r"\bcirq\.LineQubit\.range\s*\((?P<args>[^)]*)\)")
_LINEQUBIT_UNPACK_RE = re.compile(
    r"^\s*(?P<names>[^=\n]+?)\s*=\s*cirq\.LineQubit\.range\s*\(", re.MULTILINE
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_]\w*")


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


def _paren_spans(line: str) -> list[tuple[int, int]]:
    """Character spans of every parenthesised argument list on one line."""
    spans: list[tuple[int, int]] = []
    stack: list[int] = []
    for i, ch in enumerate(line):
        if ch == "(":
            stack.append(i + 1)
        elif ch == ")" and stack:
            spans.append((stack.pop(), i))
    return spans


def _split_args(text: str) -> list[str]:
    """Split an argument list on commas that are not nested in brackets."""
    args: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    args.append("".join(current).strip())
    return args


def _linequbit_indices_in_use(code: str) -> set[int] | None:
    """Every LineQubit index this source can provably occupy (None = unprovable)."""
    used = {int(m.group("index")) for m in _LINEQUBIT_RE.finditer(code)}
    for m in _LINEQUBIT_RANGE_RE.finditer(code):
        parts = [p.strip() for p in m.group("args").split(",") if p.strip()]
        if not parts or not all(re.fullmatch(r"\d+", p) for p in parts):
            return None  # a dynamic range hides which indices are taken
        numbers = [int(p) for p in parts]
        start, stop = (0, numbers[0]) if len(numbers) == 1 else (numbers[0], numbers[1])
        step = numbers[2] if len(numbers) > 2 else 1
        if step <= 0:
            return None
        used.update(range(start, stop, step))
    return used


def _is_bound_linequbit(code: str, name: str) -> bool:
    """True only when `name` provably holds one LineQubit in this source."""
    if re.search(
        rf"^\s*{re.escape(name)}\s*=\s*cirq\.LineQubit\s*\(\s*\d+\s*\)\s*$",
        code,
        re.MULTILINE,
    ):
        return True
    for m in _LINEQUBIT_UNPACK_RE.finditer(code):
        names = [n.strip() for n in m.group("names").split(",")]
        if len(names) >= 2 and name in names and all(_IDENTIFIER_RE.fullmatch(n) for n in names):
            return True
    return False


def _fresh_qubit_name(code: str, name: str, taken: set[str]) -> str | None:
    """A qubit variable name used nowhere in the source or in this patch."""
    stem = re.sub(r"\d+$", "", name) or name
    for suffix in range(2, 100):
        candidate = f"{stem}{suffix}"
        if candidate in taken:
            continue
        if re.search(rf"\b{re.escape(candidate)}\b", code) is None:
            return candidate
    return None


def _patched_code_for_duplicate_qids(code: str, error: ErrorInfo) -> str | None:
    """Give a repeated Cirq qubit operand its own distinct LineQubit.

    Deliberately narrow: it fires only when the failing line passes one plain
    identifier twice to a single call, that identifier provably holds a
    LineQubit, and every index the source can occupy is known — so the new
    qubit is provably distinct. Anything less certain returns None instead of
    guessing at a rewrite.
    """
    line_number = error.line_number
    if line_number is None:
        return None
    lines = code.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return None

    used = _linequbit_indices_in_use(code)
    if used is None:
        return None

    line = lines[idx]
    found: list[tuple[tuple[int, int], str]] = []
    for span in _paren_spans(line):
        args = _split_args(line[span[0]:span[1]])
        repeated = sorted({
            a for a in args
            if args.count(a) > 1 and _IDENTIFIER_RE.fullmatch(a)
        })
        if len(repeated) > 1:
            return None  # several operands repeat: which one is wrong is ambiguous
        if repeated:
            found.append((span, repeated[0]))
    if len(found) != 1:
        return None
    (start, end), name = found[0]

    if not _is_bound_linequbit(code, name):
        return None

    indent = line[: len(line) - len(line.lstrip())]
    declarations: list[str] = []
    taken: set[str] = set()
    next_index = max(used) + 1 if used else 0
    patched_args: list[str] = []
    kept_first = False
    for arg in _split_args(line[start:end]):
        if arg != name:
            patched_args.append(arg)
            continue
        if not kept_first:
            kept_first = True
            patched_args.append(arg)
            continue
        replacement = _fresh_qubit_name(code, name, taken)
        if replacement is None:
            return None
        taken.add(replacement)
        declarations.append(f"{replacement} = cirq.LineQubit({next_index})")
        next_index += 1
        patched_args.append(replacement)
    if not declarations:
        return None

    patched_line = line[:start] + ", ".join(patched_args) + line[end:]
    patched = "\n".join(
        lines[:idx] + [indent + d for d in declarations] + [patched_line] + lines[idx + 1:]
    )
    try:
        compile(patched, "<qresolve-patch>", "exec")
    except SyntaxError:
        return None
    return patched


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
    if diagnosis.category == "cirq_duplicate_qids":
        patched = _patched_code_for_duplicate_qids(code, error)
        if patched is not None:
            proposals.append((
                "cirq_distinct_qubits",
                f"Give the qubit repeated on line {error.line_number} its own distinct "
                "LineQubit so the gate receives unique qids.",
                patched,
                0.7,
            ))
    return proposals
