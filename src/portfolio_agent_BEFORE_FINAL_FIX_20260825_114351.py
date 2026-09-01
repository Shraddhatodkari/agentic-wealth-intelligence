"""
Portfolio Agent
---------------
Takes a list of ExtractionResult objects (one per company) and produces
a PortfolioReport ranking them by growth, risk, and debt exposure, plus
an LLM-synthesized sector narrative.

The rankings themselves are computed deterministically from each
company's already-extracted, schema-validated data - not re-derived by
another LLM call. This is a deliberate design choice: a ranking based on
"average revenue YoY %" or "count of breached covenants" should be
reproducible and auditable, not subject to LLM non-determinism. The one
genuinely LLM-generated piece is the sector_narrative, requested as its
own small schema (SectorNarrative) so the LLM call can't touch the
deterministic rankings.
"""

from __future__ import annotations

from .llm_client import LLMClient
from .schemas import CompanyRank, ExtractionResult, PortfolioReport, SectorNarrative

NARRATIVE_PROMPT_TEMPLATE = """You are synthesizing a portfolio-level
risk narrative across {num_companies} companies for an executive audience.

Growth ranking (highest average revenue YoY %% first):
{growth_ranking}

Risk ranking (highest legal/regulatory risk severity first):
{risk_ranking}

Debt ranking (most non-compliant covenants first):
{debt_ranking}

Write a concise (3-5 sentence) executive narrative identifying the
standout company in each dimension and any portfolio-level pattern
worth flagging (e.g. a sector-wide trend, a company that stands out as
notably higher-risk than peers).
"""


def _average_revenue_growth(extraction: ExtractionResult) -> tuple[float, bool]:
    signals = extraction.revenue_signals
    if not signals:
        return 0.0, False  # no data extracted - NOT the same as "0% growth"
    values = [s.yoy_change_pct for s in signals if s.yoy_change_pct is not None]
    if not values:
        return 0.0, False  # signals exist but none had a numeric YoY figure
    return sum(values) / len(values), True


def _risk_score(extraction: ExtractionResult) -> tuple[float, bool]:
    """Higher score = higher legal/regulatory risk. Weights severity, since
    a single critical risk should outrank several low-severity ones.
    A score of 0 with no legal_risks entries is a legitimate "no risks
    disclosed" result, not missing data - data_available is always True here."""
    severity_weight = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    score = float(sum(severity_weight.get(r.severity.value, 0) for r in extraction.legal_risks))
    return score, True


def _debt_risk_score(extraction: ExtractionResult) -> tuple[float, bool]:
    """Count of covenants not in compliant status - "at risk" or "breached"
    both count, with breached weighted higher. A score of 0 with no
    debt_covenants entries at all is ambiguous (compliant, or just not
    extracted?) - flagged as data_available=False in that specific case."""
    weight = {"compliant": 0, "at risk": 1, "breached": 2}
    if not extraction.debt_covenants:
        return 0.0, False
    score = float(sum(weight.get(c.current_status.lower(), 1) for c in extraction.debt_covenants))
    return score, True


def _rank(
    extractions: list[ExtractionResult], score_fn, metric_label: str, descending: bool = True
) -> list[CompanyRank]:
    scored = [(e.company, *score_fn(e)) for e in extractions]
    scored.sort(key=lambda triple: triple[1], reverse=descending)
    return [
        CompanyRank(
            company=company,
            rank=i + 1,
            metric_value=round(value, 2),
            metric_label=metric_label,
            data_available=data_available,
        )
        for i, (company, value, data_available) in enumerate(scored)
    ]


class PortfolioAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def analyze_portfolio(
        self, extractions: list[ExtractionResult], mock_response: dict | None = None
    ) -> PortfolioReport:
        if not extractions:
            raise ValueError("analyze_portfolio requires at least one company's extraction")

        growth_ranking = _rank(extractions, _average_revenue_growth, "avg revenue YoY %")
        risk_ranking = _rank(extractions, _risk_score, "legal risk severity score")
        debt_ranking = _rank(extractions, _debt_risk_score, "non-compliant covenant count")

        prompt = NARRATIVE_PROMPT_TEMPLATE.format(
            num_companies=len(extractions),
            growth_ranking=[r.model_dump() for r in growth_ranking],
            risk_ranking=[r.model_dump() for r in risk_ranking],
            debt_ranking=[r.model_dump() for r in debt_ranking],
        )

        default_mock = {"sector_narrative": "Insufficient data to synthesize a portfolio narrative."}
        narrative_result = self.llm.structured_call(
            prompt=prompt,
            schema=SectorNarrative,
            mock_response=mock_response or default_mock,
        )

        return PortfolioReport(
            companies=[e.company for e in extractions],
            growth_ranking=growth_ranking,
            risk_ranking=risk_ranking,
            debt_ranking=debt_ranking,
            sector_narrative=narrative_result.sector_narrative,
        )
