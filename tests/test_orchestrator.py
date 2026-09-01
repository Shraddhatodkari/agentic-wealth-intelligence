import os

from src.llm_client import LLMClient
from src.orchestrator import WealthIntelligencePipeline
from src.schemas import ExtractionResult, SynthesisReport
from tests.fixtures import MOCK_EXTRACTION, MOCK_SYNTHESIS

SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "sample_filings",
    "nimbus_dynamics_10k_fy2025.txt",
)


def test_full_pipeline_end_to_end():
    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    result = pipeline.run(
        filing_path=SAMPLE_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        mock_extraction=MOCK_EXTRACTION,
        mock_synthesis=MOCK_SYNTHESIS,
    )
    assert isinstance(result["extraction"], ExtractionResult)
    assert isinstance(result["report"], SynthesisReport)
    assert result["indexed_chunk_count"] > 0
    assert result["report"].executive_summary.startswith("Nimbus Dynamics")


def test_pipeline_state_carries_chunks_through():
    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    result = pipeline.run(
        filing_path=SAMPLE_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
    )
    assert len(result["chunks"]) > 1
    assert result["indexed_chunk_count"] == len(result["chunks"])


def test_pipeline_rag_agent_is_queryable_after_run():
    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    result = pipeline.run(
        filing_path=SAMPLE_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
    )
    rag = result["rag_agent"]
    ids = rag.retrieve("interest coverage ratio")
    assert len(ids) > 0
