"""系统忙碌判定：是否有正在进行的工作，用于部署前的安全闸门。

部署会重建容器并杀掉进程，因此只要有任何在途工作，就必须拒绝部署。

重要：只看 OASIS 子进程是不够的。一条流水线在
ontology / 图谱构建 / create / prepare / 报告 阶段并没有 OASIS 子进程，
`busy` 曾因此返回 False，部署照常进行，把正在准备中的任务打断。
现在把流水线条目的活跃状态一并计入。
"""

# 视为"处理中"的任务状态
_IN_PROGRESS = {"pending", "processing"}

# 流水线中代表"在途"的状态（queued 不算：排队中尚未开始做事；
# done/failed 已结束）
PIPELINE_ACTIVE_STATUSES = {
    "ontology", "building", "creating", "preparing", "running", "reporting",
}


def has_active_pipeline(pipeline_entries) -> bool:
    """True 表示有流水线条目正在推进（即使还没有 OASIS 子进程）。"""
    return any(
        (e or {}).get("status") in PIPELINE_ACTIVE_STATUSES
        for e in (pipeline_entries or [])
    )


def task_statuses_of(tasks) -> list:
    """Normalize TaskManager.list_tasks() output (dicts OR objects, enum-ish
    strings) into plain lowercase status strings for is_busy()."""
    out = []
    for t in (tasks or []):
        raw = t.get("status") if isinstance(t, dict) else getattr(t, "status", "")
        out.append(str(raw or "").split(".")[-1].lower())
    return out


def is_busy(running_simulations, task_statuses, pipeline_entries=None) -> bool:
    """True 表示系统正忙：有模拟进程存活、有任务 pending/processing，
    或有流水线条目处于在途阶段（部署会杀掉它）。"""
    if running_simulations:
        return True
    if any(str(s).lower() in _IN_PROGRESS for s in (task_statuses or [])):
        return True
    return has_active_pipeline(pipeline_entries)
