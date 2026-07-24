"""永久删除一条历史记录（级联）。

删除该记录的项目/模拟/报告本地目录，并尽力删除对应 Zep 图谱。
即使 Zep 删除失败（额度耗尽/服务不可用），本地删除仍然成功。
"""

import os
import shutil


def _safe_id(rid) -> str:
    rid = str(rid or "").strip()
    if not rid or "/" in rid or "\\" in rid or ".." in rid:
        raise ValueError(f"unsafe id: {rid!r}")
    return rid


def delete_history_records(data_dir, simulation_id, project_id=None,
                           report_id=None, graph_id=None, zep_delete=None) -> dict:
    """删除一条历史记录的本地目录 + 尽力删除 Zep 图谱。返回删除摘要。"""
    data_dir = os.path.abspath(data_dir)
    removed = []
    targets = [("simulations", simulation_id), ("projects", project_id), ("reports", report_id)]
    for sub, rid in targets:
        if not rid:
            continue
        safe = _safe_id(rid)  # 拒绝路径穿越
        path = os.path.join(data_dir, sub, safe)
        if os.path.isdir(path):
            shutil.rmtree(path)
            removed.append(f"{sub}/{safe}")

    graph_deleted = False
    if graph_id and zep_delete:
        try:
            zep_delete(graph_id)
            graph_deleted = True
        except Exception:
            graph_deleted = False  # 尽力而为，不阻断本地删除

    return {"removed": removed, "graph_deleted": graph_deleted}
