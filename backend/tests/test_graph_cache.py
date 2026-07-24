"""TDD: short-TTL cache for /api/graph/data.

Repeated graph-viz polls within the TTL return cached data (one Zep read per
window) instead of hitting Zep every poll.
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""
from app.utils.graph_cache import TTLCache


def test_hit_within_ttl():
    c = TTLCache(ttl_seconds=30)
    c.set("g1", {"nodes": [1]}, now=100.0)
    assert c.get("g1", now=120.0) == {"nodes": [1]}   # within 30s


def test_miss_after_ttl():
    c = TTLCache(ttl_seconds=30)
    c.set("g1", {"nodes": [1]}, now=100.0)
    assert c.get("g1", now=131.0) is None             # expired


def test_miss_for_unknown_key():
    c = TTLCache(ttl_seconds=30)
    assert c.get("nope", now=100.0) is None


def test_keys_are_independent():
    c = TTLCache(ttl_seconds=30)
    c.set("g1", "a", now=100.0)
    c.set("g2", "b", now=100.0)
    assert c.get("g1", now=110.0) == "a"
    assert c.get("g2", now=110.0) == "b"
