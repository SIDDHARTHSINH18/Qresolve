"""Parse raw errors/tracebacks into structured ErrorInfo.

Generic — works for any Python traceback, not tied to one Qiskit error.
"""
from __future__ import annotations

import re

from backend.models import ErrorInfo, ExecutionResult

# Matches the last frame of a traceback: File "...", line N, in ...
_FRAME_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)')
# Matches a final "ExceptionType: message" line
_FINAL_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*(?:Error|Exception|Interrupt|Exit))(?::\s*(?P<msg>.*))?$")


def parse_traceback(traceback_text: str | None) -> dict:
    """Extract the innermost user frame line number and final exception line."""
    line_number = None
    final_type = None
    final_msg = None
    if traceback_text:
        for m in _FRAME_RE.finditer(traceback_text):
            if m.group("file") in ("user_code.py", "<string>", "<module>"):
                line_number = int(m.group("line"))
        lines = [ln for ln in traceback_text.strip().splitlines() if ln.strip()]
        for ln in reversed(lines):
            m = _FINAL_RE.match(ln.strip())
            if m:
                final_type = m.group("type").rsplit(".", 1)[-1]
                final_msg = (m.group("msg") or "").strip()
                break
    return {
        "line_number": line_number,
        "exception_type": final_type,
        "message": final_msg,
    }


def source_snippet(code: str, line_number: int | None, context: int = 2) -> str | None:
    if line_number is None or not code:
        return None
    lines = code.splitlines()
    idx = line_number - 1
    if idx < 0 or idx >= len(lines):
        return None
    lo, hi = max(0, idx - context), min(len(lines), idx + context + 1)
    return "\n".join(
        f"{n + 1:>4}: {lines[n]}" for n in range(lo, hi)
    )


def parse_error(
    traceback_text: str | None = None,
    source_code: str = "",
    exception_type: str | None = None,
    message: str | None = None,
    line_number: int | None = None,
) -> ErrorInfo:
    """Build an ErrorInfo from raw parts. Explicit fields win over parsed ones."""
    parsed = parse_traceback(traceback_text)
    final_type = exception_type or parsed["exception_type"]
    final_msg = message or parsed["message"]
    # Only trust a parsed line number if the traceback came from user code
    final_line = line_number
    if final_line is None and traceback_text and 'File "user_code.py"' in traceback_text:
        final_line = parsed["line_number"]
    return ErrorInfo(
        exception_type=final_type,
        message=final_msg,
        traceback_text=traceback_text,
        line_number=final_line,
        source_snippet=source_snippet(source_code, final_line),
    )


def error_from_execution(result: ExecutionResult, source_code: str = "") -> ErrorInfo | None:
    """Extract ErrorInfo from a sandbox ExecutionResult (never fabricates)."""
    if result.success and not result.exception_type:
        return None
    tb = result.traceback_text or result.stderr or None
    return parse_error(
        traceback_text=tb,
        source_code=source_code,
        exception_type=result.exception_type,
        message=result.exception_message,
    )
