"""
FastAPI application service for Rico Multi-Model Proxy Gateway.
Serves OpenAI-compatible /v1/chat/completions with automatic circuit-breaker failover,
Prometheus /metrics endpoint, team quota management, and Mission Control UI.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rico import (
    GatewayConfig,
    RicoProxyMiddleware,
    get_structured_logger,
)
from app.api.services.gateway_service import GatewayService
from app.api.controllers.gateway_controller import router as gateway_router
from app.api.controllers.circuits_controller import router as circuits_router
from app.api.controllers.quotas_controller import router as quotas_router

# Initialize application components
config = GatewayConfig.load()
logger = get_structured_logger("rico.gateway")
gateway_service = GatewayService(config=config)

app = FastAPI(
    title="Rico — Zero-Downtime Multi-Model LLM Gateway",
    description="Resilient reverse-proxy with circuit-breaker fallbacks, Redis sliding-window rate limiters, and Prometheus metrics.",
    version=config.version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Store service in app state for controller dependency injection
app.state.gateway_service = gateway_service

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
    rate_limiter=gateway_service.rate_limiter,
    protected_paths=["/v1/chat/completions"],
)

# Mount Layered API Controllers
app.include_router(gateway_router)
app.include_router(circuits_router)
app.include_router(quotas_router)

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
    return gateway_service.render_prometheus_metrics()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=True)
