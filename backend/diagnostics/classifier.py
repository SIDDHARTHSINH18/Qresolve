"""Diagnosis: classify a parsed error into a Diagnosis with hypotheses."""
from __future__ import annotations

from backend.knowledge.errors import match_pattern
from backend.models import Diagnosis, ErrorInfo, Hypothesis

GENERIC_HYPOTHESIS = Hypothesis(
    cause="The runtime raised an error while executing the code.",
    suggestion="Inspect the traceback and the failing source line.",
    confidence=0.2,
)


def classify(error: ErrorInfo | None) -> Diagnosis:
    if error is None or (not error.exception_type and not error.message):
        return Diagnosis(summary="No error to diagnose.", category="none", error=error)

    pattern = match_pattern(error.exception_type, error.message)
    if pattern is None:
        return Diagnosis(
            summary=f"Unclassified {error.exception_type or 'error'}: {error.message or ''}".strip(),
            category="unknown",
            error=error,
            hypotheses=[GENERIC_HYPOTHESIS],
        )

    hypotheses = [
        Hypothesis(cause=cause, suggestion=suggestion, confidence=conf)
        for cause, suggestion, conf in pattern.causes
    ]
    return Diagnosis(
        summary=pattern.summary,
        category=pattern.pattern_id,
        error=error,
        hypotheses=hypotheses,
    )
