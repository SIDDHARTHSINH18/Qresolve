"""Hypothesis and attempt tracking primitives.

The Pydantic schemas themselves (ReasoningProposal, AttemptRecord,
ReasoningContext) live in backend/models.py so the API layer and the
reasoning layer share one source of truth. This module holds helpers for
deriving failure evidence from attempts.
"""
from __future__ import annotations

from backend.models import AttemptRecord, ErrorInfo


def describe_failure(previous: ErrorInfo | None, execution) -> str:
    """Explain why an attempt failed, from the actual new execution only."""
    if execution is None:
        return "Attempt could not be executed."
    if execution.success:
        return "succeeded"  # not a failure
    new_type = execution.exception_type
    new_msg = execution.exception_message
    if previous and new_type == previous.exception_type and new_msg == previous.message:
        return (
            f"Fix did not resolve the error: the runtime still raises {new_type}: {new_msg} "
            "(identical to the previous failure — the change did not address the cause)."
        )
    return (
        f"Fix changed the failure: runtime now raises {new_type}: {new_msg} "
        f"(previously {previous.exception_type}: {previous.message}) — new evidence for the next hypothesis."
    )


def failed_patches(attempts: list[AttemptRecord]) -> set[str]:
    return {a.patched_code for a in attempts if not a.verified and a.why_failed != "not executed"}
