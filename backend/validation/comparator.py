"""Comparator: compare original vs patched execution results."""
from __future__ import annotations

from backend.models import ExecutionResult


def results_differ(original: ExecutionResult, patched: ExecutionResult) -> bool:
    return original.success != patched.success


def summarize(original: ExecutionResult, patched: ExecutionResult) -> str:
    if not original.success and patched.success:
        return "Original failed, patched code succeeded."
    if original.success and patched.success:
        return "Both original and patched code succeeded."
    if not original.success and not patched.success:
        return "Both original and patched code failed."
    return "Original succeeded, patched code failed."
