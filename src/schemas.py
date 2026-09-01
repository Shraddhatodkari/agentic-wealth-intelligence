"""
Structured data contracts shared across all agents.

All agent outputs are validated through Pydantic models. The schemas are
intentionally strict so LLM-generated data cannot silently introduce
unsupported categories, statuses, or malformed financial facts.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RevenueTrend(str, Enum):
    GROWTH = "growth"
    DECLINE = "decline"
    FLAT = "flat"


class DebtStatus(str, Enum):
    COMPLIANT = "compliant"
    AT_RISK = "at risk"
    BREACHED = "breached"


class RiskCategory(str, Enum):
    REVENUE = "revenue"
    DEBT = "debt"
    LEGAL = "legal"
    MARKET = "market"


class ApprovalStatus(str, Enum):
    AUTO_APPROVED = "auto_approved"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class TrendDirection(str, Enum):
    IMPROVING = "improving"
    DETERIORATING = "deteriorating"
    STABLE = "stable"


class RevenueSignal(BaseModel):
    """
    Explicit revenue or sales movement extracted from a filing.
    """

    model_config = ConfigDict(extra="forbid")

    period: str = Field(
        ...,
        min_length=1,
        description="Fiscal period, e.g. 'FY2025'",
    )

    segment: str = Field(
        ...,
        description="Business segment or 'Total company'",
    )

    trend: RevenueTrend = Field(
        ...,
        description="Direction of the explicitly stated revenue change",
    )

    yoy_change_pct: Optional[float] = Field(
        None,
        description=(
            "Explicit year-over-year percentage change. Must preserve the sign stated in the filing."
        ),
    )

    note: str = Field(
        ...,
        description="One-sentence explanation grounded in filing evidence",
    )


class DebtCovenant(BaseModel):
    """
    Explicit debt covenant measurement extracted from the filing.
    """

    model_config = ConfigDict(extra="forbid")

    covenant_type: str = Field(
        ...,
        min_length=1,
        description="e.g. 'leverage ratio' or 'interest coverage'",
    )

    threshold: str = Field(
        ...,
        min_length=1,
        description="The explicitly stated covenant threshold or limit",
    )

    current_status: DebtStatus = Field(
        ...,
        description="Covenant compliance status",
    )

    note: str = Field(
        ...,
        description="Evidence-based explanation including the measured values",
    )


class LegalRisk(BaseModel):
    """
    Explicit legal or regulatory matter disclosed by the filing.
    """

    model_config = ConfigDict(extra="forbid")

    matter: str = Field(
        ...,
        min_length=1,
        description="Short name of the legal or regulatory matter",
    )

    severity: RiskSeverity = Field(
        ...,
        description="Severity supported by the filing evidence",
    )

    potential_exposure: Optional[str] = Field(
        None,
        description=(
            "Explicitly disclosed financial exposure, loss range, "
            "settlement, or penalty. Null when not disclosed."
        ),
    )

    note: str = Field(
        ...,
        description="Evidence-based explanation of the legal matter",
    )


class ExtractionResult(BaseModel):
    """
    Output of the Extraction Agent for a single filing.
    """

    model_config = ConfigDict(extra="forbid")

    company: str = Field(
        ...,
        min_length=1,
    )

    fiscal_year: str = Field(
        ...,
        min_length=1,
    )

    revenue_signals: List[RevenueSignal] = Field(
        default_factory=list,
    )

    debt_covenants: List[DebtCovenant] = Field(
        default_factory=list,
    )

    legal_risks: List[LegalRisk] = Field(
        default_factory=list,
    )


class RiskFlag(BaseModel):
    """
    Risk identified by the Synthesis Agent.
    """

    model_config = ConfigDict(extra="forbid")

    category: RiskCategory = Field(
        ...,
        description=(
            "Risk category. Use market for FX, interest-rate, commodity, "
            "or operational risks that are not legal proceedings or debt covenants."
        ),
    )

    severity: RiskSeverity

    headline: str = Field(
        ...,
    )

    detail: str = Field(
        ...,
    )


class SynthesisReport(BaseModel):
    """
    Final executive-level output of the Synthesis Agent.
    """

    model_config = ConfigDict(extra="forbid")

    company: str = Field(
        ...,
        min_length=1,
    )

    fiscal_year: str = Field(
        ...,
        min_length=1,
    )

    executive_summary: str = Field(
        ...,
    )

    top_risks: List[RiskFlag] = Field(
        default_factory=list,
    )

    recommendation: str = Field(
        ...,
        min_length=1,
        description=(
            "One-paragraph recommendation for M&A or portfolio "
            "decision-making, grounded in extracted evidence."
        ),
    )

    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Model self-assessed confidence from 0 to 1. Used by the human-in-the-loop approval workflow."
        ),
    )


class ReviewSubmission(BaseModel):
    """
    Human reviewer's decision on a report routed for review.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(
        ...,
        min_length=1,
        description="Name or ID of the human reviewer",
    )

    decision: ReviewDecision

    edited_recommendation: Optional[str] = Field(
        None,
        description="Reviewer's corrected recommendation, if changed",
    )

    notes: Optional[str] = Field(
        None,
        description="Reviewer's rationale for the decision",
    )


