"""TDD: multi-Zep-key failover manager.

Holds ordered keys; rotates to the next when one is exhausted/rate-limited;
raises when all are spent.
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""
import pytest

from app.utils.zep_key_manager import ZepKeyManager, AllKeysExhausted


def test_current_returns_first_key():
    m = ZepKeyManager(["k1", "k2"])
    assert m.current() == "k1"


def test_rotate_advances_to_next():
    m = ZepKeyManager(["k1", "k2", "k3"])
    assert m.current() == "k1"
    assert m.rotate() == "k2"
    assert m.current() == "k2"
    assert m.rotate() == "k3"


def test_rotate_past_last_raises_all_exhausted():
    m = ZepKeyManager(["only"])
    with pytest.raises(AllKeysExhausted):
        m.rotate()


def test_blanks_and_dupes_dropped_order_preserved():
    m = ZepKeyManager(["k1", "", None, "k1", "k2", "  "])
    assert m.keys == ["k1", "k2"]


def test_empty_is_rejected():
    with pytest.raises(ValueError):
        ZepKeyManager([])
    with pytest.raises(ValueError):
        ZepKeyManager(["", None])
