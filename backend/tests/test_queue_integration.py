"""TDD: SimulationRunner queue integration — submit_start + promote_next.

Mocks the real launcher (start_simulation) and list_running so no
subprocess spawns. Verifies the slot/queue decision and FIFO promote.
"""
import pytest

from app.services.simulation_runner import SimulationRunner
from app.services.simulation_queue import SimulationQueue


@pytest.fixture(autouse=True)
def fresh_queue(monkeypatch):
    # isolate: fresh queue + no real launches, controllable running count
    monkeypatch.setattr(SimulationRunner, "_queue", SimulationQueue(slot_limit=1, queue_limit=2))
    calls = {"started": []}
    monkeypatch.setattr(
        SimulationRunner, "start_simulation",
        classmethod(lambda cls, **kw: calls["started"].append(kw) or type("S", (), {"to_dict": lambda self: kw})()),
    )
    running = {"ids": []}
    monkeypatch.setattr(SimulationRunner, "list_running", classmethod(lambda cls: list(running["ids"])))
    # no-op status sync so promote doesn't need a real manager
    monkeypatch.setattr(SimulationRunner, "_mark_running_status", classmethod(lambda cls, sid: None), raising=False)
    return calls, running


def _payload(sid):
    return {"simulation_id": sid, "platform": "parallel", "max_rounds": None,
            "enable_graph_memory_update": False, "graph_id": None}


def test_submit_starts_when_slot_free(fresh_queue):
    calls, running = fresh_queue
    outcome, _ = SimulationRunner.submit_start(_payload("a"))
    assert outcome == "started"
    assert calls["started"][0]["simulation_id"] == "a"


def test_submit_queues_when_busy(fresh_queue):
    calls, running = fresh_queue
    running["ids"] = ["a"]                       # slot busy
    outcome, _ = SimulationRunner.submit_start(_payload("b"))
    assert outcome == "queued"
    assert calls["started"] == []               # no launch
    assert SimulationRunner._queue.ids() == ["b"]


def test_submit_full_when_slot_busy_and_queue_full(fresh_queue):
    calls, running = fresh_queue
    running["ids"] = ["a"]
    SimulationRunner.submit_start(_payload("b"))
    SimulationRunner.submit_start(_payload("c"))
    outcome, _ = SimulationRunner.submit_start(_payload("d"))
    assert outcome == "full"
    assert SimulationRunner._queue.ids() == ["b", "c"]


def test_promote_next_starts_oldest_when_slot_free(fresh_queue):
    calls, running = fresh_queue
    running["ids"] = ["a"]
    SimulationRunner.submit_start(_payload("b"))
    SimulationRunner.submit_start(_payload("c"))
    # running finishes -> slot free
    running["ids"] = []
    SimulationRunner.promote_next()
    assert calls["started"][0]["simulation_id"] == "b"   # FIFO
    assert SimulationRunner._queue.ids() == ["c"]


def test_promote_next_noop_when_queue_empty(fresh_queue):
    calls, running = fresh_queue
    SimulationRunner.promote_next()
    assert calls["started"] == []


def test_promote_next_noop_when_slot_busy(fresh_queue):
    calls, running = fresh_queue
    running["ids"] = ["a"]
    SimulationRunner.submit_start(_payload("b"))
    SimulationRunner.promote_next()              # slot still busy
    assert calls["started"] == []
    assert SimulationRunner._queue.ids() == ["b"]
