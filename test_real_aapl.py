from pathlib import Path

from src.ingestion_agent import IngestionAgent
from src.orchestrator import WealthIntelligencePipeline

ticker = "AAPL"
company = "Apple Inc."
fiscal_year = "FY2025"

print("=" * 70)
print("REAL SEC ? REAL LLM END-TO-END TEST")
print("=" * 70)

ingestion = IngestionAgent()

print("\n[1/4] Fetching latest AAPL 10-K from SEC EDGAR...")
raw_text = ingestion.fetch_from_ticker(ticker)

print(f"Retrieved characters: {len(raw_text):,}")

path = Path("data") / "aapl_real_sec_10k.txt"
path.write_text(raw_text, encoding="utf-8")

print(f"Saved filing: {path}")

print("\n[2/4] Running LangGraph pipeline...")
pipeline = WealthIntelligencePipeline()

result = pipeline.run(
    filing_path=str(path),
    company=company,
    fiscal_year=fiscal_year,
)

print(f"RAG chunks indexed: {result.get('indexed_chunk_count')}")

print("\n[3/4] Extraction summary...")
extraction = result["extraction"]

print(f"Revenue signals: {len(extraction.revenue_signals)}")
print(f"Debt covenants: {len(extraction.debt_covenants)}")
print(f"Legal risks: {len(extraction.legal_risks)}")

print("\n[4/4] Executive synthesis...")
report = result["report"]

print("\n" + "=" * 70)
print(f"EXECUTIVE RISK MEMO - {company}")
print("=" * 70)

print(report.executive_summary)

print("\nTop Risks:")
for risk in report.top_risks:
    print(f"  [{risk.severity.value.upper()}] {risk.category}: {risk.headline}")
    print(f"      {risk.detail}")

print("\nRecommendation:")
print(report.recommendation)

print("\nStage timings:")
for stage, timing in result.get("stage_timings_ms", {}).items():
    print(f"  {stage}: {timing} ms")

print("\nREAL AAPL END-TO-END TEST COMPLETE")