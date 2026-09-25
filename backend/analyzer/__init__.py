"""Analyzer: framework detection and error parsing."""
from backend.analyzer.error_parser import error_from_execution, parse_error, parse_traceback
from backend.analyzer.framework_detector import detect_framework

__all__ = ["detect_framework", "parse_error", "parse_traceback", "error_from_execution"]
