"""TDD: OASIS simulation agents run M3 with reduced reasoning.

The high-volume simulation loop (72 rounds x many agents) makes a model call
per agent action. M3 spends ~80% of completion tokens on reasoning by default,
which is wasted on simple post/like/comment decisions. reasoning_effort='low'
roughly halves completion tokens while keeping a complete answer. The report
agent keeps full reasoning via its own LLMClient path.
"""
import os

from app.utils.simulation_model import simulation_model_config


def test_simulation_agents_use_low_reasoning_effort():
    cfg = simulation_model_config()
    assert cfg["reasoning_effort"] == "low"


def test_camel_model_factory_accepts_the_config():
    # Proves camel's OpenAI backend accepts reasoning_effort and stores it,
    # so the simulation scripts can pass it via model_config_dict.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="MiniMax-M3",
        model_config_dict=simulation_model_config(),
    )
    assert model.model_config_dict.get("reasoning_effort") == "low"
