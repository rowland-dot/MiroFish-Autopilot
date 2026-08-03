"""Agent 任务的条目构造与容量判定。

代理任务就是普通的流水线条目，只是 mode 为 "agent"：浏览器驱动器只驱动
mode === 'auto' 的条目，因此它会把代理任务显示成卡片但绝不推进——避免
双驱动（历史上双驱动造成过双倍 LLM 消耗）。容量与浏览器任务共享。
"""

from datetime import datetime

ACTIVE_STATUSES = (
    "ontology", "building", "creating", "preparing", "running", "reporting",
)
SLOT_LIMIT = 1
QUEUE_LIMIT = 2


def new_job_id(now: datetime, seq: int) -> str:
    return f"tmp_{int(now.timestamp() * 1000)}_{seq}"


def make_agent_entry(job_id: str, prompt: str, file_name: str, now: datetime) -> dict:
    return {
        "tmpId": job_id,
        "mode": "agent",
        "status": "queued",
        "prompt": prompt,
        "fileName": file_name,
        "createdAt": now.isoformat(),
        "simId": None,
        "projectId": None,
        "graphId": None,
        "buildTaskId": None,
        "reportId": None,
        "error": None,
    }


def capacity_state(entries: list) -> tuple:
    running = sum(1 for e in entries if e.get("status") in ACTIVE_STATUSES)
    queued = sum(1 for e in entries if e.get("status") == "queued")
    return running, queued


def is_full(entries: list) -> bool:
    running, queued = capacity_state(entries)
    return running >= SLOT_LIMIT and queued >= QUEUE_LIMIT
