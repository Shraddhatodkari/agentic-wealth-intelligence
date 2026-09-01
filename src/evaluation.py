"""
Evaluation Harness
------------------
Measures whether the Extraction Agent's output is actually *correct*,
not just schema-valid. Schema validation (Pydantic) catches malformed
output; this harness catches *wrong* output - e.g. the agent extracting
3 revenue signals when the filing actually supports 4, or missing a
high-severity legal risk entirely.

This is the piece that turns "I built a pipeline" into "I measured
whether the pipeline works" - the difference between shipping something
and being able to say how well it performs. It's deliberately simple
(structural/count-based checks against hand-labeled ground truth,
not a full NLP eval framework) but the methodology - labeled ground
truth, per-filing accuracy, aggregate reporting - is the real pattern
used for evaluating extraction pipelines in production.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from .schemas import CheckResult, EvaluationResult, ExtractionResult


def load_ground_truth(labels_path: str) -> Dict[str, dict]:
    return json.loads(Path(labels_path).read_text(encoding="utf-8"))


def evaluate_extraction(
    extraction: ExtractionResult, filing_name: str, ground_truth: dict
) -> EvaluationResult:
    checks: List[CheckResult] = []

    def check(name: str, expected, actual):
        checks.append(
            CheckResult(
                check_name=name,
                passed=(expected == actual),
                expected=str(expected),
                actual=str(actual),
            )
        )

    check(
        "revenue_signal_count",
        ground_truth["expected_revenue_signal_count"],
        len(extraction.revenue_signals),
    )
    check(
        "debt_covenant_count",
        ground_truth["expected_debt_covenant_count"],
        len(extraction.debt_covenants),
    )
    check(
        "legal_risk_count",
        ground_truth["expected_legal_risk_count"],
        len(extraction.legal_risks),
    )
    check(
        "high_severity_legal_risk_count",
        ground_truth["expected_high_severity_legal_risks"],
        sum(1 for r in extraction.legal_risks if r.severity.value == "high"),
    )

    consolidated = next((r for r in extraction.revenue_signals if r.segment == "Consolidated"), None)
    check(
        "consolidated_revenue_trend",
        ground_truth["expected_consolidated_revenue_trend"],
        consolidated.trend if consolidated else None,
    )

    leverage = next(
        (c for c in extraction.debt_covenants if c.covenant_type == "leverage ratio"),
        None,
    )
    check(
        "leverage_ratio_status",
        ground_truth["expected_leverage_ratio_status"],
        leverage.current_status if leverage else None,
    )

    passed_count = sum(1 for c in checks if c.passed)
    return EvaluationResult(
        filing=filing_name,
        checks=checks,
        passed_count=passed_count,
        total_count=len(checks),
        accuracy=passed_count / len(checks) if checks else 0.0,
    )


def evaluate_all(
    extractions_by_filing: Dict[str, ExtractionResult], labels_path: str
) -> List[EvaluationResult]:
    """Evaluate multiple filings' extractions against ground truth in one pass."""
    ground_truth = load_ground_truth(labels_path)
    results = []
    for filing_name, extraction in extractions_by_filing.items():
        if filing_name not in ground_truth:
            continue
        results.append(evaluate_extraction(extraction, filing_name, ground_truth[filing_name]))
    return results


def summarize(results: List[EvaluationResult]) -> str:
    lines = ["Evaluation Summary", "=" * 50]
    total_passed = sum(r.passed_count for r in results)
    total_checks = sum(r.total_count for r in results)
    for r in results:
        lines.append(f"\n{r.filing}: {r.passed_count}/{r.total_count} checks passed ({r.accuracy:.0%})")
        for c in r.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{status}] {c.check_name}: expected={c.expected} actual={c.actual}")
    overall = total_passed / total_checks if total_checks else 0.0
    lines.append(f"\nOverall: {total_passed}/{total_checks} ({overall:.0%})")
    return "\n".join(lines)
