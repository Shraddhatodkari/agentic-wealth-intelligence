"""
Extraction Agent
----------------
Evidence-grounded structured extraction for SEC 10-K analysis.

The local LLM performs semantic extraction on a bounded set of relevant
chunks, while deterministic post-processing protects explicit numeric
evidence from being lost.
"""

from __future__ import annotations

import re
from typing import List

from .ingestion_agent import Chunk
from .llm_client import LLMClient
from .schemas import ExtractionResult


EXTRACTION_PROMPT_TEMPLATE = """You are a conservative financial-data extraction engine.

Company: {company}
Fiscal year: {fiscal_year}

FILING TEXT:
---
{text}
---

TASK:
Extract ONLY facts explicitly supported by the filing text.

CRITICAL RULES:

1. Preserve every explicitly stated percentage.
2. If the filing says "increased 18%", yoy_change_pct MUST be 18.0.
3. Preserve explicitly stated monetary exposure exactly.
4. If the filing says "potential exposure of $50 million",
   potential_exposure MUST be "$50 million".
5. Never replace an explicitly stated number with null.
6. Never invent a number that is not present in the filing.
7. Never infer a risk without supporting filing evidence.
8. Debt covenant status must be based only on explicit text.
9. Return empty arrays when there is no supporting evidence.
10. Keep company and fiscal year exactly as supplied.
11. Preserve units such as %, x, thousand, million, and billion.
12. Do not summarize away important numeric evidence.

Return valid JSON matching the requested schema.
"""


# The local model has a 4096-token context window. Keep the extraction
# evidence comfortably below that limit so the prompt/schema/output have
# sufficient room.
MAX_EXTRACTION_CHUNKS = 9
MAX_EXTRACTION_CHARS = 7200


RELEVANCE_TERMS = {
    "revenue": (
        "revenue",
        "sales",
        "net sales",
        "operating revenue",
        "income",
        "growth",
        "increased",
        "decreased",
        "year over year",
        "year-over-year",
        "yoy",
    ),
    "debt": (
        "debt",
        "covenant",
        "leverage",
        "debt-to-ebitda",
        "ebitda",
        "credit agreement",
        "loan",
        "borrowing",
        "interest",
        "liquidity",
    ),
    "legal": (
        "legal",
        "lawsuit",
        "litigation",
        "litigations",
        "claim",
        "claims",
        "proceeding",
        "proceedings",
        "patent",
        "regulatory",
        "settlement",
        "exposure",
        "contingent",
    ),
}


def _extract_percentages(text: str) -> list[float]:
    """Extract explicitly stated percentages from source text."""

    values: list[float] = []

    for match in re.finditer(
        r"(?<![\w.])(\d+(?:\.\d+)?)\s*%",
        text,
    ):
        values.append(float(match.group(1)))

    return values


def _extract_money(text: str) -> list[str]:
    """Extract explicitly stated USD monetary amounts from source text."""

    pattern = (
        r"\$\s*\d+(?:,\d{3})*(?:\.\d+)?"
        r"(?:\s+(?:thousand|million|billion|trillion))?"
    )

    return [
        match.group(0).strip()
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]


def _chunk_relevance_score(chunk: Chunk) -> int:
    """Score a chunk using deterministic evidence-oriented keywords."""

    text = chunk.text.lower()
    score = 0

    for terms in RELEVANCE_TERMS.values():
        for term in terms:
            if term in text:
                score += 1

    # Numeric evidence is especially important to this extraction schema.
    if _extract_percentages(chunk.text):
        score += 2

    if _extract_money(chunk.text):
        score += 2

    # Covenant ratios often appear without the literal word "covenant".
    if re.search(r"\b\d+(?:\.\d+)?\s*x\b", text):
        score += 2

    return score


def _select_relevant_chunks(chunks: List[Chunk]) -> list[Chunk]:
    """
    Select a bounded evidence set for the LLM.

    The complete filing remains available to deterministic post-processing.
    Only the most relevant chunks are sent to the local model.
    """

    if not chunks:
        return []

    ranked = sorted(
        enumerate(chunks),
        key=lambda item: (-_chunk_relevance_score(item[1]), item[0]),
    )

    selected: list[Chunk] = []
    selected_ids: set[str] = set()
    total_chars = 0

    for _, chunk in ranked:
        score = _chunk_relevance_score(chunk)

        # Once useful evidence has been exhausted, do not fill the
        # context window with irrelevant filing text.
        if score <= 0:
            continue

        if len(selected) >= MAX_EXTRACTION_CHUNKS:
            break

        remaining = MAX_EXTRACTION_CHARS - total_chars
        if remaining <= 0:
            break

        text = chunk.text[:remaining]

        if chunk.chunk_id in selected_ids:
            continue

        selected.append(
            Chunk(
                chunk_id=chunk.chunk_id,
                text=text,
                section=chunk.section,
            )
        )
        selected_ids.add(chunk.chunk_id)
        total_chars += len(text)

    # Preserve deterministic ordering for reproducibility.
    selected.sort(
        key=lambda chunk: next(
            i for i, original in enumerate(chunks)
            if original.chunk_id == chunk.chunk_id
        )
    )

    return selected


def _repair_explicit_evidence(
    result: ExtractionResult,
    source_text: str,
) -> ExtractionResult:
    """
    Deterministically recover explicit numeric evidence that the
    local LLM failed to place into structured fields.

    The filing text is authoritative for explicitly stated values.
    No new values are invented here.
    """

    percentages = _extract_percentages(source_text)
    money_values = _extract_money(source_text)

    # ---------------------------------------------------------
    # Revenue percentage recovery
    # ---------------------------------------------------------
    if percentages and result.revenue_signals:
        for signal in result.revenue_signals:
            if signal.yoy_change_pct is None:
                signal.yoy_change_pct = percentages[0]
                break

    # ---------------------------------------------------------
    # Legal monetary exposure recovery
    # ---------------------------------------------------------
    if money_values and result.legal_risks:
        for risk in result.legal_risks:
            if risk.potential_exposure is None:
                risk.potential_exposure = money_values[0]
                break

    return result


class ExtractionAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def extract(
        self,
        chunks: List[Chunk],
        company: str,
        fiscal_year: str,
        mock_response: dict | None = None,
    ) -> ExtractionResult:

        # Keep the complete source for deterministic evidence protection.
        full_source_text = "\n".join(
            chunk.text for chunk in chunks
        )

        # Only bounded, relevant evidence is sent to the LLM.
        selected_chunks = _select_relevant_chunks(chunks)

        extraction_text = "\n".join(
            chunk.text for chunk in selected_chunks
        )

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            company=company,
            fiscal_year=fiscal_year,
            text=extraction_text,
        )

        default_mock = {
            "company": company,
            "fiscal_year": fiscal_year,
            "revenue_signals": [],
            "debt_covenants": [],
            "legal_risks": [],
        }

        result = self.llm.structured_call(
            prompt=prompt,
            schema=ExtractionResult,
            mock_response=mock_response or default_mock,
        )

        # Never trust the LLM's identity fields.
        result = result.model_copy(
            update={
                "company": company,
                "fiscal_year": fiscal_year,
            }
        )

        # IMPORTANT:
        # Repair against the COMPLETE source, not just the bounded
        # LLM context. This prevents relevant numeric evidence from
        # being lost merely because it was outside the selected chunks.
        result = _repair_explicit_evidence(
            result=result,
            source_text=full_source_text,
        )

        return result
'@ | Set-Content src\extraction_agent.py -Encoding UTF8
