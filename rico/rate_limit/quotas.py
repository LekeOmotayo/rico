"""
Team quota registry for TokenOps governance.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from rico.models import TeamQuota


class TeamQuotaRegistry:
    """Manages TokenOps quota allocations per engineering team."""

    def __init__(self) -> None:
        self._quotas: Dict[str, TeamQuota] = {}
        self._init_default_teams()

    def _init_default_teams(self) -> None:
        """Initialize standard engineering team quotas."""
        defaults = [
            TeamQuota(
                team_id="team-ai-agents",
                name="Autonomous AI Agents Core",
                rpm_limit=120,
                tpm_limit=250_000,
                tier_name="enterprise",
            ),
            TeamQuota(
                team_id="team-analytics",
                name="Data Science & Analytics",
                rpm_limit=60,
                tpm_limit=100_000,
                tier_name="standard",
            ),
            TeamQuota(
                team_id="team-growth",
                name="Growth & Marketing Experimentation",
                rpm_limit=30,
                tpm_limit=40_000,
                tier_name="free",
            ),
            TeamQuota(
                team_id="default-team",
                name="General API Clients",
                rpm_limit=60,
                tpm_limit=80_000,
                tier_name="standard",
            ),
        ]
        for t in defaults:
            self._quotas[t.team_id] = t

    def get(self, team_id: str) -> TeamQuota:
        """Retrieve quota for team, returning default if not explicitly registered."""
        return self._quotas.get(
            team_id,
            TeamQuota(
                team_id=team_id,
                name=f"Team {team_id}",
                rpm_limit=60,
                tpm_limit=80_000,
                tier_name="standard",
            ),
        )

    def set(self, quota: TeamQuota) -> None:
        """Register or update a team quota."""
        self._quotas[quota.team_id] = quota

    def list_quotas(self) -> List[TeamQuota]:
        """List all team quotas."""
        return list(self._quotas.values())
