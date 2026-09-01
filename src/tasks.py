"""
Async job queue (Celery + Redis).

Long-running analysis (a real live Gemini call across a large filing)
shouldn't block an HTTP request - a real deployment would submit it as
a background job and let the client poll for the result. This wires
Celery with Redis as both broker and result backend.

Not run against a live Redis/worker in CI - `tests/test_tasks.py` sets
`task_always_eager=True`, Celery's standard testing mode that executes
tasks synchronously in-process without a broker. This verifies the task
logic is correct; running it for real requires a Redis instance and a
worker process:

    celery -A src.tasks worker --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from .config import settings

celery_app = Celery(
    "agentic_wealth_intelligence",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


@celery_app.task(bind=True, name="run_analysis_task")
def run_analysis_task(
    self, company: str, fiscal_year: str, filing_path: str, llm_mode: str = "ollama"
) -> dict:
    """Runs the full pipeline as a background job. Returns a JSON-serializable
    dict (Celery results must be serializable) - not the full pipeline state,
    which includes a live RAG session that can't cross a process boundary."""
    from .llm_client import LLMClient
    from .orchestrator import WealthIntelligencePipeline

    pipeline = WealthIntelligencePipeline(llm=LLMClient(mode=llm_mode))
    result = pipeline.run(filing_path=filing_path, company=company, fiscal_year=fiscal_year)

    return {
        "report": result["report"].model_dump(),
        "indexed_chunk_count": result["indexed_chunk_count"],
        "stage_timings_ms": result["stage_timings_ms"],
    }
