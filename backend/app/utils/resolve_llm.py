"""Resolve LLM credentials for the active model (deployment-level switch).

Two providers: MiniMax M3 (env LLM_*) and DeepSeek V4 Pro (env
DEEPSEEK_API_KEY + fixed base/model). If DeepSeek is selected but its key
is missing/blank, fall back to MiniMax (never hard-fail a run).

Spec: docs/specs/2026-07-28-model-switch-minimax-deepseek-spec.md
"""

MINIMAX_MODEL = "MiniMax-M3"
MINIMAX_BASE_DEFAULT = "https://api.minimaxi.com/v1"
DEEPSEEK_MODEL = "deepseek-v4-pro"
DEEPSEEK_BASE = "https://api.deepseek.com"


def _minimax(env):
    return {
        "api_key": env.get("LLM_API_KEY"),
        "base_url": env.get("LLM_BASE_URL") or MINIMAX_BASE_DEFAULT,
        "model": MINIMAX_MODEL,
    }


def resolve_llm(active_model, env):
    """Return {api_key, base_url, model} for the active model."""
    if active_model == "deepseek-v4-pro":
        key = (env.get("DEEPSEEK_API_KEY") or "").strip()
        if key:
            return {"api_key": key, "base_url": DEEPSEEK_BASE, "model": DEEPSEEK_MODEL}
        return _minimax(env)          # missing key -> fallback
    return _minimax(env)              # minimax-m3 + any unknown


def build_sim_env(base_env, active_model):
    """Copy base_env with LLM_* (and, for DeepSeek, LLM_BOOST_*) set to the
    resolved provider so the OASIS subprocess agents use the active model."""
    env = dict(base_env)
    r = resolve_llm(active_model, base_env)
    env["LLM_API_KEY"] = r["api_key"] or ""
    env["LLM_BASE_URL"] = r["base_url"]
    env["LLM_MODEL_NAME"] = r["model"]
    if active_model == "deepseek-v4-pro" and (base_env.get("DEEPSEEK_API_KEY") or "").strip():
        env["LLM_BOOST_API_KEY"] = r["api_key"]
        env["LLM_BOOST_BASE_URL"] = r["base_url"]
        env["LLM_BOOST_MODEL_NAME"] = r["model"]
    return env
