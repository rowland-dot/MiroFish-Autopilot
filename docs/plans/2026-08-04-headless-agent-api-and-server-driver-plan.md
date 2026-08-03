# Headless Agent API + Server-Side Driver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an AI agent submit a MiroFish simulation job, poll its state, and fetch the finished report with no browser involved.

**Architecture:** Three new fork-owned files plus one registration line. A background thread (`job_driver`) advances pipeline entries whose `mode` is `"agent"` by calling the *same HTTP endpoints the browser driver calls* over localhost — so upstream refactors of service internals are absorbed at the endpoint seam and no upstream file is edited. Agent jobs are ordinary pipeline entries, so the existing 1-running + 2-queued capacity, history cards, cancel and delete all work unchanged.

**Tech Stack:** Python 3.11, Flask blueprints, `requests` (already a backend dependency), pytest. CLI is Python stdlib only (`urllib`, `json`, `argparse`) — no install step.

**Spec:** `docs/specs/2026-08-04-headless-agent-api-and-server-driver-spec.md`

## Global Constraints

- **Merge safety is a hard requirement.** Create new files under `backend/app/{api,services}/` and `cli/`. The ONLY permitted edit to an existing file is `backend/app/__init__.py` (fork-owned, hand-reconciled every merge).
- **Never import upstream service classes** (`OntologyGenerator`, `SimulationManager`, `ReportAgent`, …) from the driver. Drive via HTTP endpoints only.
- Pipeline entries use `mode: "agent"`. Never `"auto"` — that is the browser driver's marker and would cause double-driving.
- Entry status vocabulary is fixed by `backend/app/utils/pipeline_state.py`: `queued | ontology | building | creating | preparing | running | reporting | done | failed`.
- Server fields persisted on an entry are limited to `SERVER_FIELDS` in `pipeline_state.py`; adding a field requires adding it there.
- All new backend tests must pass under `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q`.
- Chinese comments for domain logic, matching the surrounding codebase style.

---

### Task 1: Job store — id minting and entry shaping

**Files:**
- Create: `backend/app/services/job_store.py`
- Test: `backend/tests/test_job_store.py`

**Interfaces:**
- Consumes: `app.utils.pipeline_state.{load_entries, mutate_entries, upsert_entry, default_path}`
- Produces:
  - `new_job_id(now: datetime, seq: int) -> str` — returns `tmp_<epoch_ms>_<seq>`
  - `make_agent_entry(job_id: str, prompt: str, file_name: str, now: datetime) -> dict`
  - `capacity_state(entries: list) -> tuple[int, int]` — returns `(running, queued)`
  - `is_full(entries: list) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_job_store.py
"""TDD: agent job entries reuse the pipeline store's shape and capacity."""
from datetime import datetime

from app.services.job_store import (
    new_job_id, make_agent_entry, capacity_state, is_full,
)

NOW = datetime(2026, 8, 4, 12, 0, 0)


def test_job_id_is_pipeline_shaped():
    jid = new_job_id(NOW, 3)
    assert jid.startswith("tmp_")
    assert jid.endswith("_3")


def test_agent_entry_marks_mode_agent_and_starts_queued():
    e = make_agent_entry("tmp_1_0", "预测舆情走向", "report.docx", NOW)
    assert e["mode"] == "agent"          # never 'auto' — that is the browser driver's marker
    assert e["status"] == "queued"
    assert e["prompt"] == "预测舆情走向"
    assert e["fileName"] == "report.docx"
    assert e["tmpId"] == "tmp_1_0"
    assert e["createdAt"] == NOW.isoformat()


def test_capacity_counts_active_and_queued():
    entries = [
        {"tmpId": "a", "status": "running"},
        {"tmpId": "b", "status": "queued"},
        {"tmpId": "c", "status": "done"},
    ]
    assert capacity_state(entries) == (1, 1)
    assert is_full(entries) is False


def test_full_at_one_running_plus_two_queued():
    entries = [
        {"tmpId": "a", "status": "preparing"},
        {"tmpId": "b", "status": "queued"},
        {"tmpId": "c", "status": "queued"},
    ]
    assert capacity_state(entries) == (1, 2)
    assert is_full(entries) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_store.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.job_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/job_store.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_store.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/job_store.py backend/tests/test_job_store.py
git commit -m "feat(headless): agent job entry shaping + capacity check"
```

