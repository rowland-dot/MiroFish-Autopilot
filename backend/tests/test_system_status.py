"""TDD: system busy-check — used by the deploy guard to never disrupt a job.

A deploy rebuilds the container and kills any live process, so deploy must
refuse while a simulation is running or a report/graph task is in progress.
"""
from app.utils.system_status import is_busy


def test_idle_is_not_busy():
    assert is_busy(running_simulations=[], task_statuses=[]) is False
    assert is_busy(running_simulations=[], task_statuses=["completed", "failed"]) is False


def test_a_running_simulation_is_busy():
    assert is_busy(running_simulations=["sim_abc"], task_statuses=[]) is True


def test_a_processing_task_is_busy():
    assert is_busy(running_simulations=[], task_statuses=["processing"]) is True


def test_a_pending_task_is_busy():
    assert is_busy(running_simulations=[], task_statuses=["pending"]) is True


def test_mixed_completed_and_pending_is_busy():
    assert is_busy(running_simulations=[], task_statuses=["completed", "pending"]) is True
