"""
Circuit Breaker Repository for Rico Multi-Model Mesh.
"""

from typing import Dict, Any, List, Optional
from rico.circuit.router import ModelMeshRouter
from rico.circuit.breaker import ModelCircuitBreaker


class CircuitRepository:
    """Manages model mesh router and individual circuit breaker states."""

    def __init__(self, router: Optional[ModelMeshRouter] = None):
        self.router = router or ModelMeshRouter()

    def get_router(self) -> ModelMeshRouter:
        return self.router

    def get_breaker(self, model: str) -> Optional[ModelCircuitBreaker]:
        return self.router.breakers.get(model)

    def trip(self, model: str) -> bool:
        return self.router.trip_circuit(model)

    def reset(self, model: str) -> bool:
        return self.router.reset_circuit(model)

    def list_all(self) -> List[Dict[str, Any]]:
        return self.router.list_circuits()
