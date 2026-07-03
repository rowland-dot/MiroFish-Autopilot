"""Model configuration for the high-volume OASIS simulation agents.

The simulation loop makes one model call per agent action across many rounds
and agents. On a reasoning model like MiniMax-M3, ~80% of the completion
tokens are reasoning the code then discards. `reasoning_effort="low"` roughly
halves completion tokens per call while still returning a complete answer —
a large cost cut with no model downgrade.

This is intentionally NOT applied to the report agent, which keeps full
reasoning via its own LLMClient path (the high-value analysis output).
"""

SIMULATION_REASONING_EFFORT = "low"


def simulation_model_config() -> dict:
    """Return the model_config_dict for OASIS simulation agents."""
    return {"reasoning_effort": SIMULATION_REASONING_EFFORT}
