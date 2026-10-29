"""
Circuit breaker administration controller.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.services.gateway_service import GatewayService

router = APIRouter(prefix="/v1/circuits", tags=["Circuit Breakers"])


def get_service(request: Request) -> GatewayService:
    return request.app.state.gateway_service


@router.get("", summary="List all model circuit breakers")
async def list_circuits(service: GatewayService = Depends(get_service)):
    return service.list_circuits()


@router.post("/{model_id}/trip", summary="Trip a model circuit open")
async def trip_model_circuit(model_id: str, service: GatewayService = Depends(get_service)):
    success = service.trip_circuit(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in mesh")
    return {"status": "success", "message": f"Circuit for '{model_id}' forced to OPEN state."}


@router.post("/{model_id}/reset", summary="Reset a model circuit back to CLOSED")
async def reset_model_circuit(model_id: str, service: GatewayService = Depends(get_service)):
    success = service.reset_circuit(model_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found in mesh")
    return {"status": "success", "message": f"Circuit for '{model_id}' recovered to CLOSED state."}
