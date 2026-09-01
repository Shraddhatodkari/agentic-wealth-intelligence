import pytest

from src.comparison_agent import ComparisonAgent
from src.llm_client import LLMClient
from src.schemas import ComparisonReport, ExtractionResult
from tests.fixtures import MOCK_COMPARISON, MOCK_EXTRACTION, MOCK_EXTRACTION_FY2024


def test_compare_returns_valid_report():
    llm = LLMClient(mode="mock")
    agent = ComparisonAgent(llm)
    prior = ExtractionResult.model_validate(MOCK_EXTRACTION_FY2024)
    current = ExtractionResult.model_validate(MOCK_EXTRACTION)
    report = agent.compare(prior, current, mock_response=MOCK_COMPARISON)
    assert isinstance(report, ComparisonReport)
    assert report.prior_fiscal_year == "FY2024"
    assert report.current_fiscal_year == "FY2025"
    assert report.overall_trajectory == "deteriorating"
    assert len(report.trend_shifts) == 3


def test_compare_flags_high_materiality_shifts():
    llm = LLMClient(mode="mock")
    agent = ComparisonAgent(llm)
    prior = ExtractionResult.model_validate(MOCK_EXTRACTION_FY2024)
    current = ExtractionResult.model_validate(MOCK_EXTRACTION)
    report = agent.compare(prior, current, mock_response=MOCK_COMPARISON)
    high_materiality = [s for s in report.trend_shifts if s.materiality == "high"]
    assert len(high_materiality) >= 2


def test_compare_rejects_different_companies():
    llm = LLMClient(mode="mock")
    agent = ComparisonAgent(llm)
    prior = ExtractionResult(company="Company A", fiscal_year="FY2024")
    current = ExtractionResult(company="Company B", fiscal_year="FY2025")
    with pytest.raises(ValueError, match="different companies"):
        agent.compare(prior, current)


def test_compare_default_mock_when_no_shifts():
    llm = LLMClient(mode="mock")
    agent = ComparisonAgent(llm)
    prior = ExtractionResult(company="Stable Co", fiscal_year="FY2024")
    current = ExtractionResult(company="Stable Co", fiscal_year="FY2025")
    report = agent.compare(prior, current)
    assert report.trend_shifts == []
    assert report.overall_trajectory == "stable"


def test_trend_shift_rejects_empty_current_value():
    """Reproduces the exact bug observed in practice: a live model
    returning a trend shift with an empty current_value, rendering as
    'metric: value → (deteriorating)' with nothing after the arrow."""
    from pydantic import ValidationError

    from src.schemas import TrendShift

    try:
        TrendShift(
            metric="Data privacy regulations",
            prior_period="FY2024",
            current_period="FY2025",
            prior_value="Significant monetary fines",
            current_value="",  # exactly the observed bug
            direction="deteriorating",
            materiality="high",
            note="x",
        )
        assert False, "should have raised ValidationError for empty current_value"
    except ValidationError:
        pass
