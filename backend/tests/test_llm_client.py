"""Regression: chat_json must survive a reasoning model's non-deterministic,
sometimes-truncated JSON (MiniMax-M3). It asks for JSON with low reasoning
(economy think-level) and retries a truncated response before giving up.

Post-merge API: chat_json routes through self._create_completion (returning a
Chat Completions response object) and retries up to max_attempts. The economy
reasoning_effort='low' behaviour is threaded through _create_completion.
"""
from types import SimpleNamespace

import pytest

from app.utils.llm_client import LLMClient


def _client():
    # __init__ builds an OpenAI client but makes no network call.
    return LLMClient(api_key="test-key", base_url="http://localhost:9", model="MiniMax-M3")


def _resp(content, finish_reason="stop"):
    """Minimal Chat Completions response shape consumed by _parse_json_response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(
            finish_reason=finish_reason,
            message=SimpleNamespace(content=content),
        )]
    )


def test_chat_json_retries_a_truncated_response_then_succeeds():
    client = _client()
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        # 1st attempt truncated at the token limit; 2nd attempt complete.
        if len(calls) == 1:
            return _resp('{"entity_types": [{"name": "Bra', finish_reason="length")
        return _resp('{"entity_types": [], "edge_types": []}')

    client._create_completion = fake_create
    result = client.chat_json(
        messages=[{"role": "user", "content": "x"}], max_attempts=2
    )

    assert result == {"entity_types": [], "edge_types": []}
    assert len(calls) == 2  # retried exactly once


def test_chat_json_low_reasoning_in_economy_mode(tmp_path, monkeypatch):
    import app.utils.app_settings as app_settings
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", str(tmp_path / "s.json"))

    client = _client()
    seen = {}

    def fake_create(**kwargs):
        seen.update(kwargs)
        return _resp('{"ok": true}')

    client._create_completion = fake_create
    client.chat_json(messages=[{"role": "user", "content": "x"}])

    assert seen["response_format"] == {"type": "json_object"}
    assert seen["reasoning_effort"] == "low"  # economy is the default


def test_chat_json_sends_no_reasoning_param_in_deep_mode(tmp_path, monkeypatch):
    import app.utils.app_settings as app_settings
    from app.utils.app_settings import set_setting
    path = str(tmp_path / "s.json")
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", path)
    set_setting("think_level", "deep", path=path)

    client = _client()
    seen = {}

    def fake_create(**kwargs):
        seen.update(kwargs)
        return _resp('{"ok": true}')

    client._create_completion = fake_create
    client.chat_json(messages=[{"role": "user", "content": "x"}])

    assert seen.get("reasoning_effort") is None  # provider-stock behavior


def test_chat_json_raises_after_exhausting_retries():
    client = _client()

    def always_truncated(**kwargs):
        return _resp('{"broken":', finish_reason="length")

    client._create_completion = always_truncated
    with pytest.raises(ValueError):  # LLMResponseError subclasses ValueError
        client.chat_json(
            messages=[{"role": "user", "content": "x"}], max_attempts=2
        )
