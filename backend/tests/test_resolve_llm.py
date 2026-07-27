"""TDD: LLM provider routing for the model switch (MiniMax M3 / DeepSeek V4 Pro)."""
from app.utils.resolve_llm import resolve_llm, build_sim_env

MINIMAX_ENV = {"LLM_API_KEY": "mm_key", "LLM_BASE_URL": "https://api.minimaxi.com/v1"}
DS_ENV = {**MINIMAX_ENV, "DEEPSEEK_API_KEY": "ds_key"}


def test_resolve_minimax():
    r = resolve_llm("minimax-m3", MINIMAX_ENV)
    assert r == {"api_key": "mm_key", "base_url": "https://api.minimaxi.com/v1", "model": "MiniMax-M3"}


def test_resolve_minimax_base_default():
    r = resolve_llm("minimax-m3", {"LLM_API_KEY": "mm_key"})
    assert r["base_url"] == "https://api.minimaxi.com/v1"


def test_resolve_deepseek():
    r = resolve_llm("deepseek-v4-pro", DS_ENV)
    assert r == {"api_key": "ds_key", "base_url": "https://api.deepseek.com", "model": "deepseek-v4-pro"}


def test_resolve_deepseek_missing_key_falls_back_to_minimax():
    r = resolve_llm("deepseek-v4-pro", MINIMAX_ENV)
    assert r["model"] == "MiniMax-M3" and r["api_key"] == "mm_key"


def test_resolve_unknown_falls_back_to_minimax():
    assert resolve_llm("gpt-9", MINIMAX_ENV)["model"] == "MiniMax-M3"


def test_build_sim_env_minimax_untouched():
    env = build_sim_env({"LLM_API_KEY": "mm_key", "X": "1"}, "minimax-m3")
    assert env["LLM_API_KEY"] == "mm_key" and env["LLM_MODEL_NAME"] == "MiniMax-M3" and env["X"] == "1"


def test_build_sim_env_deepseek_overrides_general_and_boost():
    env = build_sim_env(DS_ENV, "deepseek-v4-pro")
    assert env["LLM_API_KEY"] == "ds_key"
    assert env["LLM_BASE_URL"] == "https://api.deepseek.com"
    assert env["LLM_MODEL_NAME"] == "deepseek-v4-pro"
    assert env["LLM_BOOST_API_KEY"] == "ds_key"
    assert env["LLM_BOOST_MODEL_NAME"] == "deepseek-v4-pro"


def test_build_sim_env_returns_copy():
    base = {"LLM_API_KEY": "mm_key"}
    build_sim_env(base, "deepseek-v4-pro")
    assert base == {"LLM_API_KEY": "mm_key"}
