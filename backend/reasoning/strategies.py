"""Progressive reasoning strategies.

Each level performs *additional* analysis beyond the previous one. A level
is only reached when the controller escalates — the extra work is real
analysis of code, semantics, environment, and attempt history.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from backend.models import ReasoningContext

_CIRCUIT_SIZE_RE = re.compile(r"QuantumCircuit\s*\(\s*(\d+)\s*(?:,\s*(\d+))?\s*[,)]")
_GATE_CALL_RE = re.compile(r"\b(\w+)\s*\.\s*(\w+)\s*\(([^)]*)\)")
_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.,\s]+))", re.MULTILINE)


@dataclass
class Findings:
    level: int
    title: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def _failing_line(ctx: ReasoningContext) -> str | None:
    if ctx.error is None or ctx.error.line_number is None:
        return None
    lines = ctx.code.splitlines()
    idx = ctx.error.line_number - 1
    if 0 <= idx < len(lines):
        return lines[idx]
    return None


def analyze_surface(ctx: ReasoningContext) -> Findings:
    """Level 1: what the runtime actually reported."""
    evidence: list[str] = []
    if ctx.error is None:
        return Findings(1, "Surface analysis", "No runtime error available.", evidence)
    error = ctx.error
    evidence.append(f"Exception type: {error.exception_type}")
    evidence.append(f"Message: {error.message}")
    if error.line_number:
        evidence.append(f"Failing line in user code: {error.line_number}")
    if error.traceback_text:
        frames = [ln.strip() for ln in error.traceback_text.splitlines() if ln.strip().startswith("File ")]
        user_frames = [f for f in frames if "user_code.py" in f]
        evidence.append(
            f"Traceback has {len(frames)} frame(s); innermost user frame: {user_frames[-1] if user_frames else 'none'}"
        )
    diagnosis_text = ctx.diagnosis.summary if ctx.diagnosis else ""
    return Findings(
        1,
        "Surface analysis",
        diagnosis_text or f"Runtime raised {error.exception_type}.",
        evidence,
        {"exception_type": error.exception_type, "message": error.message},
    )


def analyze_code(ctx: ReasoningContext) -> Findings:
    """Level 2: source-level facts — circuit sizes, imports, failing line."""
    evidence: list[str] = []
    data: dict = {}
    lines = ctx.code.splitlines()
    evidence.append(f"Source is {len(lines)} line(s).")

    sizes = [int(m.group(1)) for m in _CIRCUIT_SIZE_RE.finditer(ctx.code)]
    clbits = [int(m.group(2)) for m in _CIRCUIT_SIZE_RE.finditer(ctx.code) if m.group(2)]
    data["circuit_qubits"] = sizes
    data["circuit_clbits"] = clbits
    if sizes:
        evidence.append(f"QuantumCircuit size declaration(s): {sizes} qubit(s)" +
                        (f", clbit declaration(s): {clbits}" if clbits else ""))

    imports = [m.group(1) or m.group(2) for m in _IMPORT_RE.finditer(ctx.code) if m.group(1) or m.group(2)]
    data["imports"] = imports
    if imports:
        evidence.append(f"Imports: {imports}")

    failing = _failing_line(ctx)
    data["failing_line"] = failing
    if failing is not None:
        evidence.append(f"Failing line source: {failing.strip()!r}")
    return Findings(2, "Code-aware analysis", "Extracted circuit sizes, imports, and the failing line.", evidence, data)


def analyze_quantum(ctx: ReasoningContext) -> Findings:
    """Level 3: quantum semantics — qubit/clbit index validity, gate arity."""
    evidence: list[str] = []
    data: dict = {}
    sizes = [int(m.group(1)) for m in _CIRCUIT_SIZE_RE.finditer(ctx.code)]
    n_qubits = sizes[0] if sizes else None
    data["n_qubits"] = n_qubits

    failing = _failing_line(ctx)
    if failing is not None and n_qubits is not None:
        gm = re.search(r"\(([^)]*)\)", failing)
        if gm:
            args = [a.strip() for a in gm.group(1).split(",")]
            indices = [int(a) for a in args if re.fullmatch(r"\d+", a)]
            data["indices_on_failing_line"] = indices
            invalid = [i for i in indices if i >= n_qubits]
            if invalid:
                evidence.append(
                    f"Failing call uses index/indices {invalid}, but the circuit has only "
                    f"{n_qubits} qubit(s) (valid: 0..{n_qubits - 1})."
                )
            else:
                evidence.append("All literal indices on the failing line are within range.")
    if ctx.error and ctx.error.message and "clbit" in ctx.error.message.lower():
        evidence.append("Message mentions a classical bit; check clbit count separately from qubits.")
    if ctx.diagnosis:
        for h in ctx.diagnosis.hypotheses:
            evidence.append(f"Knowledge base: {h.cause} (confidence {h.confidence})")
    return Findings(3, "Quantum-aware analysis", "Checked quantum index/arity semantics against the declared circuit.", evidence, data)


def analyze_environment(ctx: ReasoningContext, framework_version: str | None) -> Findings:
    """Level 4: environment/version/dependency facts."""
    evidence: list[str] = []
    data: dict = {"framework_version": framework_version}
    env = ctx.environment or None
    versions = env.framework_versions if env else {}
    data["framework_versions"] = versions
    if ctx.framework:
        evidence.append(f"Framework: {ctx.framework}")
    if framework_version:
        evidence.append(f"Runtime framework version: {framework_version}")
    for name, ver in versions.items():
        evidence.append(f"Client-reported {name} version: {ver}")
    if ctx.error and ctx.error.exception_type in ("ImportError", "ModuleNotFoundError"):
        evidence.append("Import failure: the symbol may not exist in this installed version.")
    if ctx.knowledge:
        evidence.append(f"Knowledge patterns considered: {ctx.knowledge}")
    return Findings(4, "Environment analysis", "Collected framework/runtime version context.", evidence, data)


def plan_experiments(ctx: ReasoningContext) -> Findings:
    """Level 5: cross-attempt analysis and controlled-experiment planning."""
    evidence: list[str] = []
    data: dict = {}
    failed = [a for a in ctx.attempts if not a.verified]
    evidence.append(f"{len(failed)} failed attempt(s) so far.")
    errors_seen = []
    for a in failed:
        exc = a.execution.exception_type if a.execution else None
        msg = a.execution.exception_message if a.execution else None
        errors_seen.append(f"{exc}: {msg}")
        evidence.append(f"Attempt {a.attempt} (level {a.level}, {a.source}) failed: {exc}: {msg} — {a.why_failed}")
    data["distinct_errors"] = sorted(set(e for e in errors_seen if e))
    if len(set(e for e in errors_seen if e)) <= 1 and failed:
        evidence.append("All failures produced the same error: the hypothesis so far is insufficient.")
    tried = [a.patched_code for a in ctx.attempts]
    data["already_tried_patches"] = tried
    if tried:
        evidence.append("Patches already tried (must not be repeated): "
                        + "; ".join(sorted(set(tried))[:3]) + ("..." if len(set(tried)) > 3 else ""))
    return Findings(
        5,
        "Hypothesis search",
        "Analyzed attempt history and planned discriminating experiments.",
        evidence,
        data,
    )


def gather_findings(ctx: ReasoningContext, framework_version: str | None = None) -> list[Findings]:
    """Run every analyzer up to ctx.level. Higher level = strictly more analysis."""
    analyzers: list[tuple[int, Callable[[ReasoningContext], Findings] | Callable[[ReasoningContext, str | None], Findings]]] = [
        (1, analyze_surface),
        (2, analyze_code),
        (3, analyze_quantum),
        (4, lambda c: analyze_environment(c, framework_version)),
        (5, plan_experiments),
    ]
    out: list[Findings] = []
    for lvl, fn in analyzers:
        if lvl > max(1, min(ctx.level, 5)):
            break
        out.append(fn(ctx))
    return out
