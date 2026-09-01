import os

from src.ingestion_agent import IngestionAgent

SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "sample_filings",
    "nimbus_dynamics_10k_fy2025.txt",
)


def test_load_local_filing_reads_text():
    agent = IngestionAgent()
    text = agent.load_local_filing(SAMPLE_PATH)
    assert "Nimbus Dynamics" in text
    assert len(text) > 500


def test_chunking_produces_multiple_chunks_with_ids():
    agent = IngestionAgent(chunk_size=300, chunk_overlap=50)
    text = agent.load_local_filing(SAMPLE_PATH)
    chunks = agent.chunk(text, section="10-K")
    assert len(chunks) > 1
    assert all(c.chunk_id.startswith("10-K-") for c in chunks)
    assert all(len(c.text) > 0 for c in chunks)


def test_fetch_from_ticker_delegates_to_edgar_client(monkeypatch):
    """fetch_from_ticker should call the real EDGAR client - verified here
    via monkeypatching rather than hitting the live network. Short text with
    no Item headings passes through unchanged (falls back to a bounded
    truncation, which is a no-op for text this short)."""

    def fake_fetch_latest_10k(ticker):
        assert ticker == "AAPL"
        return "mocked real filing text"

    monkeypatch.setattr("src.ingestion_agent.edgar_client.fetch_latest_10k", fake_fetch_latest_10k)
    agent = IngestionAgent()
    result = agent.fetch_from_ticker("AAPL")
    assert result == "mocked real filing text"


def test_fetch_from_ticker_trims_large_filing_to_relevant_sections(monkeypatch):
    """A large real filing (with SEC-standard Item headings) should come back
    much smaller than the raw fetch - this is the fix for real tickers
    blowing past a local LLM's context window."""
    large_filing = (
        "Item 1. Business\n" + ("irrelevant business text " * 500) + "\n\n"
        "Item 7. Management Discussion and Analysis\n" + ("relevant MD&A text " * 500)
    )

    monkeypatch.setattr("src.ingestion_agent.edgar_client.fetch_latest_10k", lambda ticker: large_filing)
    agent = IngestionAgent()
    result = agent.fetch_from_ticker("AAPL")

    assert len(result) < len(large_filing) / 2
    assert "relevant MD&A text" in result
    assert "irrelevant business text" not in result


def test_fetch_from_ticker_can_skip_trimming(monkeypatch):
    large_filing = "Item 7. MD&A\n" + ("some text " * 500)
    monkeypatch.setattr("src.ingestion_agent.edgar_client.fetch_latest_10k", lambda ticker: large_filing)
    agent = IngestionAgent()
    result = agent.fetch_from_ticker("AAPL", trim_to_relevant_sections=False)
    assert result == large_filing
