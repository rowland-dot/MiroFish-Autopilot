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


def test_busy_includes_active_pipeline_entries():
    # The deploy guard reads `busy`. A job in ontology/graph-build/prepare has
    # NO live OASIS subprocess, so busy was False and deploys killed it.
    from app.utils.system_status import is_busy
    active_pipeline = [{"tmpId": "a", "status": "preparing"}]
    assert is_busy([], [], pipeline_entries=active_pipeline) is True


def test_busy_ignores_queued_and_finished_pipeline_entries():
    from app.utils.system_status import is_busy
    idle = [{"tmpId": "a", "status": "queued"}, {"tmpId": "b", "status": "done"}]
    assert is_busy([], [], pipeline_entries=idle) is False


def test_busy_backwards_compatible_without_pipeline_arg():
    from app.utils.system_status import is_busy
    assert is_busy([], []) is False
    assert is_busy(["sim_1"], []) is True


def test_task_statuses_of_reads_dicts_from_task_manager():
    # TaskManager.list_tasks() returns DICTS (to_dict()); the status endpoint
    # read them with getattr() so every status came back '' and the deploy
    # guard was blind to report/build/prepare tasks.
    from app.utils.system_status import task_statuses_of
    tasks = [{"status": "processing"}, {"status": "completed"}]
    assert task_statuses_of(tasks) == ["processing", "completed"]
    assert is_busy([], task_statuses_of(tasks)) is True


def test_task_statuses_of_reads_objects_and_enums():
    from app.utils.system_status import task_statuses_of

    class T:
        status = "TaskStatus.PENDING"
    assert task_statuses_of([T()]) == ["pending"]
    assert task_statuses_of([]) == []
