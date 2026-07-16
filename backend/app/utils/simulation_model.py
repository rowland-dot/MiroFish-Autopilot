"""Model configuration for the high-volume OASIS simulation agents.

Follows the deployment's 思考深度 (think level) setting:

- 经济 economy (default): reasoning_effort="low" — on a reasoning model like
  MiniMax-M3 this roughly halves completion tokens per agent action with no
  model downgrade (validated on MiniMax only).
- 深度 deep: empty config — no thinking-control parameter is sent, so every
  model behaves exactly as its provider intended (compatible with any
  OpenAI-format API).

The report agent is a separate path (LLMClient) and always runs full depth.
Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""

from .app_settings import get_think_level


def simulation_model_config() -> dict:
    """Return the model_config_dict for OASIS simulation agents (read at call time)."""
    if get_think_level() == "economy":
        return {"reasoning_effort": "low"}
    return {}
