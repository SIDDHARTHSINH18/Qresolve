"""Framework detection from source code.

Pattern-registry based so new frameworks can be added declaratively.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class FrameworkSpec:
    name: str
    import_patterns: list[str] = field(default_factory=list)
    api_patterns: list[str] = field(default_factory=list)


FRAMEWORK_SPECS: list[FrameworkSpec] = [
    FrameworkSpec(
        name="qiskit",
        import_patterns=[r"^\s*from\s+qiskit\b", r"^\s*import\s+qiskit\b", r"^\s*from\s+qiskit[.\w]*\s+import\b"],
        api_patterns=[r"\bQuantumCircuit\s*\(", r"\bAerSimulator\b", r"\bStatevector\b", r"\btranspile\s*\("],
    ),
    FrameworkSpec(
        name="cirq",
        import_patterns=[r"^\s*from\s+cirq\b", r"^\s*import\s+cirq\b"],
        api_patterns=[r"\bcirq\.Circuit\b", r"\bcirq\.LineQubit\b"],
    ),
    FrameworkSpec(
        name="pennylane",
        import_patterns=[r"^\s*from\s+pennylane\b", r"^\s*import\s+pennylane\b", r"^\s*import\s+penny lane\b"],
        api_patterns=[r"\bqml\.device\b", r"\bqml\.QNode\b"],
    ),
    FrameworkSpec(
        name="openqasm",
        import_patterns=[],
        api_patterns=[r"^\s*OPENQASM\s+(2|3)\b", r"^\s*(qreg|qubit)\s+\w+\s*[;\[]", r"^\s*(creg|bit)\s+\w+\s*[;\[]"],
    ),
]


def detect_framework(code: str) -> tuple[str | None, float, list[str]]:
    """Return (framework, confidence, matched_patterns)."""
    best: tuple[str | None, float, list[str]] = (None, 0.0, [])
    for spec in FRAMEWORK_SPECS:
        matched: list[str] = []
        for pattern in spec.import_patterns + spec.api_patterns:
            if re.search(pattern, code, re.MULTILINE):
                matched.append(pattern)
        imports = [p for p in spec.import_patterns if p in matched]
        if imports:
            score = 1.0
        elif matched:
            score = 0.6
        else:
            score = 0.0
        if score > best[1]:
            best = (spec.name, score, matched)
    return best
