"""
CLI demo: runs the evaluation harness, scoring the Extraction Agent's
mock output against hand-labeled ground truth for both sample filings.

Usage:
    python run_evaluation.py
"""

import os
from src.evaluation import evaluate_all, summarize
from src.schemas import ExtractionResult
from tests.fixtures import MOCK_EXTRACTION, MOCK_EXTRACTION_FY2024

LABELS_PATH = os.path.join("data", "ground_truth_labels.json")


def main():
    extractions_by_filing = {
        "nimbus_dynamics_10k_fy2025.txt": ExtractionResult.model_validate(
            MOCK_EXTRACTION
        ),
        "nimbus_dynamics_10k_fy2024.txt": ExtractionResult.model_validate(
            MOCK_EXTRACTION_FY2024
        ),
    }
    results = evaluate_all(extractions_by_filing, LABELS_PATH)
    print(summarize(results))


if __name__ == "__main__":
    main()
