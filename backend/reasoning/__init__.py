"""Reasoning package.

engine.py    — evidence -> validated proposal (AI provider with heuristic fallback)
hypotheses.py— failure-evidence helpers over attempt records
strategies.py— progressive level 1-5 analyzers
adaptive.py  — bounded failure-driven retry controller
"""
from backend.reasoning.adaptive import AdaptiveController, MAX_ATTEMPTS
from backend.reasoning.engine import ReasoningEngine
from backend.reasoning.strategies import gather_findings

__all__ = ["AdaptiveController", "MAX_ATTEMPTS", "ReasoningEngine", "gather_findings"]
