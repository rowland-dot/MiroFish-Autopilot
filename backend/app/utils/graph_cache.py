"""Short-TTL in-memory cache for graph-viz reads.

Collapses repeated /api/graph/data polls (and multiple viewers) into one Zep
read per TTL window. Time is injectable for tests.
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""

import time


class TTLCache:
    def __init__(self, ttl_seconds: float = 30.0):
        self.ttl = ttl_seconds
        self._store = {}  # key -> (value, expires_at)

    def get(self, key, now=None):
        now = time.time() if now is None else now
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if now >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key, value, now=None):
        now = time.time() if now is None else now
        self._store[key] = (value, now + self.ttl)
