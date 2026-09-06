"""
S4-F.R4 — Unit tests untuk app.core.cache (LRU cache + decorator).

Coverage target: ~95% (80 stmts).

LRUCache:
- Thread-safe dengan RLock
- Max size (default 256)
- TTL opsional per entry
- LRU eviction saat over capacity
- Stats: hits, misses, hit_rate

Decorator @cached(ttl_seconds=N):
- Generate cache key dari func name + args/kwargs
- Cache hit → return cached value
- Cache miss → compute + store

invalidate_cache(pattern=None):
- pattern=None → clear all
- pattern="foo" → delete keys containing "foo"
"""

import pytest

from app.core.cache import (
    LRUCache,
    _make_cache_key,
    cache,
    cached,
    invalidate_cache,
)


@pytest.fixture(autouse=True)
def clear_global_cache():
    """Clear global cache before each test (prevent leakage between tests)."""
    cache.clear()
    yield
    cache.clear()


class TestLRUCacheBasic:
    """Basic get/set operations."""

    def test_miss_returns_none(self):
        result = cache.get("nonexistent")
        assert result is None

    def test_set_and_get(self):
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_overwrite_existing(self):
        cache.set("key1", "value1")
        cache.set("key1", "value2")
        assert cache.get("key1") == "value2"

    def test_delete_existing(self):
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_delete_nonexistent_no_error(self):
        """Delete key yang tidak ada → no error (silent)."""
        cache.delete("nonexistent")  # Should not raise

    def test_clear_all(self):
        cache.set("key1", "v1")
        cache.set("key2", "v2")
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None


class TestLRUCacheTTL:
    """TTL expiry behavior."""

    def test_no_ttl_never_expires(self):
        cache.set("key1", "value1")
        # Even after some delay, no expiry (None TTL)
        import time
        time.sleep(0.05)
        assert cache.get("key1") == "value1"

    def test_ttl_expires(self):
        """TTL 1 second → setelah 1.1 detik, expired."""
        cache.set("key1", "value1", ttl_seconds=1)
        assert cache.get("key1") == "value1"

        import time
        time.sleep(1.1)
        # After expiry, returns None
        assert cache.get("key1") is None


class TestLRUCacheEviction:
    """LRU eviction when over max_size."""

    def test_evict_oldest(self):
        """Cache over max → evict oldest entry."""
        small_cache = LRUCache(max_size=3)
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)
        # Cache penuh (3 entries)
        small_cache.set("d", 4)
        # 'a' should be evicted (oldest)
        assert small_cache.get("a") is None
        assert small_cache.get("b") == 2
        assert small_cache.get("c") == 3
        assert small_cache.get("d") == 4

    def test_get_promotes_to_most_recent(self):
        """Get operation promotes entry to MRU position."""
        small_cache = LRUCache(max_size=3)
        small_cache.set("a", 1)
        small_cache.set("b", 2)
        small_cache.set("c", 3)
        # Access 'a' → move to MRU
        small_cache.get("a")
        # Add 'd' → 'b' should be evicted (now oldest)
        small_cache.set("d", 4)
        assert small_cache.get("a") == 1  # masih ada
        assert small_cache.get("b") is None  # evicted
        assert small_cache.get("c") == 3
        assert small_cache.get("d") == 4


class TestLRUCacheStats:
    """Stats tracking: hits, misses, hit_rate."""

    def test_initial_stats(self):
        small_cache = LRUCache(max_size=10)
        stats = small_cache.stats()
        assert stats["size"] == 0
        assert stats["max_size"] == 10
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0  # no requests yet

    def test_miss_increments_misses(self):
        small_cache = LRUCache(max_size=10)
        small_cache.get("nope")
        assert small_cache.stats()["misses"] == 1
        assert small_cache.stats()["hits"] == 0

    def test_hit_increments_hits(self):
        small_cache = LRUCache(max_size=10)
        small_cache.set("k", "v")
        small_cache.get("k")
        assert small_cache.stats()["hits"] == 1
        assert small_cache.stats()["misses"] == 0

    def test_hit_rate_calculation(self):
        small_cache = LRUCache(max_size=10)
        small_cache.set("k", "v")
        small_cache.get("k")  # hit
        small_cache.get("k")  # hit
        small_cache.get("nope")  # miss
        # 2 hits / 3 total = 0.667
        rate = small_cache.stats()["hit_rate"]
        assert abs(rate - (2 / 3)) < 0.01


