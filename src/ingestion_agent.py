"""
Ingestion Agent
---------------
Loads a 10-K filing (plain text/HTML-stripped) from disk and splits it
into overlapping chunks suitable for embedding.

`fetch_from_ticker` hits the real SEC EDGAR API (see `edgar_client.py`)
to pull an actual company's most recent 10-K - not a stub. It isn't
called in the test suite or the bundled demos, since that would require
real outbound network access and a configured SEC_USER_AGENT; instead
`tests/test_edgar_client.py` mocks the HTTP layer to verify the parsing
logic, the same mock-by-default pattern used for LLM calls throughout
this project. Run it for real once you have network access:

    export SEC_USER_AGENT="Jane Doe jane@example.com"
    python -c "from src.ingestion_agent import IngestionAgent; \\
        print(IngestionAgent().fetch_from_ticker('AAPL')[:500])"
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from . import edgar_client
from .filing_sections import extract_relevant_sections


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str


class IngestionAgent:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 120):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " "],
        )

    def load_local_filing(self, path: str) -> str:
        return Path(path).read_text(encoding="utf-8")

    def fetch_from_ticker(self, ticker: str, trim_to_relevant_sections: bool = True) -> str:
        """
        Fetch a real company's latest 10-K text from SEC EDGAR by ticker
        symbol (e.g. "AAPL", "MSFT", "NVDA"). Requires SEC_USER_AGENT to
        be set and real outbound network access.

        Real 10-Ks run 50-150+ pages - by default this trims the result to
        just the Items this system's schema actually extracts from (Risk
        Factors, MD&A, Market Risk, Legal Proceedings), via
        `filing_sections.extract_relevant_sections`. Set
        `trim_to_relevant_sections=False` to get the full raw filing text
        instead (useful for debugging, but likely to exceed a local LLM's
        context window).
        """
        full_text = edgar_client.fetch_latest_10k(ticker)
        if trim_to_relevant_sections:
            return extract_relevant_sections(full_text)
        return full_text

    def chunk(self, raw_text: str, section: str = "general") -> List[Chunk]:
        pieces = self.splitter.split_text(raw_text)
        return [
            Chunk(chunk_id=f"{section}-{i:03d}", text=piece, section=section)
            for i, piece in enumerate(pieces)
        ]
