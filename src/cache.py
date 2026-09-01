"""
Caching layer.

Repeated /analyze calls for the same (company, fiscal_year, filing_path)
re-run the full pipeline - ingestion, extraction, RAG indexing,
synthesis - for identical input, which is pure waste for anything that
gets polled or retried. A TTL cache keyed on those three fields avoids
recomputation within the TTL window.

Two backends, selected via `CACHE_BACKEND` ("memory" | "redis"):

- **memory** (default): `cachetools.TTLCache`, in-process. Zero external
  dependencies, but cache state isn't shared across multiple API
  instances - fine for a single-instance deployment, not for a scaled one.
- **redis**: shared across instances, which is what a real multi-instance
  deployment needs. Only the JSON-serializable parts of an analysis
  result are cached this way (the report, chunk count, timings) - the
  live RAG session (a ChromaDB client object) is never serialized to
  Redis and stays process-local by design, since sharing a live vector
  store connection across processes isn't what Redis is for. That's a
  deliberate scope boundary, not an oversight - see docs/TECH_DECISIONS.md.

This module isn't exercised against a live Redis server in CI - tests
use `fakeredis` (an in-memory Redis-protocol-compatible stand-in) to
verify the serialization logic, the same mock-by-default pattern used
throughout this project.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from cachetools import TTLCache

from .config import settings

DEFAULT_TTL_SECONDS = 300  # 5 minutes


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> Optional[dict]: ...

    @abstractmethod
    def set(self, key: str, value: dict) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def size(self) -> int: ...


class InMemoryCacheBackend(CacheBackend):
    """Default backend - no external service required."""

    def __init__(self, maxsize: int = 256, ttl: int = DEFAULT_TTL_SECONDS):
        self._store: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)

    def get(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    def set(self, key: str, value: dict) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)


class RedisCacheBackend(CacheBackend):
    """Shared cache backend for multi-instance deployments. Requires a
    running Redis server reachable at `REDIS_URL`. Values are stored as
    JSON strings; only JSON-serializable data can be cached this way."""

    def __init__(self, redis_client=None, ttl: int = DEFAULT_TTL_SECONDS):
        if redis_client is None:
            import redis as redis_lib

            redis_client = redis_lib.from_url(settings.redis_url)
        self._client = redis_client
        self._ttl = ttl

    def get(self, key: str) -> Optional[dict]:
        raw = self._client.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict) -> None:
        self._client.set(key, json.dumps(value), ex=self._ttl)

    def clear(self) -> None:
        self._client.flushdb()

    def size(self) -> int:
        return self._client.dbsize()


_backend: Optional[CacheBackend] = None


def get_backend() -> CacheBackend:
    global _backend
    if _backend is None:
        _backend = RedisCacheBackend() if settings.cache_backend == "redis" else InMemoryCacheBackend()
    return _backend


def reset_backend() -> None:
    """Used in tests to force re-reading settings.cache_backend."""
    global _backend
    _backend = None


def make_cache_key(company: str, fiscal_year: str, filing_path: str) -> str:
    return f"analysis:{company}|{fiscal_year}|{filing_path}"


def get_cached(key: str) -> Optional[Any]:
    return get_backend().get(key)


def set_cached(key: str, value: Any) -> None:
    get_backend().set(key, value)


def clear_cache() -> None:
    get_backend().clear()


def cache_size() -> int:
    return get_backend().size()
