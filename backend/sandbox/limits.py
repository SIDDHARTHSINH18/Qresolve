"""Execution limits for the sandbox."""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TIMEOUT_S = 30.0
MAX_TIMEOUT_S = 120.0
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024
# A fixed, published ceiling rather than a fraction of the machine's RAM: two
# runs of the same program must fail or succeed for the same reason on any
# host. A state-vector simulation beyond ~2^28 amplitudes needs more than this
# and will surface a MemoryError inside the sandbox, which the pipeline can
# diagnose instead of silently swapping until the host stalls.
DEFAULT_MAX_MEMORY_MB = 4096

# A worker thread can legitimately burn CPU faster than the wall clock, so the
# per-process CPU ceiling is scaled by the cores the child may use. It exists
# to bound a runaway multithreaded simulation, not to second-guess the timeout.
_CPU_TIME_FACTOR = 2.0


@dataclass(frozen=True)
class SandboxLimits:
    timeout_s: float = DEFAULT_TIMEOUT_S
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES
    max_memory_mb: int = DEFAULT_MAX_MEMORY_MB
    max_cpu_s: float | None = None

    def __post_init__(self) -> None:
        if self.timeout_s <= 0 or self.timeout_s > MAX_TIMEOUT_S:
            raise ValueError(f"timeout_s must be in (0, {MAX_TIMEOUT_S}]")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        if self.max_memory_mb <= 0:
            raise ValueError("max_memory_mb must be positive")
        if self.max_cpu_s is not None and self.max_cpu_s <= 0:
            raise ValueError("max_cpu_s must be positive")

    @property
    def max_memory_bytes(self) -> int:
        return self.max_memory_mb * 1024 * 1024

    @property
    def cpu_limit_s(self) -> float:
        """The CPU-time ceiling actually applied to a run."""
        if self.max_cpu_s is not None:
            return self.max_cpu_s
        return self.timeout_s * max(1, (os.cpu_count() or 1)) * _CPU_TIME_FACTOR
