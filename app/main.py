"""
FastAPI application service for Rico Multi-Model Proxy Gateway.
Serves OpenAI-compatible /v1/chat/completions with automatic circuit-breaker failover,
Prometheus /metrics endpoint, team quota management, and Mission Control UI.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rico import (
    AllModelsExhaustedException,
    ChatCompletionRequest,
    ChatCompletionResponse,
    GatewayConfig,
    ModelMeshRouter,
    PrometheusMetricsCollector,
    RicoProxyMiddleware,
    TeamQuota,
    TeamQuotaRegistry,
    TokenOpsRateLimiter,
    get_structured_logger,
)

# Initialize application components
config = GatewayConfig.load()
logger = get_structured_logger("rico.gateway")
router = ModelMeshRouter()
quota_registry = TeamQuotaRegistry()
rate_limiter = TokenOpsRateLimiter(registry=quota_registry, redis_url=config.redis_url)
metrics = PrometheusMetricsCollector()

app = FastAPI(
    title="Rico — Zero-Downtime Multi-Model LLM Gateway",
    description="Resilient reverse-proxy with circuit-breaker fallbacks, Redis sliding-window rate limiters, and Prometheus metrics.",
    version=config.version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Transparent TokenOps & Tracing Middleware
app.add_middleware(
    RicoProxyMiddleware,
    rate_limiter=rate_limiter,
    protected_paths=["/v1/chat/completions"],
)

# Static files setup
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if (STATIC_DIR / "css").exists():
        app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
    if (STATIC_DIR / "js").exists():
        app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    """Serve the interactive Mission Control dashboard."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return JSONResponse(
        content={
            "service": "Rico Zero-Downtime Multi-Model Gateway",
            "version": config.version,
            "status": "online",
            "docs": "/docs",
        }
    )


# ── Health & Telemetry ───────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    """Health check liveness probe for Docker and Render."""
    return {"status": "ok", "service": config.service_name, "version": config.version}


@app.get("/ready", tags=["Health"])
async def ready():
    """Readiness probe."""
    return {"status": "ready"}


@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"])
async def get_prometheus_metrics():
    """Prometheus exposition text format for Grafana / scraping agents."""
    # Synchronize current circuit states into gauge metrics
    for c in router.list_circuits():
        metrics.update_circuit_state(c["model_id"], c["state"])
    return metrics.render_prometheus_text()


# ── Core Proxy: Multi-Model Failover Completion ──────────────────────────────

@app.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    tags=["Chat Completions"],
    summary="Resilient multi-model chat completions with circuit-breaker failover",
)
async def chat_completions(request: Request, payload: ChatCompletionRequest):
    """
    Executes chat completions through the multi-model mesh:
    1. Primary Frontier Model (gpt-4o)
    2. Secondary Fast Model (gpt-4o-mini)
    3. Local Offline Fallback (llama-3-8b-local)
    """
    team_id = request.headers.get("X-Team-ID", payload.team_id or "default-team")
    start_t = time.perf_counter()

    try:
        response = await router.execute_chat(payload, team_id=team_id)
        duration_sec = time.perf_counter() - start_t

        # Record metrics
        metrics.record_request(
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
        metrics.record_request(
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


# ── Circuit Breaker Administration & Chaos Testing ──────────────────────────

@app.get("/v1/circuits", tags=["Circuit Breakers"])
async def list_circuits():
    """Retrieve status of all model circuit breakers in the mesh."""
    return router.list_circuits()


@app.post("/v1/circuits/{model_id}/trip", tags=["Circuit Breakers"])
async def trip_model_circuit(model_id: str):
    """Manually trip a model circuit open (for failover / chaos testing)."""
    success = router.trip_circuit(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in mesh")
    metrics.record_circuit_trip(model_id)
    return {"status": "success", "message": f"Circuit for '{model_id}' forced to OPEN state."}


@app.post("/v1/circuits/{model_id}/reset", tags=["Circuit Breakers"])
async def reset_model_circuit(model_id: str):
    """Reset a model circuit back to CLOSED state."""
    success = router.reset_circuit(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in mesh")
    return {"status": "success", "message": f"Circuit for '{model_id}' recovered to CLOSED state."}


# ── TokenOps Quotas Administration ───────────────────────────────────────────

@app.get("/v1/quotas/teams", tags=["TokenOps Quotas"])
async def list_team_quotas():
    """Retrieve all engineering team TokenOps quotas and current utilization."""
    teams = quota_registry.list_quotas()
    return [rate_limiter.get_team_usage(t.team_id) for t in teams]


@app.get("/v1/quotas/teams/{team_id}", tags=["TokenOps Quotas"])
async def get_team_quota(team_id: str):
    """Get quota utilization details for a specific team."""
    return rate_limiter.get_team_usage(team_id)


@app.put("/v1/quotas/teams/{team_id}", tags=["TokenOps Quotas"])
async def update_team_quota(team_id: str, quota: TeamQuota):
    """Configure or update TokenOps quotas for an engineering team."""
    quota.team_id = team_id
    quota_registry.set(quota)
    return {"status": "success", "quota": quota}
