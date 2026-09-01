from src.llm_client import LLMClient
from src.portfolio_agent import PortfolioAgent
from src.schemas import ExtractionResult, PortfolioReport, RevenueSignal
from tests.fixtures import (
    MOCK_EXTRACTION,
    MOCK_EXTRACTION_SOLARA,
    MOCK_EXTRACTION_VANTAGE,
    MOCK_PORTFOLIO_NARRATIVE,
)


def _extractions():
    return [
        ExtractionResult.model_validate(MOCK_EXTRACTION),
        ExtractionResult.model_validate(MOCK_EXTRACTION_SOLARA),
        ExtractionResult.model_validate(MOCK_EXTRACTION_VANTAGE),
    ]


def test_analyze_portfolio_returns_valid_report():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        _extractions(), mock_response={"sector_narrative": MOCK_PORTFOLIO_NARRATIVE}
    )
    assert isinstance(report, PortfolioReport)
    assert len(report.companies) == 3
    assert len(report.growth_ranking) == 3
    assert len(report.risk_ranking) == 3
    assert len(report.debt_ranking) == 3


def test_growth_ranking_orders_highest_growth_first():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        _extractions(), mock_response={"sector_narrative": MOCK_PORTFOLIO_NARRATIVE}
    )
    assert report.growth_ranking[0].company == "Solara Energy Corp"
    assert report.growth_ranking[0].rank == 1
    assert report.growth_ranking[-1].company == "Vantage Robotics, Inc."
    # Solara's growth number should be strictly higher than Vantage's
    assert report.growth_ranking[0].metric_value > report.growth_ranking[-1].metric_value


def test_debt_ranking_flags_covenant_breach_as_highest_risk():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        _extractions(), mock_response={"sector_narrative": MOCK_PORTFOLIO_NARRATIVE}
    )
    # Vantage is the only company with breached covenants - must rank #1 on debt risk
    assert report.debt_ranking[0].company == "Vantage Robotics, Inc."
    assert report.debt_ranking[0].metric_value > 0


def test_risk_ranking_weights_severity_not_just_count():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        _extractions(), mock_response={"sector_narrative": MOCK_PORTFOLIO_NARRATIVE}
    )
    # Nimbus has a "high" + "medium" severity risk (weight 3+2=5);
    # Vantage has one "medium" (weight 2). Nimbus must outrank Vantage.
    nimbus_rank = next(r for r in report.risk_ranking if "Nimbus" in r.company)
    vantage_rank = next(r for r in report.risk_ranking if "Vantage" in r.company)
    assert nimbus_rank.rank < vantage_rank.rank
    assert nimbus_rank.metric_value > vantage_rank.metric_value


def test_clean_company_ranks_lowest_on_both_risk_dimensions():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        _extractions(), mock_response={"sector_narrative": MOCK_PORTFOLIO_NARRATIVE}
    )
    solara_risk = next(r for r in report.risk_ranking if "Solara" in r.company)
    solara_debt = next(r for r in report.debt_ranking if "Solara" in r.company)
    assert solara_risk.metric_value == 0
    assert solara_debt.metric_value == 0


def test_analyze_portfolio_raises_on_empty_input():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    try:
        agent.analyze_portfolio([])
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_single_company_portfolio_still_works():
    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        [ExtractionResult.model_validate(MOCK_EXTRACTION)],
        mock_response={"sector_narrative": "Single-company view, no cross-company comparison available."},
    )
    assert len(report.companies) == 1
    assert report.growth_ranking[0].rank == 1


def test_missing_revenue_data_flagged_as_unavailable_not_zero_growth():
    """Reproduces the exact ambiguity observed in practice: Microsoft and
    NVIDIA both showed '+0.0% average revenue YoY' in a live run - visually
    identical to genuinely flat growth, but actually meant no revenue
    signals were extracted at all. data_available distinguishes these."""

    no_data_company = ExtractionResult(company="Microsoft Corporation", fiscal_year="FY2025")
    real_zero_growth_company = ExtractionResult(
        company="Flatline Corp",
        fiscal_year="FY2025",
        revenue_signals=[
            RevenueSignal(
                period="FY2025",
                segment="Consolidated",
                trend="flat",
                yoy_change_pct=0.0,
                note="No change YoY",
            )
        ],
    )

    agent = PortfolioAgent(LLMClient(mode="mock"))
    report = agent.analyze_portfolio(
        [no_data_company, real_zero_growth_company],
        mock_response={"sector_narrative": "test"},
    )

    no_data_rank = next(r for r in report.growth_ranking if "Microsoft" in r.company)
    real_zero_rank = next(r for r in report.growth_ranking if "Flatline" in r.company)

    assert no_data_rank.data_available is False
    assert real_zero_rank.data_available is True
    # Both show metric_value == 0.0 - the flag is the only thing that
    # distinguishes "no data" from "genuinely flat" - both must be present
    assert no_data_rank.metric_value == 0.0
    assert real_zero_rank.metric_value == 0.0
