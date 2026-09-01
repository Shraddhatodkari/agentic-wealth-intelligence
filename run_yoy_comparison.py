"""
CLI demo: runs extraction on two fiscal years of the same company and
produces a year-over-year ComparisonReport via the Comparison Agent.

Usage:
    python run_yoy_comparison.py
"""

from src.ingestion_agent import IngestionAgent
from src.extraction_agent import ExtractionAgent
from src.comparison_agent import ComparisonAgent
from src.llm_client import LLMClient
from tests.fixtures import MOCK_EXTRACTION, MOCK_EXTRACTION_FY2024, MOCK_COMPARISON

FY2024_PATH = "data/sample_filings/nimbus_dynamics_10k_fy2024.txt"
FY2025_PATH = "data/sample_filings/nimbus_dynamics_10k_fy2025.txt"


def main():
    llm = LLMClient(mode="mock")
    ingestion = IngestionAgent()
    extraction = ExtractionAgent(llm)
    comparison = ComparisonAgent(llm)

    prior_chunks = ingestion.chunk(
        ingestion.load_local_filing(FY2024_PATH), section="10-K-FY2024"
    )
    current_chunks = ingestion.chunk(
        ingestion.load_local_filing(FY2025_PATH), section="10-K-FY2025"
    )

    prior_result = extraction.extract(
        prior_chunks,
        "Nimbus Dynamics, Inc.",
        "FY2024",
        mock_response=MOCK_EXTRACTION_FY2024,
    )
    current_result = extraction.extract(
        current_chunks, "Nimbus Dynamics, Inc.", "FY2025", mock_response=MOCK_EXTRACTION
    )

    report = comparison.compare(
        prior_result, current_result, mock_response=MOCK_COMPARISON
    )

    print("=" * 70)
    print(f"YEAR-OVER-YEAR COMPARISON — {report.company}")
    print(f"{report.prior_fiscal_year} vs {report.current_fiscal_year}")
    print("=" * 70)
    print(f"\nOverall trajectory: {report.overall_trajectory.upper()}\n")
    print("Material shifts:")
    for shift in report.trend_shifts:
        print(
            f"  [{shift.materiality.upper()}] {shift.metric}: "
            f"{shift.prior_value} -> {shift.current_value} ({shift.direction})"
        )
        print(f"      {shift.note}")
    print(f"\nNarrative:\n{report.narrative}")


if __name__ == "__main__":
    main()
