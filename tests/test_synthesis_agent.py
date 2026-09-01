from src.llm_client import LLMClient
from src.schemas import ExtractionResult, SynthesisReport
from src.synthesis_agent import SynthesisAgent
from tests.fixtures import MOCK_EXTRACTION, MOCK_SYNTHESIS


def test_synthesis_returns_valid_report():
    llm = LLMClient(mode="mock")
    agent = SynthesisAgent(llm)
    extraction = ExtractionResult.model_validate(MOCK_EXTRACTION)
    report = agent.synthesize(extraction, mock_response=MOCK_SYNTHESIS)
    assert isinstance(report, SynthesisReport)
    assert report.company == "Nimbus Dynamics, Inc."
    assert len(report.top_risks) == 3
    assert "FTC" in report.top_risks[0].headline


def test_synthesis_default_mock_when_no_risks():
    llm = LLMClient(mode="mock")
    agent = SynthesisAgent(llm)
    extraction = ExtractionResult(company="Clean Co", fiscal_year="FY2025")
    report = agent.synthesize(extraction)
    assert report.top_risks == []
    assert "Insufficient" in report.recommendation


def test_synthesis_overrides_llm_hallucinated_company_and_year():
    llm = LLMClient(mode="mock")
    agent = SynthesisAgent(llm)
    extraction = ExtractionResult(company="AAPL", fiscal_year="FY2025")
    hallucinated_mock = {
        "company": "Company Name",
        "fiscal_year": "FY2026",
        "executive_summary": "x",
        "top_risks": [],
        "recommendation": "x",
        "confidence_score": 0.7,
    }
    report = agent.synthesize(extraction, mock_response=hallucinated_mock)
    assert report.company == "AAPL"
    assert report.fiscal_year == "FY2025"
