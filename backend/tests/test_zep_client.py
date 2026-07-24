"""TDD: failover execution — run a Zep op, retry on 429, rotate keys on exhaustion.

Composes ZepKeyManager + call_with_retry. Client built per active key via an
injected factory (so tests need no real Zep).
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""
import pytest

from app.utils.zep_key_manager import ZepKeyManager, AllKeysExhausted
from app.utils.zep_client import execute


class RateErr(Exception):
    status_code = 429


def test_succeeds_on_first_key():
    mgr = ZepKeyManager(["k1", "k2"])
    seen = []
    out = execute(lambda client: (seen.append(client), "ok")[1],
                  manager=mgr, build_client=lambda k: f"client:{k}",
                  max_retries=0, sleep_fn=lambda s: None)
    assert out == "ok"
    assert seen == ["client:k1"]


def test_rotates_to_second_key_when_first_is_rate_limited():
    mgr = ZepKeyManager(["k1", "k2"])
    def op(client):
        if client == "client:k1":
            raise RateErr()          # first key always rate-limited
        return f"done-on-{client}"
    out = execute(op, manager=mgr, build_client=lambda k: f"client:{k}",
                  max_retries=1, sleep_fn=lambda s: None)
    assert out == "done-on-client:k2"
    assert mgr.current() == "k2"     # rotated


def test_all_keys_exhausted_raises():
    mgr = ZepKeyManager(["k1", "k2"])
    def op(client):
        raise RateErr()              # every key rate-limited
    with pytest.raises(AllKeysExhausted):
        execute(op, manager=mgr, build_client=lambda k: k,
                max_retries=1, sleep_fn=lambda s: None)
