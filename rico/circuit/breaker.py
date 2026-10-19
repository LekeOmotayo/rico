"""
Circuit Breaker state machine for upstream LLM providers.
Enforces CLOSED -> OPEN -> HALF_OPEN state transitions.
"""

from __future__ import annotations

import time
from typing import Optional
from rico.models import CircuitState, ModelConfig


class ModelCircuitBreaker:
    """Monitors failures for an individual model and manages circuit state."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()
        self.total_trips: int = 0

    def can_execute(self) -> bool:
        """
        Check if request is permitted to route to this model.
        If state is OPEN and recovery timeout has elapsed, transitions to HALF_OPEN (canary probe).
        """
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery window has expired
            if (now - self.last_failure_time) >= self.config.recovery_time_sec:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # In half-open, we allow canary probe
            return True

        return False

    def record_success(self) -> None:
        """Record successful invocation."""
        now = time.time()
        self.success_count += 1

        if self.state == CircuitState.HALF_OPEN:
            # Canary probe succeeded: recover circuit to CLOSED
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_state_change = now
        elif self.state == CircuitState.CLOSED:
            # Reset consecutive failure counter on success
            self.failure_count = 0

    def record_failure(self, error: Optional[Exception] = None) -> None:
        """Record failed invocation or timeout."""
        now = time.time()
        self.failure_count += 1
        self.last_failure_time = now

        if self.state == CircuitState.HALF_OPEN:
            # Canary failed immediately: return to OPEN state
            self.state = CircuitState.OPEN
            self.total_trips += 1
            self.last_state_change = now
        elif self.state == CircuitState.CLOSED:
            # Check if consecutive failures breached threshold
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                self.total_trips += 1
                self.last_state_change = now

    def force_open(self) -> None:
        """Manually trip the circuit open (for simulation/chaos testing)."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.time()
        self.last_state_change = time.time()
        self.total_trips += 1

    def force_close(self) -> None:
        """Manually reset the circuit to closed."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def get_status(self) -> dict:
        """Return diagnostic status of the circuit."""
        now = time.time()
        remaining_open = max(0.0, self.config.recovery_time_sec - (now - self.last_failure_time))
        return {
            "model_id": self.config.model_id,
            "display_name": self.config.display_name,
            "tier": self.config.tier.value,
            "state": self.state.value,
            "consecutive_failures": self.failure_count,
            "failure_threshold": self.config.failure_threshold,
            "total_trips": self.total_trips,
            "recovery_time_sec": self.config.recovery_time_sec,
            "remaining_open_sec": round(remaining_open, 1) if self.state == CircuitState.OPEN else 0.0,
        }
