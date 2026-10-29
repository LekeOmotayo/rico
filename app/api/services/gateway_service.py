"""
Gateway service layer for Rico Multi-Model Gateway.
Coordinates circuit-breaker routing, quota evaluation, and metrics telemetry.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from fastapi import HTTPException

from rico import (
    AllModelsExhaustedException,
    ChatCompletionRequest,
    ChatCompletionResponse,
    GatewayConfig,
    ModelMeshRouter,
    PrometheusMetricsCollector,
    TeamQuota,
    TeamQuotaRegistry,
    TokenOpsRateLimiter,
    get_structured_logger,
)
from app.api.repositories.circuit_repository import CircuitRepository
from app.api.repositories.quota_repository import QuotaRepository


class GatewayService:
    def __init__(
        self,
        config: Optional[GatewayConfig] = None,
        router: Optional[ModelMeshRouter] = None,
        quota_registry: Optional[TeamQuotaRegistry] = None,
        rate_limiter: Optional[TokenOpsRateLimiter] = None,
        metrics: Optional[PrometheusMetricsCollector] = None,
    ):
        self.config = config or GatewayConfig.load()
        self.logger = get_structured_logger("rico.gateway.service")
        self.router = router or ModelMeshRouter()
        self.quota_registry = quota_registry or TeamQuotaRegistry()
        self.rate_limiter = rate_limiter or TokenOpsRateLimiter(
            registry=self.quota_registry, redis_url=self.config.redis_url
        )
        self.metrics = metrics or PrometheusMetricsCollector()

        # Repositories for stateful access
        self.circuit_repo = CircuitRepository(self.router)
        self.quota_repo = QuotaRepository(self.quota_registry)

    async def execute_chat(
        self, payload: ChatCompletionRequest, team_id: str
    ) -> ChatCompletionResponse:
        start_t = time.perf_counter()
        try:
            response = await self.router.execute_chat(payload, team_id=team_id)
            duration_sec = time.perf_counter() - start_t

            self.metrics.record_request(
                team_id=team_id,
                model=response.model,
                status="success",
                fallback_triggered=response.fallback_trace.fallback_triggered,
                duration_sec=duration_sec,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )
            return response
        except AllModelsExhaustedException as exc:
            duration_sec = time.perf_counter() - start_t
            self.metrics.record_request(
                team_id=team_id,
                model="none",
                status="error",
                fallback_triggered=True,
                duration_sec=duration_sec,
                prompt_tokens=0,
                completion_tokens=0,
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "All LLM models in fallback mesh failed or timed out.",
                    "type": "all_models_exhausted",
                    "fallback_trace": exc.trace.model_dump(),
                },
            )

    def list_circuits(self) -> List[Dict[str, Any]]:
        return self.circuit_repo.list_all()

    def trip_circuit(self, model_id: str) -> bool:
        success = self.circuit_repo.trip(model_id)
        if success:
            self.metrics.record_circuit_trip(model_id)
        return success

    def reset_circuit(self, model_id: str) -> bool:
        return self.circuit_repo.reset(model_id)

    def list_team_quotas(self) -> List[Dict[str, Any]]:
        teams = self.quota_repo.list_all()
        return [self.rate_limiter.get_team_usage(t.team_id) for t in teams]

    def get_team_usage(self, team_id: str) -> Dict[str, Any]:
        return self.rate_limiter.get_team_usage(team_id)

    def update_team_quota(self, team_id: str, quota: TeamQuota) -> TeamQuota:
        quota.team_id = team_id
        return self.quota_repo.save(quota)

    def render_prometheus_metrics(self) -> str:
        for c in self.list_circuits():
            self.metrics.update_circuit_state(c["model_id"], c["state"])
        return self.metrics.render_prometheus_text()
