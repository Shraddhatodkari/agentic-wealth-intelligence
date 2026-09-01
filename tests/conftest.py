"""
Pytest session-wide setup.

`src.config.settings` is a module-level singleton constructed once at
first import, and `src.tasks.celery_app` is constructed with broker/
backend URLs read from that singleton at import time. If different test
files set environment variables at different points, whichever test file
happens to trigger the first import "wins" the settings values for the
entire test session - a real footgun. This conftest guarantees the env
is set before pytest imports any test module, so every test sees the
same, deterministic configuration regardless of file collection order.
"""

import os

os.environ.setdefault("LLM_MODE", "mock")
os.environ.setdefault("API_KEYS", "test-key-123:admin,analyst-key:analyst,viewer-key:viewer")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_api.db")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
