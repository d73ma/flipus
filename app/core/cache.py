"""
FLIPUS v1.2 — In-memory cache untuk hot read endpoints.

Cache strategy:
- LRU dengan max 256 entries
- TTL configurable per decorator
- Auto-cleanup expired entries

Digunakan untuk:
- /v1/master/uni, /v1/master/misi (jarang berubah)
- /v1/reports/sabat-info (per tanggal)
- /v1/users (user list cache 5 menit)

JANGAN dipakai untuk:
- Data yang sering berubah real-time (agregat, kuitansi)
- Endpoints dengan side effects (POST/PUT/DELETE)
"""

import functools
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional


class LRUCache:
    """Thread-safe LRU cache dengan TTL."""

    def __init__(self, max_size: int = 256):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            value, expires_at = self._cache[key]

            # Check TTL
            if expires_at and time.time() > expires_at:
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        with self._lock:
            # Compute expiry
            expires_at = time.time() + ttl_seconds if ttl_seconds else None

            if key in self._cache:
                # Update existing
                self._cache.move_to_end(key)
            self._cache[key] = (value, expires_at)

            # Evict oldest kalau over capacity
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str):
        with self._lock:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }


# Global cache instance
cache = LRUCache(max_size=256)


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate deterministic cache key dari function name + args."""
    # Serialize args/kwargs ke JSON
    try:
        # Convert non-serializable args to str
        safe_args = tuple(
            json.dumps(arg, sort_keys=True, default=str)
            if isinstance(arg, (dict, list))
            else str(arg)
            for arg in args
        )
        safe_kwargs = {
            k: json.dumps(v, sort_keys=True, default=str)
            if isinstance(v, (dict, list))
            else str(v)
            for k, v in sorted(kwargs.items())
        }
    except Exception:
        safe_args = tuple(str(a) for a in args)
        safe_kwargs = {k: str(v) for k, v in kwargs.items()}

    payload = f"{func_name}|{safe_args}|{safe_kwargs}"
    return hashlib.md5(payload.encode()).hexdigest()


def cached(ttl_seconds: int = 300):
    """
    Decorator untuk cache hasil function.

    Args:
        ttl_seconds: Time-to-live dalam detik (default 5 menit)

    Usage:
        @cached(ttl_seconds=600)
        def list_uni():
            return db.query(Uni).all()
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = _make_cache_key(func.__qualname__, args, kwargs)

            # Try cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Compute
            result = func(*args, **kwargs)

            # Store
            cache.set(cache_key, result, ttl_seconds=ttl_seconds)
            return result

        return wrapper
    return decorator


def invalidate_cache(pattern: Optional[str] = None):
    """
    Invalidate cache entries.

    Args:
        pattern: substring match (None = clear all)
    """
    if pattern is None:
        cache.clear()
        return

    # Iterate dan delete matching
    # Note: LRUCache.delete() per-key
    keys_to_delete = []
    with cache._lock:
        for key in list(cache._cache.keys()):
            # Pattern matching by string conversion
            if pattern in str(key):
                keys_to_delete.append(key)
    for k in keys_to_delete:
        cache.delete(k)