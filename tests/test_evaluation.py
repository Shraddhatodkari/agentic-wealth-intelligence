import os

from src.evaluation import (
    evaluate_all,
    evaluate_extraction,
    load_ground_truth,
    summarize,
)
from src.schemas import ExtractionResult
from tests.fixtures import MOCK_EXTRACTION, MOCK_EXTRACTION_FY2024

LABELS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ground_truth_labels.json")


def test_load_ground_truth_returns_dict():
    labels = load_ground_truth(LABELS_PATH)
    assert "nimbus_dynamics_10k_fy2025.txt" in labels
    assert "nimbus_dynamics_10k_fy2024.txt" in labels


def test_evaluate_extraction_perfect_match_scores_100pct():
    labels = load_ground_truth(LABELS_PATH)
    extraction = ExtractionResult.model_validate(MOCK_EXTRACTION)
    result = evaluate_extraction(
        extraction,
        "nimbus_dynamics_10k_fy2025.txt",
        labels["nimbus_dynamics_10k_fy2025.txt"],
    )
    assert result.accuracy == 1.0
    assert result.passed_count == result.total_count


def test_evaluate_extraction_catches_wrong_count():
    labels = load_ground_truth(LABELS_PATH)
    extraction = ExtractionResult.model_validate(MOCK_EXTRACTION)
    # Corrupt the extraction to simulate a bad agent run
    extraction.legal_risks = extraction.legal_risks[:1]  # drop one legal risk
    result = evaluate_extraction(
        extraction,
        "nimbus_dynamics_10k_fy2025.txt",
        labels["nimbus_dynamics_10k_fy2025.txt"],
    )
    assert result.accuracy < 1.0
    failed = [c for c in result.checks if not c.passed]
    assert any(c.check_name == "legal_risk_count" for c in failed)


def test_evaluate_all_across_multiple_filings():
    extractions = {
        "nimbus_dynamics_10k_fy2025.txt": ExtractionResult.model_validate(MOCK_EXTRACTION),
        "nimbus_dynamics_10k_fy2024.txt": ExtractionResult.model_validate(MOCK_EXTRACTION_FY2024),
    }
    results = evaluate_all(extractions, LABELS_PATH)
    assert len(results) == 2
    assert all(r.accuracy == 1.0 for r in results)


def test_summarize_produces_readable_report():
    labels = load_ground_truth(LABELS_PATH)
    extraction = ExtractionResult.model_validate(MOCK_EXTRACTION)
    result = evaluate_extraction(
        extraction,
        "nimbus_dynamics_10k_fy2025.txt",
        labels["nimbus_dynamics_10k_fy2025.txt"],
    )
    report = summarize([result])
    assert "Overall" in report
    assert "100%" in report
