"""TDD: OASIS simulation agents' model config follows the think-level setting.

经济 economy (default): reasoning_effort=low (cheap actions, MiniMax-validated).
深度 deep: empty config — no thinking-control parameter, provider-stock
behavior, compatible with any OpenAI-format API. The report agent is a
separate path and always runs full depth regardless.

Spec: docs/specs/2026-07-16-think-level-toggle-spec.md
"""
import os

import pytest

import app.utils.app_settings as app_settings
from app.utils.app_settings import set_setting
from app.utils.simulation_model import simulation_model_config


@pytest.fixture()
def settings_path(tmp_path, monkeypatch):
    path = str(tmp_path / "app_settings.json")
    monkeypatch.setattr(app_settings, "_DEFAULT_PATH", path)
    return path


def test_economy_is_the_default_and_sets_low_reasoning(settings_path):
    assert simulation_model_config() == {"reasoning_effort": "low"}


def test_deep_sends_no_thinking_parameters(settings_path):
    set_setting("think_level", "deep", path=settings_path)
    assert simulation_model_config() == {}


def test_camel_model_factory_accepts_the_economy_config(settings_path):
    # Proves camel's OpenAI backend accepts reasoning_effort and stores it.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType

    model = ModelFactory.create(
        model_platform=ModelPlatformType.OPENAI,
        model_type="MiniMax-M3",
        model_config_dict=simulation_model_config(),
    )
    assert model.model_config_dict.get("reasoning_effort") == "low"
