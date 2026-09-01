"""
Prometheus metrics.

Exposes request count and latency by endpoint/status at /metrics in the
standard Prometheus text format - scrape this with a Prometheus server
and visualize in Grafana. No external service required to expose the
metrics themselves; Prometheus/Grafana are the (separate) services that
would consume this endpoint in a real deployment.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNT = Counter(
    "awi_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "awi_request_duration_seconds",
    "Request latency in seconds",
    ["method", "path"],
)

AGENT_STAGE_DURATION = Histogram(
    "awi_agent_stage_duration_seconds",
    "Duration of each agent pipeline stage in seconds",
    ["stage"],
)


def record_stage_duration(stage: str, duration_seconds: float) -> None:
    AGENT_STAGE_DURATION.labels(stage=stage).observe(duration_seconds)


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_COUNT.labels(method=method, path=path, status_code=status_code).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration_seconds)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