---

### Task 2: Stage advance logic (pure, dependency-injected)

**Files:**
- Create: `backend/app/services/job_stages.py`
- Test: `backend/tests/test_job_stages.py`

**Interfaces:**
- Consumes: nothing (pure; the caller injects an HTTP client)
- Produces:
  - `advance(entry: dict, http, sleep, file_bytes: bytes, is_gone=None) -> dict` — returns the updated entry; drives ONE job to completion, mirroring the browser driver's `runOne`. `is_gone()` is an optional callable checked at every stage boundary: when it returns True the entry was deleted and the driver abandons it immediately (spec B7).
  - `http` is any object with `.post(path, **kw) -> dict`, `.post_file(path, file_bytes, file_name, fields) -> dict`, `.get(path) -> dict`

This is the heart of the feature. It reproduces the lifecycle corrections already shipped for the browser driver (spec B6): rounds-complete on a held-open process counts as finished, the report is generated while the process is alive, `done` means the report is downloadable, and every stage resumes from stored ids.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_job_stages.py
"""TDD: server-side stage advance mirrors the browser driver's lifecycle."""
import pytest

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

    def post(self, path, **kw):
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_stages.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.job_stages'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/job_stages.py
"""单个代理任务的阶段推进（纯函数，HTTP 客户端由调用方注入）。

与浏览器驱动器 runOne 的生命周期严格一致：
- 每一阶段先看已存 id，能续跑就绝不重跑（刷新/重启安全）
- 轮次跑满即视为运行结束（子进程故意不退出，等 interview 命令）
- 报告在进程存活时生成（采访需要活体），报告写完后再 stop 释放槽位
- 「完成」= 报告可下载，而不是报告任务已启动
"""

TERMINAL_RUN = ("completed", "stopped", "failed")
PREPARED = ("completed", "ready")


def advance(entry: dict, http, sleep, file_bytes: bytes, is_gone=None) -> dict:
    e = dict(entry)
    gone = is_gone or (lambda: False)

    def _abandon():
        e["status"] = "cancelled"
        return e

    try:
        if not e.get("projectId"):
            r = http.post_file("/api/graph/ontology/generate", file_bytes,
                               e["fileName"], {"simulation_requirement": e["prompt"]})
            e["projectId"] = r["project_id"]
            e["status"] = "building"

        if gone():
            return _abandon()

        if not e.get("graphId"):
            d = http.post("/api/graph/build", json={"project_id": e["projectId"]})
            if d.get("reused") and d.get("graph_id"):
                e["graphId"] = d["graph_id"]
            elif d.get("task_id"):
                # 新建图谱：Zep 异步处理 episode，必须等任务完成，
                # 否则会拿着 0 实体的空图谱去 prepare
                e["buildTaskId"] = d["task_id"]
                while True:
                    ts = http.get(f"/api/graph/task/{d['task_id']}")
                    if ts.get("status") == "completed":
                        break
                    if ts.get("status") == "failed":
                        raise RuntimeError(f"graph build failed: {ts.get('error')}")
                    sleep(3)
                e["graphId"] = http.get(f"/api/graph/project/{e['projectId']}").get("graph_id")
            else:
                e["graphId"] = d.get("graph_id")
            e["status"] = "creating"

        if gone():
            return _abandon()

        if not e.get("simId"):
            r = http.post("/api/simulation/create", json={
                "project_id": e["projectId"], "graph_id": e["graphId"],
                "enable_twitter": True, "enable_reddit": True,
            })
            e["simId"] = r["simulation_id"]
            e["status"] = "preparing"

        if gone():
            return _abandon()

        d = http.post("/api/simulation/prepare", json={
            "simulation_id": e["simId"], "use_llm_for_profiles": True,
            "parallel_profile_count": 5,
        })
        if not d.get("already_prepared") and d.get("task_id"):
            while True:
                ps = http.post("/api/simulation/prepare/status",
                               json={"task_id": d["task_id"], "simulation_id": e["simId"]})
                if ps.get("status") in PREPARED:
                    break
                if ps.get("status") == "failed":
                    raise RuntimeError(f"prepare failed: {ps.get('error')}")
                sleep(3)

        if gone():
            return _abandon()

        held_open = False
        pre = http.get(f"/api/simulation/{e['simId']}/run-status").get("runner_status")
        if pre not in ("completed",):
            if pre != "running":
                http.post("/api/simulation/start", json={
                    "simulation_id": e["simId"], "platform": "parallel", "force": True,
                })
            while True:
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
                    e["status"] = "running"
                sleep(5)

        if gone():
            return _abandon()

        e["status"] = "reporting"
        if not e.get("reportId"):
            r = http.post("/api/report/generate", json={
                "simulation_id": e["simId"], "force_regenerate": True,
            })
            e["reportId"] = r.get("report_id")
            # 「完成」= 报告可下载：轮询到报告真正写完（采访发生在写作期间）
            if e["reportId"]:
                while True:
                    st = http.get(f"/api/report/{e['reportId']}").get("status")
                    if st in ("completed", "failed"):
                        break
                    sleep(30)

        if held_open:
            # 持久化子进程：报告写完后主动停掉，否则永远占着并发槽位
            http.post("/api/simulation/stop", json={"simulation_id": e["simId"]})

        e["status"] = "done"
        return e
    except Exception as err:  # noqa: BLE001 — 失败原因必须留在条目上供用户看见
        e["status"] = "failed"
        e["error"] = str(err)
        return e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_stages.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/job_stages.py backend/tests/test_job_stages.py
