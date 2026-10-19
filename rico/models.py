"""
Data models, schemas, and enums for Rico Multi-Model Gateway & TokenOps Proxy.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"         # Normal operation: traffic routes to primary
    OPEN = "OPEN"             # Tripped: primary is failing, traffic bypassed to fallback
    HALF_OPEN = "HALF_OPEN"   # Probing: testing canary requests to check if primary recovered


class ModelTier(str, Enum):
    """Model prioritization hierarchy."""
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"


class ModelConfig(BaseModel):
    """Configuration for an upstream LLM provider model."""
    model_id: str
    display_name: str
    tier: ModelTier
    provider: str = "openai" # "openai", "anthropic", "ollama", "mock"
    endpoint_url: Optional[str] = None
    timeout_sec: float = 3.0
    failure_threshold: int = 3       # Number of consecutive failures to trip circuit
    recovery_time_sec: float = 20.0   # Duration to stay OPEN before HALF_OPEN probe
    cost_per_1k_input: float = 0.005
    cost_per_1k_output: float = 0.015
    enabled: bool = True


class ChatMessage(BaseModel):
    """Chat message schema."""
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion payload."""
    model: Optional[str] = "gpt-4o"
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = 1024
    stream: bool = False
    team_id: str = "default-team"


class UsageInfo(BaseModel):
    """Token consumption info."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatChoice(BaseModel):
    """Completion choice."""
    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class FallbackTrace(BaseModel):
    """Detailed audit trace of failover resolution."""
    attempted_models: List[str] = Field(default_factory=list)
    final_model: str
    fallback_triggered: bool = False
    failover_reasons: List[str] = Field(default_factory=list)
    circuit_states: Dict[str, str] = Field(default_factory=dict)
    total_latency_ms: float = 0.0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response with Rico metadata."""
    id: str = Field(default_factory=lambda: f"chatcmpl-rico-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatChoice]
    usage: UsageInfo
    fallback_trace: FallbackTrace


class TeamQuota(BaseModel):
    """TokenOps rate limits and quotas for an engineering team."""
    team_id: str
    name: str
    rpm_limit: int = 60          # Requests per minute
    tpm_limit: int = 100_000     # Tokens per minute
    tier_name: str = "standard"  # "free", "standard", "enterprise"
    enabled: bool = True


class RateLimitStatus(BaseModel):
    """Outcome of TokenOps quota validation."""
    allowed: bool
    team_id: str
    current_rpm: int
    remaining_rpm: int
    limit_rpm: int
    current_tpm: int
    remaining_tpm: int
    limit_tpm: int
    retry_after_sec: int = 0
