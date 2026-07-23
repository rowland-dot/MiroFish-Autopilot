"""系统忙碌判定：是否有正在运行的任务，用于部署前的安全闸门。

部署会重建容器并杀掉运行中的进程，因此在有模拟运行或报告/图谱任务处理中时，
必须拒绝部署——绝不打断正在跑的任务。
"""

# 视为"处理中"的任务状态
_IN_PROGRESS = {"pending", "processing"}


def is_busy(running_simulations, task_statuses) -> bool:
    """True 表示系统正忙：有模拟进程存活，或有任务处于 pending/processing。"""
    if running_simulations:
        return True
    return any(str(s).lower() in _IN_PROGRESS for s in (task_statuses or []))