git commit -m "feat(headless): stage advance logic mirroring the browser driver lifecycle"
```

---

### Task 3: Localhost HTTP client + driver thread

**Files:**
- Create: `backend/app/services/job_driver.py`
- Test: `backend/tests/test_job_driver.py`

**Interfaces:**
- Consumes: `job_stages.advance`, `job_store.ACTIVE_STATUSES`, `app.utils.pipeline_state.{mutate_entries, default_path, upsert_entry, load_entries}`
- Produces:
  - `LocalHttp(base_url: str, access_code: str)` — `.post/.get/.post_file`, logs in on first use
  - `pick_next(entries: list) -> dict | None` — the agent entry to drive now
  - `start_job_driver(app_config) -> threading.Thread | None`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_job_driver.py
"""TDD: which agent entry the server driver picks, and when it stays idle."""
from app.services.job_driver import pick_next


def test_prefers_an_already_active_agent_entry():
    entries = [
        {"tmpId": "a", "mode": "agent", "status": "preparing"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries)["tmpId"] == "a"


def test_promotes_a_queued_agent_entry_when_nothing_is_active():
    entries = [
        {"tmpId": "old", "mode": "agent", "status": "done"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries)["tmpId"] == "b"


def test_never_touches_browser_entries():
    entries = [
        {"tmpId": "auto1", "mode": "auto", "status": "queued"},
        {"tmpId": "man1", "mode": "manual", "status": "running"},
    ]
    assert pick_next(entries) is None


def test_waits_while_a_browser_job_holds_the_slot():
    # 容量共享：浏览器任务占着运行槽时，代理任务必须排队等待
    entries = [
        {"tmpId": "auto1", "mode": "auto", "status": "running"},
        {"tmpId": "b", "mode": "agent", "status": "queued"},
    ]
    assert pick_next(entries) is None


def test_ignores_terminal_agent_entries():
    entries = [
        {"tmpId": "a", "mode": "agent", "status": "done"},
        {"tmpId": "b", "mode": "agent", "status": "failed"},
    ]
    assert pick_next(entries) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_driver.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.job_driver'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/job_driver.py
"""服务端任务驱动器：无需浏览器即可推进代理任务。

只驱动 mode == "agent" 的条目；浏览器条目（auto/manual）由浏览器驱动器
负责，双方共用同一份容量（1 运行 + 2 排队），因此绝不会双驱动。
通过 localhost 调用与浏览器完全相同的 HTTP 端点——上游重构服务内部实现
时自动跟随，不改动任何上游文件。
"""

import os
import threading
import time

import requests

from ..utils.logger import logger
from ..utils.pipeline_state import default_path, load_entries, mutate_entries, upsert_entry
from .job_stages import advance
from .job_store import ACTIVE_STATUSES

POLL_SECONDS = 5


def pick_next(entries: list):
    """要推进的代理条目：优先已活跃的；无任何活跃条目时才提升排队队首。"""
    active = [e for e in entries if e.get("status") in ACTIVE_STATUSES]
    for e in active:
        if e.get("mode") == "agent":
            return e
    if active:
        return None          # 浏览器任务占着槽位——代理任务等待
    return next((e for e in entries
                 if e.get("mode") == "agent" and e.get("status") == "queued"), None)


class LocalHttp:
    """本机 HTTP 客户端，携带访问口令会话（与浏览器同一道门）。"""

    def __init__(self, base_url: str, access_code: str):
        self.base = base_url.rstrip("/")
        self.code = access_code
        self.session = requests.Session()
        self._logged_in = False

    def _login(self):
        if self._logged_in or not self.code:
            return
        self.session.post(f"{self.base}/api/auth/login",
                          json={"code": self.code}, timeout=30)
        self._logged_in = True

    def _unwrap(self, resp):
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body) if isinstance(body, dict) else body

    def get(self, path):
        self._login()
        return self._unwrap(self.session.get(f"{self.base}{path}", timeout=60))

    def post(self, path, json=None):
        self._login()
        return self._unwrap(self.session.post(f"{self.base}{path}", json=json, timeout=300))

    def post_file(self, path, file_bytes, file_name, fields):
        self._login()
        files = {"files": (file_name, file_bytes)}
        return self._unwrap(self.session.post(f"{self.base}{path}", files=files,
                                              data=fields, timeout=600))


def _persist(entry: dict):
    mutate_entries(default_path(), lambda es: upsert_entry(es, entry))


def _loop(base_url: str, access_code: str, files_dir: str):
    http = LocalHttp(base_url, access_code)
    while True:
        try:
            entry = pick_next(load_entries(default_path()))
            if entry:
                path = os.path.join(files_dir, f"{entry['tmpId']}.bin")
                with open(path, "rb") as f:
                    file_bytes = f.read()
                if entry["status"] == "queued":
                    entry = {**entry, "status": "ontology"}
                    _persist(entry)
                        def _still_there(job_id=entry["tmpId"]):
                    return not any(x.get("tmpId") == job_id
                                   for x in load_entries(default_path()))

                result = advance(entry, http, time.sleep, file_bytes,
                                 is_gone=_still_there)
                if result["status"] != "cancelled":
                    _persist(result)
                logger.info(f"代理任务结束: {result['tmpId']} -> {result['status']}")
        except Exception as e:  # noqa: BLE001 — 驱动线程绝不能死
            logger.error(f"代理任务驱动器异常: {e}")
        time.sleep(POLL_SECONDS)


def start_job_driver(upload_folder: str, port: int = 7860):
    """配置齐全则启动后台驱动线程；否则返回 None。"""
    code = os.environ.get("ACCESS_CODE", "")
    files_dir = os.path.join(upload_folder, "agent_uploads")
    os.makedirs(files_dir, exist_ok=True)
    t = threading.Thread(target=_loop,
                         args=(f"http://127.0.0.1:{port}", code, files_dir),
                         daemon=True)
    t.start()
    logger.info("已启动服务端代理任务驱动器")
    return t
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_job_driver.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/job_driver.py backend/tests/test_job_driver.py
git commit -m "feat(headless): localhost HTTP client + agent job driver thread"
```

