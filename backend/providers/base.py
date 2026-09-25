"""AI provider abstraction.

A provider turns a prompt into a structured (JSON-decoded) response.
Implementations must never embed credentials: configuration comes from the
environment (left unset by default, so the system runs provider-free and the
heuristic fallback carries the load).
"""
from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(Exception):
    """Generic provider failure (network, HTTP, decode, policy)."""


class ProviderTimeout(ProviderError):
    """The provider did not answer within the allotted time."""


class ProviderUnavailable(ProviderError):
    """No provider is configured or the configured one cannot be reached."""


@dataclass
class ProviderResponse:
    model: str
    content: dict            # structured, JSON-decoded payload
    raw_text: str = ""
    latency_ms: float | None = None
    metadata: dict = field(default_factory=dict)


def extract_json_object(text: str) -> dict:
    """Extract the first JSON object from model text (fenced or bare).

    Raises ProviderError if no parseable object is found — malformed model
    output must be rejected, never guessed at.
    """
    if not text or not text.strip():
        raise ProviderError("Empty provider response")

    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fenced:
        candidates.append(fenced.group(1))
    # First balanced top-level object as a fallback
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                candidates.append(text[start : i + 1])
                break
    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ProviderError("No valid JSON object found in provider response")


class AIProvider(ABC):
    """Model-agnostic provider interface."""

    name: str = "abstract"

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the backing model (reported, never secret)."""

    @abstractmethod
    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        """Generate a structured response for `prompt`.

        Implementations must:
        - respect timeout_s (raise ProviderTimeout on expiry)
        - return JSON-decoded content (dict) in ProviderResponse.content
        - raise ProviderError subclasses on any failure (never return None)
        """

    def timed_generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        """Shared wrapper adding latency measurement."""
        started = time.perf_counter()
        response = self.generate(prompt, timeout_s=timeout_s)
        response.latency_ms = (time.perf_counter() - started) * 1000.0
        return response
