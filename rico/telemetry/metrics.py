"""
Prometheus metrics collector and exposition formatter.
Provides latency histograms, request counters, token totals, and circuit gauges.
"""

from __future__ import annotations

import collections
import time
from typing import Dict, List, Tuple


HISTOGRAM_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class PrometheusMetricsCollector:
    """Collects and renders metrics in Prometheus text exposition format."""

    def __init__(self) -> None:
        # Counters: (team, model, status, fallback_triggered) -> count
        self.request_counts: Dict[Tuple[str, str, str, str], int] = collections.defaultdict(int)
        # Token counters: (team, model, token_type) -> count
        self.token_counts: Dict[Tuple[str, str, str], int] = collections.defaultdict(int)
        # Circuit trip counters: model -> count
        self.circuit_trips: Dict[str, int] = collections.defaultdict(int)
        # Latency histograms: (team, model) -> list of raw observations (seconds)
        self.latency_observations: Dict[Tuple[str, str], List[float]] = collections.defaultdict(list)
        # Circuit states: model -> state_int (0=CLOSED, 1=HALF_OPEN, 2=OPEN)
        self.circuit_states: Dict[str, int] = {}

    def record_request(
        self,
        team_id: str,
        model: str,
        status: str,
        fallback_triggered: bool,
        duration_sec: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record completed request telemetry."""
        fb_str = "true" if fallback_triggered else "false"
        self.request_counts[(team_id, model, status, fb_str)] += 1
        self.token_counts[(team_id, model, "prompt")] += prompt_tokens
        self.token_counts[(team_id, model, "completion")] += completion_tokens
        self.token_counts[(team_id, model, "total")] += (prompt_tokens + completion_tokens)

        # Record latency
        obs = self.latency_observations[(team_id, model)]
        obs.append(duration_sec)
        # Keep recent 2000 observations per model to bound memory
        if len(obs) > 2000:
            del obs[:500]

    def update_circuit_state(self, model: str, state_str: str) -> None:
        """Map state string to numerical gauge (0=CLOSED, 1=HALF_OPEN, 2=OPEN)."""
        mapping = {"CLOSED": 0, "HALF_OPEN": 1, "OPEN": 2}
        self.circuit_states[model] = mapping.get(state_str, 0)

    def record_circuit_trip(self, model: str) -> None:
        """Increment circuit breaker trip counter."""
        self.circuit_trips[model] += 1

    def render_prometheus_text(self) -> str:
        """Render metrics in Prometheus format."""
        lines = []

        # ── Request Counters ──
        lines.append("# HELP rico_requests_total Total number of LLM proxy requests processed.")
        lines.append("# TYPE rico_requests_total counter")
        for (team, model, status, fb), count in sorted(self.request_counts.items()):
            lines.append(
                f'rico_requests_total{{team="{team}",model="{model}",status="{status}",fallback="{fb}"}} {count}'
            )

        # ── Token Counters ──
        lines.append("# HELP rico_tokens_consumed_total Total LLM tokens consumed per team and model.")
        lines.append("# TYPE rico_tokens_consumed_total counter")
        for (team, model, ttype), count in sorted(self.token_counts.items()):
            lines.append(
                f'rico_tokens_consumed_total{{team="{team}",model="{model}",type="{ttype}"}} {count}'
            )

        # ── Circuit Breaker State Gauge ──
        lines.append("# HELP rico_circuit_state Current circuit state (0=CLOSED, 1=HALF_OPEN, 2=OPEN).")
        lines.append("# TYPE rico_circuit_state gauge")
        for model, state_num in sorted(self.circuit_states.items()):
            lines.append(f'rico_circuit_state{{model="{model}"}} {state_num}')

        # ── Circuit Trip Counter ──
        lines.append("# HELP rico_circuit_trips_total Total times a model circuit has tripped open.")
        lines.append("# TYPE rico_circuit_trips_total counter")
        for model, trips in sorted(self.circuit_trips.items()):
            lines.append(f'rico_circuit_trips_total{{model="{model}"}} {trips}')

        # ── Latency Histogram ──
        lines.append("# HELP rico_request_duration_seconds Request latency in seconds.")
        lines.append("# TYPE rico_request_duration_seconds histogram")
        for (team, model), observations in sorted(self.latency_observations.items()):
            if not observations:
                continue
            total_sum = sum(observations)
            total_count = len(observations)

            # Cumulative counts for buckets
            cumulative = 0
            for le in HISTOGRAM_BUCKETS:
                bucket_count = sum(1 for o in observations if o <= le)
                lines.append(
                    f'rico_request_duration_seconds_bucket{{team="{team}",model="{model}",le="{le}"}} {bucket_count}'
                )
            lines.append(
                f'rico_request_duration_seconds_bucket{{team="{team}",model="{model}",le="+Inf"}} {total_count}'
            )
            lines.append(
                f'rico_request_duration_seconds_sum{{team="{team}",model="{model}"}} {total_sum:.4f}'
            )
            lines.append(
                f'rico_request_duration_seconds_count{{team="{team}",model="{model}"}} {total_count}'
            )

        return "\n".join(lines) + "\n"
