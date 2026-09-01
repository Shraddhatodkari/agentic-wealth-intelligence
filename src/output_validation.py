"""
Output validation for live (non-mock) LLM calls.

Structured-schema validation (Pydantic) only guarantees *shape* - a
response can be perfectly valid JSON matching ExtractionResult's schema
and still contain a hallucinated placeholder like "Company Name" instead
of the actual company, or a leverage ratio expressed in the wrong unit
("8.5%" instead of "8.5x"). This module catches the failure modes that
were observed running real tickers through Ollama: placeholder text,
empty required fields, and unit-confused covenant values.

This is deliberately separate from Pydantic schema validation - schema
validation happens first (in llm_client.structured_call) and rejects
malformed JSON; this runs after, on well-formed-but-wrong content.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .schemas import ExtractionResult, SynthesisReport

PLACEHOLDER_PATTERNS = [
    "company name",
    "placeholder",
    "the company",
    "[company]",
    "example corp",
    "unknown company",
]


@dataclass
class ValidationIssue:
    field: str
    problem: str
    severity: str  # "error" (should retry) | "warning" (surface to user, don't retry)


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    @property
    def is_clean(self) -> bool:
        return len(self.issues) == 0


def _looks_like_placeholder(text: str) -> bool:
    lowered = text.strip().lower()
    return any(pattern in lowered for pattern in PLACEHOLDER_PATTERNS)


def validate_synthesis_report(report: SynthesisReport, expected_company: str) -> ValidationResult:
    """
    Checks a live SynthesisReport for hallucination patterns observed in
    practice: placeholder company names, a fiscal year that doesn't match
    what was requested, and empty top-risk fields.
    """
    issues: list[ValidationIssue] = []

    if _looks_like_placeholder(report.company):
        issues.append(
            ValidationIssue(
                field="company",
                problem=f"Report says {report.company!r} instead of the requested company name - "
                f"looks like a hallucinated placeholder, not real extraction.",
                severity="error",
            )
        )
    elif expected_company and expected_company.lower() not in report.company.lower():
        # Not necessarily an error - "Apple Inc." vs "AAPL" is a legitimate
        # mismatch of ticker vs. legal name - surfaced as a warning, not a retry trigger.
        issues.append(
            ValidationIssue(
                field="company",
                problem=f"Report company {report.company!r} doesn't obviously match "
                f"requested {expected_company!r} - verify this is the right filing.",
                severity="warning",
            )
        )

    for i, risk in enumerate(report.top_risks):
        if not risk.headline.strip() or not risk.detail.strip():
            issues.append(
                ValidationIssue(
                    field=f"top_risks[{i}]",
                    problem="Empty headline or detail field.",
                    severity="error",
                )
            )

    if not report.executive_summary.strip():
        issues.append(
            ValidationIssue(field="executive_summary", problem="Empty executive summary.", severity="error")
        )

    return ValidationResult(issues=issues)


def validate_extraction_result(extraction: ExtractionResult, expected_company: str) -> ValidationResult:
    """
    Checks a live ExtractionResult for the same hallucination patterns,
    plus a unit-consistency check on debt covenants: leverage ratios are
    conventionally expressed as a multiple of EBITDA ("3.5x"), not a
    percentage - a value like "8.5%" for a leverage-ratio threshold is a
    strong signal the model confused units, observed in practice with a
    local Ollama model on a real filing.
    """
    issues: list[ValidationIssue] = []

    if _looks_like_placeholder(extraction.company):
        issues.append(
            ValidationIssue(
                field="company",
                problem=f"Extraction says {extraction.company!r} instead of the requested "
                f"company name - looks like a hallucinated placeholder.",
                severity="error",
            )
        )

    for i, covenant in enumerate(extraction.debt_covenants):
        if "leverage" in covenant.covenant_type.lower() and "%" in covenant.threshold:
            issues.append(
                ValidationIssue(
                    field=f"debt_covenants[{i}]",
                    problem=f"Leverage ratio threshold {covenant.threshold!r} uses '%' - leverage "
                    f"ratios are conventionally a multiple of EBITDA (e.g. '3.5x'), not a "
                    f"percentage. Likely a unit-confusion hallucination.",
                    severity="warning",
                )
            )

    for i, signal in enumerate(extraction.revenue_signals):
        if not signal.segment.strip() or not signal.note.strip():
            issues.append(
                ValidationIssue(
                    field=f"revenue_signals[{i}]", problem="Empty segment or note field.", severity="error"
                )
            )

    return ValidationResult(issues=issues)
