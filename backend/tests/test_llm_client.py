"""Regression: chat_json must survive a reasoning model's non-deterministic,
sometimes-truncated JSON (MiniMax-M3). It asks for JSON with low reasoning and
retries a parse failure before giving up.

These tests fail against the pre-fix chat_json (single attempt, no
reasoning_effort), which raised on the first truncated response.
"""
import pytest

from app.utils.llm_client import LLMClient


def _client():
    # __init__ builds an OpenAI client but makes no network call.
    return LLMClient(api_key="test-key", base_url="http://localhost:9", model="MiniMax-M3")


def test_chat_json_retries_a_truncated_response_then_succeeds():
    client = _client()
    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        # 1st attempt truncated mid-object; 2nd attempt complete.
        if len(calls) == 1:
            return '{"entity_types": [{"name": "Bra'
        return '{"entity_types": [], "edge_types": []}'

    client.chat = fake_chat
    result = client.chat_json(messages=[{"role": "user", "content": "x"}])

    assert result == {"entity_types": [], "edge_types": []}
    assert len(calls) == 2  # retried exactly once


def test_chat_json_low_reasoning_in_economy_mode(tmp_path, monkeypatch):
    import app.utils.app_settings as app_settings
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", str(tmp_path / "s.json"))

    client = _client()
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return '{"ok": true}'

    client.chat = fake_chat
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

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return '{"ok": true}'

    client.chat = fake_chat
    client.chat_json(messages=[{"role": "user", "content": "x"}])

    assert seen.get("reasoning_effort") is None  # provider-stock behavior


def test_chat_json_raises_after_exhausting_retries():
    client = _client()

    def always_truncated(**kwargs):
        return '{"broken":'

    client.chat = always_truncated
    with pytest.raises(ValueError):
        client.chat_json(messages=[{"role": "user", "content": "x"}], max_retries=2)
