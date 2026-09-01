"""
Tests for src/tasks.py using Celery's `task_always_eager` mode - tasks
execute synchronously in-process, no Redis broker or worker required.
This verifies the task's logic is correct; running it for real requires
a live Redis instance and a Celery worker process (see src/tasks.py docstring).
"""

import pytest

from src.tasks import celery_app, run_analysis_task

FY2025_PATH = "data/sample_filings/nimbus_dynamics_10k_fy2025.txt"


@pytest.fixture(autouse=True)
def _eager_mode():
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = False


def test_run_analysis_task_returns_serializable_result():
    result = run_analysis_task.apply(args=("Nimbus Dynamics, Inc.", "FY2025", FY2025_PATH, "mock")).get()

    assert result["report"]["company"] == "Nimbus Dynamics, Inc."
    assert result["indexed_chunk_count"] > 0
    assert "ingestion" in result["stage_timings_ms"]


def test_run_analysis_task_raises_for_missing_filing():
    with pytest.raises(FileNotFoundError):
        run_analysis_task.apply(
            args=("Ghost Corp", "FY2025", "data/sample_filings/does_not_exist.txt", "mock")
        ).get()


def test_task_is_registered_with_celery_app():
    assert "run_analysis_task" in celery_app.tasks
