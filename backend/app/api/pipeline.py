"""流水线状态 API：队列与卡片状态的服务器端存储。

独立蓝图，不改动上游文件（fork 需频繁与 upstream 同步）。
位于 /api/ 下，自动继承访问口令门（app 级 before_request，见 auth.py）。

Spec: docs/specs/2026-07-28-server-persisted-pipeline-state-spec.md
"""

import os

from flask import Blueprint, jsonify, request

from ..config import Config
from ..utils.pipeline_state import (
    default_path, expire_stale_active, load_entries, mutate_entries, prune_entries, reconcile_with_runs,
    remove_entry, run_status_reader, upsert_entry,
)

pipeline_bp = Blueprint('pipeline', __name__)


def _ok(entries):
    return jsonify({"success": True, "data": {"entries": entries}})


def _heal(entries):
    """Release entries whose simulation already finished, then prune.

    Self-healing: if the browser that owned an entry died, its run record is
    the ground truth — without this the entry holds the slot forever and the
    queue never moves.
    """
    reader = run_status_reader(os.path.join(Config.UPLOAD_FOLDER, 'simulations'))
    return prune_entries(reconcile_with_runs(expire_stale_active(entries), reader))


@pipeline_bp.route('', methods=['GET'], strict_slashes=False)
def get_pipeline():
    """读取条目（顺带清理并落盘，避免只读时文件无限增长）。"""
    # 看门狗：收尾卡死的 run（轮次跑满却停在 running）会占槽冻结整个队列，
    # 任何打开的浏览器每次轮询都顺带巡查一遍（内部 60s 节流）
    from ..utils.run_state_reconcile import watchdog_tick
    watchdog_tick(os.path.join(Config.UPLOAD_FOLDER, 'simulations'))
    return _ok(mutate_entries(default_path(), _heal))


@pipeline_bp.route('', methods=['POST'], strict_slashes=False)
def upsert_pipeline():
    """新增/更新一条（按 tmpId）。"""
    entry = request.get_json(silent=True) or {}
    if not entry.get('tmpId'):
        return jsonify({"success": False, "error": "tmpId is required"}), 400
    return _ok(mutate_entries(
        default_path(), lambda es: _heal(upsert_entry(es, entry))))


def cancel_entry_work(entry, cancel_task, cancel_for_sim, stop_sim):
    """删除条目 = 零残留：取消其名下所有后台工作。纯函数，依赖注入便于测试。

    - buildTaskId：图谱构建线程（协作式取消，下次进度更新即退出）
    - simId：prepare/report 任务（metadata 匹配）+ 停掉模拟进程本身
    """
    if not entry:
        return
    if entry.get("buildTaskId"):
        try:
            cancel_task(entry["buildTaskId"])
        except Exception:
            pass
    if entry.get("simId"):
        try:
            cancel_for_sim(entry["simId"])
        except Exception:
            pass
        try:
            stop_sim(entry["simId"])
        except Exception:
            pass


def _stop_sim_if_running(simulation_id):
    from ..services.simulation_runner import SimulationRunner
    if simulation_id in SimulationRunner.list_running():
        SimulationRunner.stop_simulation(simulation_id)


@pipeline_bp.route('/<tmp_id>', methods=['DELETE'])
def delete_pipeline(tmp_id):
    """删除一条（取消排队 / 清理）。未知 id 也返回 200，便于幂等重试。

    删除即取消：该条目名下已在跑的后台工作（建图/prepare/报告/模拟进程）
    一并终止——此前它们会作为孤儿跑完，白烧 Zep 与 LLM 配额。
    """
    from ..models.task import TaskManager
    entry = next((e for e in load_entries(default_path()) if e.get("tmpId") == tmp_id), None)
    tm = TaskManager()
    cancel_entry_work(entry, tm.cancel_task, tm.cancel_tasks_for_simulation, _stop_sim_if_running)
    return _ok(mutate_entries(
        default_path(), lambda es: _heal(remove_entry(es, tmp_id))))
