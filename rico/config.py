"""
Configuration schemas and environment loading for Rico.
"""

from __future__ import annotations

import os
from typing import List, Optional
from pydantic import BaseModel, Field


class GatewayConfig(BaseModel):
    """Global configuration settings for Rico Proxy Gateway."""
    service_name: str = "rico"
    version: str = "1.0.0"
    env: str = Field(default_factory=lambda: os.getenv("RICO_ENV", "development"))
    host: str = Field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Redis connection for sliding window rate limiter
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    redis_timeout_sec: float = 1.0

    # Upstream model provider keys
    openai_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    anthropic_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    local_ollama_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_URL", "http://localhost:11434"))

    # Circuit breaker tuning
    default_failure_threshold: int = 3
    default_recovery_time_sec: float = 20.0
    default_request_timeout_sec: float = 3.5

    # Auth & API Tokens
    api_tokens: List[str] = Field(
        default_factory=lambda: [
            t.strip() for t in os.getenv("RICO_API_TOKENS", "rico-dev-token").split(",") if t.strip()
        ]
    )

    @classmethod
    def load(cls) -> "GatewayConfig":
        """Instantiate config from environment variables."""
        return cls()
