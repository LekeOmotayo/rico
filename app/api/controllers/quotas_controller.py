"""
TokenOps Quota administration controller.
"""

from fastapi import APIRouter, Depends, Request
from rico import TeamQuota
from app.api.services.gateway_service import GatewayService

router = APIRouter(prefix="/v1/quotas/teams", tags=["TokenOps Quotas"])


def get_service(request: Request) -> GatewayService:
    return request.app.state.gateway_service


@router.get("", summary="List all engineering team quotas")
async def list_team_quotas(service: GatewayService = Depends(get_service)):
    return service.list_team_quotas()


@router.get("/{team_id}", summary="Get quota for a specific team")
async def get_team_quota(team_id: str, service: GatewayService = Depends(get_service)):
    return service.get_team_usage(team_id)


@router.put("/{team_id}", summary="Configure quota for an engineering team")
async def update_team_quota(
    team_id: str, quota: TeamQuota, service: GatewayService = Depends(get_service)
):
    saved = service.update_team_quota(team_id, quota)
    return {"status": "success", "quota": saved}
