"""
CLI demo: runs the full pipeline against the bundled sample filing in
mock mode (no API key required) and prints the executive risk memo.

Usage:
    python run_demo.py                  # mock mode, no key needed
    LLM_MODE=live GEMINI_API_KEY=... python run_demo.py   # real Gemini calls
"""

import os
import json
from src.orchestrator import WealthIntelligencePipeline
from src.llm_client import LLMClient
from tests.fixtures import MOCK_EXTRACTION, MOCK_SYNTHESIS

SAMPLE_PATH = "data/sample_filings/nimbus_dynamics_10k_fy2025.txt"


def main():
    mode = os.getenv("LLM_MODE", "mock")
    llm = LLMClient(mode=mode)
    pipeline = WealthIntelligencePipeline(llm=llm)

    kwargs = {}
    if mode == "mock":
        # In mock mode, feed realistic fixtures so the demo output is
        # coherent rather than an empty placeholder report.
        kwargs = {"mock_extraction": MOCK_EXTRACTION, "mock_synthesis": MOCK_SYNTHESIS}

    result = pipeline.run(
        filing_path=SAMPLE_PATH,
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        **kwargs,
    )

    print(f"\nIndexed {result['indexed_chunk_count']} chunks into the RAG store.\n")

    report = result["report"]
    print("=" * 70)
    print(f"EXECUTIVE RISK MEMO — {report.company} ({report.fiscal_year})")
    print("=" * 70)
    print(f"\n{report.executive_summary}\n")
    print("Top Risks:")
    for r in report.top_risks:
        print(f"  [{r.severity.upper()}] ({r.category}) {r.headline}")
        print(f"      {r.detail}")
    print(f"\nRecommendation:\n{report.recommendation}\n")

    # Demonstrate ad-hoc RAG Q&A on the indexed filing
    rag = result["rag_agent"]
    question = "What is the leverage ratio covenant status?"
    answer = rag.answer(
        question,
        mock_response=(
            {
                "question": question,
                "answer": "Leverage ratio was 3.3x against a 3.5x covenant limit - compliant but with reduced headroom.",
                "source_chunks": [],
            }
            if mode == "mock"
            else None
        ),
    )
    print("-" * 70)
    print(f"Q: {answer.question}\nA: {answer.answer}")
    print(f"(sourced from chunks: {answer.source_chunks})")


if __name__ == "__main__":
    main()
