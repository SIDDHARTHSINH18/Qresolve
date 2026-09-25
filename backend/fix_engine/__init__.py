"""Fix engine: propose patches for diagnosed errors (heuristic for now)."""
from backend.fix_engine.diff import unified_diff
from backend.fix_engine.generator import propose_fixes

__all__ = ["propose_fixes", "unified_diff"]
