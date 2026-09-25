"""FastAPI routes for QResolve."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.analyzer import detect_framework, error_from_execution, parse_error
from backend.api.solve import run_fix, run_solve_pipeline, supported_frameworks
from backend.diagnostics import classify
from backend.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    DiagnoseRequest,
    Diagnosis,
    FixRequest,
    FixResponse,
    FrameworkDetection,
    RunRequest,
    SolveRequest,
    SolveResponse,
    Verification,
    VerifyRequest,
)
from backend.runtimes import all_runtimes, get_runtime
from backend.sandbox.limits import SandboxLimits

router = APIRouter(prefix="/api")


@router.get("/frameworks")
def list_frameworks():
    return {"frameworks": supported_frameworks()}


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest):
    framework, confidence, matched = detect_framework(req.code)
    detection = FrameworkDetection(framework=framework, confidence=confidence, matched_patterns=matched)

    error = None
    if req.error is not None:
        error = parse_error(
            traceback_text=req.error.traceback_text,
            source_code=req.code,
            exception_type=req.error.exception_type,
            message=req.error.message,
            line_number=req.error.line_number,
        )
    return AnalyzeResponse(framework=detection, error=error)


@router.post("/diagnose", response_model=Diagnosis)
def diagnose(req: DiagnoseRequest):
    error = None
    if req.error is not None:
        error = parse_error(
            traceback_text=req.error.traceback_text,
            source_code=req.code,
            exception_type=req.error.exception_type,
            message=req.error.message,
            line_number=req.error.line_number,
        )
    elif req.run_if_no_error:
        framework, _, _ = detect_framework(req.code)
        runtime = get_runtime(framework) if framework else None
        if runtime is not None:
            execution = runtime.execute(req.code)
            error = error_from_execution(execution, req.code)
        elif req.code.strip():
            raise HTTPException(
                status_code=422,
                detail="No runtime for the detected framework; supply error info or run_if_no_error=false.",
            )
    return classify(error)


@router.post("/fix", response_model=FixResponse)
def fix(req: FixRequest):
    return run_fix(req)


@router.post("/validate", response_model=Verification)
def validate(req: VerifyRequest):
    framework, _, _ = detect_framework(req.code)
    name = req.framework or framework
    runtime = get_runtime(name) if name else None
    if runtime is None:
        raise HTTPException(status_code=422, detail=f"No runtime available for framework: {name}")
    execution = runtime.execute(req.code)
    return Verification(
        verified=execution.success,
        execution=execution,
        notes=(
            "Code executed successfully in the sandbox."
            if execution.success
            else "Code failed at runtime."
        ),
    )


@router.post("/run")
def run(req: RunRequest):
    framework, _, _ = detect_framework(req.code)
    name = req.framework or framework
    runtime = get_runtime(name) if name else None
    if runtime is None:
        raise HTTPException(status_code=422, detail=f"No runtime available for framework: {name}")
    limits = SandboxLimits(timeout_s=req.timeout_seconds) if req.timeout_seconds else None
    return runtime.execute(req.code, limits=limits)


@router.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    try:
        return run_solve_pipeline(req)
    except LookupError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