class RAGAnswer(BaseModel):
    """
    Evidence-grounded RAG response.
    """

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=1,
    )

    answer: str = Field(
        ...,
        min_length=1,
    )

    source_chunks: List[str] = Field(
        default_factory=list,
        description="IDs of retrieved chunks used to answer the question",
    )


class TrendShift(BaseModel):
    """
    A single metric that changed materially between two filing periods.
    """

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(
        ...,
        min_length=1,
        description="e.g. 'Cloud Infrastructure revenue' or 'leverage ratio'",
    )

    prior_period: str = Field(
        ...,
        min_length=1,
    )

    current_period: str = Field(
        ...,
        min_length=1,
    )

    prior_value: str = Field(
        ...,
        min_length=1,
        description="Explicit prior-period value",
    )

    current_value: str = Field(
        ...,
        min_length=1,
        description="Explicit current-period value",
    )

    direction: TrendDirection = Field(
        ...,
        description="Direction of the change",
    )

    materiality: RiskSeverity = Field(
        ...,
        description="Materiality of the change to the overall risk picture",
    )

    note: str = Field(
        ...,
    )


class ComparisonReport(BaseModel):
    """
    Output of the Comparison Agent.

    Compares two independent filing extractions and produces an
    evidence-grounded year-over-year trajectory.
    """

    model_config = ConfigDict(extra="forbid")

    company: str = Field(
        ...,
        min_length=1,
    )

    prior_fiscal_year: str = Field(
        ...,
        min_length=1,
    )

    current_fiscal_year: str = Field(
        ...,
        min_length=1,
    )

    trend_shifts: List[TrendShift] = Field(
        default_factory=list,
    )

    overall_trajectory: TrendDirection = Field(
        ...,
        description="Overall trajectory across the comparison",
    )

    narrative: str = Field(
        ...,
        min_length=1,
        description="Executive-level narrative explaining what changed and why",
    )


class CheckResult(BaseModel):
    """
    A single pass/fail check against ground truth.
    """

    model_config = ConfigDict(extra="forbid")

    check_name: str = Field(
        ...,
        min_length=1,
    )

    passed: bool

    expected: str

    actual: str


class EvaluationResult(BaseModel):
    """
    Evaluation result against known ground-truth labels.
    """

    model_config = ConfigDict(extra="forbid")

    filing: str = Field(
        ...,
        min_length=1,
    )

    checks: List[CheckResult] = Field(
        default_factory=list,
    )

    passed_count: int = Field(
        ...,
        ge=0,
    )

    total_count: int = Field(
        ...,
        ge=0,
    )

    accuracy: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="passed_count / total_count",
    )


class CompanyRank(BaseModel):
    """
    One company's position in a portfolio ranking dimension.
    """

    model_config = ConfigDict(extra="forbid")

    company: str = Field(
        ...,
        min_length=1,
    )

    rank: int = Field(
        ...,
        ge=1,
    )

    metric_value: float = Field(
        ...,
        description="Underlying deterministic ranking value",
    )

    metric_label: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of metric_value",
    )

    data_available: bool = Field(
        True,
        description=(
            "False when extraction found no usable data for this metric. "
            "Prevents missing data from being confused with zero."
        ),
    )


class PortfolioReport(BaseModel):
    """
    Cross-company portfolio intelligence.

    Rankings are computed deterministically from ExtractionResult.
    Only the narrative is generated by an LLM.
    """

    model_config = ConfigDict(extra="forbid")

    companies: List[str] = Field(
        default_factory=list,
    )

    growth_ranking: List[CompanyRank] = Field(
        default_factory=list,
        description="Ranked by average revenue YoY change, highest first",
    )

    risk_ranking: List[CompanyRank] = Field(
        default_factory=list,
        description="Ranked by legal/regulatory risk severity",
    )

    debt_ranking: List[CompanyRank] = Field(
        default_factory=list,
        description="Ranked by number of non-compliant debt covenants",
    )

    sector_narrative: str = Field(
        ...,
        min_length=1,
        description="Executive-level cross-company synthesis",
    )


class SectorNarrative(BaseModel):
    """
    LLM-generated narrative component of portfolio intelligence.
    """

    model_config = ConfigDict(extra="forbid")

    sector_narrative: str = Field(
        ...,
        min_length=1,
    )


class QualityReport(BaseModel):
    """
    Structural quality assessment for a LIVE extraction/synthesis run.

    This is not an accuracy score. Accuracy requires ground truth.
    """

    model_config = ConfigDict(extra="forbid")

    company: str = Field(
        ...,
        min_length=1,
    )

    fiscal_year: str = Field(
        ...,
        min_length=1,
    )

    completeness_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of expected fields that are non-empty",
    )

    error_count: int = Field(
        ...,
        ge=0,
    )

    warning_count: int = Field(
        ...,
        ge=0,
    )

    issues: List[str] = Field(
        default_factory=list,
    )
