"""
Tests for circuit breaker state machine and multi-model failover routing.
"""

import pytest
from rico.circuit.breaker import ModelCircuitBreaker
from rico.circuit.router import ModelMeshRouter, AllModelsExhaustedException
from rico.models import (
    ChatCompletionRequest,
    ChatMessage,
    CircuitState,
    ModelConfig,
    ModelTier,
)


def test_circuit_breaker_transitions():
    cfg = ModelConfig(
        model_id="test-model",
        display_name="Test Model",
        tier=ModelTier.PRIMARY,
        failure_threshold=2,
        recovery_time_sec=0.1,
    )
    breaker = ModelCircuitBreaker(cfg)

    # Initial state is CLOSED
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True

    # 1st failure
    breaker.record_failure(Exception("Timeout"))
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 1

    # 2nd failure -> Trips to OPEN
    breaker.record_failure(Exception("500 Server Error"))
    assert breaker.state == CircuitState.OPEN
    assert breaker.total_trips == 1

    # While recovery time not elapsed -> cannot execute
    # (force can_execute to evaluate before sleep)
    cfg.recovery_time_sec = 100.0
    assert breaker.can_execute() is False

    # Force recovery
    breaker.force_close()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.can_execute() is True


@pytest.mark.asyncio
async def test_router_normal_execution(router: ModelMeshRouter):
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Hello world")],
        team_id="team-ai-agents",
    )
    resp = await router.execute_chat(req)

    assert resp.model == "gpt-4o"
    assert resp.fallback_trace.fallback_triggered is False
    assert len(resp.choices) == 1
    assert "gpt-4o" in resp.choices[0].message.content.lower()


@pytest.mark.asyncio
async def test_router_automatic_failover(router: ModelMeshRouter):
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Test fallback")],
        team_id="team-ai-agents",
    )

    # Trip primary model (gpt-4o) open
    router.trip_circuit("gpt-4o")
    assert router.breakers["gpt-4o"].state == CircuitState.OPEN

    # Execute chat: should automatically degrade to gpt-4o-mini!
    resp = await router.execute_chat(req)

    assert resp.model == "gpt-4o-mini"
    assert resp.fallback_trace.fallback_triggered is True
    assert "gpt-4o" in resp.fallback_trace.attempted_models
    assert len(resp.fallback_trace.failover_reasons) >= 1


@pytest.mark.asyncio
async def test_router_degrade_to_local_fallback(router: ModelMeshRouter):
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Test local fallback")],
        team_id="team-ai-agents",
    )

    # Trip both primary and secondary
    router.trip_circuit("gpt-4o")
    router.trip_circuit("gpt-4o-mini")

    # Should degrade to local fallback
    resp = await router.execute_chat(req)

    assert resp.model == "llama-3-8b-local"
    assert resp.fallback_trace.fallback_triggered is True


@pytest.mark.asyncio
async def test_all_models_exhausted(router: ModelMeshRouter):
    req = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Test exhaustion")],
        team_id="team-ai-agents",
    )

    # Trip all models
    router.trip_circuit("gpt-4o")
    router.trip_circuit("gpt-4o-mini")
    router.trip_circuit("llama-3-8b-local")

    with pytest.raises(AllModelsExhaustedException) as exc_info:
        await router.execute_chat(req)

    assert exc_info.value.trace.final_model == "none"
