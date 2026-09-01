import os

from src.llm_client import LLMClient
from src.orchestrator import WealthIntelligencePipeline
from src.schemas import ComparisonReport
from tests.fixtures import MOCK_COMPARISON, MOCK_EXTRACTION, MOCK_EXTRACTION_FY2024

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample_filings")
FY2025_PATH = os.path.join(DATA_DIR, "nimbus_dynamics_10k_fy2025.txt")
FY2024_PATH = os.path.join(DATA_DIR, "nimbus_dynamics_10k_fy2024.txt")


def test_yoy_comparison_end_to_end():
    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    report = pipeline.run_yoy_comparison(
        prior_filing_path=FY2024_PATH,
        current_filing_path=FY2025_PATH,
        company="Nimbus Dynamics, Inc.",
        prior_fiscal_year="FY2024",
        current_fiscal_year="FY2025",
        prior_mock_extraction=MOCK_EXTRACTION_FY2024,
        current_mock_extraction=MOCK_EXTRACTION,
        mock_comparison=MOCK_COMPARISON,
    )
    assert isinstance(report, ComparisonReport)
    assert report.overall_trajectory == "deteriorating"
    assert "Cloud Infrastructure" in report.trend_shifts[0].metric


def test_yoy_comparison_both_filings_load_independently():
    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode="mock"))
    report = pipeline.run_yoy_comparison(
        prior_filing_path=FY2024_PATH,
        current_filing_path=FY2025_PATH,
        company="Nimbus Dynamics, Inc.",
        prior_fiscal_year="FY2024",
        current_fiscal_year="FY2025",
    )
    # No mocks passed for extraction -> defaults to empty, but the pipeline
    # must still run both filings through ingestion independently without error
    assert report.company == "Nimbus Dynamics, Inc."
