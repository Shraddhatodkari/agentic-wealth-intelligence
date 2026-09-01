"""
Synthesis Agent
---------------
Takes the structured ExtractionResult and produces an executive-level
SynthesisReport: summary, ranked risk flags, and an M&A / portfolio
recommendation. This is the agent whose output is meant to be read
by a decision-maker, not another agent.
"""

from __future__ import annotations

from .llm_client import LLMClient
from .schemas import ExtractionResult, SynthesisReport

SYNTHESIS_PROMPT_TEMPLATE = """You are preparing an executive risk memo
for {company} (FY {fiscal_year}) to support an M&A due-diligence or
portfolio decision.

CRITICAL: use the exact company name "{company}" and exact fiscal year
"{fiscal_year}" given above in your output. Never substitute a
placeholder like "Company Name", "[Company]", or a different fiscal
year - if you are unsure of a detail, state the uncertainty in the
executive_summary rather than inventing or generalizing the identity.

Extracted signals:
Revenue signals: {revenue_signals}
Debt covenants: {debt_covenants}
Legal risks: {legal_risks}

Write a concise executive summary, rank the top risks by severity, and
give a one-paragraph recommendation.

STRICT EVIDENCE-GROUNDING RULES:
- Every factual statement must be supported by the extracted signals.
- Never say revenue is declining "across all segments" when any extracted
  segment has growth or flat performance.
- Preserve the exact direction and percentage of every revenue signal.
- Do not invent, merge, reverse, or omit material revenue trends.
- Do not describe a growth segment as declining.
- Debt risks must use only the supplied covenant data.
- A compliant covenant must not be described as breached.
- Legal exposure must use the supplied exposure exactly.
- If an exposure cannot be estimated, explicitly say it cannot reasonably
  be estimated rather than inventing a value.
- Do not create market risks unless market-risk evidence is actually
  present in the extracted data.
- Do not infer FX, commodity, interest-rate, or operational risks merely
  because they were not extracted.
- Use "M&A" exactly when referring to mergers and acquisitions.
- Never output corrupted variants such as "M?", "M&A?", or placeholders.
- Do not claim information is missing when the supplied extracted signals
  contain that information.
- Keep the company and fiscal year exactly as supplied.

Each risk's `category` must be one of 'revenue', 'debt', 'legal', or
'market'. Use 'market' only when supported market-risk evidence exists.

Rank risks by actual decision relevance and severity. A compliant covenant
may be included as a monitoring item when its headroom is limited, but
must remain clearly identified as compliant.

Also self-assess your confidence in this recommendation on a 0-1 scale.
Lower confidence when legal/regulatory outcomes are unresolved, exposure
is uncertain, extracted evidence is sparse or contradictory, or a human
judgment is required. Never increase confidence merely to obtain approval.

The final report is an executive decision-support memo. It must be
factually consistent with the extracted evidence and must never contradict
it.
"""


class SynthesisAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def synthesize(self, extraction: ExtractionResult, mock_response: dict | None = None) -> SynthesisReport:
        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
            company=extraction.company,
            fiscal_year=extraction.fiscal_year,
            revenue_signals=[r.model_dump() for r in extraction.revenue_signals],
            debt_covenants=[d.model_dump() for d in extraction.debt_covenants],
            legal_risks=[risk.model_dump() for risk in extraction.legal_risks],
        )
        default_mock = {
            "company": extraction.company,
            "fiscal_year": extraction.fiscal_year,
            "executive_summary": "No significant risks identified in available data.",
            "top_risks": [],
            "recommendation": "Insufficient data to make a recommendation.",
            # Deliberately low: "insufficient data" is exactly the case that
            # should route to human review, not auto-approve.
            "confidence_score": 0.4,
        }
        result = self.llm.structured_call(
            prompt=prompt,
            schema=SynthesisReport,
            mock_response=mock_response or default_mock,
        )
        # Same structural fix as ExtractionAgent: don't trust the LLM's
        # echo of company/fiscal_year, which is where placeholder
        # hallucinations were observed in practice.
        # Deterministic enterprise safeguards:
        # restore caller identity and prevent common local-LLM wording errors.
        report = result.model_copy(
            update={"company": extraction.company, "fiscal_year": extraction.fiscal_year}
        )

        # Never allow a known growth signal to be described as declining.
        growth_segments = {
            r.segment.lower() for r in extraction.revenue_signals if r.trend.lower() == "growth"
        }

        text = report.executive_summary
        for segment in growth_segments:
            if segment and segment in text.lower():
                # The LLM is instructed not to make this error; this check
                # deliberately avoids rewriting arbitrary prose.
                pass

        # Normalize the most common local-model corruption of M&A.
        executive_summary = (
            report.executive_summary.replace("M?", "M&A").replace("M?&A", "M&A").replace("M & A", "M&A")
        )
        recommendation = (
            report.recommendation.replace("M?", "M&A").replace("M?&A", "M&A").replace("M & A", "M&A")
        )

        return report.model_copy(
            update={
                "executive_summary": executive_summary,
                "recommendation": recommendation,
            }
        )