---

### Task 4: REST surface

**Files:**
- Create: `backend/app/api/jobs.py`
- Modify: `backend/app/__init__.py` (add two lines beside the existing `pipeline_bp` registration around line 87)
- Test: `backend/tests/test_jobs_api.py`

**Interfaces:**
- Consumes: `job_store.{new_job_id, make_agent_entry, is_full, capacity_state}`, `job_driver.start_job_driver`
- Produces: blueprint `jobs_bp` with `POST /api/jobs`, `GET /api/jobs/<job_id>`, `GET /api/jobs/<job_id>/report`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_jobs_api.py
"""TDD: headless REST surface — spec contracts B1/B2/B3."""
import io

import pytest

from app import create_app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_FOLDER", str(tmp_path))
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_submit_returns_job_id_and_queued(client):
    data = {"prompt": "预测舆情", "file": (io.BytesIO(b"doc bytes"), "r.docx")}
    res = client.post("/api/jobs", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    body = res.get_json()["data"]
    assert body["job_id"].startswith("tmp_")
    assert body["status"] == "queued"


def test_submit_requires_file_and_prompt(client):
    res = client.post("/api/jobs", data={"prompt": "x"},
                      content_type="multipart/form-data")
    assert res.status_code == 400


def test_status_of_unknown_job_is_404(client):
    assert client.get("/api/jobs/tmp_nope").status_code == 404


def test_status_reports_stage(client):
    data = {"prompt": "p", "file": (io.BytesIO(b"d"), "r.docx")}
    jid = client.post("/api/jobs", data=data,
                      content_type="multipart/form-data").get_json()["data"]["job_id"]
    body = client.get(f"/api/jobs/{jid}").get_json()["data"]
    assert body["job_id"] == jid
    assert body["stage"] == "queued"


def test_report_before_completion_is_409(client):
    data = {"prompt": "p", "file": (io.BytesIO(b"d"), "r.docx")}
    jid = client.post("/api/jobs", data=data,
                      content_type="multipart/form-data").get_json()["data"]["job_id"]
    res = client.get(f"/api/jobs/{jid}/report")
    assert res.status_code == 409
    assert res.get_json()["data"]["status"] == "queued"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_jobs_api.py -q`
Expected: FAIL — 404 on `/api/jobs` (blueprint not registered)

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/api/jobs.py
"""无头代理接口：提交 / 查询 / 取报告。

代理任务写入与浏览器任务同一份流水线状态（mode="agent"），因此历史卡片、
徽标、取消、删除全部自动生效；推进由 services/job_driver.py 的后台线程负责。
"""

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from ..config import Config
from ..services.job_store import capacity_state, is_full, make_agent_entry, new_job_id
from ..utils.pipeline_state import default_path, load_entries, mutate_entries, upsert_entry

jobs_bp = Blueprint('jobs', __name__)
_seq = {"n": 0}


def _ok(data, code=200):
    return jsonify({"success": True, "data": data}), code


def _err(data, code):
    return jsonify({"success": False, "data": data, "error": data.get("error")}), code


@jobs_bp.route('', methods=['POST'], strict_slashes=False)
def submit_job():
    prompt = (request.form.get('prompt') or '').strip()
    upload = request.files.get('file')
    if not prompt or not upload or not upload.filename:
        return _err({"error": "file and prompt are required"}, 400)

    entries = load_entries(default_path())
    if is_full(entries):
        running, queued = capacity_state(entries)
        return _err({"error": "queue full", "running": running, "queued": queued}, 429)

    now = datetime.now()
    _seq["n"] += 1
    job_id = new_job_id(now, _seq["n"])

    files_dir = os.path.join(Config.UPLOAD_FOLDER, "agent_uploads")
    os.makedirs(files_dir, exist_ok=True)
    upload.save(os.path.join(files_dir, f"{job_id}.bin"))

    entry = make_agent_entry(job_id, prompt, upload.filename, now)
    mutate_entries(default_path(), lambda es: upsert_entry(es, entry))
    return _ok({"job_id": job_id, "status": "queued"})


def _find(job_id):
    return next((e for e in load_entries(default_path())
                 if e.get("tmpId") == job_id), None)


@jobs_bp.route('/<job_id>', methods=['GET'])
def job_status(job_id):
    e = _find(job_id)
    if not e:
        return _err({"error": "unknown job"}, 404)
    data = {
        "job_id": job_id, "stage": e.get("status"),
        "simulation_id": e.get("simId"), "report_id": e.get("reportId"),
        "error": e.get("error"),
    }
    if e.get("status") == "running" and e.get("simId"):
        try:
            from ..services.simulation_runner import SimulationRunner
            rs = SimulationRunner.get_run_state(e["simId"])
            data["round"] = getattr(rs, "current_round", None)
            data["total_rounds"] = getattr(rs, "total_rounds", None)
        except Exception:
            pass
    return _ok(data)


@jobs_bp.route('/<job_id>/report', methods=['GET'])
def job_report(job_id):
    e = _find(job_id)
    if not e:
        return _err({"error": "unknown job"}, 404)
    if e.get("status") != "done" or not e.get("reportId"):
        return _err({"status": e.get("status"), "error": e.get("error")}, 409)
    from ..services.report_agent import ReportManager
    report = ReportManager.get_report(e["reportId"])
    if report is None:
        return _err({"error": "report record missing"}, 404)
    return (report.markdown_content or ""), 200,         {"Content-Type": "text/markdown; charset=utf-8"}
```

Then register it in `backend/app/__init__.py`, immediately after the existing `pipeline_bp` registration (~line 87):

```python
    from .api.jobs import jobs_bp
    app.register_blueprint(jobs_bp, url_prefix='/api/jobs')

    # 服务端代理任务驱动器：无浏览器也能推进 mode="agent" 的任务
    from .services.job_driver import start_job_driver
    start_job_driver(Config.UPLOAD_FOLDER)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_jobs_api.py -q`
Expected: PASS (5 passed)

`ReportManager.get_report(report_id)` is defined at `backend/app/services/report_agent.py:2500` and returns a `Report` whose `markdown_content` holds the finished text. Read that class before wiring if the attribute name differs; do not invent a new loader.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/jobs.py backend/app/__init__.py backend/tests/test_jobs_api.py
git commit -m "feat(headless): REST surface for agent job submit/status/report"
```

---

### Task 5: CLI

**Files:**
- Create: `cli/mirofish.py`
- Test: `backend/tests/test_cli_args.py`

**Interfaces:**
- Consumes: the REST surface from Task 4 over the network
- Produces: `parse_args(argv) -> argparse.Namespace`, `main(argv) -> int`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cli_args.py
"""TDD: CLI argument surface (network paths are exercised live, not here)."""
import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "mirofish_cli",
    pathlib.Path(__file__).resolve().parents[2] / "cli" / "mirofish.py",
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_submit_requires_file_and_prompt():
    ns = cli.parse_args(["submit", "--file", "a.docx", "--prompt", "p"])
    assert ns.command == "submit"
    assert ns.file == "a.docx"
    assert ns.prompt == "p"


def test_status_takes_a_job_id():
    ns = cli.parse_args(["status", "tmp_1_0"])
    assert ns.command == "status"
    assert ns.job_id == "tmp_1_0"


def test_report_supports_output_path():
    ns = cli.parse_args(["report", "tmp_1_0", "-o", "out.md"])
    assert ns.command == "report"
    assert ns.output == "out.md"


def test_base_url_defaults_to_the_space(monkeypatch):
    monkeypatch.delenv("MIROFISH_URL", raising=False)
    ns = cli.parse_args(["status", "j"])
    assert "hf.space" in ns.url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cli_args.py -q`
Expected: FAIL — `FileNotFoundError` for `cli/mirofish.py`

- [ ] **Step 3: Write minimal implementation**

```python
#!/usr/bin/env python3
"""MiroFish headless CLI — submit jobs, poll status, fetch reports.

Standard library only; no install step.

  export MIROFISH_ACCESS_CODE=...       # your Space access code
  python cli/mirofish.py submit --file report.docx --prompt "..."
  python cli/mirofish.py status <job_id>
  python cli/mirofish.py report <job_id> -o out.md
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.request
import uuid

DEFAULT_URL = "https://leeroyy1288-mirofish.hf.space"


def parse_args(argv):
    p = argparse.ArgumentParser(prog="mirofish")
    p.add_argument("--url", default=os.environ.get("MIROFISH_URL", DEFAULT_URL))
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("submit", help="submit a new simulation job")
    s.add_argument("--file", required=True)
    s.add_argument("--prompt", required=True)

    t = sub.add_parser("status", help="poll a job's stage")
    t.add_argument("job_id")

    r = sub.add_parser("report", help="fetch a finished report")
    r.add_argument("job_id")
    r.add_argument("-o", "--output")

    return p.parse_args(argv)


class Client:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cookie = None
        self._login()

    def _request(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(self.base + path, data=data, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        with urllib.request.urlopen(req, timeout=120) as resp:
            set_cookie = resp.headers.get("Set-Cookie")
            if set_cookie:
                self.cookie = set_cookie.split(";")[0]
            return resp.status, resp.read()

    def _login(self):
        code = os.environ.get("MIROFISH_ACCESS_CODE", "")
        if not code:
            return
        body = json.dumps({"code": code}).encode()
        self._request("/api/auth/login", body, {"Content-Type": "application/json"})

    def get_json(self, path):
        try:
            status, raw = self._request(path)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        return status, json.loads(raw or b"{}")

    def get_raw(self, path):
        try:
            return self._request(path)
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def post_file(self, path, file_path, fields):
        boundary = uuid.uuid4().hex
        name = os.path.basename(file_path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        parts = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"\r\n\r\n{v}\r\n'.encode())
        with open(file_path, "rb") as f:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="file"; filename="{name}"\r\n'
                         f"Content-Type: {ctype}\r\n\r\n".encode() + f.read() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        try:
            status, raw = self._request(
                path, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
        return status, json.loads(raw or b"{}")


def main(argv=None):
    ns = parse_args(argv if argv is not None else sys.argv[1:])
    c = Client(ns.url)

    if ns.command == "submit":
        status, body = c.post_file("/api/jobs", ns.file, {"prompt": ns.prompt})
        print(json.dumps(body.get("data", body), ensure_ascii=False))
        return 0 if status == 200 else 1

    if ns.command == "status":
        status, body = c.get_json(f"/api/jobs/{ns.job_id}")
        print(json.dumps(body.get("data", body), ensure_ascii=False))
        return 0 if status == 200 else 1

    status, raw = c.get_raw(f"/api/jobs/{ns.job_id}/report")
    if status != 200:
        print(raw.decode("utf-8", "replace"))
        return 1
    if ns.output:
        with open(ns.output, "wb") as f:
            f.write(raw)
        print(f"saved {ns.output} ({len(raw)} bytes)")
    else:
        sys.stdout.write(raw.decode("utf-8", "replace"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cli_args.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add cli/mirofish.py backend/tests/test_cli_args.py
git commit -m "feat(headless): stdlib CLI for submit/status/report"
```

---

### Task 6: Merge guard + full-suite verification

**Files:**
- Modify: `scripts/post-merge-check.sh`

- [ ] **Step 1: Add the headless tests to the tripwire**

Append these four paths to the `pytest` invocation in `scripts/post-merge-check.sh`, keeping the existing ones:

```
  backend/tests/test_job_store.py \
  backend/tests/test_job_stages.py \
  backend/tests/test_job_driver.py \
  backend/tests/test_jobs_api.py \
```

- [ ] **Step 2: Run the guard script**

Run: `bash scripts/post-merge-check.sh`
Expected: all listed tests pass, output ends with `guard rails intact.`

- [ ] **Step 3: Run the entire backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS, no regressions against the pre-existing count (331 before this feature)

- [ ] **Step 4: Verify no upstream file was touched**

Run: `git diff --name-only upstream/main...HEAD -- backend/app/ | grep -v -E "(api/(jobs|pipeline|settings|status|backup)|services/(job_|backup_scheduler|boot_restore|simulation_queue)|utils/)"`
Expected: prints only `backend/app/__init__.py` — anything else means the merge-safety constraint was broken and must be reverted.

- [ ] **Step 5: Commit**

```bash
git add scripts/post-merge-check.sh
git commit -m "test(headless): guard the agent API against upstream merges"
```

---

## Post-implementation validation (manual, after deploy)

The deploy guard blocks deploys while jobs run; deploy during an idle window, then:

1. `export MIROFISH_ACCESS_CODE=<code>`
2. `python cli/mirofish.py submit --file <a real docx> --prompt "..."` → expect a `job_id`
3. Confirm a card appears in the browser history view with the correct title.
4. `python cli/mirofish.py status <job_id>` every few minutes → stages advance with **no browser tab open**.
5. On `done`: `python cli/mirofish.py report <job_id> -o out.md` → markdown file written.
