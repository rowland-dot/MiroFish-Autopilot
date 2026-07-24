"""TDD: 429-aware retry wrapper for Zep calls.

Retries a callable when it raises a rate-limit error (waiting the retry-after),
raises after a bounded number of attempts, and never retries non-rate errors.
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""
import pytest

from app.utils.zep_retry import call_with_retry, is_rate_error


class FakeZepError(Exception):
    def __init__(self, status_code=None, body="", headers=None):
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}
        super().__init__(body)


def test_is_rate_error_detects_429_and_message():
    assert is_rate_error(FakeZepError(status_code=429)) is True
    assert is_rate_error(FakeZepError(body="Rate limit exceeded for FREE plan")) is True
    assert is_rate_error(FakeZepError(status_code=500, body="boom")) is False
    assert is_rate_error(ValueError("nope")) is False


def test_success_first_try_no_sleep():
    slept = []
    out = call_with_retry(lambda: "ok", sleep_fn=slept.append)
    assert out == "ok"
    assert slept == []


def test_retries_then_succeeds():
    calls = {"n": 0}
    slept = []
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise FakeZepError(status_code=429, headers={"retry-after": "0"})
        return "recovered"
    out = call_with_retry(fn, max_retries=3, sleep_fn=slept.append)
    assert out == "recovered"
    assert calls["n"] == 3
    assert len(slept) == 2  # slept before each retry


def test_raises_after_max_retries():
    def fn():
        raise FakeZepError(status_code=429)
    with pytest.raises(FakeZepError):
        call_with_retry(fn, max_retries=2, sleep_fn=lambda s: None)


def test_non_rate_error_is_not_retried():
    calls = {"n": 0}
    def fn():
        calls["n"] += 1
        raise ValueError("permanent")
    with pytest.raises(ValueError):
        call_with_retry(fn, max_retries=3, sleep_fn=lambda s: None)
    assert calls["n"] == 1  # no retry
