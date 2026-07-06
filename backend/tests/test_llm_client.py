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


def test_chat_json_requests_json_with_low_reasoning():
    client = _client()
    seen = {}

    def fake_chat(**kwargs):
        seen.update(kwargs)
        return '{"ok": true}'

    client.chat = fake_chat
    client.chat_json(messages=[{"role": "user", "content": "x"}])

    assert seen["response_format"] == {"type": "json_object"}
    assert seen["reasoning_effort"] == "low"


def test_chat_json_raises_after_exhausting_retries():
    client = _client()

    def always_truncated(**kwargs):
        return '{"broken":'

    client.chat = always_truncated
    with pytest.raises(ValueError):
        client.chat_json(messages=[{"role": "user", "content": "x"}], max_retries=2)
