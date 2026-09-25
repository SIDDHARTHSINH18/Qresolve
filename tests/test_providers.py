"""Tests for the provider abstraction (no real credentials, no network)."""
import pytest

from backend.providers.base import (
    AIProvider,
    ProviderError,
    ProviderResponse,
    extract_json_object,
)
from backend.providers.registry import (
    get_provider,
    register_provider,
    registered_providers,
    unregister_provider,
)


class _FakeProvider(AIProvider):
    name = "fake"

    def __init__(self, content: dict | None = None, raw: str = "", fail: bool = False):
        self._content = content
        self._raw = raw
        self._fail = fail
        self.prompts: list[str] = []

    @property
    def model_id(self) -> str:
        return "fake-model-1"

    def generate(self, prompt: str, *, timeout_s: float = 30.0) -> ProviderResponse:
        self.prompts.append(prompt)
        if self._fail:
            raise ProviderError("fake provider down")
        return ProviderResponse(model=self.model_id, content=self._content or {}, raw_text=self._raw)


# ---------------------------------------------------------------- registry
def test_no_provider_when_env_unset(monkeypatch):
    monkeypatch.delenv("QRESOLVE_AI_PROVIDER", raising=False)
    assert get_provider() is None


def test_unknown_provider_name_raises(monkeypatch):
    monkeypatch.setenv("QRESOLVE_AI_PROVIDER", "doesnotexist")
    with pytest.raises(Exception):
        get_provider()


def test_register_and_unregister(monkeypatch):
    name = "fake-test-only"
    register_provider(name, lambda: _FakeProvider())
    try:
        assert name in registered_providers()
        monkeypatch.setenv("QRESOLVE_AI_PROVIDER", name)
        provider = get_provider()
        assert isinstance(provider, _FakeProvider)
        assert provider.model_id == "fake-model-1"
    finally:
        unregister_provider(name)
    assert name not in registered_providers()


def test_provider_that_reports_unconfigured(monkeypatch):
    name = "fake-unconfigured"
    register_provider(name, lambda: None)
    try:
        monkeypatch.setenv("QRESOLVE_AI_PROVIDER", name)
        with pytest.raises(Exception):
            get_provider()
    finally:
        unregister_provider(name)


# ------------------------------------------------------- JSON extraction
def test_extract_json_from_fenced_block():
    text = 'Here you go:\n```json\n{"a": 1, "b": "x"}\n```\nDone.'
    assert extract_json_object(text) == {"a": 1, "b": "x"}


def test_extract_json_bare_object():
    assert extract_json_object('blah {"hypothesis": "h"} trailing') == {"hypothesis": "h"}


def test_extract_json_rejects_garbage():
    with pytest.raises(ProviderError):
        extract_json_object("no json here at all")
    with pytest.raises(ProviderError):
        extract_json_object("")
