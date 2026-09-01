"""
OpenTelemetry tracing.

Adds distributed tracing spans around each pipeline stage and the API
request lifecycle - the piece that lets you answer "which stage of which
request was slow" across a real deployment, not just aggregate latency
numbers (which is what Prometheus/`metrics.py` gives you).

Exporter is configurable via `OTEL_EXPORTER` ("console" | "otlp"):
- "console" (default): prints spans to stdout - zero external dependencies,
  useful for local development and this demo.
- "otlp": sends spans to an OTLP collector (e.g. Jaeger, Grafana Tempo) at
  `OTEL_EXPORTER_OTLP_ENDPOINT` - what a real deployment would use.

Tests use an in-memory exporter (`InMemorySpanExporter`) to assert spans
are created with the right names/attributes, without needing a running
collector - the same mock-by-default pattern used throughout this project.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

SERVICE_NAME = "agentic-wealth-intelligence"

_provider: TracerProvider | None = None


def configure_tracing(exporter=None) -> TracerProvider:
    """Configure the global TracerProvider. Pass an explicit `exporter`
    (e.g. InMemorySpanExporter in tests) to override the env-configured default.

    OpenTelemetry's global tracer provider can normally only be set once per
    process - re-calling `trace.set_tracer_provider()` is a silent no-op with
    a warning. This module resets that internal state before setting, since
    tests need to reconfigure with a fresh in-memory exporter per test."""
    global _provider
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    if exporter is None:
        otel_exporter = os.getenv("OTEL_EXPORTER", "console")
        if otel_exporter == "otlp":
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        else:
            exporter = ConsoleSpanExporter()

    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Reset OTel's internal "already set" guard so this can be called more
    # than once per process (standard OTel test workaround; see
    # opentelemetry-python's own test suite for the same pattern).
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace._TRACER_PROVIDER = None
    trace.set_tracer_provider(provider)
    _provider = provider
    return provider


def get_tracer():
    return trace.get_tracer(SERVICE_NAME)
