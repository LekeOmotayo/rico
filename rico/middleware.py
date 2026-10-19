"""
ASGI / FastAPI Middleware for distributed tracing and TokenOps rate-limiting.
"""

from __future__ import annotations

from typing import Callable, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from rico.rate_limit.limiter import TokenOpsRateLimiter
from rico.telemetry.tracing import TraceContext


class RicoProxyMiddleware(BaseHTTPMiddleware):
    """
    Middleware handling:
    1. W3C Trace Context propagation
    2. Per-team sliding-window RPM and token-bucket TPM validation
    3. Injection of TokenOps audit response headers
    """

    def __init__(
        self,
        app: Callable,
        rate_limiter: Optional[TokenOpsRateLimiter] = None,
        protected_paths: Optional[list[str]] = None,
    ) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter or TokenOpsRateLimiter()
        self.protected_paths = protected_paths or ["/v1/chat/completions", "/api/chat"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. Distributed Tracing Span Context
        incoming_trace = request.headers.get("traceparent")
        trace_ctx = TraceContext.from_header(incoming_trace)
        request.state.trace = trace_ctx

        # 2. Check if route is protected by TokenOps quotas
        path = request.url.path
        is_protected = any(path.startswith(p) for p in self.protected_paths)

        if not is_protected or request.method != "POST":
            response = await call_next(request)
            response.headers["traceparent"] = trace_ctx.to_header()
            response.headers["X-Trace-Id"] = trace_ctx.trace_id
            return response

        # 3. Extract team identity
        team_id = request.headers.get("X-Team-ID", "default-team")

        # 4. Check Rate Limit & Quotas
        # Default estimated prompt tokens for pre-flight check
        status = self.rate_limiter.check_and_consume(team_id, estimated_tokens=100)

        if not status.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": f"TokenOps rate limit or token quota exceeded for team '{team_id}'.",
                        "type": "tokenops_quota_exceeded",
                        "team_id": team_id,
                        "retry_after_seconds": status.retry_after_sec,
                        "limits": {
                            "rpm_limit": status.limit_rpm,
                            "current_rpm": status.current_rpm,
                            "tpm_limit": status.limit_tpm,
                            "current_tpm": status.current_tpm,
                        },
                    }
                },
                headers={
                    "Retry-After": str(status.retry_after_sec),
                    "X-RateLimit-Limit-RPM": str(status.limit_rpm),
                    "X-RateLimit-Remaining-RPM": "0",
                    "X-TokenOps-Quota-Limit-TPM": str(status.limit_tpm),
                    "X-TokenOps-Remaining-TPM": str(status.remaining_tpm),
                    "traceparent": trace_ctx.to_header(),
                    "X-Trace-Id": trace_ctx.trace_id,
                },
            )

        # 5. Process Request Downstream
        response = await call_next(request)

        # 6. Inject Telemetry & Quota Headers
        response.headers["traceparent"] = trace_ctx.to_header()
        response.headers["X-Trace-Id"] = trace_ctx.trace_id
        response.headers["X-RateLimit-Limit-RPM"] = str(status.limit_rpm)
        response.headers["X-RateLimit-Remaining-RPM"] = str(status.remaining_rpm)
        response.headers["X-TokenOps-Quota-Limit-TPM"] = str(status.limit_tpm)
        response.headers["X-TokenOps-Remaining-TPM"] = str(status.remaining_tpm)

        return response
