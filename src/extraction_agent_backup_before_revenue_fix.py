"""
Evidence-grounded Extraction Agent.

Ollama performs semantic extraction, while deterministic reconciliation
protects explicit financial facts from sign errors, value swapping,
and unsupported inference.
"""

from __future__ import annotations

import re
from typing import List

from .ingestion_agent import Chunk
from .llm_client import LLMClient
from .schemas import DebtCovenant, ExtractionResult, LegalRisk, RevenueSignal

EXTRACTION_PROMPT_TEMPLATE = """You are a conservative financial-data
extraction engine analyzing a 10-K filing.

Company: {company}
Fiscal year: {fiscal_year}

FILING TEXT:
---
{text}
---

Extract ONLY facts explicitly supported by the filing.

NON-NEGOTIABLE RULES:

1. Preserve the exact sign of every percentage.
   "-14%" MUST remain -14.0, never +14.0.
2. Preserve every explicitly stated percentage.
3. Preserve the relationship between a number and the business segment
   or legal matter it belongs to.
4. NEVER move a monetary amount from one legal matter to another.
5. If a legal matter says a loss range is "$15 million to $40 million",
   that exact range belongs to that matter.
6. If another legal matter says the loss cannot reasonably be estimated,
   potential_exposure MUST be null.
7. Extract debt covenants when the filing explicitly states a threshold
   and current measurement.
8. For a maximum limit, current <= limit is compliant unless the filing
   explicitly says otherwise.
9. For a minimum limit, current >= limit is compliant unless the filing
   explicitly says otherwise.
10. Do not invent market risks.
11. Do not infer a risk merely because a section is called market risk.
12. "No covenant extracted" does NOT mean "no debt concern".
13. Never invent numbers.
14. Never swap numbers between facts.
15. Keep company and fiscal year exactly as supplied.
16. Return empty arrays when evidence does not exist.

Return valid JSON matching the requested schema.
"""


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
        "decline",
        "declined",
        "fall",
        "grew",
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
        "interest coverage",
        "headroom",
        "compliant",
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
        "investigative demand",
        "class action",
        "loss",
    ),
}


def _extract_percentages(text: str) -> list[float]:
    values = []
    for match in re.finditer(
        r"(?<![\w.])([+-]?\d+(?:\.\d+)?)\s*%",
        text,
    ):
        values.append(float(match.group(1)))
    return values


def _extract_money(text: str) -> list[str]:
    pattern = (
        r"\$\s*\d+(?:,\d{3})*(?:\.\d+)?"
        r"(?:\s+(?:thousand|million|billion|trillion))?"
    )
    return [match.group(0).strip() for match in re.finditer(pattern, text, flags=re.IGNORECASE)]


def _chunk_relevance_score(chunk: Chunk) -> int:
    text = chunk.text.lower()
    score = 0

    for terms in RELEVANCE_TERMS.values():
        for term in terms:
            if term in text:
                score += 1

    if _extract_percentages(chunk.text):
        score += 2

    if _extract_money(chunk.text):
        score += 2

    if re.search(r"\b\d+(?:\.\d+)?\s*x\b", text):
        score += 2

    return score


def _select_relevant_chunks(chunks: List[Chunk]) -> list[Chunk]:
    if not chunks:
        return []

    ranked = sorted(
        enumerate(chunks),
        key=lambda item: (-_chunk_relevance_score(item[1]), item[0]),
    )

    selected = []
    selected_ids = set()
    total_chars = 0

    for _, chunk in ranked:
        score = _chunk_relevance_score(chunk)

        if score <= 0:
            continue

        if len(selected) >= MAX_EXTRACTION_CHUNKS:
            break

        remaining = MAX_EXTRACTION_CHARS - total_chars

        if remaining <= 0:
            break

        if chunk.chunk_id in selected_ids:
            continue

        text = chunk.text[:remaining]

        selected.append(
            Chunk(
                chunk_id=chunk.chunk_id,
                text=text,
                section=chunk.section,
            )
        )

        selected_ids.add(chunk.chunk_id)
        total_chars += len(text)

    selected.sort(
        key=lambda chunk: next(i for i, original in enumerate(chunks) if original.chunk_id == chunk.chunk_id)
    )

    return selected


