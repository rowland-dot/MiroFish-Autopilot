"""单个代理任务的阶段推进（纯函数，HTTP 客户端由调用方注入）。

与浏览器驱动器 runOne 的生命周期严格一致：
- 每一阶段先看已存 id，能续跑就绝不重跑（刷新/重启安全）
- 每次状态/ID 变化立刻回调落盘：状态查询能实时看到进展，重启后能从
  真实进度续跑，而不是从头再跑一遍整条流水线
- 新建图谱必须等 Zep 处理完 episode，否则会拿着 0 实体的空图谱去 prepare
- 轮次跑满即视为运行结束（子进程故意不退出，等 interview 命令）
- 报告在进程存活时生成（采访需要活体），报告写完后再 stop 释放槽位
- 「完成」= 报告可下载，而不是报告任务已启动
- 每个阶段边界与每次轮询都检查条目是否已被删除（取消即停手）
"""

TERMINAL_RUN = ("completed", "stopped", "failed")
PREPARED = ("completed", "ready")

# 报告轮询上限（与浏览器驱动器一致 ~45 分钟）。无上限会把唯一的驱动线程
# 永久占死，饿死整个队列。
REPORT_POLL_MAX = 90
REPORT_POLL_SECONDS = 30


def advance(entry: dict, http, sleep, file_bytes: bytes,
            is_gone=None, on_change=None) -> dict:
    e = dict(entry)
    gone = is_gone or (lambda: False)
    notify = on_change or (lambda _e: None)

    def _save(**patch):
        e.update(patch)
        notify(dict(e))

    def _abandon():
        e["status"] = "cancelled"
        return e

    try:
        if not e.get("projectId"):
            r = http.post_file("/api/graph/ontology/generate", file_bytes,
                               e["fileName"], {"simulation_requirement": e["prompt"]})
            _save(projectId=r["project_id"], status="building")

        if gone():
            return _abandon()

        if not e.get("graphId"):
            d = http.post("/api/graph/build", json={"project_id": e["projectId"]})
            if d.get("reused") and d.get("graph_id"):
                _save(graphId=d["graph_id"])
            elif d.get("task_id"):
                _save(buildTaskId=d["task_id"])
                while True:
                    if gone():
                        return _abandon()
                    ts = http.get(f"/api/graph/task/{d['task_id']}")
                    if ts.get("status") == "completed":
                        break
                    if ts.get("status") == "failed":
                        raise RuntimeError(f"graph build failed: {ts.get('error')}")
                    sleep(3)
                _save(graphId=http.get(
                    f"/api/graph/project/{e['projectId']}").get("graph_id"))
            else:
                _save(graphId=d.get("graph_id"))
            _save(status="creating")

        if gone():
            return _abandon()

        if not e.get("simId"):
            r = http.post("/api/simulation/create", json={
                "project_id": e["projectId"], "graph_id": e["graphId"],
                "enable_twitter": True, "enable_reddit": True,
            })
            _save(simId=r["simulation_id"], status="preparing")

        if gone():
            return _abandon()

        d = http.post("/api/simulation/prepare", json={
            "simulation_id": e["simId"], "use_llm_for_profiles": True,
            "parallel_profile_count": 5,
        })
        if not d.get("already_prepared") and d.get("task_id"):
            while True:
                if gone():
                    return _abandon()
                ps = http.post("/api/simulation/prepare/status",
                               json={"task_id": d["task_id"],
                                     "simulation_id": e["simId"]})
                if ps.get("status") in PREPARED:
                    break
                if ps.get("status") == "failed":
                    raise RuntimeError(f"prepare failed: {ps.get('error')}")
                sleep(3)

        if gone():
            return _abandon()

        held_open = False
        pre = http.get(f"/api/simulation/{e['simId']}/run-status").get("runner_status")
        if pre != "completed":
            if pre != "running":
                http.post("/api/simulation/start", json={
                    "simulation_id": e["simId"], "platform": "parallel", "force": True,
                })
            while True:
                if gone():
                    return _abandon()
                rd = http.get(f"/api/simulation/{e['simId']}/run-status")
                rs = rd.get("runner_status")
                if rs in TERMINAL_RUN:
                    break
                if (rd.get("total_rounds") or 0) > 0 \
                        and (rd.get("current_round") or 0) >= rd["total_rounds"] \
                        and rd.get("twitter_completed") and rd.get("reddit_completed"):
                    held_open = True
                    break
                if rs == "running" and e["status"] != "running":
                    _save(status="running")     # 落盘：状态查询才看得到轮次
                sleep(5)

        if gone():
            return _abandon()

        _save(status="reporting")
        if not e.get("reportId"):
            r = http.post("/api/report/generate", json={
                "simulation_id": e["simId"], "force_regenerate": True,
            })
            _save(reportId=r.get("report_id"))
            if e["reportId"]:
                for _ in range(REPORT_POLL_MAX):
                    if gone():
                        return _abandon()
                    st = http.get(f"/api/report/{e['reportId']}").get("status")
                    if st in ("completed", "failed"):
                        break
                    sleep(REPORT_POLL_SECONDS)

        if held_open:
            http.post("/api/simulation/stop", json={"simulation_id": e["simId"]})

        if gone():
            return _abandon()

        _save(status="done")
        return e
    except Exception as err:  # noqa: BLE001 — 失败原因必须留在条目上供用户看见
        if gone():
            return _abandon()
        _save(status="failed", error=str(err))
        return e
