"""
Quota Repository for Rico TokenOps Rate Limiting.
"""

from typing import Dict, Optional, List
from rico.rate_limit.quotas import TeamQuota, TeamQuotaRegistry


class QuotaRepository:
    """Manages team rate limits and token quotas."""

    def __init__(self, registry: Optional[TeamQuotaRegistry] = None):
        self.registry = registry or TeamQuotaRegistry()

    def get_quota(self, team_id: str) -> TeamQuota:
        return self.registry.get(team_id)

    def save(self, quota: TeamQuota) -> TeamQuota:
        self.registry.set(quota)
        return quota

    def list_all(self) -> List[TeamQuota]:
        return self.registry.list_quotas()
