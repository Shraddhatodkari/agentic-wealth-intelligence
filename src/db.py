"""
Persistence layer.

Defaults to a local SQLite file so the project runs with zero external
services - genuinely useful for dev/test, not a placeholder. Swapping to
Postgres for production is a one-line env change:

    export DATABASE_URL=postgresql://user:pass@host:5432/dbname

No code changes needed - SQLAlchemy's engine creation is the only place
that's database-specific, and it reads the URL scheme to pick the driver.
(Postgres also requires `pip install psycopg2-binary`, not included by
default since SQLite needs no driver.)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agentic_wealth_intelligence.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class ReportRecord(Base):
    """A persisted output from /analyze, /compare, or /evaluate."""

    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type = Column(String, nullable=False)  # "synthesis" | "comparison" | "evaluation" | "portfolio"
    company = Column(String, nullable=False)
    fiscal_year = Column(String, nullable=True)
    payload_json = Column(Text, nullable=False)  # serialized Pydantic model
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Human-in-the-loop approval workflow (synthesis reports only)
    confidence_score = Column(Float, nullable=True)
    approval_status = Column(String, nullable=True)  # ApprovalStatus value
    reviewer = Column(String, nullable=True)
    review_notes = Column(Text, nullable=True)
    edited_recommendation = Column(Text, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)


class FeedbackRecord(Base):
    """
    Every human review decision, captured as labeled data.

    This is deliberately NOT an online-learning mechanism - nothing here
    updates model weights or prompts automatically. What it is: the raw
    material a future iteration could use to build a prompt-improvement
    or fine-tuning dataset from real reviewer corrections. Be precise
    about that distinction if asked "does the AI learn from feedback."
    """

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String, nullable=False)
    original_recommendation = Column(Text, nullable=False)
    edited_recommendation = Column(Text, nullable=True)
    reviewer = Column(String, nullable=False)
    decision = Column(String, nullable=False)  # ReviewDecision value
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AuditLogRecord(Base):
    """One row per authenticated API request, for audit trail purposes."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    api_key_prefix = Column(String, nullable=False)  # first 8 chars only - never store full key
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()


def save_report(
    session: Session,
    report_type: str,
    company: str,
    fiscal_year: str | None,
    payload: dict,
    confidence_score: float | None = None,
    approval_status: str | None = None,
) -> ReportRecord:
    record = ReportRecord(
        report_type=report_type,
        company=company,
        fiscal_year=fiscal_year,
        payload_json=json.dumps(payload),
        confidence_score=confidence_score,
        approval_status=approval_status,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def get_report(session: Session, report_id: str) -> ReportRecord | None:
    return session.query(ReportRecord).filter(ReportRecord.id == report_id).first()


def delete_report(session: Session, report_id: str) -> bool:
    record = get_report(session, report_id)
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True


def list_reports(session: Session, company: str | None = None, limit: int = 50) -> list[ReportRecord]:
    query = session.query(ReportRecord).order_by(ReportRecord.created_at.desc())
    if company:
        query = query.filter(ReportRecord.company == company)
    return query.limit(limit).all()


def list_pending_review(session: Session, limit: int = 50) -> list[ReportRecord]:
    """Reports currently awaiting a human reviewer's decision."""
    return (
        session.query(ReportRecord)
        .filter(ReportRecord.approval_status == "pending_review")
        .order_by(ReportRecord.created_at.asc())  # oldest first - reviewer queue order
        .limit(limit)
        .all()
    )


def submit_review(
    session: Session,
    report_id: str,
    reviewer: str,
    decision: str,
    edited_recommendation: str | None,
    notes: str | None,
) -> ReportRecord | None:
    """
    Records a human reviewer's decision on a pending report: updates the
    report's status and persists a FeedbackRecord capturing the original
    vs. edited recommendation - the labeled data a future prompt/model
    improvement pass would use.
    """
    record = get_report(session, report_id)
    if record is None:
        return None

    original_payload = json.loads(record.payload_json)
    original_recommendation = original_payload.get("recommendation", "")

    record.reviewer = reviewer
    record.review_notes = notes
    record.edited_recommendation = edited_recommendation
    record.reviewed_at = datetime.now(timezone.utc)
    record.approval_status = "approved" if decision == "approve" else "rejected"

    session.add(
        FeedbackRecord(
            report_id=report_id,
            original_recommendation=original_recommendation,
            edited_recommendation=edited_recommendation,
            reviewer=reviewer,
            decision=decision,
            notes=notes,
        )
    )
    session.commit()
    session.refresh(record)
    return record


def list_feedback(session: Session, limit: int = 100) -> list[FeedbackRecord]:
    return session.query(FeedbackRecord).order_by(FeedbackRecord.created_at.desc()).limit(limit).all()


def save_audit_entry(
    session: Session,
    request_id: str,
    endpoint: str,
    api_key: str,
    status_code: int,
    duration_ms: float,
) -> None:
    session.add(
        AuditLogRecord(
            request_id=request_id,
            endpoint=endpoint,
            api_key_prefix=api_key[:8] if api_key else "anonymous",
            status_code=status_code,
            duration_ms=int(duration_ms),
        )
    )
    session.commit()
