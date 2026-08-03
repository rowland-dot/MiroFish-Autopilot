"""TDD: cancellation propagation — deleting a job leaves ZERO residual work.

Deleting a queue entry only removed the entry; already-running background
threads (graph build / prepare / report) ran to completion as orphans,
wasting Zep credits and LLM tokens. Cooperative cancellation: the task is
flagged, and the worker thread notices at its next progress update.
"""
import pytest

from app.models.task import TaskManager, TaskStatus, TaskCancelled


@pytest.fixture()
def tm():
    m = TaskManager()
    yield m


def test_cancel_flags_an_active_task(tm):
    tid = tm.create_task("graph_build")
    assert tm.cancel_task(tid) is True
    assert tm.get_task(tid).status == TaskStatus.CANCELLED


def test_cancel_never_overrides_a_finished_task(tm):
    tid = tm.create_task("graph_build")
    tm.complete_task(tid, {"ok": True})
    assert tm.cancel_task(tid) is False
    assert tm.get_task(tid).status == TaskStatus.COMPLETED


def test_worker_notices_cancellation_at_next_progress_update(tm):
    tid = tm.create_task("prepare")
    tm.cancel_task(tid)
    with pytest.raises(TaskCancelled):
        tm.update_task(tid, progress=50, message="halfway")


def test_late_failure_does_not_overwrite_cancelled(tm):
    # the worker's generic except must not flip cancelled -> failed
    tid = tm.create_task("prepare")
    tm.cancel_task(tid)
    tm.fail_task(tid, "boom after cancel")
    assert tm.get_task(tid).status == TaskStatus.CANCELLED


def test_cancel_all_tasks_for_a_simulation(tm):
    a = tm.create_task("simulation_prepare", metadata={"simulation_id": "sim_1"})
    b = tm.create_task("report_generate", metadata={"simulation_id": "sim_1"})
    c = tm.create_task("report_generate", metadata={"simulation_id": "sim_OTHER"})
    cancelled = tm.cancel_tasks_for_simulation("sim_1")
    assert set(cancelled) == {a, b}
    assert tm.get_task(c).status != TaskStatus.CANCELLED


def test_cancelled_tasks_do_not_hold_the_deploy_guard():
    from app.utils.system_status import is_busy, task_statuses_of

    class T:
        status = "TaskStatus.CANCELLED"
    assert is_busy([], task_statuses_of([T()])) is False


def test_entry_delete_propagates_to_all_work():
    from app.api.pipeline import cancel_entry_work
    calls = []
    entry = {"tmpId": "x", "simId": "sim_9", "buildTaskId": "bt1", "status": "preparing"}
    cancel_entry_work(
        entry,
        cancel_task=lambda tid: calls.append(("task", tid)),
        cancel_for_sim=lambda sid: calls.append(("sim-tasks", sid)) or [],
        stop_sim=lambda sid: calls.append(("stop", sid)),
    )
    assert ("task", "bt1") in calls
    assert ("sim-tasks", "sim_9") in calls
    assert ("stop", "sim_9") in calls


def test_entry_delete_with_no_ids_is_a_noop():
    from app.api.pipeline import cancel_entry_work
    calls = []
    cancel_entry_work({"tmpId": "x"},
                      cancel_task=lambda t: calls.append(t),
                      cancel_for_sim=lambda s: calls.append(s),
                      stop_sim=lambda s: calls.append(s))
    assert calls == []


def test_entry_delete_also_removes_never_ran_sim_record():
    # 删除测试留下过一张「未命名模拟·失败」的幽灵卡片：任务与进程都死了，
    # 但模拟的历史记录还在。从未真正运行过的模拟，删除条目时记录一并清掉
    from app.api.pipeline import cancel_entry_work
    calls = []
    entry = {"tmpId": "x", "simId": "sim_9", "status": "preparing"}
    cancel_entry_work(
        entry,
        cancel_task=lambda t: None,
        cancel_for_sim=lambda s: [],
        stop_sim=lambda s: None,
        remove_record=lambda s: calls.append(("rm", s)),
    )
    assert ("rm", "sim_9") in calls
