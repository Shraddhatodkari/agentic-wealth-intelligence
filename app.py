"""
Streamlit UI for Agentic Wealth Intelligence.

Run with: streamlit run app.py
LLM_MODE is loaded from .env.
"""

import json
import os
import tempfile

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load .env BEFORE reading any environment variables.
load_dotenv()

from src import db, edgar_client
from src.approval_workflow import DEFAULT_CONFIDENCE_THRESHOLD, determine_approval_status
from src.comparison_agent import ComparisonAgent
from src.extraction_agent import ExtractionAgent
from src.ingestion_agent import IngestionAgent
from src.llm_client import LLMClient
from src.orchestrator import WealthIntelligencePipeline
from src.portfolio_agent import PortfolioAgent
from src.report_export import report_to_docx_bytes, report_to_markdown, report_to_pdf_bytes
st.set_page_config(
    page_title="Agentic Wealth Intelligence",
    layout="wide",
)

MODE = os.getenv("LLM_MODE", "ollama").lower()

SEVERITY_ICON = {
    "low": "LOW",
    "medium": "MEDIUM",
    "high": "HIGH",
    "critical": "CRITICAL",
}

if MODE == "mock":
    st.error(
        "Dashboard mock mode is disabled. Set LLM_MODE=ollama for the real dashboard."
    )
    st.stop()

