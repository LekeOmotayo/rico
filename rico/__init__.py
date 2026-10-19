"""
Rico — Advanced Multi-Model Gateway & TokenOps Proxy.
Provides circuit-breaker failovers, Redis-backed sliding window rate limits,
token-bucket quotas, and Prometheus telemetry.
"""

from rico.models import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    CircuitState,
    FallbackTrace,
    ModelConfig,
    ModelTier,
    RateLimitStatus,
    TeamQuota,
    UsageInfo,
)
from rico.config import GatewayConfig
from rico.circuit.breaker import ModelCircuitBreaker
from rico.circuit.router import ModelMeshRouter, AllModelsExhaustedException
from rico.rate_limit.quotas import TeamQuotaRegistry
from rico.rate_limit.limiter import TokenOpsRateLimiter
from rico.telemetry.metrics import PrometheusMetricsCollector
from rico.telemetry.tracing import TraceContext
from rico.telemetry.logger import get_structured_logger
from rico.middleware import RicoProxyMiddleware

__version__ = "1.0.0"

__all__ = [
    "GatewayConfig",
    "ModelCircuitBreaker",
    "ModelMeshRouter",
    "AllModelsExhaustedException",
    "TeamQuotaRegistry",
    "TokenOpsRateLimiter",
    "PrometheusMetricsCollector",
    "TraceContext",
    "get_structured_logger",
    "RicoProxyMiddleware",
    "ChatChoice",
    "ChatCompletionRequest",
    "ChatCompletionResponse",
    "ChatMessage",
    "CircuitState",
    "FallbackTrace",
    "ModelConfig",
    "ModelTier",
    "RateLimitStatus",
    "TeamQuota",
    "UsageInfo",
]
