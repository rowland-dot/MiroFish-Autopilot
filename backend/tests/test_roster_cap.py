"""TDD: agent roster cap.

Pre-merge economics were an accident: ontology truncated docs at 50k chars,
yielding 3-11 agents. Whole-document coverage now yields 14-17, and EVERY
inference's prompt scales with world size (fatter feeds + more memories) —
~2x per-job tokens with the same action count. Deliberate knob: keep the N
most-connected entities as agents (env MAX_SIM_AGENTS, default 12).
"""
from app.utils.roster_cap import cap_roster


class _E:
    def __init__(self, name, edges):
        self.name = name
        self.related_edges = [{}] * edges
        self.labels = ["Person"]


def test_keeps_the_most_connected_entities():
    ents = [_E("low", 1), _E("hub", 9), _E("mid", 4), _E("hub2", 8)]
    out = cap_roster(ents, max_agents=2)
    assert [e.name for e in out] == ["hub", "hub2"]


def test_under_cap_untouched_and_order_preserved():
    ents = [_E("a", 1), _E("b", 5)]
    assert cap_roster(ents, max_agents=12) == ents


def test_default_cap_from_env(monkeypatch):
    monkeypatch.setenv("MAX_SIM_AGENTS", "3")
    ents = [_E(f"e{i}", i) for i in range(10)]
    out = cap_roster(ents)
    assert len(out) == 3
    assert [e.name for e in out] == ["e9", "e8", "e7"]


def test_garbage_env_falls_back_to_12(monkeypatch):
    monkeypatch.setenv("MAX_SIM_AGENTS", "banana")
    ents = [_E(f"e{i}", 0) for i in range(20)]
    assert len(cap_roster(ents)) == 12
