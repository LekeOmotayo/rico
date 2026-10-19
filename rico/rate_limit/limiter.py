"""
Redis-backed sliding-window rate limiter & token-bucket TokenOps quota manager.
Provides graceful in-memory fallback when Redis is offline.
"""

from __future__ import annotations

import collections
import time
from typing import Dict, List, Optional, Tuple
from rico.models import RateLimitStatus, TeamQuota
from rico.rate_limit.quotas import TeamQuotaRegistry


class InMemoryTokenBucket:
    """Continuous token-bucket implementation for token quota tracking."""

    def __init__(self, capacity: int, refill_rate_per_sec: float) -> None:
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = refill_rate_per_sec
        self.last_refill = time.time()

    def update_capacity(self, new_capacity: int) -> None:
        """Update capacity and refill rate."""
        self.capacity = float(new_capacity)
        self.refill_rate = self.capacity / 60.0
        self.tokens = min(self.tokens, self.capacity)

    def consume(self, amount: int) -> Tuple[bool, int]:
        """Attempt to consume tokens. Returns (success, remaining_tokens)."""
        now = time.time()
        elapsed = now - self.last_refill
        self.last_refill = now

        # Refill tokens up to bucket capacity
        self.tokens = min(self.capacity, self.tokens + (elapsed * self.refill_rate))

        if self.tokens >= amount:
            self.tokens -= amount
            return True, int(self.tokens)
        return False, int(self.tokens)


class TokenOpsRateLimiter:
    """
    Enforces dual TokenOps boundaries:
    1. Sliding Window RPM (Requests Per Minute)
    2. Continuous Token Bucket TPM (Tokens Per Minute)
    """

    def __init__(
        self,
        registry: Optional[TeamQuotaRegistry] = None,
        redis_url: Optional[str] = None,
    ) -> None:
        self.registry = registry or TeamQuotaRegistry()
        self.redis_url = redis_url
        self._redis_client = None

        # In-memory structures
        # Sliding window timestamps: team_id -> deque of request timestamps
        self._rpm_windows: Dict[str, collections.deque[float]] = collections.defaultdict(collections.deque)
        # Token buckets: team_id -> InMemoryTokenBucket
        self._token_buckets: Dict[str, InMemoryTokenBucket] = {}

        # Attempt to connect to Redis
        if self.redis_url and "redis://" in self.redis_url:
            try:
                import redis # type: ignore
                self._redis_client = redis.from_url(self.redis_url, socket_timeout=1.0)
                self._redis_client.ping()
            except Exception:
                self._redis_client = None

    def _get_token_bucket(self, quota: TeamQuota) -> InMemoryTokenBucket:
        """Get or initialize token bucket for team."""
        if quota.team_id not in self._token_buckets:
            refill_rate = quota.tpm_limit / 60.0
            self._token_buckets[quota.team_id] = InMemoryTokenBucket(
                capacity=quota.tpm_limit,
                refill_rate_per_sec=refill_rate,
            )
        else:
            self._token_buckets[quota.team_id].update_capacity(quota.tpm_limit)
        return self._token_buckets[quota.team_id]

    def check_and_consume(
        self,
        team_id: str,
        estimated_tokens: int = 100,
    ) -> RateLimitStatus:
        """
        Validate both RPM sliding window and TPM token bucket.
        Deducts tokens and records request if allowed.
        """
        quota = self.registry.get(team_id)
        now = time.time()
        window_start = now - 60.0

        # ── 1. Check Sliding Window RPM ───────────────────────────────────────
        if self._redis_client:
            try:
                # Redis ZSET sliding window
                key = f"rico:ratelimit:rpm:{team_id}"
                pipe = self._redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, window_start)
                pipe.zcard(key)
                _, current_rpm = pipe.execute()

                if current_rpm >= quota.rpm_limit:
                    return RateLimitStatus(
                        allowed=False,
                        team_id=team_id,
                        current_rpm=current_rpm,
                        remaining_rpm=0,
                        limit_rpm=quota.rpm_limit,
                        current_tpm=0,
                        remaining_tpm=0,
                        limit_tpm=quota.tpm_limit,
                        retry_after_sec=max(1, int(60 - (now - window_start))),
                    )
            except Exception:
                # Fall back to in-memory on Redis error
                self._redis_client = None

        # In-memory sliding window check
        req_queue = self._rpm_windows[team_id]
        while req_queue and req_queue[0] < window_start:
            req_queue.popleft()

        current_rpm = len(req_queue)
        if current_rpm >= quota.rpm_limit:
            oldest = req_queue[0] if req_queue else now
            retry_after = max(1, int(60 - (now - oldest)))
            return RateLimitStatus(
                allowed=False,
                team_id=team_id,
                current_rpm=current_rpm,
                remaining_rpm=0,
                limit_rpm=quota.rpm_limit,
                current_tpm=0,
                remaining_tpm=0,
                limit_tpm=quota.tpm_limit,
                retry_after_sec=retry_after,
            )

        # ── 2. Check Token Bucket TPM ─────────────────────────────────────────
        bucket = self._get_token_bucket(quota)
        token_allowed, remaining_tpm = bucket.consume(estimated_tokens)

        if not token_allowed:
            return RateLimitStatus(
                allowed=False,
                team_id=team_id,
                current_rpm=current_rpm,
                remaining_rpm=max(0, quota.rpm_limit - current_rpm),
                limit_rpm=quota.rpm_limit,
                current_tpm=quota.tpm_limit - remaining_tpm,
                remaining_tpm=remaining_tpm,
                limit_tpm=quota.tpm_limit,
                retry_after_sec=max(1, int((estimated_tokens - remaining_tpm) / bucket.refill_rate)),
            )

        # ── 3. Record Request (Consume RPM) ───────────────────────────────────
        if self._redis_client:
            try:
                key = f"rico:ratelimit:rpm:{team_id}"
                pipe = self._redis_client.pipeline()
                pipe.zadd(key, {f"{now}:{time.time_ns()}": now})
                pipe.expire(key, 90)
                pipe.execute()
            except Exception:
                pass

        req_queue.append(now)

        return RateLimitStatus(
            allowed=True,
            team_id=team_id,
            current_rpm=current_rpm + 1,
            remaining_rpm=max(0, quota.rpm_limit - (current_rpm + 1)),
            limit_rpm=quota.rpm_limit,
            current_tpm=quota.tpm_limit - remaining_tpm,
            remaining_tpm=remaining_tpm,
            limit_tpm=quota.tpm_limit,
            retry_after_sec=0,
        )

    def get_team_usage(self, team_id: str) -> dict:
        """Return diagnostic metrics of current quota utilization."""
        quota = self.registry.get(team_id)
        now = time.time()
        window_start = now - 60.0

        req_queue = self._rpm_windows[team_id]
        while req_queue and req_queue[0] < window_start:
            req_queue.popleft()

        bucket = self._get_token_bucket(quota)
        return {
            "team_id": team_id,
            "team_name": quota.name,
            "rpm_limit": quota.rpm_limit,
            "current_rpm": len(req_queue),
            "rpm_utilization_pct": round((len(req_queue) / max(1, quota.rpm_limit)) * 100, 1),
            "tpm_limit": quota.tpm_limit,
            "available_tokens": int(bucket.tokens),
            "tpm_utilization_pct": round(((quota.tpm_limit - bucket.tokens) / max(1, quota.tpm_limit)) * 100, 1),
        }
