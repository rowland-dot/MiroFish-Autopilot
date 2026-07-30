"""TDD: simulation duration cap.

The config LLM is prompted to pick 24-168 simulated hours and its answer was
used unclamped -- jobs silently ran 96 and 120 rounds. The run stage is
~80-92% of all LLM cost, so an uncapped pick is an uncontrolled bill.
"""
from app.services.simulation_config_generator import SimulationConfigGenerator


def _parse(hours):
    gen = SimulationConfigGenerator.__new__(SimulationConfigGenerator)  # no LLM client needed
    cfg = gen._parse_time_config({"total_simulation_hours": hours}, num_entities=17)
    return cfg.total_simulation_hours


def test_llm_pick_above_cap_is_clamped_to_72():
    assert _parse(96) == 72
    assert _parse(120) == 72
    assert _parse(168) == 72


def test_llm_pick_within_cap_is_kept():
    assert _parse(48) == 48
    assert _parse(72) == 72


def test_absurdly_low_pick_is_floored():
    assert _parse(3) == 24
    assert _parse(0) == 72     # missing/zero falls back to the default, not the floor


def test_cap_overridable_via_env(monkeypatch):
    monkeypatch.setenv("MAX_SIM_HOURS", "48")
    assert _parse(72) == 48