def _parse_revenue_evidence(source_text: str) -> list[RevenueSignal]:
    """Extract explicit revenue/net-sales year-over-year changes.

    Supports common 10-K structures such as:
      - revenue ... an increase of 28%
      - revenue ... a decline of 6.3%
      - segment ... grew 18% year-over-year
      - segment ... fell 14% year-over-year
      - sales in Europe increased 8%

    Only explicit percentage changes tied to revenue/sales language
    are extracted.
    """

    signals: list[RevenueSignal] = []

    text = re.sub(r"&#\d+;|&[A-Za-z]+;", " ", source_text)
    text = re.sub(r"\s+", " ", text).strip()

    seen: set[tuple[str, float, str]] = set()

    def add_signal(segment: str, value: float) -> None:
        segment = re.sub(r"\s+", " ", segment).strip(" ,;:.-")

        if not segment:
            segment = "Total company"

        if len(segment) > 80:
            segment = segment[:80].rsplit(" ", 1)[0].strip()

        trend = "decline" if value < 0 else "growth"
        key = (segment.lower(), value, trend)

        if key in seen:
            return

        seen.add(key)

        signals.append(
            RevenueSignal(
                period="",
                segment=segment,
                trend=trend,
                yoy_change_pct=value,
                note=(f"Explicit filing evidence: {value:g}% year-over-year change."),
            )
        )

    # 1. Consolidated/company revenue:
    # "revenue ... an increase of 28%"
    # "revenue ... a decline of 6.3%"
    consolidated_patterns = [
        re.compile(
            r"\b(?:consolidated\s+)?"
            r"(?:net\s+)?(?:sales|revenue|revenues)"
            r".{0,180}?"
            r"\b(?:an?\s+)?"
            r"(?P<direction>increase|increased|growth|grew|"
            r"decline|declined|decrease|decreased|fell|fall)"
            r"(?:\s+of|\s+by)?\s+"
            r"(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%",
            re.IGNORECASE,
        ),
    ]

    for pattern in consolidated_patterns:
        for match in pattern.finditer(text):
            direction = match.group("direction").lower()
            pct = float(match.group("pct"))

            negative = bool(
                re.search(
                    r"declin|decreas|fell|fall",
                    direction,
                    re.IGNORECASE,
                )
            )

            value = -abs(pct) if negative else abs(pct)

            # Use Total company for consolidated revenue.
            prefix = text[max(0, match.start() - 30) : match.start()].lower()

            if "consolidated" in prefix:
                segment = "Total company"
            else:
                segment = "Total company"

            add_signal(segment, value)

    # 2. Segment revenue:
    # "Cloud Infrastructure segment, which grew 18%"
    # "Residential Solar segment grew 19%"
    # "Industrial Automation segment, which fell 19%"
    segment_patterns = [
        re.compile(
            r"(?P<segment>[A-Z][A-Za-z0-9&'()/.-]{1,50}?)"
            r"\s+segment"
            r"(?:,\s*which)?\s+"
            r"(?P<direction>grew|growth|increased|increases|"
            r"rose|declined|decreased|fell|falling|"
            r"were\s+up|were\s+down|was\s+up|was\s+down)"
            r"(?:\s+by|\s+of)?\s+"
            r"(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<segment>[A-Z][A-Za-z0-9&'()/.-]{1,50}?)"
            r"\s+segment"
            r".{0,80}?"
            r"(?P<direction>grew|increased|rose|declined|decreased|fell)"
            r"(?:\s+by|\s+of)?\s+"
            r"(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%",
            re.IGNORECASE,
        ),
    ]

    for pattern in segment_patterns:
        for match in pattern.finditer(text):
            segment = match.group("segment").strip()
            direction = match.group("direction").lower()
            pct = float(match.group("pct"))

            negative = bool(
                re.search(
                    r"declin|decreas|fell|fall|down",
                    direction,
                    re.IGNORECASE,
                )
            )

            value = -abs(pct) if negative else abs(pct)

            add_signal(segment, value)

    # 3. Generic "sales/revenue in [segment] increased X%"
    geographic_patterns = [
        re.compile(
            r"(?:net\s+)?(?:sales|revenue|revenues)"
            r"\s+(?:in|for|from|within)\s+"
            r"(?P<segment>[A-Z][A-Za-z0-9&'()/.-]{1,50})"
            r"\s+"
            r"(?P<direction>increased|increases|grew|rose|"
            r"declined|decreased|fell)"
            r"(?:\s+by|\s+of)?\s+"
            r"(?P<pct>[0-9]+(?:\.[0-9]+)?)\s*%",
            re.IGNORECASE,
        ),
    ]

    for pattern in geographic_patterns:
        for match in pattern.finditer(text):
            segment = match.group("segment").strip()
            direction = match.group("direction").lower()
            pct = float(match.group("pct"))

            negative = bool(
                re.search(
                    r"declin|decreas|fell|down",
                    direction,
                    re.IGNORECASE,
                )
            )

            value = -abs(pct) if negative else abs(pct)

            add_signal(segment, value)

    return signals


