# ==============================================================================
# Rico — Zero-Downtime Multi-Model Gateway & TokenOps Proxy
# Multi-stage production Dockerfile: Builder -> Non-root Runtime
# ==============================================================================

# ── Stage 1: Build & Dependencies ─────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Final Non-Root Runtime ───────────────────────────────────────────
FROM python:3.11-slim AS runner

WORKDIR /app

# Create non-root user (UID 10001)
RUN groupadd -g 10001 ricogroup && \
    useradd -u 10001 -g ricogroup -s /bin/bash -m ricouser

# Copy installed dependencies
COPY --from=builder /install /usr/local

# Copy application files
COPY --chown=ricouser:ricogroup . /app

# Switch to non-root user
USER 10001

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    RICO_ENV=production

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
