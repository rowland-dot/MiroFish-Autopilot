"""TDD: simulation queue (slot=1 running + queue=2 waiting = capacity 3).

Pure logic. Decides start/queue/full, holds FIFO waiting list, promotes
oldest, cancels/evicts by id, reports capacity_full.
"""
import pytest

from app.services.simulation_queue import SimulationQueue, QueueFull


def _entry(sid, platform="reddit"):
    return {"simulation_id": sid, "platform": platform, "max_rounds": None}


def test_decide_start_when_slot_free():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    assert q.decide(running_count=0) == "start"


def test_decide_queue_when_slot_busy_and_room():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    assert q.decide(running_count=1) == "queue"


def test_decide_full_when_slot_busy_and_queue_full():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    assert q.decide(running_count=1) == "full"


def test_enqueue_raises_when_queue_limit_reached():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    with pytest.raises(QueueFull):
        q.enqueue(_entry("c"))


def test_dequeue_is_fifo():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("first"))
    q.enqueue(_entry("second"))
    assert q.dequeue()["simulation_id"] == "first"
    assert q.dequeue()["simulation_id"] == "second"
    assert q.dequeue() is None


def test_ids_reflect_order():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    assert q.ids() == ["a", "b"]


def test_cancel_removes_by_id():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    assert q.cancel("a") is True
    assert q.ids() == ["b"]
    assert q.cancel("missing") is False


def test_remove_evicts_queued_id_for_delete():
    # B7: deleting a queued sim must evict it before its config is gone
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    assert q.remove("a") is True
    assert q.ids() == []


def test_capacity_full_only_when_slot_busy_and_queue_full():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    assert q.capacity_full(running_count=0) is False
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    assert q.capacity_full(running_count=0) is False  # slot still free
    assert q.capacity_full(running_count=1) is True    # slot busy + queue full


def test_queue_full_but_slot_free_still_starts():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a"))
    q.enqueue(_entry("b"))
    # slot free -> a new submit starts immediately even though queue full
    assert q.decide(running_count=0) == "start"


def test_contains_and_get():
    q = SimulationQueue(slot_limit=1, queue_limit=2)
    q.enqueue(_entry("a", platform="twitter"))
    assert q.contains("a") is True
    assert q.get("a")["platform"] == "twitter"
    assert q.contains("z") is False
