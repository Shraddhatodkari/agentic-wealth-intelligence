from src.quality_report import build_quality_report
from src.schemas import DebtCovenant, ExtractionResult, RevenueSignal, SynthesisReport


def test_clean_extraction_has_full_completeness_and_no_issues():
    extraction = ExtractionResult(
        company="AAPL",
        fiscal_year="FY2025",
        revenue_signals=[
            RevenueSignal(period="FY2025", segment="Europe", trend="growth", note="Strong sales")
        ],
        debt_covenants=[
            DebtCovenant(
                covenant_type="leverage ratio", threshold="3.5x max", current_status="compliant", note="ok"
            )
        ],
    )
    report = build_quality_report(extraction, expected_company="AAPL")
    assert report.completeness_score == 1.0
    assert report.error_count == 0
    assert report.warning_count == 0


def test_placeholder_company_counts_as_error():
    extraction = ExtractionResult(company="Company Name", fiscal_year="FY2025")
    report = build_quality_report(extraction, expected_company="AAPL")
    assert report.error_count >= 1


def test_leverage_ratio_percent_counts_as_warning_not_error():
    extraction = ExtractionResult(
        company="AAPL",
        fiscal_year="FY2025",
        debt_covenants=[
            DebtCovenant(covenant_type="leverage ratio", threshold="8.5%", current_status="at risk", note="x")
        ],
    )
    report = build_quality_report(extraction, expected_company="AAPL")
    assert report.error_count == 0
    assert report.warning_count == 1


def test_empty_extraction_has_low_completeness():
    extraction = ExtractionResult(company="AAPL", fiscal_year="FY2025")
    report = build_quality_report(extraction, expected_company="AAPL")
    assert report.completeness_score < 1.0


def test_including_synthesis_report_adds_its_checks():
    extraction = ExtractionResult(
        company="AAPL",
        fiscal_year="FY2025",
        revenue_signals=[RevenueSignal(period="FY2025", segment="Europe", trend="growth", note="ok")],
    )
    bad_synthesis = SynthesisReport(
        company="AAPL",
        fiscal_year="FY2025",
        executive_summary="",
        top_risks=[],
        recommendation="x",
        confidence_score=0.5,
    )
    report = build_quality_report(extraction, expected_company="AAPL", synthesis_report=bad_synthesis)
    assert report.error_count >= 1
    assert any("executive_summary" in issue for issue in report.issues)


def test_quality_report_is_not_labeled_as_accuracy():
    # Sanity check on the schema itself - field names shouldn't imply
    # ground-truth-based accuracy, since none exists for live tickers.
    extraction = ExtractionResult(company="AAPL", fiscal_year="FY2025")
    report = build_quality_report(extraction, expected_company="AAPL")
    field_names = report.model_dump().keys()
    assert "accuracy" not in field_names
    assert "hallucination_rate" not in field_names
