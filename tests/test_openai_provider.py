"""Tests for the real OpenAI-compatible provider: HTTP mechanics, timeouts,
sanitization, env configuration, and end-to-end solve — all with a mocked
transport (no network, no real credentials)."""
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.providers.base import ProviderError, ProviderTimeout, ProviderUnavailable
from backend.providers.openai_compat import OpenAICompatibleProvider
from backend.providers.registry import get_provider
from backend.reasoning.engine import ReasoningEngine
from tests.test_reasoning import BROKEN_CODE, GOOD_CODE, VALID_PROPOSAL, _broken_context

SECRET_KEY = "sk-super-secret-test-key-9f3a"
BASE_URL = "https://ai.example.test/v1"
MODEL = "test-model"


def _provider():
    return OpenAICompatibleProvider(base_url=BASE_URL, api_key=SECRET_KEY, model=MODEL)


class _FakeHTTPResponse:
    def __init__(self, body: bytes):
        self._buf = io.BytesIO(body)

    def read(self):
        return self._buf.read()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _completion_body(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")


def _mock_urlopen(monkeypatch, handler):
    """Patch urllib.request.urlopen; handler(request, timeout) -> response | raise."""
    captured = {}

    def fake_urlopen(request, timeout=None, **kwargs):
        captured["request"] = request
        captured["timeout"] = timeout
        return handler(request, timeout)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    return captured


# ---------------------------------------------------------------- from_env
def test_from_env_requires_all_three_vars(monkeypatch):
    monkeypatch.delenv("QRESOLVE_AI_BASE_URL", raising=False)
    monkeypatch.delenv("QRESOLVE_AI_API_KEY", raising=False)
    monkeypatch.delenv("QRESOLVE_AI_MODEL", raising=False)
    assert OpenAICompatibleProvider.from_env() is None

    monkeypatch.setenv("QRESOLVE_AI_BASE_URL", BASE_URL)
    monkeypatch.setenv("QRESOLVE_AI_API_KEY", SECRET_KEY)
    assert OpenAICompatibleProvider.from_env() is None

    monkeypatch.setenv("QRESOLVE_AI_MODEL", MODEL)
    provider = OpenAICompatibleProvider.from_env()
    assert provider is not None
    assert provider.model_id == MODEL


def test_registry_openai_compat_unconfigured_raises_sanitized(monkeypatch):
    monkeypatch.setenv("QRESOLVE_AI_PROVIDER", "openai-compatible")
    monkeypatch.delenv("QRESOLVE_AI_BASE_URL", raising=False)
    monkeypatch.delenv("QRESOLVE_AI_API_KEY", raising=False)
    monkeypatch.delenv("QRESOLVE_AI_MODEL", raising=False)
    with pytest.raises(ProviderUnavailable) as exc_info:
        get_provider()
    assert SECRET_KEY not in str(exc_info.value)


# ---------------------------------------------------------------- success
def test_generate_success_parses_structured_content(monkeypatch):
    payload = json.dumps(VALID_PROPOSAL)
    captured = _mock_urlopen(
        monkeypatch, lambda req, timeout: _FakeHTTPResponse(_completion_body(payload))
    )
    response = _provider().timed_generate("solve this", timeout_s=7.5)

    assert response.content["next_action"] == "apply_fix"
    assert response.content["patched_code"] == GOOD_CODE
    assert response.model == MODEL
    assert response.latency_ms is not None and response.latency_ms >= 0

    request = captured["request"]
    assert request.full_url == f"{BASE_URL}/chat/completions"
    assert request.get_header("Authorization") == f"Bearer {SECRET_KEY}"
    assert captured["timeout"] == 7.5  # timeout is bounded and propagated
    sent = json.loads(request.data.decode("utf-8"))
    assert sent["model"] == MODEL
    assert sent["messages"] == [{"role": "user", "content": "solve this"}]
    assert sent["response_format"] == {"type": "json_object"}


def test_generate_accepts_fenced_json_text(monkeypatch):
    text = "Sure!\n```json\n" + json.dumps(VALID_PROPOSAL) + "\n```"
    _mock_urlopen(monkeypatch, lambda req, timeout: _FakeHTTPResponse(_completion_body(text)))
    response = _provider().generate("prompt")
    assert response.content["hypothesis"] == VALID_PROPOSAL["hypothesis"]


# ---------------------------------------------------------------- failures
def test_generate_timeout_raises_provider_timeout(monkeypatch):
    def raise_timeout(req, timeout):
        raise TimeoutError("timed out")

    _mock_urlopen(monkeypatch, raise_timeout)
    with pytest.raises(ProviderTimeout):
        _provider().generate("prompt", timeout_s=1.0)


def test_generate_urlerror_timeout_raises_provider_timeout(monkeypatch):
    def raise_urlerror(req, timeout):
        raise urllib.error.URLError(TimeoutError("timed out"))

    _mock_urlopen(monkeypatch, raise_urlerror)
    with pytest.raises(ProviderTimeout):
        _provider().generate("prompt", timeout_s=1.0)


def test_generate_http_error_sanitized(monkeypatch):
    def raise_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {}, None)

    _mock_urlopen(monkeypatch, raise_http)
    with pytest.raises(ProviderError) as exc_info:
        _provider().generate("prompt")
    message = str(exc_info.value)
    assert "500" in message
    assert SECRET_KEY not in message
    assert BASE_URL not in message


