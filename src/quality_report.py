"""
Data quality reporting for LIVE runs (real tickers, no ground truth).

This is deliberately NOT the same thing as evaluation.py's accuracy
scoring. evaluate_all() in evaluation.py measures extraction accuracy
against hand-labeled ground truth - a real, defensible percentage, but
only possible for the bundled synthetic sample filings where that
ground truth exists. For a real company's filing, there is no ground
truth in this codebase, so an "accuracy" or "hallucination rate" number
for AAPL/MSFT/etc. would be fabricated - not measured from anything.

What IS honestly measurable without ground truth: structural
completeness (are fields populated) and consistency (do detected values
pass sanity checks, via output_validation.py). This module computes
that, framed explicitly as data quality, not accuracy.
"""

from __future__ import annotations

from .output_validation import validate_extraction_result, validate_synthesis_report
from .schemas import ExtractionResult, QualityReport, SynthesisReport


def _completeness_score(extraction: ExtractionResult, report: SynthesisReport | None) -> float:
    """Fraction of expected top-level fields that are non-empty. Coarse but
    honest - doesn't pretend to measure whether the *content* is correct,
    only whether the pipeline actually populated what it's supposed to."""
    checks = [
        bool(extraction.revenue_signals),
        bool(extraction.debt_covenants) or bool(extraction.legal_risks),
    ]
    if report is not None:
        checks.append(bool(report.executive_summary.strip()))
        checks.append(bool(report.recommendation.strip()))
        checks.append(bool(report.top_risks) or "no" in report.executive_summary.lower())
    return sum(checks) / len(checks) if checks else 0.0


def build_quality_report(
    extraction: ExtractionResult,
    expected_company: str,
    synthesis_report: SynthesisReport | None = None,
) -> QualityReport:
    extraction_validation = validate_extraction_result(extraction, expected_company)
    all_issues = list(extraction_validation.issues)

    if synthesis_report is not None:
        synthesis_validation = validate_synthesis_report(synthesis_report, expected_company)
        all_issues.extend(synthesis_validation.issues)

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    issues = [f"[{i.severity}] {i.field}: {i.problem}" for i in all_issues]

    return QualityReport(
        company=extraction.company,
        fiscal_year=extraction.fiscal_year,
        completeness_score=round(_completeness_score(extraction, synthesis_report), 3),
        error_count=error_count,
        warning_count=warning_count,
        issues=issues,
    )
