"""
Tests for src/cache.py.

The Redis backend is tested against `fakeredis` - an in-memory,
Redis-protocol-compatible stand-in - so the serialization logic is
verified without needing a real Redis server, the same mock-by-default
pattern used throughout this project.
"""

import fakeredis
import pytest

from src.cache import InMemoryCacheBackend, RedisCacheBackend, make_cache_key


def test_make_cache_key_is_deterministic_and_distinguishes_inputs():
    key1 = make_cache_key("Acme Corp", "FY2025", "path/a.txt")
    key2 = make_cache_key("Acme Corp", "FY2025", "path/a.txt")
    key3 = make_cache_key("Acme Corp", "FY2024", "path/a.txt")
    assert key1 == key2
    assert key1 != key3


class TestInMemoryCacheBackend:
    def test_set_then_get_returns_value(self):
        backend = InMemoryCacheBackend()
        backend.set("k1", {"foo": "bar"})
        assert backend.get("k1") == {"foo": "bar"}

    def test_get_missing_key_returns_none(self):
        backend = InMemoryCacheBackend()
        assert backend.get("does-not-exist") is None

    def test_clear_empties_cache(self):
        backend = InMemoryCacheBackend()
        backend.set("k1", {"a": 1})
        backend.clear()
        assert backend.get("k1") is None
        assert backend.size() == 0

    def test_size_reflects_entry_count(self):
        backend = InMemoryCacheBackend()
        backend.set("k1", {"a": 1})
        backend.set("k2", {"b": 2})
        assert backend.size() == 2

    def test_respects_ttl_expiry(self):
        backend = InMemoryCacheBackend(ttl=0.01)
        backend.set("k1", {"a": 1})
        import time

        time.sleep(0.05)
        assert backend.get("k1") is None


class TestRedisCacheBackend:
    def _backend(self):
        fake_client = fakeredis.FakeStrictRedis(decode_responses=True)
        return RedisCacheBackend(redis_client=fake_client)

    def test_set_then_get_returns_deserialized_value(self):
        backend = self._backend()
        backend.set("k1", {"report": {"company": "Acme"}, "count": 3})
        assert backend.get("k1") == {"report": {"company": "Acme"}, "count": 3}

    def test_get_missing_key_returns_none(self):
        backend = self._backend()
        assert backend.get("does-not-exist") is None

    def test_clear_empties_cache(self):
        backend = self._backend()
        backend.set("k1", {"a": 1})
        backend.clear()
        assert backend.get("k1") is None

    def test_size_reflects_entry_count(self):
        backend = self._backend()
        backend.set("k1", {"a": 1})
        backend.set("k2", {"b": 2})
        assert backend.size() == 2

    def test_only_json_serializable_values_supported(self):
        backend = self._backend()
        with pytest.raises(TypeError):
            backend.set("k1", {"bad": object()})
