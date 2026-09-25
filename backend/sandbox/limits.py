"""Execution limits for the sandbox."""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 30.0
MAX_TIMEOUT_S = 120.0
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024


@dataclass(frozen=True)
class SandboxLimits:
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        if self.timeout_s <= 0 or self.timeout_s > MAX_TIMEOUT_S:
            raise ValueError(f"timeout_s must be in (0, {MAX_TIMEOUT_S}]")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
