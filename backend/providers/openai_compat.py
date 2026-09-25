"""OpenAI-compatible chat-completions provider.

Configuration (environment only — nothing is hard-coded):
- QRESOLVE_AI_BASE_URL  e.g. https://api.example.com/v1   (required)
- QRESOLVE_AI_API_KEY   bearer token                      (required)
- QRESOLVE_AI_MODEL     model identifier                  (required)

All three must be present; from_env() returns None otherwise, so tests and
local development run fully provider-free. No HTTP client dependency: uses
urllib from the standard library.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from backend.providers.base import (
    AIProvider,
    ProviderError,
    ProviderResponse,
    ProviderTimeout,
    extract_json_object,
)


class OpenAICompatibleProvider(AIProvider):
    name = "openai-compatible"

    def __init__(self, base_url: str, api_key: str, model: str, extra_headers: dict | None = None):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._extra_headers = extra_headers or {}

    @property
    def model_id(self) -> str:
        return self._model

    @classmethod
    def from_env(cls) -> "OpenAICompatibleProvider | None":
        base_url = os.environ.get("QRESOLVE_AI_BASE_URL")
        api_key = os.environ.get("QRESOLVE_AI_API_KEY")
        model = os.environ.get("QRESOLVE_AI_MODEL")
        if not (base_url and api_key and model):
            return None
        return cls(base_url=base_url, api_key=api_key, model=model)

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        payload = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                **self._extra_headers,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as resp:
                raw_body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # Only the status code is surfaced: response bodies may echo
            # request details and must never reach logs or API responses.
            raise ProviderError(f"Provider HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise ProviderTimeout(f"Provider timed out after {timeout_s}s") from None
            raise ProviderError(f"Provider unreachable: {type(getattr(exc, 'reason', exc)).__name__}") from None
        except TimeoutError as exc:
            raise ProviderTimeout(f"Provider timed out after {timeout_s}s") from None

        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ProviderError("Provider returned a non-JSON body") from None

        try:
            raw_text = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Unexpected provider response shape: {exc}") from exc

        return ProviderResponse(
            model=self._model,
            raw_text=raw_text,
            content=extract_json_object(raw_text),
        )
