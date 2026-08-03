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


def test_login_retries_after_a_failed_attempt():
    # 口令错误/首次失败时若仍标记已登录，之后每个任务都会 401 到进程重启为止
    from app.services.job_driver import LocalHttp

    class Resp:
        def __init__(self, code):
            self.status_code = code

    class Sess:
        def __init__(self):
            self.logins = 0

        def post(self, url, **kw):
            if url.endswith("/api/auth/login"):
                self.logins += 1
                return Resp(401 if self.logins == 1 else 200)
            return Resp(200)

    h = LocalHttp("http://x", "code")
    h.session = Sess()
    h._login()
    assert h._logged_in is False, "failed login must not latch"
    h._login()
    assert h.session.logins == 2 and h._logged_in is True


def test_missing_upload_fails_the_entry_with_a_reason(tmp_path, monkeypatch):
    # 文件丢失时静默重试会让任务永远卡在 queued 并占死槽位，且 error 为空
    from app.services import job_driver as jd
    from app.utils import pipeline_state as ps
    monkeypatch.setattr(ps, "_DEFAULT_PATH", str(tmp_path / "p.json"))
    entry = {"tmpId": "j1", "mode": "agent", "status": "queued",
             "prompt": "p", "fileName": "f.docx"}
    ps.mutate_entries(ps.default_path(), lambda es: ps.upsert_entry(es, entry))

    jd.run_once(str(tmp_path / "uploads"), http=None)

    saved = ps.load_entries(ps.default_path())[0]
    assert saved["status"] == "failed"
    assert "上传文件" in (saved["error"] or "") or "upload" in (saved["error"] or "").lower()


def test_upload_bytes_are_cleaned_up_when_a_job_ends(tmp_path):
    from app.services.job_driver import cleanup_upload
    d = tmp_path / "uploads"
    d.mkdir()
    f = d / "j1.bin"
    f.write_bytes(b"x")
    cleanup_upload(str(d), "j1")
    assert not f.exists()
    cleanup_upload(str(d), "missing")      # 幂等，不抛异常