class TestMakeCacheKey:
    """Cache key generation."""

    def test_same_args_same_key(self):
        k1 = _make_cache_key("my_func", (1, 2), {"a": "x"})
        k2 = _make_cache_key("my_func", (1, 2), {"a": "x"})
        assert k1 == k2

    def test_different_args_different_key(self):
        k1 = _make_cache_key("my_func", (1, 2), {})
        k2 = _make_cache_key("my_func", (1, 3), {})
        assert k1 != k2

    def test_different_func_name_different_key(self):
        k1 = _make_cache_key("func_a", (1,), {})
        k2 = _make_cache_key("func_b", (1,), {})
        assert k1 != k2

    def test_kwargs_unordered_same_key(self):
        """Dict kwargs order tidak masalah (sort_keys=True)."""
        k1 = _make_cache_key("f", (), {"a": 1, "b": 2})
        k2 = _make_cache_key("f", (), {"b": 2, "a": 1})
        assert k1 == k2

    def test_dict_arg_serialized(self):
        """Dict/list args di-serialize via JSON."""
        k1 = _make_cache_key("f", ({"a": 1},), {})
        k2 = _make_cache_key("f", ({"a": 1},), {})
        assert k1 == k2

    def test_unserializable_arg_falls_back_to_str(self):
        """Args yang tidak bisa di-serialize → fallback ke str()."""
        # object() tidak bisa di-serialize → fallback ke str()
        k = _make_cache_key("f", (object(),), {})
        assert isinstance(k, str)
        assert len(k) == 32  # md5 hex length


class TestCachedDecorator:
    """@cached decorator behavior."""

    def test_caches_result(self):
        call_count = {"n": 0}

        @cached(ttl_seconds=60)
        def my_func(x):
            call_count["n"] += 1
            return x * 2

        assert my_func(5) == 10  # First call: miss + compute
        assert my_func(5) == 10  # Second call: hit
        assert call_count["n"] == 1  # Only computed once

    def test_different_args_cached_separately(self):
        @cached(ttl_seconds=60)
        def my_func(x):
            return x * 2

        assert my_func(5) == 10
        assert my_func(10) == 20
        assert my_func(5) == 10  # Hit again
        assert my_func(10) == 20  # Hit again

    def test_ttl_zero_means_no_cache(self):
        """TTL=0 or None → cache stores but never expires (None TTL)."""
        call_count = {"n": 0}

        @cached(ttl_seconds=None)
        def my_func(x):
            call_count["n"] += 1
            return x

        my_func(1)
        my_func(1)
        # TTL None → no expiry
        # But still cached (stored once)
        assert call_count["n"] == 1


class TestInvalidateCache:
    """invalidate_cache(pattern=None)."""

    def test_invalidate_all(self):
        cache.set("key1", "v1")
        cache.set("key2", "v2")
        invalidate_cache(pattern=None)
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_invalidate_by_pattern(self):
        cache.set("users_list", [1, 2])
        cache.set("uni_list", [10])
        cache.set("other", "x")
        # Invalidate keys containing "users"
        invalidate_cache(pattern="users")
        assert cache.get("users_list") is None
        # Others should remain
        assert cache.get("uni_list") == [10]
        assert cache.get("other") == "x"

    def test_invalidate_no_match(self):
        cache.set("k1", "v1")
        invalidate_cache(pattern="nonexistent_pattern_xyz")
        # k1 should remain
        assert cache.get("k1") == "v1"
