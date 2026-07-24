"""429-aware retry for Zep calls.

Retries a callable on a rate-limit error (waiting the retry-after seconds),
raises after a bounded number of attempts, and never retries non-rate errors.
On final exhaustion the caller rotates to a fallback key (see zep_key_manager).
Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""

import time


def is_rate_error(exc) -> bool:
    """True if exc looks like a Zep 429 / rate-limit error."""
    if getattr(exc, "status_code", None) == 429:
        return True
    body = str(getattr(exc, "body", "")) + " " + str(exc)
    return "rate limit" in body.lower()


def _retry_after(exc, default: float) -> float:
    headers = getattr(exc, "headers", None) or {}
    try:
        return float(headers.get("retry-after", default))
    except (TypeError, ValueError):
        return default


def call_with_retry(fn, max_retries: int = 3, base_delay: float = 2.0, sleep_fn=time.sleep):
    """Call fn(); on a rate error retry up to max_retries, waiting retry-after.

    Non-rate errors propagate immediately. Raises the last rate error if all
    attempts are exhausted.
    """
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not is_rate_error(exc) or attempt >= max_retries:
                raise
            sleep_fn(_retry_after(exc, base_delay))
            attempt += 1
