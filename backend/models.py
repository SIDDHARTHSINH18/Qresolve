"""Shared Pydantic models for QResolve requests and responses."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EnvironmentInfo(BaseModel):
    """Version/environment information supplied by the client (all optional)."""

    python_version: Optional[str] = None
    framework_versions: dict[str, str] = Field(default_factory=dict)
    notes: Optional[str] = None


class ErrorInput(BaseModel):
    """Raw error information as submitted by the client."""

    exception_type: Optional[str] = None
    message: Optional[str] = None
    traceback_text: Optional[str] = None
    line_number: Optional[int] = None


class FrameworkDetection(BaseModel):
    framework: Optional[str] = None
    confidence: float = 0.0
    matched_patterns: list[str] = Field(default_factory=list)


class ErrorInfo(BaseModel):
    """Structured error extracted from a traceback or runtime result."""

    exception_type: Optional[str] = None
    message: Optional[str] = None
    traceback_text: Optional[str] = None
    line_number: Optional[int] = None
    source_snippet: Optional[str] = None


class ExecutionResult(BaseModel):
    """Result of executing quantum code inside the sandbox."""

    success: bool
    exit_code: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    exception_type: Optional[str] = None
    exception_message: Optional[str] = None
    traceback_text: Optional[str] = None
    execution_time_ms: Optional[float] = None
    timed_out: bool = False
    output_truncated: bool = False
    error: Optional[ErrorInfo] = None


class AnalyzeRequest(BaseModel):
    code: str
    error: Optional[ErrorInput] = None
    environment: Optional[EnvironmentInfo] = None


class AnalyzeResponse(BaseModel):
    framework: FrameworkDetection
    error: Optional[ErrorInfo] = None


class DiagnoseRequest(AnalyzeRequest):
    """Analyze request plus optional flag to execute the code when no error is given."""

    run_if_no_error: bool = True


class Hypothesis(BaseModel):
    cause: str
    suggestion: str
    confidence: float = 0.0


class Diagnosis(BaseModel):
    summary: str
    category: str
    error: Optional[ErrorInfo] = None
    hypotheses: list[Hypothesis] = Field(default_factory=list)


class ProposedFix(BaseModel):
    description: str
    strategy: str
    patched_code: str
    diff: str
    confidence: float = 0.0


class ReasoningProposal(BaseModel):
    """Structured, validated AI/heuristic reasoning output.

    This is always a *proposal*: only the validator (real runtime execution)
    may declare a fix verified.
    """

    hypothesis: str = Field(min_length=1)
    diagnosis: str = Field(min_length=1)
    proposed_fix: str = Field(min_length=1)
    patched_code: str
    reasoning_summary: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    next_action: str = "apply_fix"  # apply_fix | need_more_info | give_up


class AttemptRecord(BaseModel):
    """One bounded attempt: hypothesis -> fix -> execution -> verdict."""

    attempt: int
    level: int
    source: str  # "ai" | "heuristic"
    hypothesis: str
    fix_description: str
    patched_code: str
    verified: bool = False
    execution: Optional[ExecutionResult] = None
    why_failed: Optional[str] = None


class ReasoningContext(BaseModel):
    """Everything the reasoning engine may look at for one proposal."""

    code: str
    framework: Optional[str] = None
    error: Optional[ErrorInfo] = None
    diagnosis: Optional[Diagnosis] = None
    environment: Optional[EnvironmentInfo] = None
    knowledge: list[str] = Field(default_factory=list)
    attempts: list[AttemptRecord] = Field(default_factory=list)
    level: int = 1


class FixRequest(BaseModel):
    code: str
    diagnosis: Optional[Diagnosis] = None
    error: Optional[ErrorInput] = None


class FixResponse(BaseModel):
    fix: Optional[ProposedFix] = None
    diagnosis: Optional[Diagnosis] = None
    status: str
    detail: Optional[str] = None


class VerifyRequest(BaseModel):
    code: str
    framework: Optional[str] = None


class Verification(BaseModel):
    verified: bool
    execution: ExecutionResult
    notes: Optional[str] = None


class RunRequest(BaseModel):
    code: str
    framework: Optional[str] = None
    timeout_seconds: Optional[float] = None


class SolveRequest(BaseModel):
    code: str
    error: Optional[ErrorInput] = None
    framework: Optional[str] = None
    environment: Optional[EnvironmentInfo] = None
    timeout_seconds: Optional[float] = None


class SolveResponse(BaseModel):
    status: str  # "solved" | "unsolved" | "no_error"
    framework: FrameworkDetection
    execution: Optional[ExecutionResult] = None
    error: Optional[ErrorInfo] = None
    diagnosis: Optional[Diagnosis] = None
    fix: Optional[ProposedFix] = None
    verification: Optional[Verification] = None
    attempts: list[AttemptRecord] = Field(default_factory=list)
    final_level: int = 1
    detail: Optional[str] = None
