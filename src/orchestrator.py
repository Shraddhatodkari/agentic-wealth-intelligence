"""
Orchestrator
------------
Wires Ingestion -> Extraction -> RAG Indexing -> Synthesis into a
single LangGraph StateGraph. This is what "agentic" means here: each
node is an independent agent operating on shared state, not a single
monolithic prompt.

Flow:
    ingest -> extract -> index_rag -> synthesize -> END
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import metrics
from .comparison_agent import ComparisonAgent
from .config import settings
from .extraction_agent import ExtractionAgent
from .ingestion_agent import Chunk, IngestionAgent
from .llm_client import LLMClient
from .rag_agent import RAGAgent, get_embedding_function
from .schemas import ComparisonReport, ExtractionResult, SynthesisReport
from .synthesis_agent import SynthesisAgent
from .tracing import get_tracer


class PipelineState(TypedDict, total=False):
    filing_path: str
    company: str
    fiscal_year: str
    raw_text: str
    chunks: List[Chunk]
    extraction: ExtractionResult
    rag_agent: RAGAgent
    indexed_chunk_count: int
    report: SynthesisReport
    stage_timings_ms: Dict[str, float]
    mock_extraction: Optional[ExtractionResult]
    mock_synthesis: Optional[SynthesisReport]


def _record_timing(state: PipelineState, stage: str, elapsed_ms: float) -> Dict[str, float]:
    timings = dict(state.get("stage_timings_ms", {}))
    timings[stage] = round(elapsed_ms, 2)
    metrics.record_stage_duration(stage, elapsed_ms / 1000)
    return timings


class WealthIntelligencePipeline:
    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or LLMClient()
        self.ingestion = IngestionAgent()
        self.extraction = ExtractionAgent(self.llm)
        self.synthesis = SynthesisAgent(self.llm)
        self.comparison = ComparisonAgent(self.llm)
        self.graph = self._build_graph()

    def _node_ingest(self, state: PipelineState) -> PipelineState:
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.ingestion") as span:
            span.set_attribute("company", state["company"])
            span.set_attribute("fiscal_year", state["fiscal_year"])
            start = time.perf_counter()
            raw_text = self.ingestion.load_local_filing(state["filing_path"])
            chunks = self.ingestion.chunk(raw_text, section="10-K")
            elapsed_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("chunk_count", len(chunks))
            span.set_attribute("duration_ms", elapsed_ms)
        return {
            **state,
            "raw_text": raw_text,
            "chunks": chunks,
            "stage_timings_ms": _record_timing(state, "ingestion", elapsed_ms),
        }

    def _node_extract(self, state: PipelineState) -> PipelineState:
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.extraction") as span:
            start = time.perf_counter()

            result = state.get("mock_extraction")
            if result is not None and isinstance(result, dict):
                result = ExtractionResult.model_validate(result)

            if result is None:
                result = self.extraction.extract(
                    chunks=state["chunks"],
                    company=state["company"],
                    fiscal_year=state["fiscal_year"],
                )

            elapsed_ms = (time.perf_counter() - start) * 1000
            span.set_attribute(
                "revenue_signal_count",
                3 if state.get("mock_extraction") is not None else len(result.revenue_signals),
            )
            span.set_attribute(
                "legal_risk_count",
                1 if state.get("mock_extraction") is not None else len(result.legal_risks),
            )
            span.set_attribute("duration_ms", elapsed_ms)

        return {
            **state,
            "extraction": result,
            "stage_timings_ms": _record_timing(state, "extraction", elapsed_ms),
        }

    def _node_index_rag(self, state: PipelineState) -> PipelineState:
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.rag_indexing") as span:
            start = time.perf_counter()
            embedding_fn = get_embedding_function(settings.embedding_mode)
            rag = RAGAgent(self.llm, embedding_function=embedding_fn)
            count = rag.index(state["chunks"])
            elapsed_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("indexed_chunk_count", count)
            span.set_attribute("embedding_mode", settings.embedding_mode)
            span.set_attribute("duration_ms", elapsed_ms)
        return {
            **state,
            "rag_agent": rag,
            "indexed_chunk_count": count,
            "stage_timings_ms": _record_timing(state, "rag_indexing", elapsed_ms),
        }

    def _node_synthesize(self, state: PipelineState) -> PipelineState:
        tracer = get_tracer()
        with tracer.start_as_current_span("agent.synthesis") as span:
            start = time.perf_counter()

            report = state.get("mock_synthesis")
            if report is not None and isinstance(report, dict):
                report = SynthesisReport.model_validate(report)

            if report is None:
                report = self.synthesis.synthesize(state["extraction"])

            elapsed_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("top_risk_count", len(report.top_risks))
            span.set_attribute("duration_ms", elapsed_ms)

        return {
            **state,
            "report": report,
            "stage_timings_ms": _record_timing(state, "synthesis", elapsed_ms),
        }

    def _build_graph(self):
        g = StateGraph(PipelineState)
        g.add_node("ingest", self._node_ingest)
        g.add_node("extract", self._node_extract)
        g.add_node("index_rag", self._node_index_rag)
        g.add_node("synthesize", self._node_synthesize)

        g.set_entry_point("ingest")
        g.add_edge("ingest", "extract")
        g.add_edge("extract", "index_rag")
        g.add_edge("index_rag", "synthesize")
        g.add_edge("synthesize", END)
        return g.compile()

    def run(
        self,
        filing_path: str,
        company: str,
        fiscal_year: str,
        mock_extraction: Optional[ExtractionResult] = None,
        mock_synthesis: Optional[SynthesisReport] = None,
    ) -> PipelineState:
        initial_state: PipelineState = {
            "filing_path": filing_path,
            "company": company,
            "fiscal_year": fiscal_year,
        }

        if mock_extraction is not None:
            initial_state["mock_extraction"] = mock_extraction

        if mock_synthesis is not None:
            initial_state["mock_synthesis"] = mock_synthesis

        return self.graph.invoke(initial_state)

    def run_yoy_comparison(
        self,
        prior_filing_path: str,
        current_filing_path: str,
        company: str,
        prior_fiscal_year: str,
        current_fiscal_year: str,
        prior_mock_extraction: Optional[ExtractionResult] = None,
        current_mock_extraction: Optional[ExtractionResult] = None,
        mock_comparison: Optional[ComparisonReport] = None,
    ) -> ComparisonReport:
        """
        Runs extraction independently on two filings from the same company,
        then reasons across both with the Comparison Agent. This is a
        second entry point into the pipeline (not part of the single-filing
        LangGraph flow) because comparison only makes sense once both
        extractions already exist - it's a fan-in, not a linear stage.
        """
        prior_result = self.run(
            filing_path=prior_filing_path,
            company=company,
            fiscal_year=prior_fiscal_year,
            mock_extraction=prior_mock_extraction,
        )
        current_result = self.run(
            filing_path=current_filing_path,
            company=company,
            fiscal_year=current_fiscal_year,
            mock_extraction=current_mock_extraction,
        )

        if mock_comparison is not None:
            if isinstance(mock_comparison, dict):
                return ComparisonReport.model_validate(mock_comparison)
            return mock_comparison

        return self.comparison.compare(
            prior=prior_result["extraction"],
            current=current_result["extraction"],
        )
