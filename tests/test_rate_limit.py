"""
Tests for sliding-window rate limiters and token-bucket TokenOps quotas.
"""

from rico.models import TeamQuota
from rico.rate_limit.limiter import TokenOpsRateLimiter
from rico.rate_limit.quotas import TeamQuotaRegistry


def test_rpm_sliding_window_rate_limiting():
    registry = TeamQuotaRegistry()
    registry.set(
        TeamQuota(
            team_id="team-limited",
            name="Limited Team",
            rpm_limit=3,
            tpm_limit=50000,
        )
    )
    limiter = TokenOpsRateLimiter(registry=registry)

    # 1st, 2nd, 3rd requests allowed
    assert limiter.check_and_consume("team-limited", estimated_tokens=10).allowed is True
    assert limiter.check_and_consume("team-limited", estimated_tokens=10).allowed is True
    assert limiter.check_and_consume("team-limited", estimated_tokens=10).allowed is True

    # 4th request blocked by RPM sliding window
    status = limiter.check_and_consume("team-limited", estimated_tokens=10)
    assert status.allowed is False
    assert status.remaining_rpm == 0
    assert status.retry_after_sec >= 1


def test_tpm_token_bucket_exhaustion():
    registry = TeamQuotaRegistry()
    registry.set(
        TeamQuota(
            team_id="team-tpm-capped",
            name="Token Capped Team",
            rpm_limit=100,
            tpm_limit=500, # Only 500 tokens in bucket
        )
    )
    limiter = TokenOpsRateLimiter(registry=registry)

    # Consume 400 tokens -> Allowed
    status1 = limiter.check_and_consume("team-tpm-capped", estimated_tokens=400)
    assert status1.allowed is True
    assert status1.remaining_tpm <= 100

    # Request 200 tokens -> Exceeds bucket -> Blocked!
    status2 = limiter.check_and_consume("team-tpm-capped", estimated_tokens=200)
    assert status2.allowed is False
    assert status2.retry_after_sec >= 1


def test_per_team_isolation():
    registry = TeamQuotaRegistry()
    registry.set(TeamQuota(team_id="team-a", name="A", rpm_limit=1, tpm_limit=1000))
    registry.set(TeamQuota(team_id="team-b", name="B", rpm_limit=10, tpm_limit=1000))
    limiter = TokenOpsRateLimiter(registry=registry)

    # Exhaust team A
    assert limiter.check_and_consume("team-a").allowed is True
    assert limiter.check_and_consume("team-a").allowed is False

    # Team B should be completely unaffected!
    assert limiter.check_and_consume("team-b").allowed is True
    assert limiter.check_and_consume("team-b").allowed is True


def test_team_usage_diagnostics():
    registry = TeamQuotaRegistry()
    limiter = TokenOpsRateLimiter(registry=registry)
    limiter.check_and_consume("team-ai-agents", estimated_tokens=50)

    usage = limiter.get_team_usage("team-ai-agents")
    assert usage["team_id"] == "team-ai-agents"
    assert usage["current_rpm"] == 1
    assert "rpm_utilization_pct" in usage
    assert "available_tokens" in usage
