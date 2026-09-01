from src.report_export import report_to_docx_bytes, report_to_markdown, report_to_pdf_bytes
from tests.fixtures import MOCK_COMPARISON, MOCK_SYNTHESIS


def test_synthesis_markdown_contains_key_sections():
    md = report_to_markdown("synthesis", "Nimbus Dynamics, Inc.", "FY2025", MOCK_SYNTHESIS)
    assert "Executive Summary" in md
    assert "Top Risks" in md
    assert "Recommendation" in md
    assert "Nimbus Dynamics, Inc." in md


def test_comparison_markdown_contains_key_sections():
    md = report_to_markdown("comparison", "Nimbus Dynamics, Inc.", "FY2025", MOCK_COMPARISON)
    assert "Overall Trajectory" in md
    assert "Material Trend Shifts" in md
    assert "Narrative" in md


def test_synthesis_pdf_generates_valid_pdf_bytes():
    pdf_bytes = report_to_pdf_bytes("synthesis", "Nimbus Dynamics, Inc.", "FY2025", MOCK_SYNTHESIS)
    assert pdf_bytes[:5] == b"%PDF-"
    assert len(pdf_bytes) > 500


def test_comparison_pdf_generates_valid_pdf_bytes():
    pdf_bytes = report_to_pdf_bytes("comparison", "Nimbus Dynamics, Inc.", "FY2025", MOCK_COMPARISON)
    assert pdf_bytes[:5] == b"%PDF-"


def test_synthesis_docx_generates_valid_docx_bytes():
    docx_bytes = report_to_docx_bytes("synthesis", "Nimbus Dynamics, Inc.", "FY2025", MOCK_SYNTHESIS)
    assert docx_bytes[:4] == b"PK\x03\x04"  # DOCX is a zip archive
    assert len(docx_bytes) > 1000


def test_markdown_handles_missing_fiscal_year_gracefully():
    md = report_to_markdown(
        "evaluation", "all_sample_filings", None, {"overall_accuracy": 1.0, "results": []}
    )
    assert "Fiscal Year" not in md
    assert "Overall Accuracy" in md
