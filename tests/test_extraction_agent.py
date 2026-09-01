import os

from src.extraction_agent import ExtractionAgent
from src.ingestion_agent import IngestionAgent
from src.llm_client import LLMClient
from src.schemas import ExtractionResult
from tests.fixtures import MOCK_EXTRACTION

SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data",
    "sample_filings",
    "nimbus_dynamics_10k_fy2025.txt",
)


def _chunks():
    ing = IngestionAgent()
    text = ing.load_local_filing(SAMPLE_PATH)
    return ing.chunk(text)


def test_extraction_returns_valid_schema():
    llm = LLMClient(mode="mock")
    agent = ExtractionAgent(llm)
    result = agent.extract(
        chunks=_chunks(),
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        mock_response=MOCK_EXTRACTION,
    )
    assert isinstance(result, ExtractionResult)
    assert result.company == "Nimbus Dynamics, Inc."
    assert len(result.revenue_signals) >= 3
    assert len(result.debt_covenants) >= 1
    assert len(result.legal_risks) >= 1


def test_extraction_flags_high_severity_legal_risk():
    llm = LLMClient(mode="mock")
    agent = ExtractionAgent(llm)
    result = agent.extract(
        chunks=_chunks(),
        company="Nimbus Dynamics, Inc.",
        fiscal_year="FY2025",
        mock_response=MOCK_EXTRACTION,
    )
    severities = [r.severity for r in result.legal_risks]
    assert "high" in severities


def test_extraction_defaults_to_empty_when_no_mock_given():
    llm = LLMClient(mode="mock")
    agent = ExtractionAgent(llm)
    result = agent.extract(chunks=_chunks(), company="Empty Co", fiscal_year="FY2025")
    assert isinstance(result.revenue_signals, list)
    assert isinstance(result.debt_covenants, list)
    assert isinstance(result.legal_risks, list)


def test_extraction_overrides_llm_hallucinated_company_and_year():
    """Reproduces the exact bug observed in practice: a live model
    returning a placeholder company name / wrong fiscal year despite the
    prompt. The agent must override these with the known-correct values
    from the caller, not trust the LLM's echo."""
    llm = LLMClient(mode="mock")
    agent = ExtractionAgent(llm)
    hallucinated_mock = {
        "company": "Company Name",  # exactly the observed hallucination
        "fiscal_year": "FY2026",  # wrong year, exactly as observed
        "revenue_signals": [],
        "debt_covenants": [],
        "legal_risks": [],
    }
    result = agent.extract(
        chunks=_chunks(), company="AAPL", fiscal_year="FY2025", mock_response=hallucinated_mock
    )
    assert result.company == "AAPL"
    assert result.fiscal_year == "FY2025"