def _parse_debt_evidence(source_text: str) -> list[DebtCovenant]:
    """Extract only explicit debt-covenant measurements.

    This deliberately refuses to classify arbitrary financial numbers as
    covenants. A covenant must contain debt/credit/covenant language and
    an explicit ratio/limit/current measurement.
    """

    results: list[DebtCovenant] = []

    text = re.sub(r"&#\d+;|&[A-Za-z]+;", " ", source_text)
    text = re.sub(r"\s+", " ", text)

    # Maximum leverage covenant.
    leverage_patterns = [
        re.compile(
            r"(?:maximum\s+)?leverage\s+ratio"
            r".{0,160}?"
            r"(?:limit|maximum|covenant)"
            r".{0,80}?"
            r"(?P<limit>[0-9]+(?:\.[0-9]+)?)\s*x"
            r".{0,180}?"
            r"(?:leverage\s+ratio|reported|was|is)"
            r".{0,80}?"
            r"(?P<current>[0-9]+(?:\.[0-9]+)?)\s*x",
            re.IGNORECASE,
        ),
        re.compile(
            r"leverage\s+ratio"
            r".{0,120}?"
            r"(?P<current>[0-9]+(?:\.[0-9]+)?)\s*x"
            r".{0,160}?"
            r"(?:maximum|limit|covenant)"
            r".{0,80}?"
            r"(?P<limit>[0-9]+(?:\.[0-9]+)?)\s*x",
            re.IGNORECASE,
        ),
    ]

    for pattern in leverage_patterns:
        match = pattern.search(text)
        if not match:
            continue

        current = float(match.group("current"))
        limit = float(match.group("limit"))

        status = "compliant" if current <= limit else "breached"

        results.append(
            DebtCovenant(
                covenant_type="leverage ratio",
                threshold=f"{limit:g}x maximum",
                current_status=status,
                note=(f"Explicit filing evidence: leverage ratio is {current:g}x versus {limit:g}x maximum."),
            )
        )
        break

    # Minimum interest-coverage covenant.
    interest_patterns = [
        re.compile(
            r"(?:minimum\s+)?interest\s+coverage\s+ratio"
            r".{0,120}?"
            r"(?P<limit>[0-9]+(?:\.[0-9]+)?)\s*x"
            r".{0,180}?"
            r"(?:interest\s+coverage|coverage\s+ratio)"
            r".{0,100}?"
            r"(?P<current>[0-9]+(?:\.[0-9]+)?)\s*x",
            re.IGNORECASE,
        ),
        re.compile(
            r"interest\s+coverage"
            r".{0,120}?"
            r"(?P<current>[0-9]+(?:\.[0-9]+)?)\s*x"
            r".{0,160}?"
            r"(?:minimum|threshold|covenant)"
            r".{0,80}?"
            r"(?P<limit>[0-9]+(?:\.[0-9]+)?)\s*x",
            re.IGNORECASE,
        ),
    ]

    for pattern in interest_patterns:
        match = pattern.search(text)
        if not match:
            continue

        current = float(match.group("current"))
        limit = float(match.group("limit"))

        status = "compliant" if current >= limit else "breached"

        results.append(
            DebtCovenant(
                covenant_type="interest coverage",
                threshold=f"{limit:g}x minimum",
                current_status=status,
                note=(
                    f"Explicit filing evidence: interest coverage is {current:g}x versus {limit:g}x minimum."
                ),
            )
        )
        break

    return results


