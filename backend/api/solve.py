"""The /api/solve pipeline: AI proposes -> runtime tests -> validator verifies.

The adaptive controller (backend/reasoning/adaptive.py) owns the loop:
runtime reproduction -> analysis -> reasoning -> proposal -> sandbox ->
validator -> PASS/FAIL -> failure evidence -> deeper reasoning. The
heuristic knowledge base remains as fallback when no AI provider is
configured (or when the provider fails).
"""
from __future__ import annotations

from backend.models import FixResponse
from backend.providers import get_provider
from backend.reasoning.adaptive import AdaptiveController

# Re-exported for /api/fix and /health compatibility
from backend.analyzer import detect_framework, error_from_execution, parse_error  # noqa: F401
from backend.diagnostics import classify  # noqa: F401
from backend.fix_engine import propose_fixes, unified_diff  # noqa: F401
from backend.models import (  # noqa: F401
    FrameworkDetection,
    ProposedFix,
    ReasoningProposal,
    SolveRequest,
    SolveResponse,
)


def run_solve_pipeline(req: SolveRequest) -> SolveResponse:
    from backend.runtimes import get_runtime

    framework_name, _, _ = detect_framework(req.code)
    target = req.framework or framework_name
    if req.framework:
        from backend.reasoning.adaptive import _known_frameworks

        if req.framework.lower() not in _known_frameworks():
            raise LookupError(f"Unknown framework: {req.framework}")
    runtime = get_runtime(target) if target else None
    if runtime is None:
        detection = FrameworkDetection(framework=framework_name)
        if req.error is None:
            return SolveResponse(
                status="no_error",
                framework=detection,
                detail="No runtime available for this framework and no error supplied.",
            )
        error = parse_error(
            traceback_text=req.error.traceback_text,
            source_code=req.code,
            exception_type=req.error.exception_type,
            message=req.error.message,
            line_number=req.error.line_number,
        )
        return SolveResponse(
            status="unsolved",
            framework=detection,
            error=error,
            diagnosis=classify(error),
            detail="No runtime available for this framework; analysis only, no verification.",
        )

    controller = AdaptiveController(runtime=runtime, provider=get_provider_or_none())
    return controller.solve(req)


def get_provider_or_none():
    """Never let provider misconfiguration take the API down."""
    try:
        return get_provider()
    except Exception:
        return None


def run_fix(req) -> FixResponse:
    """Heuristic fix proposal for /api/fix (verification happens via /api/validate)."""
    from backend.models import Diagnosis, ErrorInfo

    detection_framework, confidence, matched = detect_framework(req.code)
    framework = FrameworkDetection(
        framework=detection_framework, confidence=confidence, matched_patterns=matched
    )
    if req.diagnosis is not None:
        diagnosis = req.diagnosis
    else:
        raw = req.error
        error: ErrorInfo | None = None
        if raw is not None:
            error = parse_error(
                traceback_text=raw.traceback_text,
                source_code=req.code,
                exception_type=raw.exception_type,
                message=raw.message,
                line_number=raw.line_number,
            )
        if error is None:
            from backend.runtimes import get_runtime

            runtime = get_runtime(detection_framework) if detection_framework else None
            execution = runtime.execute(req.code) if runtime else None
            error = error_from_execution(execution, req.code) if execution else None
            if error is None:
                return FixResponse(
                    status="no_error",
                    framework=framework,
                    detail="Code executed successfully; nothing to fix.",
                )
        diagnosis = classify(error)

    candidates = propose_fixes(req.code, diagnosis)
    if not candidates:
        return FixResponse(
            status="no_fix",
            framework=framework,
            diagnosis=diagnosis,
            detail="Heuristic fix engine has no strategy for this diagnosis yet.",
        )
    strategy, description, patched_code, conf = candidates[0]
    fix = ProposedFix(
        description=description,
        strategy=strategy,
        patched_code=patched_code,
        diff=unified_diff(req.code, patched_code),
        confidence=conf,
    )
    return FixResponse(status="proposed", framework=framework, diagnosis=diagnosis, fix=fix)


def supported_frameworks() -> list[dict]:
    from backend.runtimes import all_runtimes

    out = []
    for name, rt in sorted(all_runtimes().items()):
        out.append(
            {
                "name": name,
                "runtime_available": rt.is_available(),
                "version": rt.version(),
            }
        )
    return out
