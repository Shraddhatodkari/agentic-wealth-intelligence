from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..schemas import ComparisonReport, EvaluationResult, PortfolioReport, SynthesisReport


class AnalyzeRequest(BaseModel):
    company: str = Field(..., examples=["AAPL"])
    fiscal_year: str = Field(..., examples=["FY2025"])
    filing_path: Optional[str] = Field(
        default="data/sample_filings/nimbus_dynamics_10k_fy2025.txt",
        description="Server-side path to the filing text. In a live deployment this "
        "would accept an uploaded file or an EDGAR accession number instead.",
    )


class AnalyzeResponse(BaseModel):
    report: SynthesisReport
    indexed_chunk_count: int
    stage_timings_ms: dict[str, float]
    cache_hit: bool = False
    approval_status: str


class PendingReviewSummary(BaseModel):
    id: str
    company: str
    fiscal_year: Optional[str]
    confidence_score: Optional[float]
    recommendation_preview: str
    created_at: str


class ReviewRequest(BaseModel):
    reviewer: str = Field(..., examples=["jane.analyst"])
    decision: str = Field(..., examples=["approve"], description="'approve' or 'reject'")
    edited_recommendation: Optional[str] = Field(
        None, description="Reviewer's corrected recommendation, if changed"
    )
    notes: Optional[str] = Field(None, description="Reviewer's rationale")


class ReviewResponse(BaseModel):
    id: str
    approval_status: str
    reviewer: str
    edited_recommendation: Optional[str]
    reviewed_at: str


class CompareRequest(BaseModel):
    company: str = Field(..., examples=["AAPL"])
    prior_fiscal_year: str = Field(..., examples=["FY2024"])
    current_fiscal_year: str = Field(..., examples=["FY2025"])
    prior_filing_path: str = Field(default="data/sample_filings/nimbus_dynamics_10k_fy2024.txt")
    current_filing_path: str = Field(default="data/sample_filings/nimbus_dynamics_10k_fy2025.txt")


class CompareResponse(BaseModel):
    report: ComparisonReport


class EvaluateResponse(BaseModel):
    results: list[EvaluationResult]
    overall_accuracy: float


class QuestionRequest(BaseModel):
    question: str = Field(..., examples=["What is the leverage ratio covenant status?"])


class QuestionResponse(BaseModel):
    answer: str
    source_chunks: list[str]


class HealthResponse(BaseModel):
    status: str
    llm_mode: str


class AsyncTaskSubmitResponse(BaseModel):
    task_id: str
    status: str


class AsyncTaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None


class ReportSummary(BaseModel):
    id: str
    report_type: str
    company: str
    fiscal_year: Optional[str]
    created_at: str


class ReportDetail(BaseModel):
    id: str
    report_type: str
    company: str
    fiscal_year: Optional[str]
    created_at: str
    payload: dict


class PortfolioCompanyInput(BaseModel):
    company: str = Field(..., examples=["AAPL"])
    fiscal_year: str = Field(..., examples=["FY2025"])
    filing_path: str = Field(..., examples=["data/sample_filings/nimbus_dynamics_10k_fy2025.txt"])


class PortfolioAnalyzeRequest(BaseModel):
    companies: list[PortfolioCompanyInput] = Field(..., min_length=1)


class PortfolioAnalyzeResponse(BaseModel):
    report: PortfolioReport

