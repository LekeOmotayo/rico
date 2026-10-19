"""
Pytest fixtures for Rico Multi-Model Gateway.
"""

import pytest
from rico.config import GatewayConfig
from rico.circuit.router import ModelMeshRouter
from rico.rate_limit.quotas import TeamQuotaRegistry
from rico.rate_limit.limiter import TokenOpsRateLimiter
from rico.telemetry.metrics import PrometheusMetricsCollector


@pytest.fixture
def config() -> GatewayConfig:
    return GatewayConfig(
        service_name="rico-test",
        env="testing",
        default_failure_threshold=3,
        default_recovery_time_sec=1.0,
    )


@pytest.fixture
def router() -> ModelMeshRouter:
    return ModelMeshRouter()


@pytest.fixture
def quota_registry() -> TeamQuotaRegistry:
    return TeamQuotaRegistry()


@pytest.fixture
def rate_limiter(quota_registry) -> TokenOpsRateLimiter:
    return TokenOpsRateLimiter(registry=quota_registry, redis_url=None)


@pytest.fixture
def metrics() -> PrometheusMetricsCollector:
    return PrometheusMetricsCollector()
