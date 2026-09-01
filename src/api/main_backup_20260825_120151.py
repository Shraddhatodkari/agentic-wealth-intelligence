"""
REST API for Agentic Wealth Intelligence.

Wraps the LangGraph pipeline, comparison agent, and evaluation harness
as authenticated, rate-limited HTTP endpoints - the layer that turns
this from "a set of scripts" into a deployable service other systems
could call.

Run with: uvicorn src.api.main:app --reload
Docs at:  http://localhost:8000/docs
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .. import cache, db
from .. import metrics as metrics_module
from ..approval_workflow import determine_approval_status
from ..comparison_agent import ComparisonAgent
from ..config import settings
from ..extraction_agent import ExtractionAgent
from ..ingestion_agent import IngestionAgent
from ..llm_client import LLMClient
from ..logging_config import logger
from ..orchestrator import WealthIntelligencePipeline
from ..portfolio_agent import PortfolioAgent
from ..report_export import report_to_docx_bytes, report_to_markdown, report_to_pdf_bytes
from ..schemas import SynthesisReport
from ..tracing import configure_tracing
from .auth import require_api_key, require_role
from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    AsyncTaskStatusResponse,
    AsyncTaskSubmitResponse,
    CompareRequest,
    CompareResponse,
    EvaluateResponse,
    HealthResponse,
    PendingReviewSummary,
    PortfolioAnalyzeRequest,
    PortfolioAnalyzeResponse,
    QuestionRequest,
    QuestionResponse,
    ReportDetail,
    ReportSummary,
    ReviewRequest,
    ReviewResponse,
)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    configure_tracing()
    yield


app = FastAPI(
    title="Agentic Wealth Intelligence API",
    description="Multi-agent 10-K risk analysis: extraction, RAG Q&A, synthesis, "
    "year-over-year comparison, and accuracy evaluation.",
    version="1.0.0",
    lifespan=lifespan,
)
FastAPIInstrumentor.instrument_app(app)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# In-memory store of the last pipeline run per request, so /ask can reuse
# the indexed RAG store without re-ingesting. A production deployment would
# back this with a real session/job store (Redis) keyed by tenant + job id,
# not a process-local dict - the persisted report data (see /reports below)
# is what's durable; this cache is only for RAG-session convenience.
_last_run_cache: dict = {}


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    start = time.time()
    response = await call_next(request)
    duration_seconds = time.time() - start
    duration_ms = round(duration_seconds * 1000, 1)

    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        },
    )
    metrics_module.record_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration_seconds,
    )

    # Audit trail: skip /health and /metrics to avoid noise from liveness probes
    if request.url.path not in ("/health", "/metrics"):
        api_key = request.headers.get("x-api-key", "")
        session = db.get_session()
        try:
            db.save_audit_entry(
                session,
                request_id,
                request.url.path,
                api_key,
                response.status_code,
                duration_ms,
            )
        finally:
            session.close()

    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health", response_model=HealthResponse)
async def health():
    """Unauthenticated liveness check - what a load balancer would poll."""
    return HealthResponse(status="ok", llm_mode=settings.llm_mode)


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint. Unauthenticated, as is standard for /metrics
    (protect it at the network/ingress level in a real deployment, not with an API key).
    """
    body, content_type = metrics_module.metrics_response()
    return Response(content=body, media_type=content_type)


