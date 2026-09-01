"""
Live portfolio intelligence CLI.

Usage:
    python run_portfolio_analysis.py
    python run_portfolio_analysis.py AMZN AAPL MSFT GOOGL META

Uses real SEC EDGAR data and Ollama.
Mock data is NOT used.
"""

import sys

from src.edgar_client import fetch_latest_10k
from src.extraction_agent import ExtractionAgent
from src.ingestion_agent import IngestionAgent
from src.llm_client import LLMClient
from src.portfolio_agent import PortfolioAgent


DEFAULT_TICKERS = ["AAPL", "MSFT", "AMZN", "NVDA", "TSLA"]
FISCAL_YEAR = "FY2025"


def main():
    tickers = [
        x.strip().upper()
        for x in (sys.argv[1:] or DEFAULT_TICKERS)
        if x.strip()
    ]

    if not tickers:
        raise SystemExit("Provide at least one SEC ticker.")

    print("=" * 70)
    print(f"LIVE PORTFOLIO INTELLIGENCE — {len(tickers)} companies")
    print("=" * 70)
    print(f"Mode: OLLAMA")
    print(f"Fiscal year: {FISCAL_YEAR}")
    print(f"Tickers: {', '.join(tickers)}")
    print()

    llm = LLMClient(mode="ollama")
    ingestion = IngestionAgent()
    extraction_agent = ExtractionAgent(llm)
    portfolio_agent = PortfolioAgent(llm)

    extractions = []

    for index, ticker in enumerate(tickers, start=1):
        print("-" * 70)
        print(f"[{index}/{len(tickers)}] Fetching {ticker} from SEC EDGAR...")

        try:
            filing_text = fetch_latest_10k(ticker)

            if not filing_text:
                print(f"SKIPPED {ticker}: SEC returned no filing content.")
                continue

            print(f"[{index}/{len(tickers)}] Chunking {ticker} filing...")
            chunks = ingestion.chunk(
                filing_text,
                section=ticker,
            )

            print(
                f"[{index}/{len(tickers)}] Running Ollama extraction for "
                f"{ticker} ({len(chunks)} chunks)..."
            )

            extraction = extraction_agent.extract(
                chunks,
                ticker,
                FISCAL_YEAR,
            )

            extractions.append(extraction)

            print(
                f"[{index}/{len(tickers)}] {ticker} extraction complete: "
                f"{len(extraction.revenue_signals)} revenue signals, "
                f"{len(extraction.debt_covenants)} debt covenants, "
                f"{len(extraction.legal_risks)} legal risks"
            )

        except Exception as exc:
            print(f"SKIPPED {ticker}: {type(exc).__name__}: {exc}")

    if not extractions:
        raise SystemExit("No companies were successfully processed.")

    print()
    print("=" * 70)
    print(
        f"GENERATING LIVE PORTFOLIO INTELLIGENCE — "
        f"{len(extractions)} companies"
    )
    print("=" * 70)

    report = portfolio_agent.analyze_portfolio(extractions)

    print()
    print("=" * 70)
    print(f"PORTFOLIO INTELLIGENCE — {len(report.companies)} companies")
    print("=" * 70)

    print("\nCompanies processed:")
    for company in report.companies:
        print(f"  - {company}")

    print("\nTop Growth:")
    for r in report.growth_ranking:
        print(
            f"  {r.rank}. {r.company}: "
            f"{r.metric_value:+.1f}% ({r.metric_label})"
        )

    print("\nHighest Legal/Regulatory Risk:")
    for r in report.risk_ranking:
        print(
            f"  {r.rank}. {r.company}: "
            f"{r.metric_value:.1f} ({r.metric_label})"
        )

    print("\nHighest Debt Exposure:")
    for r in report.debt_ranking:
        print(
            f"  {r.rank}. {r.company}: "
            f"{r.metric_value:.1f} ({r.metric_label})"
        )

    print(f"\nSector Narrative:\n{report.sector_narrative}")


if __name__ == "__main__":
    main()
