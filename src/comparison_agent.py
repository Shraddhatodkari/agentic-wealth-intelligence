"""
Comparison Agent
----------------
Takes two ExtractionResults from the same company (different fiscal
years) and reasons across both to produce a ComparisonReport: what
changed, how material each shift is, and the overall trajectory.

This is a materially harder problem than single-filing synthesis: the
agent has to align metrics that may be named or scoped differently across
two independently-extracted filings (e.g. "Cloud Infrastructure revenue"
in FY2025 vs the same segment in FY2024), not just summarize one
document. It's the piece that turns this from "read one filing" into
"track a company over time" - closer to what a real credit or equity
analyst actually does.
"""

from __future__ import annotations

from .llm_client import LLMClient
from .schemas import ComparisonReport, ExtractionResult

COMPARISON_PROMPT_TEMPLATE = """You are comparing two fiscal years of
10-K disclosures for {company} to identify material trends.

Prior period ({prior_year}):
{prior_data}

Current period ({current_year}):
{current_data}

For each metric that changed materially (revenue by segment, covenant
compliance, legal risk profile), identify the direction of change and
how material it is to the overall risk picture. Then give an overall
trajectory assessment and a short executive narrative.
"""


class ComparisonAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def compare(
        self,
        prior: ExtractionResult,
        current: ExtractionResult,
        mock_response: dict | None = None,
    ) -> ComparisonReport:
        if prior.company != current.company:
            raise ValueError(
                f"Cannot compare filings from different companies: {prior.company!r} vs {current.company!r}"
            )

        prompt = COMPARISON_PROMPT_TEMPLATE.format(
            company=current.company,
            prior_year=prior.fiscal_year,
            current_year=current.fiscal_year,
            prior_data=prior.model_dump(),
            current_data=current.model_dump(),
        )
        default_mock = {
            "company": current.company,
            "prior_fiscal_year": prior.fiscal_year,
            "current_fiscal_year": current.fiscal_year,
            "trend_shifts": [],
            "overall_trajectory": "stable",
            "narrative": "No material changes identified between periods.",
        }
        result = self.llm.structured_call(
            prompt=prompt,
            schema=ComparisonReport,
            mock_response=mock_response or default_mock,
        )
        # Same structural fix as ExtractionAgent/SynthesisAgent - don't
        # trust the LLM's echo of identity fields we already know.
        return result.model_copy(
            update={
                "company": current.company,
                "prior_fiscal_year": prior.fiscal_year,
                "current_fiscal_year": current.fiscal_year,
            }
        )
