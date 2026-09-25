"""Quantum runtime registry.

Add a new framework by implementing QuantumRuntime and registering it here.
All four runtimes share the single sandbox path in backend/runtimes/_exec.py.
"""
from __future__ import annotations

from backend.runtimes.base import QuantumRuntime
from backend.runtimes.cirq import CirqRuntime
from backend.runtimes.openqasm import OpenQasmRuntime
from backend.runtimes.pennylane_rt import PennyLaneRuntime
from backend.runtimes.qiskit import QiskitRuntime

_REGISTRY: dict[str, QuantumRuntime] = {}


def _register(runtime: QuantumRuntime) -> None:
    _REGISTRY[runtime.name] = runtime


_register(QiskitRuntime())
_register(CirqRuntime())
_register(PennyLaneRuntime())
_register(OpenQasmRuntime())


def get_runtime(name: str) -> QuantumRuntime | None:
    return _REGISTRY.get(name.lower())


def all_runtimes() -> dict[str, QuantumRuntime]:
    return dict(_REGISTRY)


__all__ = [
    "QuantumRuntime",
    "QiskitRuntime",
    "CirqRuntime",
    "PennyLaneRuntime",
    "OpenQasmRuntime",
    "get_runtime",
    "all_runtimes",
]