def _parse_legal_evidence(source_text: str) -> list[LegalRisk]:
    """Extract generic legal/regulatory evidence without company-specific names.

    The parser only creates a legal risk when the filing contains explicit
    legal/regulatory terminology. Financial/tax language by itself is not
    treated as litigation.
    """

    results: list[LegalRisk] = []

    text = re.sub(r"&#\d+;|&[A-Za-z]+;", " ", source_text)
    text = re.sub(r"\s+", " ", text)

    legal_pattern = re.compile(
        r"(?P<context>"
        r"(?:civil\s+investigative\s+demand|"
        r"investigative\s+demand|"
        r"class\s+action|"
        r"class\s+actions|"
        r"lawsuit|"
        r"litigation|"
        r"legal\s+proceeding|"
        r"regulatory\s+proceeding|"
        r"government\s+investigation|"
        r"governmental\s+investigation|"
        r"regulatory\s+investigation|"
        r"patent\s+litigation|"
        r"antitrust\s+investigation|"
        r"enforcement\s+action)"
        r")"
        r".{0,500}?",
        re.IGNORECASE,
    )

    seen: set[str] = set()

    for match in legal_pattern.finditer(text):
        matter = " ".join(match.group("context").split()).strip()

        key = matter.lower()
        if key in seen:
            continue

        seen.add(key)

        window_start = match.start()
        window_end = min(len(text), match.end() + 500)
        window = text[window_start:window_end]

        exposure_match = re.search(
            r"(?:loss|exposure|settlement|penalty)"
            r".{0,100}?"
            r"(\$[0-9][0-9,]*(?:\.[0-9]+)?"
            r"(?:\s+(?:million|billion|thousand))?"
            r"(?:\s+to\s+\$[0-9][0-9,]*(?:\.[0-9]+)?"
            r"(?:\s+(?:million|billion|thousand))?)?)",
            window,
            re.IGNORECASE,
        )

        exposure = exposure_match.group(1) if exposure_match else None

        lower_window = window.lower()

        if any(
            term in lower_window
            for term in (
                "reasonably possible",
                "probable",
                "material adverse",
                "significant",
            )
        ):
            severity = "high"
        elif any(term in lower_window for term in ("possible", "contingent", "uncertain")):
            severity = "medium"
        else:
            severity = "low"

        results.append(
            LegalRisk(
                matter=matter,
                severity=severity,
                potential_exposure=exposure,
                note=("Legal or regulatory matter identified from explicit filing evidence."),
            )
        )

    return results


def _reconcile_with_source(
    result: ExtractionResult,
    source_text: str,
) -> ExtractionResult:
    """
    Source text is authoritative for explicit financial facts.

    Ollama supplies semantic interpretation; deterministic parsing protects
    exact values, signs, associations, and covenant status.
    """

    parsed_revenue = _parse_revenue_evidence(source_text)
    parsed_debt = _parse_debt_evidence(source_text)
    parsed_legal = _parse_legal_evidence(source_text)

    if parsed_revenue:
        for item in parsed_revenue:
            item.period = result.fiscal_year

        result.revenue_signals = parsed_revenue

    if parsed_debt:
        result.debt_covenants = parsed_debt

    if parsed_legal:
        result.legal_risks = parsed_legal

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

        full_source_text = "\n".join(chunk.text for chunk in chunks)

        selected_chunks = _select_relevant_chunks(chunks)

        extraction_text = "\n".join(chunk.text for chunk in selected_chunks)

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

        result = result.model_copy(
            update={
                "company": company,
                "fiscal_year": fiscal_year,
            }
        )

        return _reconcile_with_source(
            result=result,
            source_text=full_source_text,
        )
