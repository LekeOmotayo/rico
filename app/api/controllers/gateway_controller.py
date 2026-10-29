"""
Chat completion gateway controller.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from rico import ChatCompletionRequest, ChatCompletionResponse
from app.api.services.gateway_service import GatewayService

router = APIRouter(prefix="/v1", tags=["Chat Completions"])


def get_service(request: Request) -> GatewayService:
    return request.app.state.gateway_service


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Resilient multi-model chat completions with circuit-breaker failover",
)
async def chat_completions(
    request: Request,
    payload: ChatCompletionRequest,
    service: GatewayService = Depends(get_service),
):
    team_id = request.headers.get("X-Team-ID", payload.team_id or "default-team")
    return await service.execute_chat(payload, team_id=team_id)
