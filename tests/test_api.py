"""
Integration tests for FastAPI endpoints, proxy routing, and middleware.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_readiness():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res_ready = client.get("/ready")
    assert res_ready.status_code == 200


def test_prometheus_metrics_endpoint():
    res = client.get("/metrics")
    assert res.status_code == 200
    assert "rico_requests_total" in res.text
    assert "text/plain" in res.headers["content-type"]


def test_chat_completions_endpoint():
    payload = {
        "model": "gpt-4o",
        "messages": [{"role": "user", "content": "Integration test query"}],
        "team_id": "team-ai-agents",
    }
    res = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"X-Team-ID": "team-ai-agents"},
    )
    assert res.status_code == 200
    data = res.json()

    assert data["model"] == "gpt-4o"
    assert "fallback_trace" in data
    assert "X-Trace-Id" in res.headers
    assert "X-RateLimit-Limit-RPM" in res.headers


def test_circuit_breaker_admin_api():
    # 1. List circuits
    list_res = client.get("/v1/circuits")
    assert list_res.status_code == 200
    circuits = list_res.json()
    assert any(c["model_id"] == "gpt-4o" for c in circuits)

    # 2. Trip circuit
    trip_res = client.post("/v1/circuits/gpt-4o/trip")
    assert trip_res.status_code == 200

    # Verify model is now OPEN
    list_res2 = client.get("/v1/circuits")
    gpt4o = next(c for c in list_res2.json() if c["model_id"] == "gpt-4o")
    assert gpt4o["state"] == "OPEN"

    # 3. Call chat completion -> should automatically failover to gpt-4o-mini!
    chat_res = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "Test failover"}]},
        headers={"X-Team-ID": "team-ai-agents"},
    )
    assert chat_res.status_code == 200
    assert chat_res.json()["model"] == "gpt-4o-mini"
    assert chat_res.json()["fallback_trace"]["fallback_triggered"] is True

    # 4. Reset circuit back to CLOSED
    reset_res = client.post("/v1/circuits/gpt-4o/reset")
    assert reset_res.status_code == 200


def test_quotas_admin_api():
    res = client.get("/v1/quotas/teams")
    assert res.status_code == 200
    teams = res.json()
    assert isinstance(teams, list)
    assert any(t["team_id"] == "team-ai-agents" for t in teams)

    # Get single team
    res_single = client.get("/v1/quotas/teams/team-ai-agents")
    assert res_single.status_code == 200
    assert res_single.json()["team_id"] == "team-ai-agents"
