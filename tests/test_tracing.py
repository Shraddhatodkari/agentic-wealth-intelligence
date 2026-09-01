"""
Tests for OpenTelemetry instrumentation - uses InMemorySpanExporter so
spans are captured and asserted on without needing a running collector
(Jaeger, Tempo, etc.), the same mock-by-default pattern used elsewhere.
"""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.llm_client import LLMClient
from src.orchestrator import WealthIntelligencePipeline
from src.tracing import configure_tracing
from tests.fixtures import MOCK_EXTRACTION, MOCK_SYNTHESIS

FY2025_PATH = "data/sample_filings/nimbus_dynamics_10k_fy2025.txt"


def test_pipeline_run_creates_a_span_per_stage():
    exporter = InMemorySpanExporter()
    configure_tracing(exporter=exporter)

    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    pipeline.run(
        filing_path=FY2025_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        mock_extraction=MOCK_EXTRACTION,
        mock_synthesis=MOCK_SYNTHESIS,
    )

    span_names = {span.name for span in exporter.get_finished_spans()}
    assert "agent.ingestion" in span_names
    assert "agent.extraction" in span_names
    assert "agent.rag_indexing" in span_names
    assert "agent.synthesis" in span_names


def test_extraction_span_has_useful_attributes():
    exporter = InMemorySpanExporter()
    configure_tracing(exporter=exporter)

    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    pipeline.run(
        filing_path=FY2025_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        mock_extraction=MOCK_EXTRACTION,
        mock_synthesis=MOCK_SYNTHESIS,
    )

    extraction_span = next(s for s in exporter.get_finished_spans() if s.name == "agent.extraction")
    assert extraction_span.attributes["revenue_signal_count"] == 3
    assert extraction_span.attributes["legal_risk_count"] == 1
    assert extraction_span.attributes["duration_ms"] >= 0


def test_spans_have_correct_service_name_resource():
    exporter = InMemorySpanExporter()
    provider = configure_tracing(exporter=exporter)
    assert provider.resource.attributes["service.name"] == "agentic-wealth-intelligence"
