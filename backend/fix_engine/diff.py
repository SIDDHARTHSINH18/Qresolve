"""Diff helpers for proposed fixes."""
from __future__ import annotations

import difflib


def unified_diff(original: str, patched: str, fromfile: str = "original.py", tofile: str = "patched.py") -> str:
    return "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            patched.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
