"""TDD: server-side stage advance mirrors the browser driver's lifecycle."""
from app.services.job_stages import advance


class FakeHttp:
    """Records calls; returns canned payloads keyed by path prefix."""

    def __init__(self, run_seq=None):
        self.calls = []
        self.run_seq = run_seq or ["idle", "running", "completed"]
        self._run_i = 0

    def post_file(self, path, file_bytes, file_name, fields):
        self.calls.append("ontology")
        return {"project_id": "proj_1"}

    def post(self, path, json=None):
        if path.endswith("/graph/build"):
            self.calls.append("build")
            return {"task_id": "bt1"}
        if path.endswith("/simulation/create"):
            self.calls.append("create")
            return {"simulation_id": "sim_1"}
        if path.endswith("/simulation/prepare"):
            self.calls.append("prepare")
            return {"already_prepared": True}
        if path.endswith("/simulation/start"):
            self.calls.append("start")
            return {"runner_status": "running"}
        if path.endswith("/simulation/stop"):
            self.calls.append("stop")
            return {"runner_status": "stopped"}
        if path.endswith("/simulation/close-env"):
            self.calls.append("close-env")
            return {"success": True}
        if path.endswith("/report/generate"):
            self.calls.append("report")
            return {"report_id": "rep_1"}
        raise AssertionError(f"unexpected post {path}")

    def get(self, path):
        if "/graph/task/" in path:
            return {"status": "completed"}
        if "/graph/project/" in path:
            return {"graph_id": "g1"}
        if path.endswith("/run-status"):
            st = self.run_seq[min(self._run_i, len(self.run_seq) - 1)]
            self._run_i += 1
            return {"runner_status": st, "current_round": 72, "total_rounds": 72,
                    "twitter_completed": True, "reddit_completed": True}
        if "/report/" in path:
            return {"status": "completed"}
        raise AssertionError(f"unexpected get {path}")


def _entry(**over):
    e = {"tmpId": "j1", "mode": "agent", "status": "queued",
         "prompt": "p", "fileName": "f.docx",
         "projectId": None, "graphId": None, "simId": None,
         "buildTaskId": None, "reportId": None, "error": None}
    e.update(over)
    return e


def test_full_sequence_reaches_done():
    http = FakeHttp()
    out = advance(_entry(), http, sleep=lambda s: None, file_bytes=b"x")
    # 正确序列：持久化进程先 close-env 转终态，之后才允许生成报告
    assert http.calls == ["ontology", "build", "create", "prepare", "start",
                          "close-env", "report"]
    assert out["status"] == "done"
    assert out["simId"] == "sim_1"
    assert out["reportId"] == "rep_1"