def test_generate_unreachable_sanitized(monkeypatch):
    def raise_urlerror(req, timeout):
        raise urllib.error.URLError(ConnectionRefusedError("connection refused"))

    _mock_urlopen(monkeypatch, raise_urlerror)
    with pytest.raises(ProviderError) as exc_info:
        _provider().generate("prompt")
    message = str(exc_info.value)
    assert SECRET_KEY not in message
    assert "connection refused" not in message  # raw socket detail withheld


def test_generate_non_json_body_raises_provider_error(monkeypatch):
    _mock_urlopen(
        monkeypatch,
        lambda req, timeout: _FakeHTTPResponse(b"<html>gateway error</html>"),
    )
    with pytest.raises(ProviderError) as exc_info:
        _provider().generate("prompt")
    assert "non-JSON" in str(exc_info.value)


def test_generate_malformed_shape_raises_provider_error(monkeypatch):
    _mock_urlopen(
        monkeypatch,
        lambda req, timeout: _FakeHTTPResponse(json.dumps({"unexpected": True}).encode()),
    )
    with pytest.raises(ProviderError) as exc_info:
        _provider().generate("prompt")
    assert "Unexpected provider response shape" in str(exc_info.value)


# ------------------------------------------------- engine-level resilience
def test_provider_timeout_falls_back_to_heuristic():
    class _TimeoutProvider(OpenAICompatibleProvider):
        def generate(self, prompt, *, timeout_s=30.0):
            raise ProviderTimeout("timed out")

    context, _, _ = _broken_context()
    engine = ReasoningEngine(provider=_TimeoutProvider(BASE_URL, SECRET_KEY, MODEL))
    proposal, source = engine.propose(context)
    assert source == "heuristic"
    assert "qc.cx(0, 1)" in proposal.patched_code


def test_unexpected_provider_bug_falls_back_to_heuristic():
    class _BuggyProvider(OpenAICompatibleProvider):
        def generate(self, prompt, *, timeout_s=30.0):
            raise RuntimeError("unexpected internal bug")

    context, _, _ = _broken_context()
    engine = ReasoningEngine(provider=_BuggyProvider(BASE_URL, SECRET_KEY, MODEL))
    proposal, source = engine.propose(context)
    assert source == "heuristic"
    assert proposal.next_action == "apply_fix"


# ------------------------------------------------------------ end-to-end
def test_api_solve_uses_env_configured_provider(monkeypatch):
    monkeypatch.setenv("QRESOLVE_AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("QRESOLVE_AI_BASE_URL", BASE_URL)
    monkeypatch.setenv("QRESOLVE_AI_API_KEY", SECRET_KEY)
    monkeypatch.setenv("QRESOLVE_AI_MODEL", MODEL)
    _mock_urlopen(
        monkeypatch,
        lambda req, timeout: _FakeHTTPResponse(_completion_body(json.dumps(VALID_PROPOSAL))),
    )

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/api/solve", json={"code": BROKEN_CODE})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "solved"
    assert body["attempts"][0]["source"] == "ai"
    assert body["verification"]["verified"] is True
    assert body["fix"]["patched_code"] == GOOD_CODE
    assert SECRET_KEY not in response.text


def test_api_solve_survives_provider_outage(monkeypatch):
    monkeypatch.setenv("QRESOLVE_AI_PROVIDER", "openai-compatible")
    monkeypatch.setenv("QRESOLVE_AI_BASE_URL", BASE_URL)
    monkeypatch.setenv("QRESOLVE_AI_API_KEY", SECRET_KEY)
    monkeypatch.setenv("QRESOLVE_AI_MODEL", MODEL)

    def raise_http(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable", {}, None)

    _mock_urlopen(monkeypatch, raise_http)

    client = TestClient(app, raise_server_exceptions=True)
    response = client.post("/api/solve", json={"code": BROKEN_CODE})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "solved"  # heuristic fallback carried the solve
    assert all(a["source"] == "heuristic" for a in body["attempts"])
    assert SECRET_KEY not in response.text
