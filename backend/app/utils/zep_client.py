"""Zep failover execution: run an op, retry on 429, rotate keys on exhaustion.

Composes ZepKeyManager (multi-account) + call_with_retry (429 back-off). The
Zep client is built per active key via a factory. A module-level singleton
(configured from env keys) is used by graph_builder / zep_tools.

Spec: docs/specs/2026-07-24-zep-burn-reduction-spec.md
"""

from .zep_key_manager import ZepKeyManager, AllKeysExhausted, keys_from_env
from .zep_retry import call_with_retry, is_rate_error


def execute(op, manager: ZepKeyManager, build_client, max_retries: int = 3,
            base_delay: float = 2.0, sleep_fn=None):
    """Run op(client) with 429 retry; on persistent rate error rotate to the
    next key and retry; raise AllKeysExhausted when every key is spent.
    """
    kwargs = {"max_retries": max_retries, "base_delay": base_delay}
    if sleep_fn is not None:
        kwargs["sleep_fn"] = sleep_fn
    while True:
        client = build_client(manager.current())
        try:
            return call_with_retry(lambda: op(client), **kwargs)
        except Exception as exc:
            if not is_rate_error(exc):
                raise
            manager.rotate()  # raises AllKeysExhausted when no keys remain


# ---- module singleton (app wiring) ----
_manager = None


def _build_zep(key):
    from zep_cloud.client import Zep
    return Zep(api_key=key)


def init_manager(env):
    """(Re)build the singleton key manager from environment. Returns it or None
    if no keys are configured (feature degrades to the plain client elsewhere)."""
    global _manager
    keys = keys_from_env(env)
    _manager = ZepKeyManager(keys) if keys else None
    return _manager


def get_manager():
    return _manager


def active_client():
    """Zep client for the current active key (falls back to plain construction
    when the manager isn't configured)."""
    if _manager is None:
        return None
    return _build_zep(_manager.current())


def run(op):
    """Run op(client) with retry + key failover using the singleton manager."""
    if _manager is None:
        raise RuntimeError("Zep key manager not initialised")
    return execute(op, _manager, _build_zep)