@app.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyze(request: Request, body: AnalyzeRequest, api_key: str = Depends(require_role("analyst"))):
    """Run the full single-filing pipeline: ingest -> extract -> index -> synthesize.
    Repeated calls with the same company/fiscal_year/filing_path within the cache TTL
    return the cached result instead of recomputing. Only the JSON-serializable report
    data is cached (compatible with both the in-memory and Redis backends) - the live
    RAG session is always process-local, since a vector-store client isn't something
    Redis is meant to hold; see docs/TECH_DECISIONS.md.

    The report's confidence_score determines its approval_status via the
    human-in-the-loop workflow (src/approval_workflow.py): high-confidence
    reports are auto_approved; everything else is pending_review until a
    human reviewer calls POST /reports/{id}/review."""

    cache_key = cache.make_cache_key(body.company, body.fiscal_year, body.filing_path)
    cached_result = cache.get_cached(cache_key)
    if cached_result is not None:
        return AnalyzeResponse(
            report=SynthesisReport.model_validate(cached_result["report"]),
            indexed_chunk_count=cached_result["indexed_chunk_count"],
            stage_timings_ms=cached_result["stage_timings_ms"],
            cache_hit=True,
            approval_status=cached_result["approval_status"],
        )

    llm = LLMClient(mode=settings.llm_mode)
    pipeline = WealthIntelligencePipeline(llm=llm)

    try:
        result = pipeline.run(
            filing_path=body.filing_path,
            company=body.company,
            fiscal_year=body.fiscal_year,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Filing not found: {body.filing_path}")

    approval_status = determine_approval_status(result["report"].confidence_score).value

    _last_run_cache["rag_agent"] = result["rag_agent"]
    cache.set_cached(
        cache_key,
        {
            "report": result["report"].model_dump(),
            "indexed_chunk_count": result["indexed_chunk_count"],
            "stage_timings_ms": result["stage_timings_ms"],
            "approval_status": approval_status,
        },
    )

    session = db.get_session()
    try:
        db.save_report(
            session,
            "synthesis",
            body.company,
            body.fiscal_year,
            result["report"].model_dump(),
            confidence_score=result["report"].confidence_score,
            approval_status=approval_status,
        )
    finally:
        session.close()

    return AnalyzeResponse(
        report=result["report"],
        indexed_chunk_count=result["indexed_chunk_count"],
        stage_timings_ms=result["stage_timings_ms"],
        cache_hit=False,
        approval_status=approval_status,
    )


@app.post("/analyze/async", response_model=AsyncTaskSubmitResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def analyze_async(
    request: Request, body: AnalyzeRequest, api_key: str = Depends(require_role("analyst"))
):
    """Submit the pipeline as a background Celery job instead of running it
    inline. Returns immediately with a task_id to poll via /tasks/{task_id}.
    Requires a running Redis broker and a Celery worker
    (`celery -A src.tasks worker`) - not started automatically by the API
    process itself."""
    from ..tasks import run_analysis_task

    async_result = run_analysis_task.delay(
        body.company, body.fiscal_year, body.filing_path, settings.llm_mode
    )
    return AsyncTaskSubmitResponse(task_id=async_result.id, status=async_result.status)


@app.get("/tasks/{task_id}", response_model=AsyncTaskStatusResponse)
async def get_task_status(task_id: str, api_key: str = Depends(require_api_key)):
    """Poll the status/result of a job submitted via /analyze/async."""
    from ..tasks import celery_app

    async_result = celery_app.AsyncResult(task_id)
    result_data = None
    if async_result.successful():
        result_data = async_result.result
    return AsyncTaskStatusResponse(task_id=task_id, status=async_result.status, result=result_data)


@app.post("/ask", response_model=QuestionResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def ask(request: Request, body: QuestionRequest, api_key: str = Depends(require_role("analyst"))):
    """Ask an ad-hoc question against the most recently indexed filing."""
    rag = _last_run_cache.get("rag_agent")
    if rag is None:
        raise HTTPException(status_code=400, detail="No filing indexed yet - call /analyze first.")

    mock_answer = None
    if settings.llm_mode == "mock":
        mock_answer = {
            "question": body.question,
            "answer": "See extracted data from the most recent /analyze call.",
            "source_chunks": [],
        }
    answer = rag.answer(body.question, mock_response=mock_answer)
    return QuestionResponse(answer=answer.answer, source_chunks=answer.source_chunks)


@app.post("/compare", response_model=CompareResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def compare(request: Request, body: CompareRequest, api_key: str = Depends(require_role("analyst"))):
    """Run extraction on two fiscal years and produce a year-over-year comparison."""

    llm = LLMClient(mode=settings.llm_mode)
    ingestion = IngestionAgent()
    extraction = ExtractionAgent(llm)
    comparison = ComparisonAgent(llm)

    try:
        prior_chunks = ingestion.chunk(ingestion.load_local_filing(body.prior_filing_path), section="prior")
        current_chunks = ingestion.chunk(
            ingestion.load_local_filing(body.current_filing_path), section="current"
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    prior_result = extraction.extract(prior_chunks, body.company, body.prior_fiscal_year)
    current_result = extraction.extract(
        current_chunks,
        body.company,
        body.current_fiscal_year,
    )
    report = comparison.compare(prior_result, current_result)

    session = db.get_session()
    try:
        db.save_report(
            session,
            "comparison",
            body.company,
            body.current_fiscal_year,
            report.model_dump(),
        )
    finally:
        session.close()

    return CompareResponse(report=report)


@app.get("/evaluate", response_model=EvaluateResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def evaluate(request: Request, api_key: str = Depends(require_role("analyst"))):
    """Score the bundled sample extractions against hand-labeled ground truth."""
    total_passed = sum(r.passed_count for r in results)
    total_checks = sum(r.total_count for r in results)
    overall = total_passed / total_checks if total_checks else 0.0

    session = db.get_session()
    try:
        db.save_report(
            session,
            "evaluation",
            "all_sample_filings",
            None,
            {
                "overall_accuracy": round(overall, 3),
                "results": [r.model_dump() for r in results],
            },
        )
    finally:
        session.close()

    return EvaluateResponse(results=results, overall_accuracy=round(overall, 3))


@app.post("/portfolio/analyze", response_model=PortfolioAnalyzeResponse)
@limiter.limit(f"{settings.rate_limit_per_minute}/minute")
async def portfolio_analyze(
    request: Request, body: PortfolioAnalyzeRequest, api_key: str = Depends(require_role("analyst"))
):
    """Extract each listed company's filing, then rank them by growth,
    legal/regulatory risk, and debt covenant compliance - portfolio-level
    intelligence rather than single-filing analysis. Rankings are computed
    deterministically from each extraction (see src/portfolio_agent.py);
    only the sector narrative is LLM-generated."""

    llm = LLMClient(mode=settings.llm_mode)
    ingestion = IngestionAgent()
    extraction_agent = ExtractionAgent(llm)
    portfolio_agent = PortfolioAgent(llm)

    extractions = []
    for company_input in body.companies:
        try:
            chunks = ingestion.chunk(
                ingestion.load_local_filing(company_input.filing_path), section=company_input.company
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Filing not found: {company_input.filing_path}")

        extraction = extraction_agent.extract(chunks, company_input.company, company_input.fiscal_year)
        extractions.append(extraction)
    report = portfolio_agent.analyze_portfolio(extractions)

    session = db.get_session()
    try:
        db.save_report(
            session,
            "portfolio",
            ", ".join(report.companies),
            None,
            report.model_dump(),
        )
    finally:
        session.close()

    return PortfolioAnalyzeResponse(report=report)


@app.get("/reports", response_model=list[ReportSummary])
async def list_reports(company: str | None = None, api_key: str = Depends(require_api_key)):
    """List persisted reports, optionally filtered by company - the audit trail."""
    session = db.get_session()
    try:
        records = db.list_reports(session, company=company)
        return [
            ReportSummary(
                id=r.id,
                report_type=r.report_type,
                company=r.company,
                fiscal_year=r.fiscal_year,
                created_at=r.created_at.isoformat(),
            )
            for r in records
        ]
    finally:
        session.close()


@app.get("/reports/pending-review", response_model=list[PendingReviewSummary])
async def list_pending_review(api_key: str = Depends(require_role("analyst"))):
    """The human reviewer's queue: reports whose confidence_score fell below
    the auto-approval threshold. Oldest first.

    NOTE: this route is deliberately registered before GET /reports/{report_id}
    - FastAPI/Starlette match routes in registration order, so if the
    parameterized route came first, a request to /reports/pending-review
    would be incorrectly matched as report_id="pending-review"."""
    session = db.get_session()
    try:
        records = db.list_pending_review(session)
        summaries = []
        for r in records:
            payload = json.loads(r.payload_json)
            recommendation = payload.get("recommendation", "")
            preview = recommendation[:150] + ("..." if len(recommendation) > 150 else "")
            summaries.append(
                PendingReviewSummary(
                    id=r.id,
                    company=r.company,
                    fiscal_year=r.fiscal_year,
                    confidence_score=r.confidence_score,
                    recommendation_preview=preview,
                    created_at=r.created_at.isoformat(),
                )
            )
        return summaries
    finally:
        session.close()


@app.get("/reports/{report_id}", response_model=ReportDetail)
async def get_report(report_id: str, api_key: str = Depends(require_api_key)):
    """Fetch a single persisted report by ID."""
    session = db.get_session()
    try:
        record = db.get_report(session, report_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        return ReportDetail(
            id=record.id,
            report_type=record.report_type,
            company=record.company,
            fiscal_year=record.fiscal_year,
            created_at=record.created_at.isoformat(),
            payload=json.loads(record.payload_json),
        )
    finally:
        session.close()


@app.get("/reports/{report_id}/export")
async def export_report(report_id: str, format: str = "md", api_key: str = Depends(require_api_key)):
    """Export a persisted report as markdown, PDF, or DOCX - the format an
    analyst would actually forward, not a JSON blob. `format` is one of
    'md' | 'pdf' | 'docx'."""
    session = db.get_session()
    try:
        record = db.get_report(session, report_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        payload = json.loads(record.payload_json)
    finally:
        session.close()

    if format == "md":
        content = report_to_markdown(record.report_type, record.company, record.fiscal_year, payload)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report_{report_id}.md"'},
        )
    elif format == "pdf":
        content = report_to_pdf_bytes(record.report_type, record.company, record.fiscal_year, payload)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report_{report_id}.pdf"'},
        )
    elif format == "docx":
        content = report_to_docx_bytes(record.report_type, record.company, record.fiscal_year, payload)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="report_{report_id}.docx"'},
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format!r}. Use md, pdf, or docx.")


@app.post("/reports/{report_id}/review", response_model=ReviewResponse)
async def submit_review(report_id: str, body: ReviewRequest, api_key: str = Depends(require_role("analyst"))):
    """A human reviewer approves or rejects a pending report, optionally
    editing the recommendation. This is the human-in-the-loop control point:
    a report below the confidence threshold cannot reach a decision-maker
    without going through this endpoint. The decision is also persisted as
    a FeedbackRecord - labeled data for future prompt/model improvement,
    not an automatic learning mechanism (see docs/TECH_DECISIONS.md)."""
    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    session = db.get_session()
    try:
        updated = db.submit_review(
            session,
            report_id=report_id,
            reviewer=body.reviewer,
            decision=body.decision,
            edited_recommendation=body.edited_recommendation,
            notes=body.notes,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        return ReviewResponse(
            id=updated.id,
            approval_status=updated.approval_status,
            reviewer=updated.reviewer,
            edited_recommendation=updated.edited_recommendation,
            reviewed_at=updated.reviewed_at.isoformat(),
        )
    finally:
        session.close()


@app.delete("/reports/{report_id}")
async def delete_report(report_id: str, api_key: str = Depends(require_role("admin"))):
    """Delete a persisted report. Admin-only - the RBAC example in this
    API: viewers and analysts can read/create reports, only admins can
    delete them."""
    session = db.get_session()
    try:
        deleted = db.delete_report(session, report_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Report not found: {report_id}")
        return {"deleted": True, "id": report_id}
    finally:
        session.close()
