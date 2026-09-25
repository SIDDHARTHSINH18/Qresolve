"""Tests for /health and /api/frameworks."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_ok():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "QResolve"


def test_frameworks_endpoint():
    res = client.get("/api/frameworks")
    assert res.status_code == 200
    frameworks = res.json()["frameworks"]
    names = [f["name"] for f in frameworks]
    assert "qiskit" in names
    qiskit = next(f for f in frameworks if f["name"] == "qiskit")
    assert qiskit["runtime_available"] is True
    assert qiskit["version"]
