from src.output_validation import validate_extraction_result, validate_synthesis_report
from src.schemas import DebtCovenant, ExtractionResult, RevenueSignal, RiskFlag, SynthesisReport


def _valid_report(**overrides):
    defaults = dict(
        company="Apple Inc.",
        fiscal_year="FY2025",
        executive_summary="Revenue grew 6% YoY driven by Services.",
        top_risks=[
            RiskFlag(category="legal", severity="medium", headline="Data privacy", detail="GDPR exposure.")
        ],
        recommendation="Continue monitoring.",
        confidence_score=0.85,
    )
    defaults.update(overrides)
    return SynthesisReport(**defaults)


def test_valid_report_has_no_errors():
    # A ticker vs legal-name difference ("AAPL" vs "Apple Inc.") is an
    # expected warning, not an error - check has_errors, not is_clean.
    result = validate_synthesis_report(_valid_report(), expected_company="AAPL")
    assert not result.has_errors


def test_placeholder_company_name_flagged_as_error():
    report = _valid_report(company="Company Name")
    result = validate_synthesis_report(report, expected_company="AAPL")
    assert result.has_errors
    assert any("company" in i.field for i in result.issues)


def test_placeholder_variants_all_caught():
    for placeholder in ["Company Name", "[Company]", "Example Corp", "Unknown Company", "The Company"]:
        report = _valid_report(company=placeholder)
        result = validate_synthesis_report(report, expected_company="AAPL")
        assert result.has_errors, f"{placeholder!r} should have been flagged"


def test_ticker_vs_legal_name_mismatch_is_warning_not_error():
    # "Apple Inc." vs requested "AAPL" is a legitimate mismatch (ticker vs
    # legal name), not a hallucination - should warn, not force a retry.
    report = _valid_report(company="Apple Inc.")
    result = validate_synthesis_report(report, expected_company="AAPL")
    assert not result.has_errors


def test_empty_risk_fields_flagged():
    report = _valid_report(top_risks=[RiskFlag(category="legal", severity="high", headline="", detail="")])
    result = validate_synthesis_report(report, expected_company="AAPL")
    assert result.has_errors


def test_empty_executive_summary_flagged():
    report = _valid_report(executive_summary="   ")
    result = validate_synthesis_report(report, expected_company="AAPL")
    assert result.has_errors


def _valid_extraction(**overrides):
    defaults = dict(company="Apple Inc.", fiscal_year="FY2025")
    defaults.update(overrides)
    return ExtractionResult(**defaults)


def test_valid_extraction_has_no_issues():
    extraction = _valid_extraction(
        company="AAPL",
        debt_covenants=[
            DebtCovenant(
                covenant_type="leverage ratio", threshold="3.5x max", current_status="compliant", note="ok"
            )
        ],
    )
    result = validate_extraction_result(extraction, expected_company="AAPL")
    assert result.is_clean


def test_leverage_ratio_percent_unit_flagged():
    """Reproduces the exact bug observed in practice: a local model
    returning '8.5%' for a leverage ratio threshold, which should be
    expressed as a multiple like '8.5x'."""
    extraction = _valid_extraction(
        debt_covenants=[
            DebtCovenant(covenant_type="leverage ratio", threshold="8.5%", current_status="at risk", note="x")
        ]
    )
    result = validate_extraction_result(extraction, expected_company="AAPL")
    assert not result.is_clean
    assert any("%" in i.problem for i in result.issues)


def test_interest_coverage_percent_not_flagged():
    # Only leverage-ratio-type covenants get the unit check - other
    # covenant types legitimately may use different conventions.
    extraction = _valid_extraction(
        debt_covenants=[
            DebtCovenant(
                covenant_type="interest coverage ratio",
                threshold="2.5x min",
                current_status="compliant",
                note="ok",
            )
        ]
    )
    result = validate_extraction_result(extraction, expected_company="AAPL")
    assert result.is_clean


def test_placeholder_extraction_company_flagged():
    extraction = _valid_extraction(company="Placeholder Corp")
    result = validate_extraction_result(extraction, expected_company="AAPL")
    assert result.has_errors


def test_empty_revenue_signal_fields_flagged():
    extraction = _valid_extraction(
        revenue_signals=[RevenueSignal(period="FY2025", segment="", trend="growth", note="")]
    )
    result = validate_extraction_result(extraction, expected_company="AAPL")
    assert result.has_errors
