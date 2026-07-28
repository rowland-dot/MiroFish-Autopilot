"""系统状态接口：报告是否有任务正在运行。

供部署安全脚本（deploy_hf.sh）在推送前查询——有任务在跑就中止部署，绝不打断。
位于 /api/ 下，AUTH_ENABLED 时受访问口令门保护（部署脚本本就会登录以备份）。
"""

from flask import Blueprint, jsonify

from ..models.task import TaskManager
from ..services.simulation_runner import SimulationRunner
from ..utils.system_status import has_active_pipeline, is_busy

status_bp = Blueprint('status', __name__)

_ACTIVE = {"pending", "processing"}


@status_bp.route('/status', methods=['GET'])
def system_status():
    running = SimulationRunner.list_running()
    try:
        tasks = TaskManager().list_tasks()
        statuses = [str(getattr(t, 'status', '')).split('.')[-1].lower() for t in tasks]
    except Exception:
        statuses = []
    active_tasks = [s for s in statuses if s in _ACTIVE]
    queued = SimulationRunner._queue.ids()

    # 流水线条目：ontology/图谱构建/prepare 阶段没有 OASIS 子进程，
    # 不计入的话部署闸门看不到它们，会把准备中的任务直接杀掉。
    try:
        from ..utils.pipeline_state import default_path, load_entries
        pipeline_entries = load_entries(default_path())
    except Exception:
        pipeline_entries = []

    return jsonify({
        "success": True,
        "data": {
            "busy": is_busy(running, statuses, pipeline_entries),
            "pipeline_active": has_active_pipeline(pipeline_entries),
            "running_simulations": running,
            "active_tasks": len(active_tasks),
            # 排队器：等待中的模拟 id（有序）+ 是否已满（前端据此禁用开始区）
            "queued_simulations": queued,
            "capacity_full": SimulationRunner._queue.capacity_full(len(running)),
        }
    })
