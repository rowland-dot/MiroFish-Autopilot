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
    assert http.calls == ["ontology", "build", "create", "prepare", "start", "report", "stop"]
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


def test_held_open_process_is_reported_then_stopped():
    # 上游持久化设计：轮次跑满后子进程不退出，等待 interview 命令。
    # 必须在进程存活时生成报告（采访要活体），随后主动 stop 释放槽位。
    http = FakeHttp(run_seq=["running", "running", "running"])
    out = advance(_entry(projectId="p", graphId="g", simId="s"),
                  http, sleep=lambda s: None, file_bytes=b"x")
    assert http.calls.index("report") < http.calls.index("stop")
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