def test_resume_skips_completed_stages():
    http = FakeHttp(run_seq=["completed"])
    out = advance(_entry(projectId="proj_1", graphId="g1", simId="sim_1"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert "ontology" not in http.calls
    assert "build" not in http.calls
    assert "create" not in http.calls
    assert out["status"] == "done"


def test_existing_report_is_not_regenerated():
    http = FakeHttp(run_seq=["completed"])
    out = advance(_entry(projectId="p", graphId="g", simId="s", reportId="rep_9"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert "report" not in http.calls
    assert out["status"] == "done"


def test_held_open_process_is_closed_before_reporting():
    # 上游持久化设计：轮次跑满后子进程不退出（等 interview 命令），run_state
    # 永远停在 running。后端又拒绝在非终态生成报告——必须先 close-env。
    http = FakeHttp(run_seq=["running", "running", "completed"])
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert http.calls.index("close-env") < http.calls.index("report")
    assert out["status"] == "done"


def test_deleted_entry_is_abandoned_at_the_next_stage_boundary():
    # 用户删除卡片后，已在跑的阶段不再继续（残留工作由取消传播终止）
    http = FakeHttp()
    gone = {"v": False}

    def is_gone():
        return gone["v"]

    def onto(path, file_bytes, file_name, fields):
        http.calls.append("ontology")
        gone["v"] = True
        return {"project_id": "proj_1"}

    http.post_file = onto
    out = advance(_entry(), http, sleep=lambda s: None, file_bytes=b"x", is_gone=is_gone)
    assert http.calls == ["ontology"]
    assert out["status"] == "cancelled"


def test_failure_records_error_and_stops():
    http = FakeHttp()

    def boom(path, file_bytes, file_name, fields):
        raise RuntimeError("LLM provider request failed (HTTP 429)")

    http.post_file = boom
    out = advance(_entry(), http, sleep=lambda s: None, file_bytes=b"x")
    assert out["status"] == "failed"
    assert "429" in out["error"]


def test_every_stage_transition_is_persisted_immediately():
    # 只在最后落盘 = 状态查询几小时看不到进展，且重启后从头重跑整条流水线
    http = FakeHttp()
    seen = []
    advance(_entry(), http, sleep=lambda s: None, file_bytes=b"x",
            on_change=lambda e: seen.append((e["status"], e.get("projectId"),
                                             e.get("simId"), e.get("reportId"))))
    stages = [s[0] for s in seen]
    assert "building" in stages and "creating" in stages
    assert "preparing" in stages and "reporting" in stages
    # ids 必须在各自阶段之后立刻可见（重启续跑靠它们）
    assert any(p == "proj_1" for _, p, _, _ in seen)
    assert any(s == "sim_1" for _, _, s, _ in seen)
    assert seen[-1][0] == "done"


def test_report_poll_is_bounded_not_infinite():
    # 报告任务卡死时，无上限轮询会永久占死唯一的驱动线程，饿死整个队列
    http = FakeHttp(run_seq=["completed"])
    http.get_report_status = "generating"

    def never_finishes(path):
        if "/report/" in path and "/graph/" not in path:
            return {"status": "generating"}
        return FakeHttp.get(http, path)

    http.get = never_finishes
    slept = []
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: slept.append(s), file_bytes=b"x")
    assert len(slept) <= 95, "report polling must be capped"
    assert out["status"] == "done"       # best-effort：超时也放行，不卡死驱动器


def test_deleted_entry_during_report_poll_is_abandoned():
    http = FakeHttp(run_seq=["completed"])
    gone = {"v": False}
    original_get = http.get

    def get(path):
        if "/report/" in path and "/graph/" not in path:
            gone["v"] = True
            return {"status": "generating"}
        return original_get(path)

    http.get = get
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x",
                  is_gone=lambda: gone["v"])
    assert out["status"] == "cancelled"


def test_held_open_closes_env_then_reports_after_terminal():
    # 后端拒绝在 run 非终态时生成报告；持久化进程会永远停在 running。
    # 正确序列（与 UI 一致）：close-env 优雅退出 -> 等终态 -> 再生成报告。
    http = FakeHttp(run_seq=["running", "running"])
    closed = {"v": False}
    orig_post, orig_get = http.post, http.get

    def post(path, json=None):
        if path.endswith("/simulation/close-env"):
            http.calls.append("close-env")
            closed["v"] = True
            return {"success": True}
        return orig_post(path, json=json)

    def get(path):
        if path.endswith("/run-status"):
            return {"runner_status": "completed" if closed["v"] else "running",
                    "current_round": 72, "total_rounds": 72,
                    "twitter_completed": True, "reddit_completed": True}
        return orig_get(path)

    http.post, http.get = post, get
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert "close-env" in http.calls, "must gracefully close the held-open env"
    assert http.calls.index("close-env") < http.calls.index("report"), \
        "report only after the run is terminal"
    assert out["status"] == "done"


def test_close_env_failure_falls_back_to_force_stop():
    http = FakeHttp(run_seq=["running", "running"])
    closed = {"v": False}
    orig_post, orig_get = http.post, http.get

    def post(path, json=None):
        if path.endswith("/simulation/close-env"):
            http.calls.append("close-env")
            raise RuntimeError("env not responding")
        if path.endswith("/simulation/stop"):
            http.calls.append("stop")
            closed["v"] = True
            return {"runner_status": "stopped"}
        return orig_post(path, json=json)

    def get(path):
        if path.endswith("/run-status"):
            return {"runner_status": "stopped" if closed["v"] else "running",
                    "current_round": 72, "total_rounds": 72,
                    "twitter_completed": True, "reddit_completed": True}
        return orig_get(path)

    http.post, http.get = post, get
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert http.calls.index("stop") < http.calls.index("report")
    assert out["status"] == "done"


def test_report_rejection_fails_the_job_instead_of_silently_finishing():
    # 「完成」= 报告可下载。报告拒绝/失败绝不能静默标记 done（无报告的空任务）
    http = FakeHttp(run_seq=["completed"])
    orig_post = http.post

    def post(path, json=None):
        if path.endswith("/report/generate"):
            raise RuntimeError("409 Client Error: CONFLICT")
        return orig_post(path, json=json)

    http.post = post
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert out["status"] == "failed"
    assert "409" in out["error"]


def test_terminal_run_is_never_restarted_on_resume():
    # stopped/failed 也是终态：绝不能再 force start 一遍
    for st in ("stopped", "failed"):
        http = FakeHttp(run_seq=[st])
        advance(_entry(projectId="p", graphId="g", simId="s"),
                http, sleep=lambda s: None, file_bytes=b"x")
        assert "start" not in http.calls, f"{st} must not be restarted"


def test_transient_404_while_the_report_record_settles_is_not_fatal():
    # /report/generate 返回 report_id 后，记录要过一会儿才落盘：首次轮询可能
    # 404。把它当致命错误会把一个正在正常生成报告的任务标记为失败。
    http = FakeHttp(run_seq=["completed"])
    orig_get = http.get
    polls = {"n": 0}

    def get(path):
        if "/report/" in path and "/graph/" not in path:
            polls["n"] += 1
            if polls["n"] <= 2:
                raise RuntimeError("404 Client Error: NOT FOUND for url: /api/report/x")
            return {"status": "completed"}
        return orig_get(path)

    http.get = get
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert out["status"] == "done"
    assert polls["n"] >= 3


def test_persistent_report_read_failure_still_fails_the_job():
    http = FakeHttp(run_seq=["completed"])
    orig_get = http.get

    def get(path):
        if "/report/" in path and "/graph/" not in path:
            raise RuntimeError("500 Server Error")
        return orig_get(path)

    http.get = get
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert out["status"] == "failed"