# --------------------------------------------------------------- STYLING ---
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 10px;
        padding: 12px 16px;
    }
    div[data-testid="stMetricValue"] { font-size: 1.6rem; }
    .awi-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
    }
    .awi-badge-mode {
        background-color: rgba(99, 102, 241, 0.15);
        color: #6366f1;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------ HEADER ---

header_cols = st.columns([5, 1])

with header_cols[0]:
    st.title("Agentic Wealth Intelligence")
    st.caption(
        "Institutional-grade SEC 10-K intelligence: "
        "live filing ingestion -> structured extraction -> RAG -> "
        "executive risk synthesis -> YoY comparison -> portfolio intelligence."
    )

with header_cols[1]:
    st.markdown(
        f'<div style="text-align:right; padding-top:20px;">'
        f'<span class="awi-badge awi-badge-mode">MODE: {MODE.upper()}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

if MODE == "ollama":
    st.info(
        "Live production dashboard: SEC EDGAR data is retrieved in real time "
        "and processed through the configured local Ollama model."
    )

# --------------------------------------------------------------- SIDEBAR ---

with st.sidebar:
    st.header("Configuration")
    st.caption("All dashboard analysis uses live SEC EDGAR filings.")

    ticker_input = st.text_input(
        "Company ticker",
        placeholder="AAPL, MSFT, NVDA, AMZN...",
        key="main_ticker",
    )

    fiscal_year_input = st.text_input(
        "Fiscal year",
        value="FY2025",
        key="main_fiscal_year",
    )

    if not os.getenv("SEC_USER_AGENT"):
        st.error(
            "SEC_USER_AGENT is not configured. Add a descriptive SEC User-Agent "
            "to your .env file before running live analysis."
        )

    st.caption(
        "Example SEC User-Agent: Your Name your.email@example.com"
    )

    st.divider()
    st.caption(
        f"Auto-approval threshold: "
        f"{DEFAULT_CONFIDENCE_THRESHOLD * 100:.0f}%"
    )


def _get_llm():
    return LLMClient(mode=MODE)


tab_analyze, tab_compare, tab_portfolio, tab_review, tab_evaluate, tab_history = st.tabs(
    [
        "Analyze",
        "Compare Years",
        "Portfolio",
        "Pending Review",
        "Quality",
        "Report History",
    ]
)

# ---------------------------------------------------------------- ANALYZE ---

with tab_analyze:
    st.subheader("Live SEC filing analysis")

    ticker = ticker_input.strip().upper()
    fiscal_year = fiscal_year_input.strip() or "FY2025"

    st.caption(
        f"Source: SEC EDGAR | Ticker: {ticker or 'not selected'} | "
        f"Fiscal year: {fiscal_year}"
    )

    run_clicked = st.button(
        "Run live SEC analysis",
        type="primary",
        use_container_width=True,
        disabled=not ticker,
    )

    if run_clicked:
        pipeline = WealthIntelligencePipeline(llm=_get_llm())
        ingestion = IngestionAgent()

        with st.spinner(
            f"Fetching {ticker} {fiscal_year} 10-K from SEC EDGAR..."
        ):
            try:
                raw_text = ingestion.fetch_from_ticker(ticker)
            except Exception as e:
                st.error(f"SEC EDGAR fetch failed: {e}")
                raw_text = None

        if raw_text:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".txt",
                delete=False,
                encoding="utf-8",
            ) as tmp:
                tmp.write(raw_text)
                tmp_path = tmp.name

            try:
                with st.spinner("Running extraction, RAG and executive synthesis..."):
                    result = pipeline.run(
                        filing_path=tmp_path,
                        company=ticker,
                        fiscal_year=fiscal_year,
                    )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            approval_status = determine_approval_status(
                result["report"].confidence_score
            ).value

            result["approval_status"] = approval_status
            st.session_state["analyze_result"] = result

            session = db.get_session()
            try:
                db.save_report(
                    session,
                    "synthesis",
                    ticker,
                    fiscal_year,
                    result["report"].model_dump(),
                    confidence_score=result["report"].confidence_score,
                    approval_status=approval_status,
                )
            finally:
                session.close()

    if "analyze_result" in st.session_state:
        result = st.session_state["analyze_result"]
        report = result["report"]
        extraction = result["extraction"]

        confidence_pct = report.confidence_score * 100
        approval_status = result.get("approval_status", "unknown")

        if approval_status == "auto_approved":
            st.success(
                f"Auto-approved | confidence {confidence_pct:.0f}%"
            )
        else:
            st.warning(
                f"Human review required | confidence {confidence_pct:.0f}%"
            )

        metric_cols = st.columns(4)
        metric_cols[0].metric(
            "Chunks indexed",
            result["indexed_chunk_count"],
        )
        metric_cols[1].metric(
            "Top risks",
            len(report.top_risks),
        )

        total_ms = sum(
            result.get("stage_timings_ms", {}).values()
        )

        total_seconds = total_ms / 1000

        if total_seconds >= 60:
            minutes = int(total_seconds // 60)
            seconds = total_seconds % 60
            processing_display = f"{minutes}m {seconds:.0f}s"
        else:
            processing_display = f"{total_seconds:.1f}s"

        metric_cols[2].metric(
            "Processing time",
            processing_display,
        )

        metric_cols[3].metric(
            "Revenue signals",
            len(extraction.revenue_signals),
        )

        st.divider()

        st.markdown(
            f"### {report.company} - {report.fiscal_year} Executive Risk Memo"
        )

        st.write(report.executive_summary)

        st.markdown("#### Top Risks")

        if report.top_risks:
            for risk in report.top_risks:
                st.markdown(
                    f"**{risk.severity.value.upper()} | "
                    f"{risk.headline}**"
                )
                st.caption(
                    f"{risk.category.value}: {risk.detail}"
                )
        else:
            st.info("No material risks identified.")

        st.markdown("#### Recommendation")
        st.write(report.recommendation)

        if extraction.revenue_signals:
            st.markdown("#### Revenue signals")

            chart_df = pd.DataFrame(
                {
                    "Segment": [
                        r.segment
                        for r in extraction.revenue_signals
                    ],
                    "YoY change %": [
                        r.yoy_change_pct or 0
                        for r in extraction.revenue_signals
                    ],
                }
            ).set_index("Segment")

            st.bar_chart(chart_df)

        if extraction.debt_covenants:
            st.markdown("#### Debt covenant status")

            covenant_df = pd.DataFrame(
                [
                    {
                        "Covenant": c.covenant_type,
                        "Threshold": c.threshold,
                        "Status": c.current_status.value,
                    }
                    for c in extraction.debt_covenants
                ]
            )

            st.dataframe(
                covenant_df,
                use_container_width=True,
                hide_index=True,
            )

        if extraction.legal_risks:
            st.markdown("#### Legal and regulatory risks")

            legal_df = pd.DataFrame(
                [
                    {
                        "Matter": r.matter,
                        "Severity": r.severity.value,
                        "Potential exposure": r.potential_exposure or "Not disclosed",
                    }
                    for r in extraction.legal_risks
                ]
            )

            st.dataframe(
                legal_df,
                use_container_width=True,
                hide_index=True,
            )

        st.divider()

        st.markdown("#### Ask the filing")

        question = st.text_input(
            "Question",
            value="What is the leverage ratio covenant status?",
            key="rag_question",
        )

        if st.button("Ask filing", key="ask_filing"):
            answer = result["rag_agent"].answer(question)
            st.write(f"**Answer:** {answer.answer}")
            st.caption(
                f"Retrieved source chunks: {answer.source_chunks}"
            )

        st.divider()
        st.markdown("#### Download report")

        payload = report.model_dump()
        dl_cols = st.columns(3)

        dl_cols[0].download_button(
            "Markdown",
            data=report_to_markdown(
                "synthesis",
                report.company,
                report.fiscal_year,
                payload,
            ),
            file_name=f"{ticker}_{fiscal_year}_risk_memo.md",
            use_container_width=True,
        )

        dl_cols[1].download_button(
            "PDF",
            data=report_to_pdf_bytes(
                "synthesis",
                report.company,
                report.fiscal_year,
                payload,
            ),
            file_name=f"{ticker}_{fiscal_year}_risk_memo.pdf",
            use_container_width=True,
        )

        dl_cols[2].download_button(
            "DOCX",
            data=report_to_docx_bytes(
                "synthesis",
                report.company,
                report.fiscal_year,
                payload,
            ),
            file_name=f"{ticker}_{fiscal_year}_risk_memo.docx",
            use_container_width=True,
        )

        with st.expander("Structured extraction"):
            st.json(extraction.model_dump())

# ---------------------------------------------------------------- COMPARE ---

with tab_compare:
    st.subheader("Live year-over-year comparison")

    c1, c2, c3 = st.columns(3)

    with c1:
        comparison_ticker = st.text_input(
            "Ticker",
            value=ticker_input,
            key="comparison_ticker",
        ).strip().upper()

    with c2:
        prior_year = st.text_input(
            "Prior fiscal year",
            value="FY2024",
            key="comparison_prior_year",
        ).strip()

    with c3:
        current_year = st.text_input(
            "Current fiscal year",
            value="FY2025",
            key="comparison_current_year",
        ).strip()

    if st.button(
        "Run live YoY comparison",
        type="primary",
        disabled=not comparison_ticker,
    ):
        llm = _get_llm()
        extraction_agent = ExtractionAgent(llm)
        comparison_agent = ComparisonAgent(llm)

        with st.spinner("Retrieving both real SEC 10-K filings..."):
            try:
                prior_text = edgar_client.fetch_10k_for_fiscal_year(
                    comparison_ticker,
                    prior_year,
                )
                current_text = edgar_client.fetch_10k_for_fiscal_year(
                    comparison_ticker,
                    current_year,
                )
            except Exception as e:
                st.error(f"SEC historical filing retrieval failed: {e}")
                prior_text = None
                current_text = None

        if prior_text and current_text:
            ingestion = IngestionAgent()

            with st.spinner("Extracting both fiscal periods..."):
                prior_chunks = ingestion.chunk(
                    prior_text,
                    section="prior",
                )
                current_chunks = ingestion.chunk(
                    current_text,
                    section="current",
                )

                prior_extraction = extraction_agent.extract(
                    prior_chunks,
                    comparison_ticker,
                    prior_year,
                )

                current_extraction = extraction_agent.extract(
                    current_chunks,
                    comparison_ticker,
                    current_year,
                )

            with st.spinner("Generating evidence-based YoY comparison..."):
                report = comparison_agent.compare(
                    prior_extraction,
                    current_extraction,
                )

            st.session_state["compare_result"] = {
                "report": report,
                "prior": prior_extraction,
                "current": current_extraction,
            }

            session = db.get_session()
            try:
                db.save_report(
                    session,
                    "comparison",
                    comparison_ticker,
                    current_year,
                    report.model_dump(),
                )
            finally:
                session.close()

    if "compare_result" in st.session_state:
        cr = st.session_state["compare_result"]
        report = cr["report"]

        trajectory = report.overall_trajectory.value

        st.metric(
            "Overall trajectory",
            trajectory.upper(),
        )

        st.markdown("#### Material trend shifts")

        if report.trend_shifts:
            shift_df = pd.DataFrame(
                [
                    {
                        "Metric": s.metric,
                        "Prior": s.prior_value,
                        "Current": s.current_value,
                        "Direction": s.direction.value,
                        "Materiality": s.materiality.value,
                    }
                    for s in report.trend_shifts
                ]
            )

            st.dataframe(
                shift_df,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No material changes identified.")

        st.markdown("#### Executive narrative")
        st.write(report.narrative)

        prior_map = {
            r.segment: r.yoy_change_pct or 0
            for r in cr["prior"].revenue_signals
        }

        current_map = {
            r.segment: r.yoy_change_pct or 0
            for r in cr["current"].revenue_signals
        }

        segments = sorted(
            set(prior_map) | set(current_map)
        )

        if segments:
            st.markdown("#### Revenue YoY comparison")

            chart_df = pd.DataFrame(
                {
                    cr["prior"].fiscal_year: [
                        prior_map.get(x, None)
                        for x in segments
                    ],
                    cr["current"].fiscal_year: [
                        current_map.get(x, None)
                        for x in segments
                    ],
                },
                index=segments,
            )

            st.bar_chart(chart_df)

        payload = report.model_dump()

        dl_cols = st.columns(3)

        dl_cols[0].download_button(
            "Markdown",
            data=report_to_markdown(
                "comparison",
                report.company,
                report.current_fiscal_year,
                payload,
            ),
            file_name=f"{report.company}_{report.current_fiscal_year}_yoy.md",
        )

        dl_cols[1].download_button(
            "PDF",
            data=report_to_pdf_bytes(
                "comparison",
                report.company,
                report.current_fiscal_year,
                payload,
            ),
            file_name=f"{report.company}_{report.current_fiscal_year}_yoy.pdf",
        )

        dl_cols[2].download_button(
            "DOCX",
            data=report_to_docx_bytes(
                "comparison",
                report.company,
                report.current_fiscal_year,
                payload,
            ),
            file_name=f"{report.company}_{report.current_fiscal_year}_yoy.docx",
        )

# --------------------------------------------------------------- PORTFOLIO ---

with tab_portfolio:
    st.subheader("Live multi-company portfolio intelligence")

    portfolio_input = st.text_input(
        "SEC tickers",
        value="AAPL, MSFT, AMZN, NVDA, TSLA",
        key="live_portfolio_tickers",
    )

    portfolio_year = st.text_input(
        "Fiscal year",
        value="FY2025",
        key="live_portfolio_year",
    )

    if st.button(
        "Run live portfolio analysis",
        type="primary",
        key="run_live_portfolio",
    ):
        tickers = [
            x.strip().upper()
            for x in portfolio_input.split(",")
            if x.strip()
        ]

        llm = _get_llm()
        ingestion = IngestionAgent()
        extraction_agent = ExtractionAgent(llm)
        portfolio_agent = PortfolioAgent(llm)

        extractions = []
        progress = st.progress(
            0.0,
            text="Starting live SEC portfolio run...",
        )

        for i, ticker in enumerate(tickers):
            progress.progress(
                i / len(tickers),
                text=f"Fetching {ticker} from SEC EDGAR...",
            )

            try:
                raw_text = ingestion.fetch_from_ticker(ticker)

                chunks = ingestion.chunk(
                    raw_text,
                    section=ticker,
                )

                extraction = extraction_agent.extract(
                    chunks,
                    ticker,
                    portfolio_year,
                )

                extractions.append(extraction)

            except Exception as e:
                st.error(
                    f"{ticker} skipped: {e}"
                )

        if extractions:
            progress.progress(
                1.0,
                text="Generating portfolio intelligence...",
            )

            portfolio_report = portfolio_agent.analyze_portfolio(
                extractions
            )

            st.session_state["portfolio_result"] = portfolio_report

            session = db.get_session()
            try:
                db.save_report(
                    session,
                    "portfolio",
                    ", ".join(
                        portfolio_report.companies
                    ),
                    portfolio_year,
                    portfolio_report.model_dump(),
                )
            finally:
                session.close()

        progress.empty()

    if "portfolio_result" in st.session_state:
        pr = st.session_state["portfolio_result"]

        rank_cols = st.columns(3)

        with rank_cols[0]:
            st.markdown("#### Top Growth")
            for r in pr.growth_ranking:
                st.markdown(
                    f"**{r.rank}. {r.company}**"
                )
                st.caption(
                    f"{r.metric_value:+.1f}% average revenue YoY"
                )

        with rank_cols[1]:
            st.markdown("#### Legal Risk")
            for r in pr.risk_ranking:
                st.markdown(
                    f"**{r.rank}. {r.company}**"
                )
                st.caption(
                    f"Severity score: {r.metric_value:.1f}"
                )

        with rank_cols[2]:
            st.markdown("#### Debt Exposure")
            for r in pr.debt_ranking:
                st.markdown(
                    f"**{r.rank}. {r.company}**"
                )
                if r.data_available:
                    st.caption(
                        f"Non-compliant covenants: {r.metric_value:.1f}"
                    )
                else:
                    st.caption("Debt covenant data unavailable")

        st.markdown("#### Portfolio growth")

        growth_chart_df = pd.DataFrame(
            {
                "Company": [
                    r.company
                    for r in pr.growth_ranking
                ],
                "Average YoY %": [
                    r.metric_value
                    for r in pr.growth_ranking
                ],
            }
        ).set_index("Company")

        st.bar_chart(growth_chart_df)

        st.markdown("#### Portfolio narrative")
        st.write(pr.sector_narrative)

# ------------------------------------------------------------ PENDING REVIEW ---
with tab_review:
    st.subheader("Human-in-the-loop review queue")
    st.caption(
        f"Reports with confidence below {DEFAULT_CONFIDENCE_THRESHOLD * 100:.0f}% are routed here for "
        "human review instead of being auto-approved â€” the responsible-AI governance control point."
    )

    _review_session = db.get_session()
    try:
        pending = db.list_pending_review(_review_session)
    finally:
        _review_session.close()

    if not pending:
        st.info(
            "No reports currently pending review. Run an analysis with a "
            "sub-90% confidence score to populate this queue."
        )
    for record in pending:
        payload = json.loads(record.payload_json)
        with st.expander(
            f"{record.company} ({record.fiscal_year}) â€” confidence {record.confidence_score * 100:.0f}%"
        ):
            st.write("**AI-generated recommendation:**")
            st.write(payload.get("recommendation", ""))

            reviewer = st.text_input("Reviewer name", key=f"reviewer_{record.id}")
            edited = st.text_area(
                "Edited recommendation (optional)",
                value=payload.get("recommendation", ""),
                key=f"edit_{record.id}",
            )
            notes = st.text_area("Review notes", key=f"notes_{record.id}")

            btn_cols = st.columns(2)
            if btn_cols[0].button("âœ… Approve", key=f"approve_{record.id}"):
                session = db.get_session()
                try:
                    db.submit_review(session, record.id, reviewer or "anonymous", "approve", edited, notes)
                finally:
                    session.close()
                st.rerun()
            if btn_cols[1].button("âŒ Reject", key=f"reject_{record.id}"):
                session = db.get_session()
                try:
                    db.submit_review(session, record.id, reviewer or "anonymous", "reject", edited, notes)
                finally:
                    session.close()
                st.rerun()

# --------------------------------------------------------------- EVALUATE ---

with tab_evaluate:
    st.subheader("Live extraction quality")

    st.caption(
        "This dashboard does not fabricate an accuracy score for live SEC filings. "
        "Live filings have no hand-labelled ground truth here. Instead, structural "
        "quality is measured from the actual extraction and synthesis."
    )

    if "analyze_result" in st.session_state:
        from src.quality_report import build_quality_report

        last_result = st.session_state["analyze_result"]
        extraction = last_result["extraction"]
        report = last_result["report"]

        quality = build_quality_report(
            extraction,
            expected_company=extraction.company,
            synthesis_report=report,
        )

        qcols = st.columns(3)

        qcols[0].metric(
            "Completeness",
            f"{quality.completeness_score * 100:.0f}%",
        )

        qcols[1].metric(
            "Errors",
            quality.error_count,
        )

        qcols[2].metric(
            "Warnings",
            quality.warning_count,
        )

        if quality.issues:
            st.markdown("#### Quality issues")

            for issue in quality.issues:
                st.markdown(f"- {issue}")
        else:
            st.success(
                "No structural quality issues detected."
            )

    else:
        st.info(
            "Run a live SEC analysis in the Analyze tab first."
        )

# --------------------------------------------------------------- HISTORY ---
with tab_history:
    st.subheader("Report history")
    st.caption("Every report generated via this dashboard or the API is persisted here (SQLite by default).")

    if st.button("Refresh history"):
        st.rerun()

    _history_session = db.get_session()
    try:
        records = db.list_reports(_history_session, limit=50)
    finally:
        _history_session.close()

    if records:
        history_df = pd.DataFrame(
            [
                {
                    "id": r.id[:8],
                    "type": r.report_type,
                    "company": r.company,
                    "fiscal_year": r.fiscal_year,
                    "confidence": (
                        f"{r.confidence_score * 100:.0f}%" if r.confidence_score is not None else "â€”"
                    ),
                    "status": r.approval_status or "â€”",
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
                for r in records
            ]
        )
        st.dataframe(history_df, use_container_width=True, hide_index=True)
    else:
        st.caption(
            "No reports generated yet â€” run an analysis, comparison, portfolio run, or evaluation above."
        )
