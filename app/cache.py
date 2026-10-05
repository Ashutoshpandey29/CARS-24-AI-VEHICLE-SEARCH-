"""Small key/value cache with TTL.

In-process LRU by default. Set REDIS_URL to share the cache between workers
and instances (needs the `redis` package).
"""
import logging
import threading
import time
from collections import OrderedDict
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: int) -> None: ...
    def clear(self) -> None: ...


class MemoryCache:
    def __init__(self, maxsize: int):
        self.maxsize = maxsize
        self._data: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires, value = item
            if expires < time.monotonic():
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class RedisCache:
    def __init__(self, url: str, prefix: str = "vs:"):
        import redis

        self._r = redis.Redis.from_url(url, socket_timeout=0.5, decode_responses=True)
        self._prefix = prefix

    def get(self, key: str) -> str | None:
        try:
            return self._r.get(self._prefix + key)
        except Exception as e:  # cache trouble should never break a search
            log.warning("redis get failed: %s", e)
            return None

    def set(self, key: str, value: str, ttl: int) -> None:
        try:
            self._r.set(self._prefix + key, value, ex=ttl)
        except Exception as e:
            log.warning("redis set failed: %s", e)

    def clear(self) -> None:
        for key in self._r.scan_iter(self._prefix + "*"):
            self._r.delete(key)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        s = get_settings()
        _cache = RedisCache(s.redis_url) if s.redis_url else MemoryCache(s.cache_size)
    return _cache
