"""Adaptive retry controller: bounded, failure-driven solving loop.

For each attempt: gather findings at the current reasoning level, obtain a
proposal (AI if configured, else heuristic), execute the patched code in
the real runtime, and let the validator decide. Failures are recorded with
concrete evidence and drive both the next hypothesis and level escalation.
"""
from __future__ import annotations

import uuid

from backend.analyzer import detect_framework, error_from_execution, parse_error
from backend.diagnostics import classify
from backend.fix_engine import unified_diff
from backend.models import (
    AttemptRecord,
    EnvironmentInfo,
    ErrorInfo,
    FrameworkDetection,
    ProposedFix,
    ReasoningContext,
    SolveRequest,
    SolveResponse,
    Verification,
)
from backend.providers.base import AIProvider
from backend.runtimes.base import QuantumRuntime
from backend.validation import verify_fix

MAX_ATTEMPTS = 5
MAX_LEVEL = 5


class AdaptiveController:
    def __init__(
        self,
        runtime: QuantumRuntime,
        provider: AIProvider | None = None,
        max_attempts: int = MAX_ATTEMPTS,
        provider_timeout_s: float = 30.0,
    ):
        from backend.reasoning.engine import ReasoningEngine

        self.runtime = runtime
        self.max_attempts = max(1, max_attempts)
        self.engine = ReasoningEngine(provider=provider, provider_timeout_s=provider_timeout_s)

    # ------------------------------------------------------------------
    def solve(self, req: SolveRequest) -> SolveResponse:
        framework_name, confidence, matched = detect_framework(req.code)
        if req.framework:
            if req.framework.lower() not in _known_frameworks():
                raise LookupError(f"Unknown framework: {req.framework}")
            framework_name = req.framework
        framework = FrameworkDetection(framework=framework_name, confidence=confidence, matched_patterns=matched)

        # Runtime reproduction (the evidence source of truth)
        execution = self.runtime.execute(req.code)
        if not execution.success:
            error = error_from_execution(execution, req.code)
        elif req.error is not None:
            error = parse_error(
                traceback_text=req.error.traceback_text,
                source_code=req.code,
                exception_type=req.error.exception_type,
                message=req.error.message,
                line_number=req.error.line_number,
            )
        else:
            error = None

        if error is None:
            return SolveResponse(
                status="no_error",
                framework=framework,
                execution=execution,
                detail="Code executed successfully; nothing to solve.",
            )

        diagnosis = classify(error)
        environment = EnvironmentInfo(
            framework_versions={self.runtime.name: self.runtime.version() or "unknown"}
        )
        knowledge = _knowledge_for(diagnosis.category)

        attempts: list[AttemptRecord] = []
        level = 1
        verified_fix: ProposedFix | None = None
        verification: Verification | None = None
        stop_reason: str | None = None

        for attempt_no in range(1, self.max_attempts + 1):
            context = ReasoningContext(
                code=req.code,
                framework=framework_name,
                error=error,
                diagnosis=diagnosis,
                environment=environment,
                knowledge=knowledge,
                attempts=attempts,
                level=level,
            )
            proposal, source = self.engine.propose(context, framework_version=self.runtime.version())

            if proposal.next_action != "apply_fix" or not proposal.patched_code.strip():
                stop_reason = (
                    f"No viable hypothesis at attempt {attempt_no} "
                    f"(next_action={proposal.next_action})."
                )
                break

            if proposal.patched_code in {a.patched_code for a in attempts if not a.verified}:
                record = AttemptRecord(
                    attempt=attempt_no,
                    level=level,
                    source=source,
                    hypothesis=proposal.hypothesis,
                    fix_description=proposal.proposed_fix,
                    patched_code=proposal.patched_code,
                    verified=False,
                    why_failed=(
                        "Repeated an already-failed patch; rejected without execution "
                        "to avoid looping on the same hypothesis."
                    ),
                )
                attempts.append(record)
                level = min(MAX_LEVEL, level + 1)
                continue

            v = verify_fix(self.runtime, proposal.patched_code)
            why_failed = None
            if v.verified:
                verified_fix = ProposedFix(
                    description=proposal.proposed_fix,
                    strategy=f"{source}:{proposal.hypothesis[:60]}",
                    patched_code=proposal.patched_code,
                    diff=unified_diff(req.code, proposal.patched_code),
                    confidence=proposal.confidence,
                )
                verification = v
            else:
                from backend.reasoning.hypotheses import describe_failure

                why_failed = describe_failure(error, v.execution)
                verification = v

            attempts.append(
                AttemptRecord(
                    attempt=attempt_no,
                    level=level,
                    source=source,
                    hypothesis=proposal.hypothesis,
                    fix_description=proposal.proposed_fix,
                    patched_code=proposal.patched_code,
                    verified=v.verified,
                    execution=v.execution,
                    why_failed=why_failed,
                )
            )

            if v.verified:
                return self._response(
                    "solved", framework, execution, error, diagnosis,
                    verified_fix, verification, attempts, level, None,
                )

            # Failure-driven escalation: real evidence decides the new level.
            error = error_from_execution(v.execution, req.code) or error
            diagnosis = classify(error)
            if why_failed and "identical to the previous failure" in why_failed:
                level = min(MAX_LEVEL, level + 1)
            elif len(attempts) >= 2:
                level = min(MAX_LEVEL, level + 1)

        if stop_reason is None:
            stop_reason = f"Maximum attempts ({self.max_attempts}) reached without a verified fix."
        return self._response(
            "unsolved", framework, execution, error, diagnosis,
            None, verification, attempts, level, stop_reason,
        )

    # ------------------------------------------------------------------
    def _response(
        self, status, framework, execution, error, diagnosis,
        fix, verification, attempts, level, detail,
    ) -> SolveResponse:
        return SolveResponse(
            status=status,
            framework=framework,
            execution=execution,
            error=error,
            diagnosis=diagnosis,
            fix=fix,
            verification=verification,
            attempts=attempts,
            final_level=level,
            detail=detail,
        )


def _known_frameworks() -> set[str]:
    from backend.analyzer.framework_detector import FRAMEWORK_SPECS

    return {s.name for s in FRAMEWORK_SPECS}


def _knowledge_for(category: str | None) -> list[str]:
    if not category or category == "unknown":
        return []
    from backend.knowledge.errors import PATTERNS

    return [p.pattern_id for p in PATTERNS if p.pattern_id == category]
