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


# ---- activation cap (agents_per_hour) --------------------------------------
# The upstream merge's whole-document ontology coverage tripled entity counts,
# and the config LLM scales per-hour activation to entity count (2-8 pre-merge
# -> 3-12 after). Round cost scales directly with activated agents. Clamp the
# ceiling back to the pre-merge envelope; env-tunable like MAX_SIM_HOURS.

def _parse_agents(hours_result):
    gen = SimulationConfigGenerator.__new__(SimulationConfigGenerator)
    cfg = gen._parse_time_config(hours_result, num_entities=17)
    return cfg.agents_per_hour_min, cfg.agents_per_hour_max


def test_activation_ceiling_clamped_to_8():
    lo, hi = _parse_agents({"agents_per_hour_min": 5, "agents_per_hour_max": 12})
    assert hi == 8
    assert lo == 5


def test_activation_within_cap_kept():
    lo, hi = _parse_agents({"agents_per_hour_min": 2, "agents_per_hour_max": 6})
    assert (lo, hi) == (2, 6)


def test_activation_min_follows_ceiling_down():
    # LLM picked min 10 / max 12 -> ceiling 8 must also pull min below it
    lo, hi = _parse_agents({"agents_per_hour_min": 10, "agents_per_hour_max": 12})
    assert hi == 8
    assert lo <= hi


def test_activation_cap_env_tunable(monkeypatch):
    monkeypatch.setenv("MAX_AGENTS_PER_HOUR", "5")
    _, hi = _parse_agents({"agents_per_hour_min": 2, "agents_per_hour_max": 12})
    assert hi == 5
