"""Bounded in-process read-through cache for public, non-personal catalog reads.

Design constraints (see docs/adr/ADR-003-caching-and-read-replicas.md):
* Only anonymous, non-personal responses are cached; never sessions, orders or money.
* Quotes and checkout always re-read the primary under row locks, so a stale listing
  can never change what a buyer is charged or oversell stock.
* Entries expire after a short TTL; writers in this process invalidate a namespace
  immediately, and other replicas converge within one TTL.
* A per-key lock gives single-flight loading, so a burst of identical misses runs the
  database query once instead of once per request (cache-stampede protection).
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any

from app.config import get_settings

DEFAULT_MAX_ENTRIES = 2048


class TTLCache:
    """A thread-safe LRU cache whose entries expire ``ttl_seconds`` after loading."""

    def __init__(self, max_entries: int = DEFAULT_MAX_ENTRIES, clock=time.monotonic):
        self._entries: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._loading: dict[Hashable, threading.Lock] = {}
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._clock = clock
        self.hits = 0
        self.misses = 0

    def _fresh(self, key):
        entry = self._entries.get(key)
        if entry and entry[0] > self._clock():
            self._entries.move_to_end(key)
            self.hits += 1
            return True, entry[1]
        return False, None

    def get_or_load(self, key: Hashable, ttl_seconds: float, loader: Callable[[], Any]):
        """Return a fresh cached value or load it once, even under concurrent misses."""
        if ttl_seconds <= 0:
            return loader()
        with self._lock:
            found, value = self._fresh(key)
            if found:
                return value
            key_lock = self._loading.setdefault(key, threading.Lock())
        with key_lock:
            with self._lock:
                found, value = self._fresh(key)
                if found:
                    return value
                self.misses += 1
            try:
                value = loader()
            finally:
                with self._lock:
                    self._loading.pop(key, None)
            with self._lock:
                self._entries[key] = (self._clock() + ttl_seconds, value)
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            return value

    def invalidate(self, namespace: str | None = None):
        """Drop every entry, or only keys whose first element equals ``namespace``."""
        with self._lock:
            if namespace is None:
                self._entries.clear()
                return
            for key in [k for k in self._entries if isinstance(k, tuple) and k[0] == namespace]:
                del self._entries[key]

    def __len__(self):
        with self._lock:
            return len(self._entries)


CATALOG = "catalog"
TRANSLATIONS = "translations"
STATS = "stats"

_shared = TTLCache()


def shared() -> TTLCache:
    """The process-wide cache instance."""
    return _shared


def cached(namespace: str, key: tuple, loader: Callable[[], Any], ttl_seconds=None):
    """Read through the shared cache with the configured public TTL by default."""
    ttl = get_settings().public_cache_seconds if ttl_seconds is None else ttl_seconds
    return _shared.get_or_load((namespace, *key), ttl, loader)


def invalidate_catalog():
    """Call after any seller write that changes what public catalog reads return."""
    _shared.invalidate(CATALOG)
    _shared.invalidate(STATS)
