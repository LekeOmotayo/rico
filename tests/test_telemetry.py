"""
Tests for Prometheus telemetry exposition and W3C distributed tracing.
"""

from rico.telemetry.metrics import PrometheusMetricsCollector
from rico.telemetry.tracing import TraceContext


def test_w3c_traceparent_parsing():
    # Valid W3C traceparent
    header = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    ctx = TraceContext.from_header(header)

    assert ctx.trace_id == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert ctx.parent_span_id == "00f067aa0ba902b7"
    assert len(ctx.span_id) == 16
    assert ctx.span_id != "00f067aa0ba902b7" # New child span created
    assert ctx.to_header().startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")


def test_w3c_traceparent_fresh_generation():
    ctx = TraceContext.from_header(None)
    assert len(ctx.trace_id) == 32
    assert len(ctx.span_id) == 16
    assert ctx.flags == "01"


def test_prometheus_metrics_rendering():
    collector = PrometheusMetricsCollector()

    collector.record_request(
        team_id="team-ai-agents",
        model="gpt-4o",
        status="success",
        fallback_triggered=False,
        duration_sec=0.15,
        prompt_tokens=50,
        completion_tokens=40,
    )
    collector.update_circuit_state("gpt-4o", "CLOSED")
    collector.record_circuit_trip("gpt-4o")

    rendered = collector.render_prometheus_text()

    assert "rico_requests_total" in rendered
    assert 'team="team-ai-agents"' in rendered
    assert 'model="gpt-4o"' in rendered
    assert "rico_tokens_consumed_total" in rendered
    assert "rico_circuit_state" in rendered
    assert "rico_circuit_trips_total" in rendered
    assert "rico_request_duration_seconds" in rendered
